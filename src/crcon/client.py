import asyncio
import inspect
import json
import logging
import re
from datetime import datetime, timezone
from typing import Callable, Dict, Optional, Set

import aiohttp


logger = logging.getLogger(__name__)


class CRCONClient:
    """One isolated CRCON connection.

    Every instance owns its HTTP session, WebSocket cursor and ticket state.
    Tickets are indexed by the stable platform ``player_id``; player names are
    retained only for display and CRCON audit history.
    """

    def __init__(self, config, server_config: Optional[dict] = None):
        self.config = config
        if server_config is None:
            server_config = config.get_servers()[0]

        self.server_config = server_config
        self.server_id = server_config["id"]
        self.server_name = server_config["name"]
        self.base_url = server_config["crcon"]["base_url"].rstrip("/")
        self.api_token = server_config["crcon"]["api_token"]

        self.session: Optional[aiohttp.ClientSession] = None
        self.monitoring = False
        self.message_callback: Optional[Callable] = None
        self.player_response_callback: Optional[Callable] = None
        self.health_callback: Optional[Callable] = None
        self.headers = {"Authorization": f"Bearer {self.api_token}"}

        # Stable player_id -> ticket metadata / close time.
        self.active_threads: Dict[str, dict] = {}
        self.closed_tickets: Dict[str, datetime] = {}

        self.ws_last_seen_id: Optional[str] = None
        self.ws_seen_ids: Set[str] = set()

        # A health incident stays open until the log stream returns a valid
        # payload. Repeated identical failures are counted but not re-alerted.
        self.outage_started_at: Optional[datetime] = None
        self.outage_failure_count = 0
        self._outage_fingerprints: Set[tuple] = set()
        self._health_initialized = False

        logger.info(
            "CRCON configured: server=%s url=%s", self.server_id, self.base_url
        )

    def _server_setting(self, key: str, default):
        return self.server_config.get("crcon", {}).get(
            key, self.config.get(f"crcon.{key}", default)
        )

    async def create_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(headers=self.headers)

    async def close_session(self):
        if self.session and not self.session.closed:
            await self.session.close()
        self.session = None

    async def test_connection(self) -> bool:
        try:
            await self.create_session()
            async with self.session.get(f"{self.base_url}/api/get_status") as response:
                if response.status != 200:
                    logger.error(
                        "CRCON connection failed: server=%s status=%s",
                        self.server_id,
                        response.status,
                    )
                    await self.report_outage(
                        component="CRCON API",
                        summary="The CRCON status endpoint is unavailable",
                        detail=f"GET /api/get_status returned HTTP {response.status}",
                    )
                    return False
                data = await response.json()
                remote_name = (data.get("result") or {}).get("name", "Unknown")
                logger.info(
                    "Connected to CRCON API: server=%s remote=%s",
                    self.server_id,
                    remote_name,
                )
                return True
        except Exception as exc:
            logger.error(
                "Failed to connect to CRCON API: server=%s error=%s",
                self.server_id,
                exc,
            )
            await self.report_outage(
                component="CRCON API",
                summary="The responder cannot connect to CRCON",
                detail=f"{type(exc).__name__}: {exc}",
            )
            return False

    def register_admin_thread(self, player_id: str, thread_info: dict):
        self.closed_tickets.pop(player_id, None)
        self.active_threads[player_id] = thread_info
        logger.info(
            "Registered ticket: server=%s player_id=%s player=%s",
            self.server_id,
            player_id,
            thread_info.get("player_name"),
        )

    def unregister_admin_thread(self, player_id: str):
        self.active_threads.pop(player_id, None)

    def mark_ticket_closed(self, player_id: str):
        self.closed_tickets[player_id] = datetime.utcnow()
        self.unregister_admin_thread(player_id)

    async def send_message_to_player(
        self, player_id: str, player_name: str, message: str
    ) -> bool:
        """Send a message using the stable player ID captured from the log."""
        if not player_id:
            logger.error(
                "Refusing to message a player without player_id: server=%s player=%s",
                self.server_id,
                player_name,
            )
            return False

        try:
            await self.create_session()
            payload = {
                "player_id": player_id,
                "player_name": player_name,
                "message": message,
                "by": "Discord Admin",
            }
            async with self.session.post(
                f"{self.base_url}/api/message_player", json=payload
            ) as response:
                response_text = await response.text()
                if response.status == 200:
                    try:
                        result = json.loads(response_text)
                    except json.JSONDecodeError:
                        result = {}
                    if result.get("failed") is True:
                        logger.error(
                            "CRCON rejected player message: server=%s player_id=%s error=%s",
                            self.server_id,
                            player_id,
                            result.get("error"),
                        )
                        return False
                    logger.info(
                        "Sent message: server=%s player_id=%s player=%s",
                        self.server_id,
                        player_id,
                        player_name,
                    )
                    return True

                logger.error(
                    "Failed to send message: server=%s player_id=%s status=%s response=%s",
                    self.server_id,
                    player_id,
                    response.status,
                    response_text[:200],
                )
                return False
        except Exception as exc:
            logger.error(
                "Error sending message: server=%s player_id=%s error=%s",
                self.server_id,
                player_id,
                exc,
            )
            return False

    async def get_players(self) -> list:
        """Return current player display metadata, keyed by CRCON player_id."""
        try:
            await self.create_session()
            async with self.session.get(
                f"{self.base_url}/api/get_live_game_stats"
            ) as response:
                if response.status != 200:
                    logger.error(
                        "Failed to get players: server=%s status=%s",
                        self.server_id,
                        response.status,
                    )
                    return []

                data = await response.json()
                stats = ((data.get("result") or {}).get("stats") or [])
                return [
                    {
                        "name": stat.get("player"),
                        "player_id": stat.get("player_id"),
                        "team": stat.get("team") or stat.get("side"),
                    }
                    for stat in stats
                ]
        except Exception as exc:
            logger.error(
                "Error getting players: server=%s error=%s", self.server_id, exc
            )
            return []

    def set_message_callback(self, callback: Callable):
        self.message_callback = callback

    def set_player_response_callback(self, callback: Callable):
        self.player_response_callback = callback

    def set_health_callback(self, callback: Callable):
        self.health_callback = callback

    async def _emit_health_event(self, event: dict):
        if not self.health_callback:
            return
        try:
            result = self.health_callback(event)
            if inspect.isawaitable(result):
                await result
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception(
                "Health alert callback failed: server=%s error=%s",
                self.server_id,
                exc,
            )

    async def report_outage(self, component: str, summary: str, detail: str):
        """Emit only incident transitions, while counting repeated failures."""
        now = datetime.now(timezone.utc)
        clean_detail = str(detail or "No additional detail")[:2000]
        fingerprint = (component, summary, clean_detail)
        self.outage_failure_count += 1
        self._health_initialized = True

        if self.outage_started_at is None:
            self.outage_started_at = now
            status = "outage"
        elif fingerprint not in self._outage_fingerprints:
            status = "update"
        else:
            return

        self._outage_fingerprints.add(fingerprint)
        await self._emit_health_event(
            {
                "status": status,
                "server_id": self.server_id,
                "server_name": self.server_name,
                "component": component,
                "summary": summary,
                "detail": clean_detail,
                "endpoint": self.base_url,
                "occurred_at": now,
                "started_at": self.outage_started_at,
                "failure_count": self.outage_failure_count,
            }
        )

    async def report_recovery(self):
        """Close an active incident after a valid log-stream payload arrives."""
        if self.outage_started_at is None:
            if not self._health_initialized:
                self._health_initialized = True
                now = datetime.now(timezone.utc)
                await self._emit_health_event(
                    {
                        "status": "healthy",
                        "server_id": self.server_id,
                        "server_name": self.server_name,
                        "component": "CRCON log stream",
                        "summary": "A valid CRCON log-stream payload was received",
                        "detail": "Admin-request monitoring is operational.",
                        "endpoint": self.base_url,
                        "occurred_at": now,
                        "failure_count": 0,
                        "duration_seconds": 0,
                    }
                )
            return

        now = datetime.now(timezone.utc)
        started_at = self.outage_started_at
        failure_count = self.outage_failure_count
        duration_seconds = max(0, int((now - started_at).total_seconds()))

        self.outage_started_at = None
        self.outage_failure_count = 0
        self._outage_fingerprints.clear()
        await self._emit_health_event(
            {
                "status": "recovered",
                "server_id": self.server_id,
                "server_name": self.server_name,
                "component": "CRCON log stream",
                "summary": "A valid CRCON log-stream payload was received",
                "detail": "Admin-request monitoring is operational again.",
                "endpoint": self.base_url,
                "occurred_at": now,
                "started_at": started_at,
                "failure_count": failure_count,
                "duration_seconds": duration_seconds,
            }
        )

    @staticmethod
    def _clean_message(message: str) -> str:
        if not message:
            return ""
        # Older CRCON raw chat strings could suffix a Steam ID. Structured
        # ``message`` values normally do not, but stripping it is harmless.
        return re.sub(r"\(76561\d+\)", "", message).strip()

    async def process_log_entry(self, entry: dict):
        """Route one CRCON structured CHAT log entry.

        Kept separate from the socket loop to make player-ID behavior directly
        testable without a live WebSocket.
        """
        stream_id = entry.get("id")
        if stream_id and stream_id in self.ws_seen_ids:
            return
        if stream_id:
            self.ws_seen_ids.add(stream_id)
            if len(self.ws_seen_ids) > 5000:
                self.ws_seen_ids.clear()
                self.ws_seen_ids.add(stream_id)

        log = entry.get("log") or {}
        if not str(log.get("action") or "").startswith("CHAT"):
            return

        player_id = log.get("player_id_1")
        player_name = log.get("player_name_1")
        content = log.get("message") or log.get("raw") or ""
        event_time = log.get("event_time")
        if not player_name or not content:
            return
        if not player_id:
            logger.warning(
                "Ignoring CHAT log without player_id: server=%s player=%s",
                self.server_id,
                player_name,
            )
            return

        full_message = self._clean_message(content)
        if player_id in self.active_threads:
            # Keep the latest display name in case it changed during a ticket.
            self.active_threads[player_id]["player_name"] = player_name
            if self.player_response_callback:
                await self.player_response_callback(
                    player_id, player_name, full_message, event_time
                )
            return

        if "admin" in content.lower():
            self.closed_tickets.pop(player_id, None)
            if self.message_callback:
                await self.message_callback(player_id, player_name, full_message)

    async def start_monitoring(self):
        """Continuously monitor this server's structured log WebSocket."""
        reconnect_delay = int(self._server_setting("ws_reconnect_initial_seconds", 3))
        max_delay = int(self._server_setting("ws_reconnect_max_seconds", 30))
        self.monitoring = True

        while self.monitoring:
            if not await self.test_connection():
                logger.warning(
                    "CRCON unavailable; retrying: server=%s delay=%ss",
                    self.server_id,
                    reconnect_delay,
                )
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, max_delay)
                continue

            try:
                await self.monitor_via_websocket()
                reconnect_delay = int(
                    self._server_setting("ws_reconnect_initial_seconds", 3)
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error(
                    "WebSocket loop error: server=%s error=%s", self.server_id, exc
                )
                await self.report_outage(
                    component="CRCON log stream",
                    summary="The CRCON WebSocket connection failed",
                    detail=f"{type(exc).__name__}: {exc}",
                )

            if self.monitoring:
                logger.warning(
                    "WebSocket disconnected; reconnecting: server=%s delay=%ss",
                    self.server_id,
                    reconnect_delay,
                )
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, max_delay)

    def stop_monitoring(self):
        self.monitoring = False

    async def monitor_via_websocket(self):
        await self.create_session()
        ws_url = self.base_url.replace("http://", "ws://", 1).replace(
            "https://", "wss://", 1
        )
        ws_url = f"{ws_url.rstrip('/')}/ws/logs"
        logger.info(
            "Connecting to WebSocket log stream: server=%s url=%s",
            self.server_id,
            ws_url,
        )

        async with self.session.ws_connect(
            ws_url, headers=self.headers, heartbeat=30
        ) as websocket:
            await websocket.send_json(
                {"last_seen_id": self.ws_last_seen_id, "actions": ["CHAT"]}
            )
            logger.info("WebSocket stream started: server=%s", self.server_id)
            reported_stream_error = False

            while self.monitoring:
                message = await websocket.receive()
                if message.type == aiohttp.WSMsgType.TEXT:
                    try:
                        data = json.loads(message.data)
                    except (json.JSONDecodeError, TypeError):
                        logger.warning(
                            "Invalid WebSocket payload: server=%s", self.server_id
                        )
                        reported_stream_error = True
                        await self.report_outage(
                            component="CRCON log stream",
                            summary="CRCON returned an invalid WebSocket payload",
                            detail="The response was not valid JSON.",
                        )
                        continue

                    if not isinstance(data, dict):
                        continue
                    if data.get("error"):
                        logger.error(
                            "WebSocket server error: server=%s error=%s",
                            self.server_id,
                            data["error"],
                        )
                        reported_stream_error = True
                        await self.report_outage(
                            component="CRCON log stream",
                            summary="CRCON rejected log streaming",
                            detail=str(data["error"]),
                        )
                        await asyncio.sleep(1)
                        continue

                    reported_stream_error = False
                    await self.report_recovery()
                    if data.get("last_seen_id"):
                        self.ws_last_seen_id = data["last_seen_id"]
                    for entry in data.get("logs") or []:
                        await self.process_log_entry(entry)
                elif message.type in (
                    aiohttp.WSMsgType.CLOSED,
                    aiohttp.WSMsgType.CLOSE,
                    aiohttp.WSMsgType.ERROR,
                ):
                    if not reported_stream_error:
                        await self.report_outage(
                            component="CRCON log stream",
                            summary="The CRCON WebSocket disconnected",
                            detail=(
                                f"message_type={message.type.name}; "
                                f"close_code={websocket.close_code}"
                            ),
                        )
                    break
