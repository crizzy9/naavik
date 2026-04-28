{ pkgs ? import <nixpkgs> {}, ... }:

let
  python = pkgs.python312;
in
pkgs.python312Packages.buildPythonApplication {
  pname = "naavik";
  version = "0.1.0";
  pyproject = true;

  src = ./..;

  propagatedBuildInputs = with pkgs.python312Packages; [
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
  ];

  nativeBuildInputs = with pkgs.python312Packages; [
    setuptools
    wheel
  ];

  buildInputs = with pkgs; [
    typst
  ];

  makeWrapperArgs = [
    "--prefix PATH : ${pkgs.lib.makeBinPath [ pkgs.typst ]}"
  ];

  meta = with pkgs.lib; {
    description = "Open-source, self-hosted career automation platform";
    license = licenses.agpl3Only;
    platforms = platforms.linux;
  };
}
