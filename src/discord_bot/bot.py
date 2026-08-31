import asyncio
import logging
from datetime import datetime, timedelta, timezone
from functools import partial
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands


logger = logging.getLogger(__name__)
TicketKey = Tuple[str, str]  # (server_id, player_id)
PARIS_TIMEZONE = ZoneInfo("Europe/Paris")
DISPLAY_DATETIME_FORMAT = "%Y-%m-%d %H:%M"
DEFAULT_REPORT_TEXT = "Demande d'assistance administrateur"
EMPTY_REPORT_TEXT = "Aucun détail fourni après la commande admin"


def summarize_report_text(value: str, limit: int) -> str:
    """Return a single-line Discord-safe summary with a predictable length."""
    text = " ".join(str(value or DEFAULT_REPORT_TEXT).split())
    text = text.replace("@", "@\u200b")
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1].rstrip()}…"


def build_ticket_thread_name(
    date_time: str, player_name: str, report_text: str, limit: int = 100
) -> str:
    """Keep the previous ticket title while appending the useful report text."""
    prefix = f"{date_time} - {player_name} - "
    remaining = max(1, limit - len(prefix))
    return f"{prefix}{summarize_report_text(report_text, remaining)}"[:limit]


def format_embed_value(value: object) -> str:
    """Format extracted metadata like the compact values in the reference card."""
    text = " ".join(str(value or "Non disponible").split())
    text = text.replace("`", "'").replace("@", "@\u200b")
    return f"`{text[:1000]}`"


def format_paris_datetime(value) -> str:
    """Format a UTC datetime value for Discord in Paris local time."""
    parsed_value = value

    if isinstance(value, str):
        stripped_value = value.strip()
        try:
            parsed_value = datetime.fromisoformat(
                stripped_value.replace("Z", "+00:00")
            )
        except ValueError:
            return value
    elif isinstance(value, (int, float)):
        parsed_value = datetime.fromtimestamp(value, tz=timezone.utc)

    if not isinstance(parsed_value, datetime):
        return str(value)
    if parsed_value.tzinfo is None:
        # CRCON currently serializes its UTC event_time without an offset.
        parsed_value = parsed_value.replace(tzinfo=timezone.utc)

    return parsed_value.astimezone(PARIS_TIMEZONE).strftime(
        DISPLAY_DATETIME_FORMAT
    )


