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
        # Tools every dev-orchestrator process needs in PATH
        devTools = with pkgs; [uv py typst];
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

          # Self-heal a stale `postmaster.pid` left over from a prior unclean
          # shutdown (kill -9, OOM, host reboot, etc). Postgres refuses to start
          # while that lock file points at any PID — even one that's long dead —
          # producing the cryptic "lock file already exists" loop. We only drop
          # the file if its recorded PID is genuinely gone, so an actually-
          # running Postgres is never disturbed.
          cli.preHook = ''
            _pid_file=./.naavik/db/postmaster.pid
            if [ -f "$_pid_file" ]; then
              _stale_pid=$(head -n1 "$_pid_file" 2>/dev/null | tr -d '[:space:]')
              if [ -n "$_stale_pid" ] && ! kill -0 "$_stale_pid" 2>/dev/null; then
                echo "[preHook] removing stale postmaster.pid (PID $_stale_pid is gone)"
                rm -f "$_pid_file"
              fi
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
              # Force line-buffered stdout. Without this, when fastapi/alembic
              # stdout is a pipe (not a TTY), Python block-buffers up to 4-8 KB
              # before flushing. That made the FastAPI banner + uvicorn "started"
              # lines look invisible for ~5s — easy to mistake for "app never
              # started" when actually output was still in a kernel pipe buffer.
              export PYTHONUNBUFFERED=1
            '';
            # Every dev process gets the same shutdown discipline so Ctrl-C
            # never hangs: SIGTERM first, SIGKILL after 10s if the child is
            # wedged on something (e.g. uv mid-network-call).
            cleanShutdown = {
              signal = 15; # SIGTERM
              timeout_seconds = 10;
            };
          in {
            # 1. Sync Python deps from uv.lock.
            # We dropped `--quiet` so first-run download progress is visible —
            # the previous silent variant looked like a 30+ second hang.
            deps = {
              command = ''
                ${devEnv}
                exec uv sync
              '';
              availability.restart = "exit_on_failure";
              shutdown = cleanShutdown;
            };

            # 2. Run alembic migrations once Postgres is ready
            migrate = {
              command = ''
                ${devEnv}
                exec uv run alembic upgrade head
              '';
              depends_on = {
                "db".condition = "process_healthy";
                "deps".condition = "process_completed_successfully";
              };
              availability.restart = "exit_on_failure";
              shutdown = cleanShutdown;
            };

            # 3. FastAPI dev server with auto-reload.
            # No readiness_probe by design: nothing depends on app being healthy
            # (it's the leaf of the chain), so the probe was purely cosmetic.
            # The probe used to fire at t=2s before fastapi finished binding
            # `:8000` (cold-start takes 4-7s), logging an alarming
            # `connection refused` line every run. Without the probe, app is
            # marked "running" once the process is alive — verify it's actually
            # serving by hitting <http://localhost:8000> in a browser.
            app = {
              command = ''
                ${devEnv}
                exec uv run fastapi dev src/main.py
              '';
              depends_on."migrate".condition = "process_completed_successfully";
              shutdown = cleanShutdown;
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
