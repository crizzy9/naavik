{
  pkgs ? import <nixpkgs> {},
  ...
}:
pkgs.mkShell {
  # Plan 09 adds `playwright` (via uv at run time) plus the Playwright system
  # libs (chromium dependencies) so visual-QA snapshots can run without a
  # bespoke install. Plan 10a (PC.3, 2026-05-02) added `nodejs_22` so the
  # pip-installed playwright python package can use a Nix-built node binary
  # via `PLAYWRIGHT_NODEJS_PATH` instead of the pypi-bundled prebuilt node
  # (which can't run on NixOS' non-FHS layout — produces "Could not start
  # dynamically linked executable").
  buildInputs = with pkgs; [
    python312
    uv
    typst
    ruff
    postgresql_17
    pre-commit
    stdenv.cc.cc.lib
    # Playwright visual-QA dependencies (Chromium needs these to launch headless).
    playwright-driver.browsers
    # Nix-built node for the playwright JS driver (replaces the bundled
    # prebuilt node that can't exec on NixOS).
    nodejs_22
  ];

  shellHook = ''
    echo "Naavik dev shell ready"
    export PYTHONPATH="$PWD/src:$PYTHONPATH"
    export LD_LIBRARY_PATH="${pkgs.stdenv.cc.cc.lib}/lib''${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
    # Plan 10c (10c.1, 2026-05-11): mirror the orchestrator's default so
    # `uv run python -m db.seed` and `uv run fastapi dev` inside `nix develop`
    # (or under direnv on `cd`) hit the live dev Postgres instead of the
    # in-memory shadow lists. Without this, an operator who drops into the
    # interactive shell silently runs in memory mode while the orchestrator
    # ran in db mode — same defect class as 10b items 1/2 on the shell side.
    export NAAVIK_PERSISTENCE=db
    # Point Playwright at the Nix-provided Chromium so `playwright install`
    # is a no-op when the dev shell ships the browsers.
    export PLAYWRIGHT_BROWSERS_PATH="${pkgs.playwright-driver.browsers}"
    export PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
    # Plan 10a (PC.3, 2026-05-02): tell pypi-installed playwright python to
    # use Nix's node binary instead of its bundled-prebuilt one. The bundled
    # `<venv>/lib/.../playwright/driver/node` expects a glibc layout NixOS
    # doesn't have. Supported by playwright >= 1.40.
    export PLAYWRIGHT_NODEJS_PATH="${pkgs.nodejs_22}/bin/node"
  '';
}
