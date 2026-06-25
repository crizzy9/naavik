{ config, lib, pkgs, settings, ... }:
let
  cfg = settings.servicesConfig.apps.tools.naavik or {};
  enable = cfg.enable or false;
  domain = "${cfg.subdomain or "jobs"}.${settings.servicesConfig.domain or "domainname.net"}";
  port = cfg.port or 8003;
  storage = settings.servicesConfig.storage or {};
  dataDir = "${storage.appdata or "/data/appdata"}/naavik";
  naavikPkg = pkgs.callPackage ./package.nix {};
in {
  config = lib.mkIf enable {
    systemd.services.naavik = {
      description = "Naavik - Career automation platform";
      after = [ "network.target" "postgresql.service" ];
      wantedBy = [ "multi-user.target" ];

      environment = {
        NAAVIK_DATA_DIR = dataDir;
        HOST = "127.0.0.1";
        PORT = toString port;
      };

      serviceConfig = {
        # Run alembic migrations before the main service starts
        ExecStartPre = "${naavikPkg}/bin/naavik-migrate";
        ExecStart = "${naavikPkg}/bin/naavik";
        EnvironmentFile = lib.mkIf (config.sops.secrets ? "naavik_env") [
          config.sops.secrets."naavik_env".path
        ];
        User = "naavik";
        Group = "services";
        StateDirectory = "naavik";
        ReadWritePaths = [ dataDir ];
        WorkingDirectory = dataDir;

        CapabilityBoundingSet = "";
        LockPersonality = true;
        NoNewPrivileges = true;
        PrivateDevices = true;
        PrivateTmp = true;
        ProtectClock = true;
        ProtectControlGroups = true;
        ProtectHome = true;
        ProtectHostname = true;
        ProtectKernelLogs = true;
        ProtectKernelModules = true;
        ProtectKernelTunables = true;
        ProtectSystem = "strict";
        RestrictAddressFamilies = [ "AF_INET" "AF_INET6" "AF_UNIX" ];
        RestrictNamespaces = true;
        RestrictRealtime = true;
        SystemCallArchitectures = "native";
      };
    };

    users.users.naavik = {
      isSystemUser = true;
      group = "services";
      home = dataDir;
    };

    systemd.tmpfiles.rules = [
      "d ${dataDir} 0750 naavik services -"
    ];

    sops.secrets."naavik_env" = {
      sopsFile = ../../hosts/${settings.system.os}/${settings.host}/secrets.yaml;
      owner = "naavik";
      group = "services";
      mode = "0440";
    };

    services.traefik.dynamicConfigOptions.http = lib.mkIf (settings.servicesConfig.infrastructure.traefik.enable or false) {
      routers.naavik = {
        rule = "Host(`${domain}`)";
        service = "naavik";
        entryPoints = [ "websecure" ];
      };
      services.naavik.loadBalancer.servers = [
        { url = "http://127.0.0.1:${toString port}"; }
      ];
    };

    services.postgresql = {
      ensureDatabases = [ "naavik" ];
      ensureUsers = [
        {
          name = "naavik";
          ensureDBOwnership = true;
        }
      ];
    };
  };
}
