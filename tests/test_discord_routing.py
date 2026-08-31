import unittest
from datetime import datetime, timedelta, timezone

from discord_bot.bot import DiscordBot, build_ticket_thread_name


class FakeClient:
    def __init__(self, server_id):
        self.server_id = server_id
        self.message_callback = None
        self.response_callback = None
        self.health_callback = None

    def set_message_callback(self, callback):
        self.message_callback = callback

    def set_player_response_callback(self, callback):
        self.response_callback = callback

    def set_health_callback(self, callback):
        self.health_callback = callback


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
                "discord": {
                    "admin_channel_id": "100",
                    "admin_roles": ["10"],
                    "outage_user_ids": ["40", "50"],
                },
            },
            {
                "id": "vietnam",
                "name": "Vietnam",
                "rcon": {"host": "game-2", "port": 7778, "password": "p2"},
                "crcon": {"base_url": "https://viet", "api_token": "b"},
                "discord": {
                    "admin_channel_id": "200",
                    "admin_roles": ["20"],
                    "outage_user_ids": ["60"],
                },
            },
        ]


class FakeOutageThread:
    def __init__(self):
        self.id = 999
        self.sent = []
        self.edits = []

    async def send(self, **kwargs):
        self.sent.append(kwargs)

    async def edit(self, **kwargs):
        self.edits.append(kwargs)


class DiscordRoutingTests(unittest.IsolatedAsyncioTestCase):
    def test_ticket_title_includes_a_clean_report_summary(self):
        title = build_ticket_thread_name(
            "2026-08-31 14:20",
            "Reporter",
            "Mister-Picklles93\nqui TK volontairement",
        )

        self.assertEqual(
            title,
            "2026-08-31 14:20 - Reporter - Mister-Picklles93 qui TK volontairement",
        )
        self.assertLessEqual(len(title), 100)

    async def test_registers_server_specific_callbacks_and_keys(self):
        clients = {server_id: FakeClient(server_id) for server_id in ("ww2", "vietnam")}
        bot = DiscordBot(FakeConfig(), clients)
        try:
            self.assertEqual(clients["ww2"].message_callback.args[0], "ww2")
            self.assertEqual(clients["vietnam"].message_callback.args[0], "vietnam")
            self.assertEqual(clients["ww2"].health_callback.args[0], "ww2")
            self.assertEqual(clients["vietnam"].health_callback.args[0], "vietnam")
            self.assertIs(bot.get_client("ww2"), clients["ww2"])
            self.assertEqual(bot.get_admin_mentions("ww2"), "<@&10>")
            self.assertEqual(bot.get_admin_mentions("vietnam"), "<@&20>")
            self.assertEqual(bot.get_outage_mentions("ww2"), "<@40> <@50>")
            self.assertEqual(bot.get_outage_mentions("vietnam"), "<@60>")

            bot.player_names[("ww2", "same-id")] = "Classic player"
            bot.player_names[("vietnam", "same-id")] = "Vietnam player"
            self.assertEqual(bot.get_player_name(("ww2", "same-id")), "Classic player")
            self.assertEqual(bot.get_player_name(("vietnam", "same-id")), "Vietnam player")
            self.assertIn("OUTAGE", bot.STATUS_TAGS)

            await clients["ww2"].health_callback(
                {"status": "outage", "summary": "test"}
            )
            queued_event = await bot.health_event_queue.get()
            self.assertEqual(queued_event["server_id"], "ww2")
            self.assertEqual(queued_event["status"], "outage")
            bot.health_event_queue.task_done()
        finally:
            await bot.close()

    async def test_recovery_closes_and_archives_the_outage_thread(self):
        clients = {server_id: FakeClient(server_id) for server_id in ("ww2", "vietnam")}
        bot = DiscordBot(FakeConfig(), clients)
        thread = FakeOutageThread()
        bot.outage_threads["ww2"] = thread
        applied_tags = []

        async def apply_tag(server_id, target_thread, tag_name):
            applied_tags.append((server_id, target_thread, tag_name))

        bot.apply_forum_tag = apply_tag
        now = datetime.now(timezone.utc)
        try:
            delivered = await bot.deliver_health_event(
                {
                    "status": "recovered",
                    "server_id": "ww2",
                    "occurred_at": now,
                    "started_at": now - timedelta(minutes=2),
                    "duration_seconds": 125,
                    "failure_count": 4,
                }
            )

            self.assertTrue(delivered)
            self.assertEqual(applied_tags, [("ww2", thread, "CLOSED")])
            self.assertEqual(thread.edits, [{"archived": True, "locked": True}])
            self.assertNotIn("ww2", bot.outage_threads)
            self.assertEqual(len(thread.sent), 1)
            self.assertEqual(
                thread.sent[0]["embed"].fields[1].value, "2 min 5 s"
            )
        finally:
            await bot.close()


if __name__ == "__main__":
    unittest.main()