class CloseTicketView(discord.ui.View):
    def __init__(self, ticket_key: TicketKey, discord_bot):
        super().__init__(timeout=None)
        self.ticket_key = ticket_key
        self.discord_bot = discord_bot

    @discord.ui.button(
        label="Fermer le ticket",
        style=discord.ButtonStyle.danger,
        emoji="🔒",
        custom_id="close_ticket_button",
    )
    async def close_ticket(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self.discord_bot.close_ticket_from_interaction(
            self.ticket_key, interaction, self
        )


class ClaimTicketView(discord.ui.View):
    def __init__(self, ticket_key: TicketKey, discord_bot):
        super().__init__(timeout=None)
        self.ticket_key = ticket_key
        self.discord_bot = discord_bot

    @discord.ui.button(
        label="Prendre le ticket",
        style=discord.ButtonStyle.primary,
        custom_id="claim_ticket_button",
    )
    async def claim_ticket(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self.discord_bot.claim_ticket_from_interaction(
            self.ticket_key, interaction
        )

    @discord.ui.button(
        label="Fermer le ticket",
        style=discord.ButtonStyle.danger,
        emoji="🔒",
        custom_id="close_ticket_button",
    )
    async def close_ticket(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self.discord_bot.close_ticket_from_interaction(
            self.ticket_key, interaction, self
        )


class DiscordBot:
    """Discord side of the multi-server ticket router."""

    STATUS_TAGS = ("NEW", "REPLIED", "OUTAGE", "CLOSED")

    def __init__(self, config, crcon_clients):
        self.config = config
        self.servers = {server["id"]: server for server in config.get_servers()}

        if isinstance(crcon_clients, dict):
            self.crcon_clients = crcon_clients
        else:
            self.crcon_clients = {crcon_clients.server_id: crcon_clients}

        missing_clients = set(self.servers) - set(self.crcon_clients)
        if missing_clients:
            raise ValueError(
                f"Missing CRCON clients for server(s): {', '.join(sorted(missing_clients))}"
            )

        self.active_threads: Dict[TicketKey, discord.Thread] = {}
        self.thread_tickets: Dict[int, TicketKey] = {}
        self.active_button_messages: Dict[TicketKey, discord.Message] = {}
        self.player_tickets: Dict[TicketKey, bool] = {}
        self.player_names: Dict[TicketKey, str] = {}
        self.claimed_by: Dict[TicketKey, str] = {}
        self.status_messages: Dict[TicketKey, List[int]] = {}
        self.current_status_message: Dict[TicketKey, int] = {}
        self.last_activity: Dict[TicketKey, datetime] = {}
        self.outage_threads: Dict[str, discord.Thread] = {}
        self.forum_tags: Dict[str, Dict[str, Optional[discord.ForumTag]]] = {
            server_id: {tag: None for tag in self.STATUS_TAGS}
            for server_id in self.servers
        }
        self.health_event_queue: asyncio.Queue = asyncio.Queue()
        self.health_event_task: Optional[asyncio.Task] = None

        self.auto_close_minutes = int(
            self.config.get("tickets.auto_close_minutes", 90)
        )
        self.inactivity_check_interval = int(
            self.config.get("tickets.inactivity_check_interval_seconds", 60)
        )
        self.inactivity_task: Optional[asyncio.Task] = None

        intents = discord.Intents.default()
        intents.message_content = True
        self.bot = commands.Bot(command_prefix="!", intents=intents)
        self.setup_events()

        for server_id, client in self.crcon_clients.items():
            client.set_message_callback(partial(self.handle_admin_request, server_id))
            client.set_player_response_callback(
                partial(self.handle_player_response, server_id)
            )
            client.set_health_callback(partial(self.queue_health_event, server_id))

        logger.info(
            "Discord bot initialized for servers: %s", ", ".join(self.servers)
        )

    def get_client(self, server_id: str):
        return self.crcon_clients[server_id]

    def get_server(self, server_id: str) -> dict:
        return self.servers[server_id]

    def get_player_name(self, ticket_key: TicketKey) -> str:
        return self.player_names.get(ticket_key, "Joueur inconnu")

    def get_admin_mentions(self, server_id: str) -> str:
        roles = self.get_server(server_id)["discord"].get("admin_roles", [])
        return " ".join(f"<@&{role_id}>" for role_id in roles)

    def get_outage_mentions(self, server_id: str) -> str:
        user_ids = self.get_server(server_id)["discord"].get(
            "outage_user_ids", []
        )
        return " ".join(f"<@{user_id}>" for user_id in user_ids)

    async def queue_health_event(self, server_id: str, event: dict):
        """Queue health transitions so CRCON monitoring never waits on Discord."""
        queued_event = dict(event)
        queued_event["server_id"] = server_id
        await self.health_event_queue.put(queued_event)

    @staticmethod
    def _safe_health_text(value, limit: int = 1024) -> str:
        text = str(value or "Non renseigné").strip()
        # Diagnostic data must never be able to generate an unexpected mention.
        text = text.replace("@", "@\u200b")
        if len(text) > limit:
            return f"{text[: limit - 1]}…"
        return text

    @staticmethod
    def _format_duration(total_seconds: int) -> str:
        seconds = max(0, int(total_seconds))
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            return f"{hours} h {minutes} min {seconds} s"
        if minutes:
            return f"{minutes} min {seconds} s"
        return f"{seconds} s"

    async def monitor_health_events(self):
        """Deliver queued incidents in order and retry across Discord outages."""
        while not self.bot.is_closed():
            try:
                event = await self.health_event_queue.get()
            except asyncio.CancelledError:
                break

            try:
                delivered = False
                while not delivered and not self.bot.is_closed():
                    await self.bot.wait_until_ready()
                    try:
                        delivered = await self.deliver_health_event(event)
                    except asyncio.CancelledError:
                        raise
                    except discord.HTTPException as exc:
                        logger.error(
                            "Discord outage alert delivery failed: server=%s error=%s",
                            event.get("server_id"),
                            exc,
                        )
                    except Exception as exc:
                        logger.exception(
                            "Unexpected outage alert error: server=%s error=%s",
                            event.get("server_id"),
                            exc,
                        )
                    if not delivered and not self.bot.is_closed():
                        await asyncio.sleep(30)
            except asyncio.CancelledError:
                break
            finally:
                self.health_event_queue.task_done()

    async def deliver_health_event(self, event: dict) -> bool:
        server_id = event["server_id"]
        status = event.get("status")
        thread = self.outage_threads.get(server_id)
        existing_incident = thread is not None

        if status in ("outage", "update"):
            if thread is None:
                channel = await self._get_forum(server_id)
                if channel is None:
                    return False

                occurred_at = event.get("occurred_at") or discord.utils.utcnow()
                date_time = format_paris_datetime(occurred_at)
                server_name = self.get_server(server_id)["name"]
                mentions = self.get_outage_mentions(server_id)
                content = "🚨 **PANNE DU RESPONDER ADMIN** 🚨"
                if mentions:
                    content = f"{content}\n{mentions}"
                outage_tag = self.forum_tags[server_id].get("OUTAGE")
                fallback_tag = self.forum_tags[server_id].get("NEW")
                tag = outage_tag or fallback_tag
                thread, _ = await channel.create_thread(
                    name=f"OUTAGE - {date_time} - {server_name}"[:100],
                    content=content,
                    applied_tags=[tag] if tag else [],
                )
                self.outage_threads[server_id] = thread

            embed = discord.Embed(
                title=(
                    "🚨 Panne de surveillance détectée"
                    if status == "outage" and not existing_incident
                    else "⚠️ Mise à jour de la panne"
                ),
                description=(
                    "Le responder ne peut plus garantir la réception des demandes "
                    "`!admin` pour ce serveur."
                ),
                color=(
                    discord.Color.red()
                    if status == "outage"
                    else discord.Color.orange()
                ),
                timestamp=event.get("occurred_at") or discord.utils.utcnow(),
            )
            embed.add_field(
                name="🎮 Serveur",
                value=self._safe_health_text(self.get_server(server_id)["name"]),
            )
            embed.add_field(
                name="🧩 Composant",
                value=self._safe_health_text(event.get("component")),
            )
            embed.add_field(
                name="🕐 Détectée (Paris)",
                value=format_paris_datetime(event.get("started_at")),
            )
            embed.add_field(
                name="Résumé",
                value=self._safe_health_text(event.get("summary")),
                inline=False,
            )
            embed.add_field(
                name="Détails techniques",
                value=f"```\n{self._safe_health_text(event.get('detail'), 980)}\n```",
                inline=False,
            )
            embed.add_field(
                name="Endpoint",
                value=self._safe_health_text(event.get("endpoint")),
                inline=False,
            )
            await thread.send(embed=embed)
            logger.warning(
                "Outage ticket delivered: server=%s status=%s thread_id=%s",
                server_id,
                status,
                thread.id,
            )
            return True

        if status in ("recovered", "healthy"):
            if thread is None:
                return True

            occurred_at = event.get("occurred_at") or discord.utils.utcnow()
            started_at = event.get("started_at") or thread.created_at
            duration_seconds = event.get("duration_seconds", 0)
            if status == "healthy" and started_at:
                duration_seconds = max(
                    0, int((occurred_at - started_at).total_seconds())
                )
            embed = discord.Embed(
                title="✅ Surveillance rétablie",
                description=(
                    "Le flux CRCON a renvoyé des données valides. La réception des "
                    "demandes `!admin` est de nouveau opérationnelle."
                ),
                color=discord.Color.green(),
                timestamp=occurred_at,
            )
            embed.add_field(
                name="🎮 Serveur",
                value=self._safe_health_text(self.get_server(server_id)["name"]),
            )
            embed.add_field(
                name="Durée de la panne",
                value=self._format_duration(duration_seconds),
            )
            embed.add_field(
                name="Erreurs observées",
                value=str(event.get("failure_count", 0)),
            )
            await thread.send(embed=embed)
            await self.apply_forum_tag(server_id, thread, "CLOSED")
            await thread.edit(archived=True, locked=True)
            self.outage_threads.pop(server_id, None)
            logger.info(
                "Outage ticket closed after recovery: server=%s thread_id=%s",
                server_id,
                thread.id,
            )
            return True

        logger.error(
            "Unknown health event status: server=%s status=%s", server_id, status
        )
        return True

    async def _get_forum(self, server_id: str) -> Optional[discord.ForumChannel]:
        channel_id = int(
            self.get_server(server_id)["discord"]["admin_channel_id"]
        )
        channel = self.bot.get_channel(channel_id)
        if channel is None and self.bot.is_ready():
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                channel = None

        if channel is None:
            logger.error(
                "Discord forum not found: server=%s channel_id=%s",
                server_id,
                channel_id,
            )
            return None
        if not isinstance(channel, discord.ForumChannel):
            logger.error(
                "Configured Discord channel is not a forum: server=%s channel_id=%s type=%s",
                server_id,
                channel_id,
                type(channel).__name__,
            )
            return None
        return channel

    def setup_events(self):
        @self.bot.event
        async def on_ready():
            logger.info("%s connected to Discord", self.bot.user)
            await self.setup_forum_tags()
            if not self.inactivity_task or self.inactivity_task.done():
                self.inactivity_task = asyncio.create_task(
                    self.monitor_ticket_inactivity()
                )
            if not self.health_event_task or self.health_event_task.done():
                self.health_event_task = asyncio.create_task(
                    self.monitor_health_events(), name="discord-health-alerts"
                )

        @self.bot.event
        async def on_message(message):
            if message.author == self.bot.user:
                return
            if isinstance(message.channel, discord.Thread):
                await self.handle_thread_message(message)
            await self.bot.process_commands(message)

        @self.bot.command(name="cleanup_tickets")
        @commands.has_permissions(administrator=True)
        async def cleanup_tickets(ctx):
            removed = 0
            for ticket_key, thread in list(self.active_threads.items()):
                try:
                    await self.bot.fetch_channel(thread.id)
                except (discord.NotFound, discord.Forbidden):
                    self._remove_ticket_state(ticket_key)
                    self.get_client(ticket_key[0]).unregister_admin_thread(
                        ticket_key[1]
                    )
                    removed += 1
                except discord.HTTPException:
                    continue
            await ctx.send(f"{removed} ticket(s) supprimé(s) du suivi.")

    async def setup_forum_tags(self):
        for server_id in self.servers:
            channel = await self._get_forum(server_id)
            if not channel:
                continue

            existing_tags = {tag.name.upper(): tag for tag in channel.available_tags}
            for tag_name in self.STATUS_TAGS:
                tag = existing_tags.get(tag_name)
                if tag is None:
                    try:
                        tag = await channel.create_tag(name=tag_name, moderated=False)
                        logger.info(
                            "Created forum tag: server=%s tag=%s",
                            server_id,
                            tag_name,
                        )
                    except discord.HTTPException as exc:
                        logger.error(
                            "Failed to create forum tag: server=%s tag=%s error=%s",
                            server_id,
                            tag_name,
                            exc,
                        )
                self.forum_tags[server_id][tag_name] = tag

            logger.info(
                "Discord forum ready: server=%s forum=%s channel_id=%s",
                server_id,
                channel.name,
                channel.id,
            )
            if server_id not in self.outage_threads:
                outage_tag = self.forum_tags[server_id].get("OUTAGE")
                active_incidents = [
                    thread
                    for thread in channel.threads
                    if not thread.archived
                    and (
                        thread.name.startswith("OUTAGE - ")
                        or (
                            outage_tag is not None
                            and any(
                                tag.id == outage_tag.id
                                for tag in thread.applied_tags
                            )
                        )
                    )
                ]
                if active_incidents:
                    incident = max(
                        active_incidents,
                        key=lambda thread: thread.created_at,
                    )
                    self.outage_threads[server_id] = incident
                    logger.info(
                        "Reusing active outage ticket: server=%s thread_id=%s",
                        server_id,
                        incident.id,
                    )

    async def apply_forum_tag(
        self, server_id: str, thread: discord.Thread, tag_name: str
    ):
        tag = self.forum_tags.get(server_id, {}).get(tag_name)
        if tag is None:
            logger.warning(
                "Forum tag unavailable: server=%s tag=%s", server_id, tag_name
            )
            return

        non_status_tags = [
            current
            for current in thread.applied_tags
            if current.name.upper() not in self.STATUS_TAGS
        ]
        await thread.edit(applied_tags=non_status_tags + [tag])

    async def claim_ticket_from_interaction(
        self, ticket_key: TicketKey, interaction: discord.Interaction
    ):
        player_name = self.get_player_name(ticket_key)
        claimer = interaction.user.display_name
        try:
            self.claimed_by[ticket_key] = claimer
            self.last_activity[ticket_key] = datetime.utcnow()
            embed = discord.Embed(
                title="🎛️ Statut du ticket",
                description=(
                    f"Ticket de **{player_name}** — pris en charge par **{claimer}**"
                ),
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow(),
            )
            await interaction.response.edit_message(
                embed=embed, view=CloseTicketView(ticket_key, self)
            )
            self.active_button_messages[ticket_key] = interaction.message
            self.current_status_message[ticket_key] = interaction.message.id
            self.status_messages[ticket_key] = [interaction.message.id]

            server_id, player_id = ticket_key
            sent = await self.get_client(server_id).send_message_to_player(
                player_id,
                player_name,
                "Un modérateur s'occupe maintenant de votre demande.",
            )
            if not sent:
                logger.warning(
                    "Could not notify player of claim: server=%s player_id=%s",
                    server_id,
                    player_id,
                )
        except Exception as exc:
            logger.error("Error claiming ticket %s: %s", ticket_key, exc)
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "Impossible de prendre ce ticket.", ephemeral=True
                )

    async def close_ticket_from_interaction(
        self,
        ticket_key: TicketKey,
        interaction: discord.Interaction,
        view: discord.ui.View,
    ):
        player_name = self.get_player_name(ticket_key)
        thread = (
            interaction.message.channel
            if isinstance(interaction.message.channel, discord.Thread)
            else self.active_threads.get(ticket_key)
        )
        try:
            if thread:
                await self.apply_forum_tag(ticket_key[0], thread, "CLOSED")
            view.clear_items()
            embed = discord.Embed(
                title="🎛️ Statut du ticket",
                description=(
                    f"Le ticket de **{player_name}** est clôturé par "
                    f"**{interaction.user.display_name}**"
                ),
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow(),
            )
            await interaction.response.edit_message(embed=embed, view=None)
            await self.finalize_ticket_close(
                ticket_key,
                thread,
                notify_player_message=(
                    "Votre ticket admin a été fermé par un modérateur. Merci !"
                ),
                closed_by=interaction.user.display_name,
                closure_source="manual",
            )
        except Exception as exc:
            logger.error("Error closing ticket %s: %s", ticket_key, exc)
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "Impossible de fermer ce ticket.", ephemeral=True
                )

    def _remove_ticket_state(self, ticket_key: TicketKey):
        thread = self.active_threads.pop(ticket_key, None)
        if thread:
            self.thread_tickets.pop(thread.id, None)
        self.player_tickets.pop(ticket_key, None)
        self.player_names.pop(ticket_key, None)
        self.active_button_messages.pop(ticket_key, None)
        self.status_messages.pop(ticket_key, None)
        self.current_status_message.pop(ticket_key, None)
        self.claimed_by.pop(ticket_key, None)
        self.last_activity.pop(ticket_key, None)

    async def finalize_ticket_close(
        self,
        ticket_key: TicketKey,
        thread: Optional[discord.Thread],
        *,
        notify_player_message: Optional[str] = None,
        closed_by: Optional[str] = None,
        closure_source: str = "manual",
    ):
        server_id, player_id = ticket_key
        player_name = self.get_player_name(ticket_key)
        target_thread = thread or self.active_threads.get(ticket_key)
        client = self.get_client(server_id)

        if target_thread:
            try:
                await self.apply_forum_tag(server_id, target_thread, "CLOSED")
            except discord.HTTPException as exc:
                logger.error("Failed to apply CLOSED tag to %s: %s", ticket_key, exc)

        if notify_player_message:
            await client.send_message_to_player(
                player_id, player_name, notify_player_message
            )

        client.mark_ticket_closed(player_id)
        self._remove_ticket_state(ticket_key)

        if target_thread and isinstance(target_thread, discord.Thread):
            try:
                await target_thread.edit(archived=True, locked=True)
            except discord.HTTPException as exc:
                logger.error("Failed to archive ticket %s: %s", ticket_key, exc)

        logger.info(
            "Ticket closed: server=%s player_id=%s player=%s by=%s source=%s",
            server_id,
            player_id,
            player_name,
            closed_by,
            closure_source,
        )

    async def monitor_ticket_inactivity(self):
        await self.bot.wait_until_ready()
        inactivity_window = timedelta(minutes=self.auto_close_minutes)
        while not self.bot.is_closed():
            try:
                now = datetime.utcnow()
                for ticket_key in list(self.player_tickets):
                    last = self.last_activity.setdefault(ticket_key, now)
                    if now - last >= inactivity_window:
                        await self._close_ticket_for_inactivity(ticket_key)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Inactivity monitor error: %s", exc)
            await asyncio.sleep(self.inactivity_check_interval)

    async def _close_ticket_for_inactivity(self, ticket_key: TicketKey):
        thread = self.active_threads.get(ticket_key)
        if not thread:
            self._remove_ticket_state(ticket_key)
            return

        player_name = self.get_player_name(ticket_key)
        notice = discord.Embed(
            title="[AUTO] Ticket clos automatiquement",
            description=(
                f"Aucune activité depuis {self.auto_close_minutes} minutes. "
                "Utilisez `!admin` en jeu pour ouvrir un nouveau ticket."
            ),
            color=discord.Color.dark_grey(),
            timestamp=discord.utils.utcnow(),
        )
        try:
            await thread.send(embed=notice)
            status_message = self.active_button_messages.get(ticket_key)
            if status_message:
                status = discord.Embed(
                    title="🎛️ Statut du ticket",
                    description=(
                        f"Ticket de **{player_name}** fermé automatiquement pour inactivité."
                    ),
                    color=discord.Color.dark_grey(),
                    timestamp=discord.utils.utcnow(),
                )
                await status_message.edit(embed=status, view=None)
        except discord.HTTPException as exc:
            logger.error("Failed to update inactive ticket %s: %s", ticket_key, exc)

        await self.finalize_ticket_close(
            ticket_key,
            thread,
            notify_player_message=(
                f"Votre ticket admin a été fermé automatiquement après "
                f"{self.auto_close_minutes} minutes sans activité."
            ),
            closed_by="Fermeture automatique",
            closure_source="auto_inactivity",
        )

    async def handle_admin_request(
        self,
        server_id: str,
        player_id: str,
        player_name: str,
        admin_message: str,
        full_admin_message: Optional[str] = None,
    ):
        await self.bot.wait_until_ready()
        ticket_key = (server_id, player_id)
        self.player_names[ticket_key] = player_name
        client = self.get_client(server_id)

        if self.player_tickets.get(ticket_key):
            thread = self.active_threads.get(ticket_key)
            if thread and admin_message.strip():
                embed = discord.Embed(
                    title="💬 Message additionnel du joueur",
                    description=admin_message,
                    color=discord.Color.blue(),
                    timestamp=discord.utils.utcnow(),
                )
                embed.set_footer(text=f"Joueur : {player_name}")
                await thread.send(embed=embed)
                self.last_activity[ticket_key] = datetime.utcnow()
            await client.send_message_to_player(
                player_id,
                player_name,
                "Vous avez déjà un ticket admin actif. Écrivez simplement dans le chat pour le compléter.",
            )
            return

        channel = await self._get_forum(server_id)
        if not channel:
            return

        now = datetime.now(PARIS_TIMEZONE)
        date_time = format_paris_datetime(now)
        extracted_report_text = admin_message.strip()
        full_message_text = (
            str(full_admin_message).strip()
            if full_admin_message is not None
            else extracted_report_text
        )
        report_text = extracted_report_text or EMPTY_REPORT_TEXT
        title_text = (
            extracted_report_text
            or full_message_text
            or DEFAULT_REPORT_TEXT
        )
        thread_name = build_ticket_thread_name(
            date_time, player_name, title_text
        )
        mentions = self.get_admin_mentions(server_id)
        content = "🚨 **Nouveau ping MODO** 🚨"
        if mentions:
            content = f"{content}\n{mentions}"

        new_tag = self.forum_tags[server_id].get("NEW")
        thread, _ = await channel.create_thread(
            name=thread_name,
            content=content,
            applied_tags=[new_tag] if new_tag else [],
        )

        self.player_tickets[ticket_key] = True
        self.active_threads[ticket_key] = thread
        self.thread_tickets[thread.id] = ticket_key
        self.last_activity[ticket_key] = datetime.utcnow()
        client.register_admin_thread(
            player_id,
            {
                "thread_id": thread.id,
                "player_id": player_id,
                "player_name": player_name,
            },
        )

        game_context = await client.get_ticket_context(player_id)
        embed = discord.Embed(
            title=(
                "🚨 Ping MODO — "
                f"{summarize_report_text(title_text, 220)}"
            )[:256],
            color=discord.Color.red(),
            timestamp=now,
        )
        embed.add_field(
            name="📝 Texte du signalement",
            value=summarize_report_text(report_text, 1024),
            inline=False,
        )
        extracted_fields = (
            ("🎮 Jeu / serveur", self.get_server(server_id)["name"]),
            ("👤 Nom du plaignant", player_name),
            ("🆔 Player ID", player_id),
            ("⚑ Équipe actuelle", game_context.get("team")),
            ("🗺️ Carte actuelle", game_context.get("map")),
            ("⚔️ Mode de jeu", game_context.get("mode")),
            ("⚖️ Score / objectifs", game_context.get("score")),
            ("⏱️ Temps restant", game_context.get("time_remaining")),
            ("🕐 Heure de Paris", date_time),
            (
                "💬 Message complet reçu",
                full_message_text or DEFAULT_REPORT_TEXT,
            ),
        )
        for field_name, field_value in extracted_fields:
            embed.add_field(
                name=field_name,
                value=format_embed_value(field_value),
                inline=False,
            )
        await thread.send(embed=embed)

        controls = discord.Embed(
            title="🎛️ Statut du ticket",
            description=f"Ticket de **{player_name}** — en attente",
            color=discord.Color.blue(),
            timestamp=now,
        )
        button_message = await thread.send(
            embed=controls, view=ClaimTicketView(ticket_key, self)
        )
        self.active_button_messages[ticket_key] = button_message
        self.current_status_message[ticket_key] = button_message.id
        self.status_messages[ticket_key] = [button_message.id]

        await client.send_message_to_player(
            player_id,
            player_name,
            "Votre ticket admin a bien été reçu ! Écrivez simplement dans le chat pour répondre.",
        )
        logger.info(
            "Ticket created: server=%s player_id=%s player=%s thread_id=%s",
            server_id,
            player_id,
            player_name,
            thread.id,
        )

    async def handle_player_response(
        self,
        server_id: str,
        player_id: str,
        player_name: str,
        message: str,
        event_time: str,
    ):
        ticket_key = (server_id, player_id)
        self.player_names[ticket_key] = player_name
        thread = self.active_threads.get(ticket_key)
        if not thread:
            await self.handle_admin_request(
                server_id, player_id, player_name, message
            )
            return

        try:
            await self.apply_forum_tag(server_id, thread, "NEW")
            response = discord.Embed(
                title=f"💬 Réponse de {player_name}",
                description=message,
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow(),
            )
            if event_time:
                response.set_footer(
                    text=f"Heure de Paris : {format_paris_datetime(event_time)}"
                )
            await thread.send(embed=response)

            claimer = self.claimed_by.get(ticket_key)
            description = f"Ticket de **{player_name}** — en attente"
            view = ClaimTicketView(ticket_key, self)
            if claimer:
                description = (
                    f"Ticket de **{player_name}** — pris en charge par **{claimer}**"
                )
                view = CloseTicketView(ticket_key, self)
            controls = discord.Embed(
                title="🎛️ Statut du ticket",
                description=description,
                color=discord.Color.blue(),
            )

            status_message = self.active_button_messages.get(ticket_key)
            if status_message:
                try:
                    await status_message.edit(embed=controls, view=view)
                except discord.HTTPException:
                    status_message = None
            if status_message is None:
                status_message = await thread.send(embed=controls, view=view)
                self.active_button_messages[ticket_key] = status_message
                self.current_status_message[ticket_key] = status_message.id
                self.status_messages[ticket_key] = [status_message.id]
            self.last_activity[ticket_key] = datetime.utcnow()
        except (discord.NotFound, discord.Forbidden):
            self._remove_ticket_state(ticket_key)
            self.get_client(server_id).unregister_admin_thread(player_id)
            await self.handle_admin_request(
                server_id, player_id, player_name, message
            )

    async def handle_thread_message(self, message: discord.Message):
        if message.author == self.bot.user:
            return
        if message.type != discord.MessageType.default or message.embeds:
            return
        if not message.content.strip():
            return

        ticket_key = self.thread_tickets.get(message.channel.id)
        if not ticket_key:
            return

        server_id, player_id = ticket_key
        player_name = self.get_player_name(ticket_key)
        sent = await self.get_client(server_id).send_message_to_player(
            player_id, player_name, f"[ADMIN]: {message.content}"
        )
        if not sent:
            await message.add_reaction("❌")
            return

        await self.apply_forum_tag(server_id, message.channel, "REPLIED")
        await message.add_reaction("✅")
        self.last_activity[ticket_key] = datetime.utcnow()

        if ticket_key not in self.claimed_by:
            claimer = message.author.display_name
            self.claimed_by[ticket_key] = claimer
            controls = discord.Embed(
                title="🎛️ Statut du ticket",
                description=(
                    f"Ticket de **{player_name}** — pris en charge par **{claimer}**"
                ),
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow(),
            )
            status_message = self.active_button_messages.get(ticket_key)
            if status_message:
                try:
                    await status_message.edit(
                        embed=controls, view=CloseTicketView(ticket_key, self)
                    )
                except discord.HTTPException:
                    status_message = None
            if status_message is None:
                status_message = await message.channel.send(
                    embed=controls, view=CloseTicketView(ticket_key, self)
                )
                self.active_button_messages[ticket_key] = status_message
                self.current_status_message[ticket_key] = status_message.id
                self.status_messages[ticket_key] = [status_message.id]

    async def start(self):
        token = self.config.get("discord.token")
        if not token:
            raise ValueError("Discord token not found in configuration")
        await self.bot.start(token)

    async def close(self):
        if self.inactivity_task:
            self.inactivity_task.cancel()
        if self.health_event_task:
            self.health_event_task.cancel()
        if not self.bot.is_closed():
            await self.bot.close()
