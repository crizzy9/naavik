{
  pkgs ? import <nixpkgs> {},
  ...
}:
pkgs.mkShell {
  # Plan 09 adds `playwright` (via uv at run time) plus the Playwright system
  # libs (chromium dependencies) so visual-QA snapshots can run without a
  # bespoke install. The browsers themselves come from `playwright install
  # chromium` (run once per dev shell entry — see shellHook).
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
  ];

  shellHook = ''
    echo "Naavik dev shell ready"
    export PYTHONPATH="$PWD/src:$PYTHONPATH"
    export LD_LIBRARY_PATH="${pkgs.stdenv.cc.cc.lib}/lib''${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
    # Point Playwright at the Nix-provided Chromium so `playwright install`
    # is a no-op when the dev shell ships the browsers.
    export PLAYWRIGHT_BROWSERS_PATH="${pkgs.playwright-driver.browsers}"
    export PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
  '';
}
