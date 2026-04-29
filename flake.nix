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

      perSystem = {pkgs, ...}: let
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
            '';
          in {
            # 1. Sync Python deps from uv.lock
            deps = {
              command = ''
                ${devEnv}
                exec uv sync --quiet
              '';
              availability.restart = "exit_on_failure";
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
            };

            # 3. FastAPI dev server with auto-reload
            app = {
              command = ''
                ${devEnv}
                exec uv run fastapi dev src/main.py
              '';
              depends_on."migrate".condition = "process_completed_successfully";
              readiness_probe = {
                http_get = {
                  host = "127.0.0.1";
                  port = 8000;
                  path = "/api/health";
                };
                initial_delay_seconds = 2;
                period_seconds = 5;
                timeout_seconds = 3;
              };
            };
          };
        };
      };

      flake.nixosModules = {
        default = import ./nix/module.nix;
        naavik = import ./nix/module.nix;
      };
    };
}
