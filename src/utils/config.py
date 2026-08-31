import json
import os
import re
from copy import deepcopy
from typing import Any, Dict, List

import yaml


ENV_PATTERN = re.compile(r"\$\{([^}]+)\}")


class Config:
    def __init__(self, config_file: str = "config.yaml"):
        self.config_file = config_file
        self.data = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """Load YAML configuration and substitute ${ENV_VAR} values."""
        try:
            with open(self.config_file, "r", encoding="utf-8-sig") as file:
                content = file.read()

            def replace_env_var(match: re.Match) -> str:
                var_name = match.group(1)
                return os.getenv(var_name, match.group(0))

            config = yaml.safe_load(ENV_PATTERN.sub(replace_env_var, content)) or {}
            print(f"Configuration loaded from {self.config_file}")
            return config
        except FileNotFoundError:
            print(f"Configuration file {self.config_file} not found")
            return {}
        except yaml.YAMLError as exc:
            print(f"Error parsing YAML configuration: {exc}")
            return {}

    @staticmethod
    def _as_list(value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        if isinstance(value, (list, tuple, set)):
            return [str(item).strip() for item in value if str(item).strip()]
        return [str(value).strip()]

    @staticmethod
    def _require_resolved(value: Any, label: str) -> Any:
        if value in (None, ""):
            raise ValueError(f"Missing required configuration value: {label}")
        if isinstance(value, str) and ENV_PATTERN.search(value):
            raise ValueError(f"Environment variable is not set for: {label}")
        return value

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value using dot notation."""
        value: Any = self.data
        for part in key.split("."):
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return default

        if key.endswith(("admin_roles", "outage_user_ids")):
            return self._as_list(value)
        return value

    def get_servers(self) -> List[Dict[str, Any]]:
        """Return normalized server definitions.

        ``GAME_SERVERS`` is a JSON array stored in .env and is the preferred
        format. If it is absent, a YAML ``servers`` list or the old global
        single-server settings are accepted for backward compatibility.
        """
        raw_servers = None
        environment_servers = os.getenv("GAME_SERVERS")
        if environment_servers:
            try:
                raw_servers = json.loads(environment_servers)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"GAME_SERVERS must be a valid JSON array: {exc}"
                ) from exc

        if raw_servers is None:
            raw_servers = self.data.get("servers")
        if raw_servers is None:
            raw_servers = [
                {
                    "id": "default",
                    "name": self.get("crcon.name", "HLL"),
                    "rcon": deepcopy(self.data.get("rcon", {})),
                    "crcon": deepcopy(self.data.get("crcon", {})),
                    "discord": {
                        "admin_channel_id": self.get("discord.admin_channel_id"),
                        "admin_roles": self.get("discord.admin_roles", []),
                        "outage_user_ids": self.get(
                            "discord.outage_user_ids", []
                        ),
                    },
                }
            ]

        if not isinstance(raw_servers, list) or not raw_servers:
            raise ValueError("The 'servers' configuration must be a non-empty list")

        normalized: List[Dict[str, Any]] = []
        seen_ids = set()
        global_roles = self.get("discord.admin_roles", [])
        global_outage_user_ids = self.get("discord.outage_user_ids", [])

        for index, raw_server in enumerate(raw_servers):
            if not isinstance(raw_server, dict):
                raise ValueError(f"servers[{index}] must be an object")

            server_id = str(
                self._require_resolved(raw_server.get("id"), f"servers[{index}].id")
            ).strip()
            if not re.fullmatch(r"[a-z0-9_-]+", server_id):
                raise ValueError(
                    f"Invalid server id '{server_id}'; use lowercase letters, digits, _ or -"
                )
            if server_id in seen_ids:
                raise ValueError(f"Duplicate server id: {server_id}")
            seen_ids.add(server_id)

            rcon = raw_server.get("rcon") or {}
            crcon = raw_server.get("crcon") or {}
            discord_config = raw_server.get("discord") or {}
            if not all(
                isinstance(section, dict)
                for section in (rcon, crcon, discord_config)
            ):
                raise ValueError(
                    f"servers[{index}].rcon, .crcon and .discord must be objects"
                )

            rcon_host = str(
                self._require_resolved(
                    rcon.get("host"), f"servers[{index}].rcon.host"
                )
            ).strip()
            rcon_password = str(
                self._require_resolved(
                    rcon.get("password"), f"servers[{index}].rcon.password"
                )
            )
            raw_rcon_port = self._require_resolved(
                rcon.get("port"), f"servers[{index}].rcon.port"
            )
            try:
                rcon_port = int(raw_rcon_port)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"servers[{index}].rcon.port must be an integer"
                ) from exc
            if not 1 <= rcon_port <= 65535:
                raise ValueError(
                    f"servers[{index}].rcon.port must be between 1 and 65535"
                )

            base_url = str(
                self._require_resolved(
                    crcon.get("base_url"), f"servers[{index}].crcon.base_url"
                )
            ).rstrip("/")
            api_token = str(
                self._require_resolved(
                    crcon.get("api_token"), f"servers[{index}].crcon.api_token"
                )
            )
            channel_id = str(
                self._require_resolved(
                    discord_config.get("channel_id")
                    or discord_config.get("admin_channel_id"),
                    f"servers[{index}].discord.channel_id",
                )
            )

            roles = discord_config.get("admin_roles")
            if roles is None:
                roles = global_roles
            outage_user_ids = discord_config.get("outage_user_ids")
            if outage_user_ids is None:
                outage_user_ids = global_outage_user_ids

            normalized.append(
                {
                    "id": server_id,
                    "name": str(raw_server.get("name") or server_id),
                    "rcon": {
                        **rcon,
                        "host": rcon_host,
                        "port": rcon_port,
                        "password": rcon_password,
                    },
                    "crcon": {
                        **crcon,
                        "base_url": base_url,
                        "api_token": api_token,
                    },
                    "discord": {
                        **discord_config,
                        "admin_channel_id": channel_id,
                        "admin_roles": self._as_list(roles),
                        "outage_user_ids": self._as_list(outage_user_ids),
                    },
                }
            )

        return normalized

    def __getitem__(self, key: str) -> Any:
        return self.get(key)

    def __contains__(self, key: str) -> bool:
        return self.get(key) is not None
