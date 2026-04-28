{
  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
    flake-parts.url = "github:hercules-ci/flake-parts";
  };

  outputs = inputs:
    inputs.flake-parts.lib.mkFlake {inherit inputs;} {
      systems = [
        "x86_64-linux"
        "aarch64-linux"
      ];

      perSystem = {pkgs, system, ...}: {
        devShells.default = pkgs.callPackage ./nix/devshell.nix {};
        packages.default = pkgs.callPackage ./nix/package.nix {};
        packages.naavik = pkgs.callPackage ./nix/package.nix {};
      };

      flake.nixosModules = {
        default = import ./nix/module.nix;
        naavik = import ./nix/module.nix;
      };
    };
}
