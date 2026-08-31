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

    async def _get_api_result(self, endpoint: str) -> dict:
        """Return a CRCON API result without interrupting ticket delivery."""
        try:
            await self.create_session()
            async with self.session.get(
                f"{self.base_url}/api/{endpoint}"
            ) as response:
                if response.status != 200:
                    logger.warning(
                        "Optional CRCON context unavailable: server=%s "
                        "endpoint=%s status=%s",
                        self.server_id,
                        endpoint,
                        response.status,
                    )
                    return {}

                data = await response.json()
                if data.get("failed") is True:
                    logger.warning(
                        "CRCON rejected optional context request: server=%s "
                        "endpoint=%s error=%s",
                        self.server_id,
                        endpoint,
                        data.get("error"),
                    )
                    return {}
                result = data.get("result") or {}
                return result if isinstance(result, dict) else {}
        except Exception as exc:
            logger.warning(
                "Error getting optional CRCON context: server=%s endpoint=%s "
                "error=%s",
                self.server_id,
                endpoint,
                exc,
            )
            return {}

    async def get_players(self) -> list:
        """Return current player display metadata, keyed by CRCON player_id."""
        data = await self._get_api_result("get_live_game_stats")
        stats = data.get("stats") or []
        return [
            {
                "name": stat.get("player"),
                "player_id": stat.get("player_id") or stat.get("steam_id_64"),
                "team": stat.get("team") or stat.get("side"),
            }
            for stat in stats
            if isinstance(stat, dict)
        ]

    @staticmethod
    def _map_value(current_map: object, *keys: str):
        if not isinstance(current_map, dict):
            return current_map if isinstance(current_map, str) else None

        map_metadata = current_map.get("map")
        sources = [map_metadata, current_map]
        for source in sources:
            if not isinstance(source, dict):
                continue
            for key in keys:
                value = source.get(key)
                if value not in (None, ""):
                    return value
        return None

    @staticmethod
    def _display_mode(game_state: dict, current_map: object) -> Optional[str]:
        mode = game_state.get("game_mode") or game_state.get("mode")
        if not mode and isinstance(current_map, dict):
            mode = current_map.get("game_mode") or current_map.get("mode")

        layer_id = None
        if isinstance(current_map, dict):
            layer_id = current_map.get("id") or current_map.get("layer")
        if not mode and layer_id:
            layer_name = str(layer_id).lower()
            for known_mode in ("warfare", "offensive", "skirmish", "control"):
                if known_mode in layer_name:
                    mode = known_mode
                    break

        if mode in (None, ""):
            return None
        clean_mode = str(mode).rsplit(".", 1)[-1].replace("_", " ").strip()
        return clean_mode.title()

    @staticmethod
    def _display_time_remaining(game_state: dict) -> Optional[str]:
        value = game_state.get("raw_time_remaining")
        if value in (None, ""):
            value = game_state.get("time_remaining")
        if value in (None, ""):
            return None

        if isinstance(value, (int, float)) or str(value).strip().isdigit():
            seconds = max(0, int(float(value)))
            hours, remainder = divmod(seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

        clean_value = str(value).strip()
        if " day" in clean_value:
            clean_value = clean_value.rsplit(", ", 1)[-1]
        return clean_value

    @classmethod
    def _build_ticket_context(
        cls, live_stats: dict, game_state: dict, player_id: str
    ) -> dict:
        """Normalize CRCON's changing response shapes for the Discord card."""
        stats = live_stats.get("stats") or []
        player = next(
            (
                stat
                for stat in stats
                if isinstance(stat, dict)
                and str(stat.get("player_id") or stat.get("steam_id_64") or "")
                == str(player_id)
            ),
            {},
        )

        current_map = game_state.get("current_map")
        map_name = cls._map_value(
            current_map, "pretty_name", "human_name", "shortname", "name", "id"
        )

        map_metadata = (
            current_map.get("map", {})
            if isinstance(current_map, dict)
            else {}
        )
        allied_faction = (
            map_metadata.get("allies", {}).get("name")
            if isinstance(map_metadata, dict)
            and isinstance(map_metadata.get("allies"), dict)
            else None
        )
        axis_faction = (
            map_metadata.get("axis", {}).get("name")
            if isinstance(map_metadata, dict)
            and isinstance(map_metadata.get("axis"), dict)
            else None
        )

        raw_team = player.get("team") or player.get("side")
        team = raw_team
        normalized_team = str(raw_team or "").lower()
        if normalized_team in ("allies", "allied") and allied_faction:
            team = allied_faction
        elif normalized_team == "axis" and axis_faction:
            team = axis_faction

        allied_score = game_state.get("allied_score")
        axis_score = game_state.get("axis_score")
        score = None
        if allied_score is not None and axis_score is not None:
            allied_label = str(allied_faction or "Alliés").upper()
            axis_label = str(axis_faction or "Axe").upper()
            score = f"{allied_label} {allied_score} | {axis_label} {axis_score}"

        return {
            "team": str(team).upper() if team not in (None, "") else None,
            "map": str(map_name) if map_name not in (None, "") else None,
            "mode": cls._display_mode(game_state, current_map),
            "score": score,
            "time_remaining": cls._display_time_remaining(game_state),
        }

    async def get_ticket_context(self, player_id: str) -> dict:
        """Fetch and normalize the live details useful to an admin responder."""
        live_stats, game_state = await asyncio.gather(
            self._get_api_result("get_live_game_stats"),
            self._get_api_result("get_gamestate"),
        )
        return self._build_ticket_context(live_stats, game_state, player_id)

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
    def _clean_message(
        message: str, player_name: Optional[str] = None, player_id: Optional[str] = None
    ) -> str:
        if not message:
            return ""
        cleaned = " ".join(str(message).split())

        # Raw CRCON fallback lines can duplicate data already shown in the
        # ticket fields: ``Player: @admin report (player_id)``.
        if player_name:
            prefix_pattern = (
                rf"^.*?{re.escape(str(player_name))}"
                rf"(?:\([^)]*\))?\s*:\s*"
            )
            cleaned = re.sub(prefix_pattern, "", cleaned, count=1)
        if player_id:
            cleaned = re.sub(
                rf"\s*\(\s*{re.escape(str(player_id))}\s*\)\s*$",
                "",
                cleaned,
            )

        # Keep backward compatibility for older Steam-only raw strings.
        return re.sub(r"\s*\(76561\d+\)\s*$", "", cleaned).strip()

    @staticmethod
    def _extract_admin_report(message: str) -> Optional[str]:
        """Return only the report text following an admin ping trigger."""
        trigger = re.search(
            r"(?:^|\s)[!@/]?admin(?:istrateur)?\b\s*[:,-]?\s*",
            message,
            flags=re.IGNORECASE,
        )
        if trigger is None:
            return None
        return message[trigger.end() :].strip()

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

        full_message = self._clean_message(content, player_name, player_id)
        if player_id in self.active_threads:
            # Keep the latest display name in case it changed during a ticket.
            self.active_threads[player_id]["player_name"] = player_name
            if self.player_response_callback:
                await self.player_response_callback(
                    player_id, player_name, full_message, event_time
                )
            return

        admin_report = self._extract_admin_report(full_message)
        if admin_report is not None:
            self.closed_tickets.pop(player_id, None)
            if self.message_callback:
                await self.message_callback(
                    player_id,
                    player_name,
                    admin_report,
                    full_message,
                )

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
