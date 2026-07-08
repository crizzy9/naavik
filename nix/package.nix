{
  pkgs ? import <nixpkgs> {},
  ...
}:
let
  py = pkgs.python312;
in
py.pkgs.buildPythonApplication {
  pname = "naavik";
  version = "0.2.6";
  pyproject = true;

  src = ./..;

  propagatedBuildInputs = with py.pkgs; [
    fastapi
    uvicorn
    sqlmodel
    asyncpg
    alembic
    pydantic-settings
    jinja2
    python-multipart
    anthropic
    openai
    httpx
    icalendar
  ];

  nativeBuildInputs = with py.pkgs; [
    setuptools
    wheel
  ];

  # nixpkgs' pythonRuntimeDepsCheck hook cross-checks pyproject Requires-Dist
  # against propagatedBuildInputs and has been failing since well before plan
  # 96 (a dozen deps — psycopg, playwright, crawl4ai, ... — were added to
  # pyproject across plans 29-66 without mirroring them here, and crawl4ai
  # isn't packaged in nixpkgs at all, so the list CANNOT be made complete).
  # The self-host path runs `uv sync` against uv.lock; this package exists for
  # the NixOS module's `naavik-migrate` + entrypoint wrapper. Discovered (not
  # introduced) during plan 96d's icalendar addition, 2026-07-08.
  dontCheckRuntimeDeps = true;

  buildInputs = with pkgs; [
    typst
  ];

  # Bundle migrations + alembic config; emit naavik-migrate wrapper for the NixOS module
  postInstall = ''
    mkdir -p $out/share/naavik
    cp -r migrations $out/share/naavik/
    cp alembic.ini $out/share/naavik/

    # Strip dev-only prepend_sys_path; in the installed package, config/main live in the venv
    substituteInPlace $out/share/naavik/alembic.ini \
      --replace "prepend_sys_path = src" "prepend_sys_path = ."

    cat > $out/bin/naavik-migrate <<MIGRATE_SH
    #!${pkgs.runtimeShell}
    set -e
    cd $out/share/naavik
    exec $out/bin/naavik-alembic upgrade head
    MIGRATE_SH
    chmod +x $out/bin/naavik-migrate
  '';

  makeWrapperArgs = [
    "--prefix PATH : ${pkgs.lib.makeBinPath [pkgs.typst]}"
  ];

  meta = with pkgs.lib; {
    description = "Open-source, self-hosted career automation platform";
    license = licenses.agpl3Only;
    platforms = platforms.linux;
  };
}
