import asyncio
import json
import unittest
from datetime import timedelta
from unittest.mock import AsyncMock, patch

from crcon.client import CRCONClient


class FakeConfig:
    def __init__(self, values=None):
        self.values = values or {}

    def get(self, key, default=None):
        return self.values.get(key, default)


SERVER = {
    "id": "vietnam",
    "name": "Vietnam",
    "crcon": {"base_url": "https://viet.example", "api_token": "token"},
    "discord": {"admin_channel_id": "200", "admin_roles": []},
}


class FakeResponse:
    status = 200

    async def text(self):
        return json.dumps({"failed": False, "result": True})

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class FakeSession:
    closed = False

    def __init__(self):
        self.calls = []

    def post(self, url, json):
        self.calls.append((url, json))
        return FakeResponse()


class CRCONPlayerIdTests(unittest.IsolatedAsyncioTestCase):
    async def test_first_valid_stream_payload_reports_initial_health_once(self):
        client = CRCONClient(FakeConfig(), SERVER)
        events = []

        async def on_health(event):
            events.append(event)

        client.set_health_callback(on_health)
        await client.report_recovery()
        await client.report_recovery()

        self.assertEqual([event["status"] for event in events], ["healthy"])

    async def test_monitor_reconnects_after_a_websocket_disconnect(self):
        client = CRCONClient(FakeConfig(), SERVER)
        client.test_connection = AsyncMock(return_value=True)
        connection_attempts = 0

        async def monitor_once():
            nonlocal connection_attempts
            connection_attempts += 1
            if connection_attempts == 1:
                return
            raise asyncio.CancelledError

        client.monitor_via_websocket = monitor_once
        with patch("crcon.client.asyncio.sleep", new=AsyncMock()) as sleep:
            with self.assertRaises(asyncio.CancelledError):
                await client.start_monitoring()

        self.assertEqual(connection_attempts, 2)
        sleep.assert_awaited_once_with(3)

    async def test_unhealthy_websocket_reconnects_use_exponential_backoff(self):
        client = CRCONClient(FakeConfig(), SERVER)
        client.test_connection = AsyncMock(return_value=True)
        connection_attempts = 0

        async def monitor_until_cancelled():
            nonlocal connection_attempts
            connection_attempts += 1
            if connection_attempts <= 2:
                return False
            raise asyncio.CancelledError

        client.monitor_via_websocket = monitor_until_cancelled
        with patch("crcon.client.asyncio.sleep", new=AsyncMock()) as sleep:
            with self.assertRaises(asyncio.CancelledError):
                await client.start_monitoring()

        self.assertEqual(connection_attempts, 3)
        self.assertEqual(
            [awaited.args for awaited in sleep.await_args_list],
            [(3,), (6,)],
        )

    async def test_health_events_are_deduplicated_updated_and_recovered(self):
        client = CRCONClient(
            FakeConfig(
                {
                    "crcon.health_failure_threshold": 2,
                    "crcon.health_failure_grace_seconds": 0,
                    "crcon.health_emit_updates": True,
                    "crcon.health_update_cooldown_seconds": 0,
                }
            ),
            SERVER,
        )
        events = []

        async def on_health(event):
            events.append(event)

        client.set_health_callback(on_health)

        await client.report_outage(
            "CRCON API",
            "Status endpoint unavailable",
            "GET /api/get_status returned HTTP 502",
        )
        await client.report_outage(
            "CRCON API",
            "Status endpoint unavailable",
            "GET /api/get_status returned HTTP 502",
        )
        self.assertEqual([event["status"] for event in events], ["outage"])

        await client.report_outage(
            "CRCON log stream",
            "CRCON rejected log streaming",
            "Log stream is not enabled in your config",
        )
        self.assertEqual(
            [event["status"] for event in events], ["outage", "update"]
        )
        self.assertEqual(events[-1]["failure_count"], 3)

        await client.report_recovery()
        await client.report_recovery()
        self.assertEqual(
            [event["status"] for event in events],
            ["outage", "update", "recovered"],
        )
        self.assertEqual(events[-1]["failure_count"], 3)
        self.assertEqual(events[-1]["server_id"], "vietnam")

    async def test_transient_failure_recovers_without_an_outage_event(self):
        client = CRCONClient(FakeConfig(), SERVER)
        events = []
        client.set_health_callback(events.append)

        # Establish normal operation, then simulate one short network failure.
        await client.report_recovery()
        events.clear()
        await client.report_outage(
            "CRCON API",
            "Status endpoint unavailable",
            "ClientOSError: broken pipe",
        )
        await client.report_recovery()

        self.assertEqual(events, [])
        self.assertIsNone(client.outage_started_at)
        self.assertEqual(client.outage_failure_count, 0)

    async def test_outage_requires_both_failure_count_and_grace_period(self):
        client = CRCONClient(
            FakeConfig(
                {
                    "crcon.health_failure_threshold": 2,
                    "crcon.health_failure_grace_seconds": 60,
                }
            ),
            SERVER,
        )
        events = []
        client.set_health_callback(events.append)

        for _ in range(2):
            await client.report_outage("CRCON API", "Unavailable", "timeout")
        self.assertEqual(events, [])

        client.outage_started_at -= timedelta(seconds=61)
        await client.report_outage("CRCON API", "Unavailable", "timeout")
        self.assertEqual([event["status"] for event in events], ["outage"])

    async def test_active_outage_updates_are_silent_by_default(self):
        client = CRCONClient(
            FakeConfig(
                {
                    "crcon.health_failure_threshold": 1,
                    "crcon.health_failure_grace_seconds": 0,
                }
            ),
            SERVER,
        )
        events = []
        client.set_health_callback(events.append)

        await client.report_outage("CRCON API", "Unavailable", "timeout")
        await client.report_outage(
            "CRCON log stream", "Disconnected", "close_code=1011"
        )

        self.assertEqual([event["status"] for event in events], ["outage"])

    async def test_routes_logs_and_ticket_state_by_player_id(self):
        client = CRCONClient(FakeConfig(), SERVER)
        admin_requests = []
        responses = []

        async def on_admin(player_id, player_name, message, full_message):
            admin_requests.append(
                (player_id, player_name, message, full_message)
            )

        async def on_response(player_id, player_name, message, event_time):
            responses.append((player_id, player_name, message, event_time))

        client.set_message_callback(on_admin)
        client.set_player_response_callback(on_response)
        entry = {
            "id": "1-0",
            "log": {
                "action": "CHAT[Team]",
                "player_id_1": "76561190000000001",
                "player_name_1": "SameName",
                "message": "!admin besoin d'aide",
                "event_time": "now",
            },
        }

        await client.process_log_entry(entry)
        self.assertEqual(
            admin_requests,
            [
                (
                    "76561190000000001",
                    "SameName",
                    "besoin d'aide",
                    "!admin besoin d'aide",
                )
            ],
        )

        client.register_admin_thread("76561190000000001", {"player_name": "SameName"})
        entry["id"] = "2-0"
        entry["log"]["message"] = "message suivant"
        await client.process_log_entry(entry)
        self.assertEqual(responses[0][0], "76561190000000001")

        # The same display name with another ID is a different player/ticket.
        entry["id"] = "3-0"
        entry["log"]["player_id_1"] = "76561190000000002"
        entry["log"]["message"] = "!admin autre joueur"
        await client.process_log_entry(entry)
        self.assertEqual(admin_requests[-1][0], "76561190000000002")

    async def test_extracts_report_from_raw_crossplay_chat(self):
        client = CRCONClient(FakeConfig(), SERVER)
        admin_requests = []

        async def on_admin(*args):
            admin_requests.append(args)

        client.set_message_callback(on_admin)
        await client.process_log_entry(
            {
                "id": "raw-1",
                "log": {
                    "action": "CHAT[Team]",
                    "player_id_1": "00028700f0c249bea56accca47967c56",
                    "player_name_1": "OhaxFR",
                    "raw": (
                        "OhaxFR: @admin Mister-Picklles93 qui TK volontairement "
                        "(00028700f0c249bea56accca47967c56)"
                    ),
                },
            }
        )

        self.assertEqual(
            admin_requests,
            [
                (
                    "00028700f0c249bea56accca47967c56",
                    "OhaxFR",
                    "Mister-Picklles93 qui TK volontairement",
                    "@admin Mister-Picklles93 qui TK volontairement",
                )
            ],
        )

    async def test_preserves_a_bare_admin_command_as_the_full_message(self):
        client = CRCONClient(FakeConfig(), SERVER)
        admin_requests = []

        async def on_admin(*args):
            admin_requests.append(args)

        client.set_message_callback(on_admin)
        await client.process_log_entry(
            {
                "id": "bare-admin",
                "log": {
                    "action": "CHAT[Team]",
                    "player_id_1": "player-1",
                    "player_name_1": "Reporter",
                    "message": "admin",
                },
            }
        )

        self.assertEqual(
            admin_requests,
            [("player-1", "Reporter", "", "admin")],
        )

    def test_normalizes_live_ticket_context(self):
        context = CRCONClient._build_ticket_context(
            {
                "stats": [
                    {
                        "player": "Reporter",
                        "player_id": "player-1",
                        "team": "allies",
                    }
                ]
            },
            {
                "current_map": {
                    "id": "carentan_offensive_ger",
                    "map": {
                        "pretty_name": "Carentan",
                        "allies": {"name": "us"},
                        "axis": {"name": "ger"},
                    },
                },
                "game_mode": "offensive",
                "allied_score": 2,
                "axis_score": 3,
                "raw_time_remaining": "00:31:42",
            },
            "player-1",
        )

        self.assertEqual(
            context,
            {
                "team": "US",
                "map": "Carentan",
                "mode": "Offensive",
                "score": "US 2 | GER 3",
                "time_remaining": "00:31:42",
            },
        )

    async def test_ignores_chat_without_player_id(self):
        client = CRCONClient(FakeConfig(), SERVER)
        calls = []

        async def on_admin(*args):
            calls.append(args)

        client.set_message_callback(on_admin)
        await client.process_log_entry(
            {
                "id": "1-0",
                "log": {
                    "action": "CHAT[Team]",
                    "player_name_1": "NoId",
                    "message": "!admin help",
                },
            }
        )
        self.assertEqual(calls, [])

    async def test_message_player_uses_captured_id_without_name_lookup(self):
        client = CRCONClient(FakeConfig(), SERVER)
        session = FakeSession()
        client.session = session

        sent = await client.send_message_to_player(
            "76561190000000001", "DisplayName", "Bonjour"
        )

        self.assertTrue(sent)
        self.assertEqual(len(session.calls), 1)
        _, payload = session.calls[0]
        self.assertEqual(payload["player_id"], "76561190000000001")
        self.assertEqual(payload["player_name"], "DisplayName")


if __name__ == "__main__":
    unittest.main()
