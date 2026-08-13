import unittest

from discord_bot.bot import DiscordBot


class FakeClient:
    def __init__(self, server_id):
        self.server_id = server_id
        self.message_callback = None
        self.response_callback = None

    def set_message_callback(self, callback):
        self.message_callback = callback

    def set_player_response_callback(self, callback):
        self.response_callback = callback


class FakeConfig:
    def get(self, key, default=None):
        values = {
            "tickets.auto_close_minutes": 90,
            "tickets.inactivity_check_interval_seconds": 60,
        }
        return values.get(key, default)

    def get_servers(self):
        return [
            {
                "id": "ww2",
                "name": "Classic",
                "rcon": {"host": "game-1", "port": 7777, "password": "p1"},
                "crcon": {"base_url": "https://ww2", "api_token": "a"},
                "discord": {"admin_channel_id": "100", "admin_roles": ["10"]},
            },
            {
                "id": "vietnam",
                "name": "Vietnam",
                "rcon": {"host": "game-2", "port": 7778, "password": "p2"},
                "crcon": {"base_url": "https://viet", "api_token": "b"},
                "discord": {"admin_channel_id": "200", "admin_roles": ["20"]},
            },
        ]


class DiscordRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_registers_server_specific_callbacks_and_keys(self):
        clients = {server_id: FakeClient(server_id) for server_id in ("ww2", "vietnam")}
        bot = DiscordBot(FakeConfig(), clients)
        try:
            self.assertEqual(clients["ww2"].message_callback.args[0], "ww2")
            self.assertEqual(clients["vietnam"].message_callback.args[0], "vietnam")
            self.assertIs(bot.get_client("ww2"), clients["ww2"])
            self.assertEqual(bot.get_admin_mentions("ww2"), "<@&10>")
            self.assertEqual(bot.get_admin_mentions("vietnam"), "<@&20>")

            bot.player_names[("ww2", "same-id")] = "Classic player"
            bot.player_names[("vietnam", "same-id")] = "Vietnam player"
            self.assertEqual(bot.get_player_name(("ww2", "same-id")), "Classic player")
            self.assertEqual(bot.get_player_name(("vietnam", "same-id")), "Vietnam player")
        finally:
            await bot.close()


if __name__ == "__main__":
    unittest.main()
