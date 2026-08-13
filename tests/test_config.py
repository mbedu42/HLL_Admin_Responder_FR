import json
import os
import unittest
from unittest.mock import patch

from utils.config import Config


def config_with(data):
    config = Config.__new__(Config)
    config.config_file = "<memory>"
    config.data = data
    return config


class ServerConfigTests(unittest.TestCase):
    def test_normalizes_multiple_servers_and_inherits_roles(self):
        config = config_with(
            {
                "discord": {"admin_roles": "10,20"},
                "servers": [
                    {
                        "id": "ww2",
                        "name": "Classic",
                        "rcon": {"host": "game-1", "port": 7777, "password": "p1"},
                        "crcon": {"base_url": "https://ww2/", "api_token": "a"},
                        "discord": {"admin_channel_id": 100},
                    },
                    {
                        "id": "vietnam",
                        "rcon": {"host": "game-2", "port": 7778, "password": "p2"},
                        "crcon": {"base_url": "https://viet", "api_token": "b"},
                        "discord": {
                            "admin_channel_id": 200,
                            "admin_roles": ["30"],
                        },
                    },
                ],
            }
        )

        servers = config.get_servers()

        self.assertEqual([server["id"] for server in servers], ["ww2", "vietnam"])
        self.assertEqual(servers[0]["crcon"]["base_url"], "https://ww2")
        self.assertEqual(servers[0]["discord"]["admin_roles"], ["10", "20"])
        self.assertEqual(servers[1]["discord"]["admin_roles"], ["30"])
        self.assertEqual(servers[1]["discord"]["admin_channel_id"], "200")

    def test_legacy_single_server_configuration_still_works(self):
        config = config_with(
            {
                "discord": {"admin_channel_id": "100", "admin_roles": "10"},
                "rcon": {"host": "game", "port": "7777", "password": "pw"},
                "crcon": {
                    "base_url": "http://localhost:8010",
                    "api_token": "secret",
                },
            }
        )

        servers = config.get_servers()

        self.assertEqual(len(servers), 1)
        self.assertEqual(servers[0]["id"], "default")
        self.assertEqual(servers[0]["discord"]["admin_roles"], ["10"])

    def test_rejects_duplicate_server_ids(self):
        server = {
            "id": "same",
            "rcon": {"host": "game", "port": 7777, "password": "pw"},
            "crcon": {"base_url": "https://example", "api_token": "token"},
            "discord": {"admin_channel_id": "100"},
        }
        config = config_with({"servers": [server, server]})

        with self.assertRaisesRegex(ValueError, "Duplicate server id"):
            config.get_servers()

    def test_rejects_unresolved_environment_variable(self):
        config = config_with(
            {
                "servers": [
                    {
                        "id": "test",
                        "rcon": {"host": "game", "port": 7777, "password": "pw"},
                        "crcon": {
                            "base_url": "${MISSING_URL}",
                            "api_token": "token",
                        },
                        "discord": {"admin_channel_id": "100"},
                    }
                ]
            }
        )

        with self.assertRaisesRegex(ValueError, "Environment variable"):
            config.get_servers()

    def test_game_servers_environment_array_is_dynamic_and_takes_priority(self):
        servers = [
            {
                "id": "one",
                "rcon": {"host": "host-1", "port": 7001, "password": "pw-1"},
                "crcon": {"base_url": "https://one", "api_token": "token-1"},
                "discord": {"channel_id": "101"},
            },
            {
                "id": "two",
                "rcon": {"host": "host-2", "port": 7002, "password": "pw-2"},
                "crcon": {"base_url": "https://two", "api_token": "token-2"},
                "discord": {"channel_id": "102"},
            },
            {
                "id": "three",
                "rcon": {"host": "host-3", "port": 7003, "password": "pw-3"},
                "crcon": {"base_url": "https://three", "api_token": "token-3"},
                "discord": {"channel_id": "103"},
            },
        ]
        config = config_with({"servers": []})

        with patch.dict(os.environ, {"GAME_SERVERS": json.dumps(servers)}):
            normalized = config.get_servers()

        self.assertEqual([server["id"] for server in normalized], ["one", "two", "three"])
        self.assertEqual(normalized[2]["rcon"]["port"], 7003)
        self.assertEqual(normalized[2]["discord"]["admin_channel_id"], "103")


if __name__ == "__main__":
    unittest.main()
