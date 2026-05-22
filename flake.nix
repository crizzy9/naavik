{
  description = "Naavik — open-source self-hosted career automation platform";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
    flake-parts.url = "github:hercules-ci/flake-parts";
    process-compose-flake.url = "github:Platonic-Systems/process-compose-flake";
    services-flake.url = "github:juspay/services-flake";
  };

  outputs = inputs:
    inputs.flake-parts.lib.mkFlake {inherit inputs;} {
      systems = [
        "x86_64-linux"
        "aarch64-linux"
      ];

      imports = [
        inputs.process-compose-flake.flakeModule
      ];

      perSystem = {
        config,
        pkgs,
        lib,
        ...
      }: let
        py = pkgs.python312;
        # Tools every dev-orchestrator process needs in PATH.
        # Plan 10a (PC.1, 2026-05-02): coreutils added so `setsid` is in PATH —
        # used to detach migrate / app from the orchestrator's controlling TTY,
        # otherwise fastapi-cli's `/dev/tty` open + read triggers SIGTTIN and
        # the process wedges in `T` state without ever binding `:8000`.
        devTools = with pkgs; [uv py typst coreutils];
        devPath = pkgs.lib.makeBinPath devTools;
      in {
        devShells.default = pkgs.callPackage ./nix/devshell.nix {};
        packages.default = pkgs.callPackage ./nix/package.nix {};
        packages.naavik = pkgs.callPackage ./nix/package.nix {};

        # `nix run .#dev` — boots Postgres + alembic + FastAPI in one terminal.
        # Per-project state at ./.naavik/db (gitignored). Ctrl-C tears down cleanly.
        process-compose."dev" = {
          imports = [
            inputs.services-flake.processComposeModules.default
          ];

          # TUI off by default → plain log streaming. Errors land in stdout
          # immediately, no TUI panes to hide them. Toggle back on with
          # `nix run .#dev -- --tui=true`; the wrapper below also injects
          # `--theme="Catppuccin Mocha"` so the TUI is readable when re-enabled.
          cli.environment.PC_DISABLE_TUI = true;

          # preHook runs once before any service process starts. Two jobs:
          #
          # 1. Self-heal a stale `postmaster.pid` left over from a prior unclean
          #    shutdown (kill -9, OOM, host reboot, etc). Postgres refuses to
          #    start while that lock file points at any PID — even one that's
          #    long dead — producing the cryptic "lock file already exists" loop.
          #    We only drop the file if its recorded PID is genuinely gone, so
          #    an actually-running Postgres is never disturbed.
          #
          # 2. Normalize `.naavik/db/` permissions to PG-acceptable 0700 (no
          #    group / no other) AND strip any inherited POSIX ACLs (0.7.0.43,
          #    2026-05-22). Some operator setups carry a default ACL on a parent
          #    directory (e.g. `setfacl -d -m user:hermes:rwx ~/personal/dev` for
          #    pair-sharing between local users). Subdirs created under such a
          #    parent inherit the default ACL at creation time, which makes
          #    `ls -ld .naavik/db/` show `drwxrwx---+` (mode 0770 + ACL marker).
          #    Postgres 14+ tightened the data-dir permission check; it accepts
          #    only 0700 or 0750-with-matching-group and refuses 0770, producing
          #    `FATAL: data directory ... has invalid permissions`.
          #
          #    The fix is idempotent + safe on hosts without ACLs:
          #      - `mkdir -p .naavik` then `setfacl -k .naavik` strips the default
          #        ACL on the PARENT so any subsequent child-mkdir (services-flake's
          #        initdb on first boot, our own walks on later boots) inherits
          #        no default ACL. **We do NOT pre-create `.naavik/db` itself** —
          #        services-flake's setup-script gates initdb on `! -d $PGDATA`
          #        (juspay/services-flake nix/services/postgres/setup-script.nix),
          #        so a pre-existing empty dir would silently skip initdb +
          #        leave the cluster un-bootstrapped → PG `pg_ctl: not a database
          #        cluster directory` on first boot. Architect PR #209 review
          #        2026-05-22 surfaced this gotcha.
          #      - On boots where `.naavik/db` already exists (i.e. NOT first
          #        boot), do the full cleanup: `setfacl -bR` to remove any access
          #        ACLs inherited at creation time, `setfacl -k` to strip the
          #        default ACL on the child too, and `chmod -R u=rwX,go=` to
          #        enforce 0700 dirs + 0600 files (capital X = "x only if
          #        already x on dirs"). Matches what initdb itself sets.
          #      - `|| true` keeps the boot moving if setfacl/chmod fails (NFS,
          #        SMB, container mounts without xattr support). We INTENTIONALLY
          #        leave stderr unredirected so a real failure (operator's dir
          #        owned by another user → `Operation not permitted`) is visible
          #        in the preHook output instead of buried under PG's downstream
          #        FATAL. Architect PR #209 LOW F3.
          cli.preHook = ''
            _pid_file=./.naavik/db/postmaster.pid
            if [ -f "$_pid_file" ]; then
              _stale_pid=$(head -n1 "$_pid_file" 2>/dev/null | tr -d '[:space:]')
              if [ -n "$_stale_pid" ] && ! kill -0 "$_stale_pid" 2>/dev/null; then
                echo "[preHook] removing stale postmaster.pid (PID $_stale_pid is gone)"
                rm -f "$_pid_file"
              fi
            fi
            mkdir -p ./.naavik
            ${pkgs.acl}/bin/setfacl -k ./.naavik || true
            if [ -d ./.naavik/db ]; then
              ${pkgs.acl}/bin/setfacl -bR ./.naavik/db || true
              ${pkgs.acl}/bin/setfacl -k ./.naavik/db || true
              chmod -R u=rwX,go= ./.naavik/db || true
            fi
            unset _pid_file _stale_pid
          '';

          # Dev DB on 5433 to avoid colliding with system Postgres on 5432
          services.postgres."db" = {
            enable = true;
            dataDir = "./.naavik/db";
            listen_addresses = "127.0.0.1";
            port = 5433;
            extensions = exts: [exts.pgvector];
            initialScript.before = ''
              CREATE USER naavik WITH PASSWORD 'password' SUPERUSER;
            '';
            initialDatabases = [
              {
                name = "naavik";
                schemas = [
                  (pkgs.writeText "00-extensions.sql" ''
                    CREATE EXTENSION IF NOT EXISTS vector;
                  '')
                ];
              }
            ];
          };

          settings.processes = let
            devEnv = ''
              export PATH="${devPath}:$PATH"
              export DATABASE_URL="postgresql+asyncpg://naavik:password@127.0.0.1:5433/naavik"
              # Plan 10b (item 1, 2026-05-03): SQLAlchemy's greenlet bridge
              # dlopens libstdc++.so.6 the first time an async DB statement runs.
              # NixOS' Python venv has no system libstdc++ on the loader's search
              # path, so the dlopen fails with `cannot open shared object file`
              # and the greenlet bridge raises ValueError. nix/devshell.nix sets
              # this for the interactive shell; the orchestrator must do the
              # same so `nix run .#dev` sees a writable Postgres path.
              # `zlib` for numpy (transitive via `pgvector`; plan 61 / 0.2.7.16).
              export LD_LIBRARY_PATH="${pkgs.stdenv.cc.cc.lib}/lib:${pkgs.zlib}/lib''${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
              # Plan 17 (PC.5): NAAVIK_DEBUG=1 bypasses the SECRET_KEY 32-byte
              # boot-time validator so `nix run .#dev` works without a `.env`.
              # Also flips `app_settings.debug` on, gating `/_design/components`
              # and the dev first-boot log line. Production stacks (docker
              # compose / NixOS module) leave it unset.
              export NAAVIK_DEBUG=1
              # Force line-buffered stdout. Without this, when fastapi/alembic
              # stdout is a pipe (not a TTY), Python block-buffers up to 4-8 KB
              # before flushing. That made the FastAPI banner + uvicorn "started"
              # lines look invisible for ~5s — easy to mistake for "app never
              # started" when actually output was still in a kernel pipe buffer.
              export PYTHONUNBUFFERED=1
              # Plan 10a (PC.1, 2026-05-02): scrub PYTHONPATH before any uv-managed
              # process starts. A `nix develop` shell sets `PYTHONPATH=src:<lots of
              # python3.13 site-packages from pre-commit's deps>` for interactive
              # convenience. Inheriting that into the orchestrator's python3.12 venv
              # leaks 3.13 paths onto sys.path and is a documented source of
              # async-loop / SSL-module weirdness. The venv already has src/ on its
              # import path via setuptools `package-dir = {"" = "src"}`.
              unset PYTHONPATH
            '';
            # Every dev process gets the same shutdown discipline so Ctrl-C
            # never hangs: SIGTERM first, SIGKILL after 10s if the child is
            # wedged on something (e.g. uv mid-network-call).
            cleanShutdown = {
              signal = 15; # SIGTERM
              timeout_seconds = 10;
            };
            # Plan 10a (PC.1, 2026-05-02 — orphan fix): `setsid -w` detaches
            # children into a new session so /dev/tty access fails gracefully
            # (the actual wedge cure). The trade-off is that SIGTERM to
            # `setsid -w` doesn't propagate to its detached child session —
            # process-compose's normal cleanShutdown leaves uvicorn workers
            # orphaned and bound to :8000. Override `shutdown.command` to
            # pkill by command-line pattern so the orphans get swept too.
            # Patterns are tight enough (the fastapi cmdline + the project's
            # venv path in multiprocessing-spawn workers / alembic) to avoid
            # hitting unrelated processes on the host. `|| true` keeps the
            # shutdown clean if procs are already gone (crashed / completed
            # early). Use absolute /nix/store paths since shutdown.command
            # runs in process-compose's shell, not the per-process devEnv.
            pkill = "${pkgs.procps}/bin/pkill";
            sleep = "${pkgs.coreutils}/bin/sleep";
            setsidShutdown = cleanShutdown // {
              command = ''
                ${pkill} -TERM -f 'fastapi dev src/main.py' 2>/dev/null || true
                ${pkill} -TERM -f 'naavik/.venv/bin/python -s -c' 2>/dev/null || true
                ${pkill} -TERM -f 'naavik/.venv/bin/alembic' 2>/dev/null || true
                ${sleep} 1
                ${pkill} -KILL -f 'fastapi dev src/main.py' 2>/dev/null || true
                ${pkill} -KILL -f 'naavik/.venv/bin/python -s -c' 2>/dev/null || true
                ${pkill} -KILL -f 'naavik/.venv/bin/alembic' 2>/dev/null || true
                true
              '';
            };
          in {
            # 1. Sync Python deps from uv.lock.
            # We dropped `--quiet` so first-run download progress is visible —
            # the previous silent variant looked like a 30+ second hang.
            # Plan 10a (PC.3, 2026-05-02): `--extra dev` keeps playwright +
            # pytest + ruff in `.venv` so visual-QA capture and pytest don't
            # need a manual `uv sync --extra dev` after the orchestrator
            # uninstalls them. The dev orchestrator IS for development; the
            # production path runs `uv sync --no-dev` separately.
            deps = {
              command = ''
                ${devEnv}
                exec uv sync --extra dev
              '';
              availability.restart = "exit_on_failure";
              shutdown = cleanShutdown;
            };

            # 2. Run alembic migrations once Postgres is ready.
            # Plan 10a (PC.1, 2026-05-02 — revised after user-side wedge):
            #   * `setsid -w` puts alembic in a new session with no controlling
            #     TTY, so any `/dev/tty` open() fails fast (ENXIO) instead of
            #     blocking with SIGTTIN. `-w` keeps setsid waiting on the
            #     child so process-compose still tracks the real exit code.
            #   * `--no-sync` skips uv's per-run venv resync (deps already did
            #     the full sync — saves 50-200ms per cold boot).
            #   * `< /dev/null` redirects stdin away from the inherited pipe
            #     (defense in depth on top of setsid's session detach).
            # env.py is sync (psycopg) so the migration path has no greenlet
            # bridge, no asyncio loop. Fast and predictable.
            migrate = {
              command = ''
                ${devEnv}
                exec setsid -w uv run --no-sync alembic upgrade head < /dev/null
              '';
              depends_on = {
                "db".condition = "process_healthy";
                "deps".condition = "process_completed_successfully";
              };
              availability.restart = "exit_on_failure";
              shutdown = setsidShutdown;
            };

            # 3. FastAPI dev server with auto-reload.
            # No readiness_probe by design: nothing depends on app being healthy
            # (it's the leaf of the chain), so the probe was purely cosmetic.
            # The probe used to fire at t=2s before fastapi finished binding
            # `:8000` (cold-start takes 4-7s), logging an alarming
            # `connection refused` line every run. Without the probe, app is
            # marked "running" once the process is alive — verify it's actually
            # serving by hitting <http://localhost:8000> in a browser.
            # Plan 10a (PC.1, 2026-05-02 — revised): `setsid -w` is the actual
            # cure for the user-reported wedge. fastapi-cli opens `/dev/tty`
            # for terminal-detection (Rich / Click), and when process-compose
            # runs the child in a background process group of an interactive
            # TTY (the user's foreground `nix run .#dev`), reading /dev/tty
            # raises SIGTTIN and stops the process in `T` state — `:8000`
            # never binds and no [app] log line ever appears. setsid creates
            # a new session with no controlling TTY → /dev/tty open returns
            # ENXIO → fastapi-cli takes its headless code path → starts cleanly.
            app = {
              command = ''
                ${devEnv}
                exec setsid -w uv run --no-sync fastapi dev src/main.py < /dev/null
              '';
              depends_on."migrate".condition = "process_completed_successfully";
              shutdown = setsidShutdown;
            };
          };
        };

        # Override `packages.dev` (which process-compose-flake auto-derives from
        # `process-compose."dev".outputs.package`) with a thin shell wrapper that
        # injects `--theme="Catppuccin Mocha"`. process-compose-flake doesn't
        # expose `--theme` via its typed schema, so we wrap. The theme name is
        # the runtime YAML name (Title Case with a space), not the file-system
        # name (`catppuccin-mocha-theme.yaml`) — the latter is rejected as
        # "Theme not found". User flags via `nix run .#dev -- <flags>` still
        # work; they're appended after ours.
        packages.dev = lib.mkForce (pkgs.writeShellApplication {
          name = "dev";
          text = ''
            exec ${config.process-compose."dev".outputs.package}/bin/dev \
              --theme="Catppuccin Mocha" "$@"
          '';
        });
      };

      flake.nixosModules = {
        default = import ./nix/module.nix;
        naavik = import ./nix/module.nix;
      };
    };
}
