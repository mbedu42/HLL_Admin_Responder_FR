import json
import unittest

from crcon.client import CRCONClient


class FakeConfig:
    def get(self, key, default=None):
        return default


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
    async def test_routes_logs_and_ticket_state_by_player_id(self):
        client = CRCONClient(FakeConfig(), SERVER)
        admin_requests = []
        responses = []

        async def on_admin(player_id, player_name, message):
            admin_requests.append((player_id, player_name, message))

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
            [("76561190000000001", "SameName", "!admin besoin d'aide")],
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
