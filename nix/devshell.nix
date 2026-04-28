{
  pkgs ? import <nixpkgs> {},
  ...
}:
pkgs.mkShell {
  buildInputs = with pkgs; [
    python312
    uv
    typst
    ruff
    postgresql_17
    pre-commit
    stdenv.cc.cc.lib
  ];

  shellHook = ''
    echo "Naavik dev shell ready"
    export PYTHONPATH="$PWD/src:$PYTHONPATH"
    export LD_LIBRARY_PATH="${pkgs.stdenv.cc.cc.lib}/lib''${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
  '';
}
