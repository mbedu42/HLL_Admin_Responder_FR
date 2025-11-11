import aiohttp
import asyncio
import logging
from typing import Optional, Callable, Set, Dict
import json
from datetime import datetime, timedelta
import re
import discord
from discord.ext import commands

logger = logging.getLogger(__name__)

class CRCONClient:
    def __init__(self, config):
        self.config = config
        self.base_url = config.get('crcon.base_url')
        self.api_token = config.get('crcon.api_token')
        self.session = None
        self.monitoring = False
        self.message_callback: Optional[Callable] = None
        self.player_response_callback: Optional[Callable] = None
        self.processed_log_ids: Set[int] = set()
        self.headers = {"Authorization": f"Bearer {self.api_token}"}
        
        # Track active admin threads - player_name -> thread info
        self.active_threads: Dict[str, dict] = {}
        
        # WebSocket stream cursor/dedupe
        self.ws_last_seen_id: Optional[str] = None
        self.ws_seen_ids: Set[str] = set()
        
        logger.info(f"CRCON Config - URL: {self.base_url}")
        
        # WS-only mode: we do not poll HTTP logs anymore
        self.use_websocket_stream = True
    
    async def create_session(self):
        """Create HTTP session"""
        if not self.session:
            self.session = aiohttp.ClientSession(headers=self.headers)
    
    async def close_session(self):
        """Close HTTP session"""
        if self.session:
            await self.session.close()
            self.session = None
    
    async def test_connection(self) -> bool:
        """Test API connection"""
        try:
            await self.create_session()
            url = f'{self.base_url}/api/get_status'
            
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"Connected to CRCON API: {data.get('result', {}).get('name', 'Unknown')}")
                    return True
                else:
                    logger.error(f"API connection failed with status: {response.status}")
                    return False
        except Exception as e:
            logger.error(f"Failed to connect to CRCON API: {e}")
            return False
    
    async def initialize_log_tracking(self):
        """Polling disabled. WS-only mode."""
        logger.info("initialize_log_tracking called but polling is disabled (WS-only mode)")
    
    def register_admin_thread(self, player_name: str, thread_info: dict):
        """Register an active admin thread for a player"""
        self.active_threads[player_name] = thread_info
        print(f" CRCON: Registered admin thread for {player_name}")
        print(f" CRCON: Currently tracking {len(self.active_threads)} players: {list(self.active_threads.keys())}")
    
    def unregister_admin_thread(self, player_name: str):
        """Remove an admin thread when it's closed"""
        if player_name in self.active_threads:
            del self.active_threads[player_name]
            print(f" CRCON: Unregistered admin thread for {player_name}")
            print(f" CRCON: Now tracking {len(self.active_threads)} players: {list(self.active_threads.keys())}")
        else:
            print(f" CRCON: Tried to unregister {player_name} but they weren't tracked")
    
    async def send_message_to_player(self, player_name: str, message: str):
        """Send message to player via API"""
        try:
            await self.create_session()
            
            # First get player info to get player_id
            players = await self.get_players()
            player_id = None
            
            for player in players:
                if player.get('name') == player_name:
                    player_id = player.get('player_id') or player.get('steam_id_64')
                    break
            
            if not player_id:
                logger.warning(f"Player not found: {player_name}")
                return False
            
            # Use the correct endpoint: message_player
            url = f'{self.base_url}/api/message_player'
            data = {
                "player_name": player_name,
                "player_id": player_id,
                "message": message,
                "by": "Discord Admin"
            }
            
            print(f"Sending POST to: {url}")
            print(f"Data: {data}")
            
            async with self.session.post(url, json=data) as response:
                response_text = await response.text()
                print(f"Response status: {response.status}")
                print(f"Response: {response_text[:200]}...")
                
                if response.status == 200:
                    logger.info(f"Sent message to {player_name}: {message}")
                    return True
                else:
                    logger.error(f"Failed to send message, status: {response.status}, response: {response_text}")
                    return False
                    
        except Exception as e:
            logger.error(f"Error sending message to {player_name}: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def get_players(self) -> list:
        """Get current players from live game stats"""
        try:
            await self.create_session()
            url = f'{self.base_url}/api/get_live_game_stats'
            
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    stats = data.get('result', {}).get('stats', [])
                    
                    players = []
                    for stat in stats:
                        players.append({
                            'name': stat.get('player'),
                            'player_id': stat.get('player_id'),
                            'steam_id_64': stat.get('player_id'),
                            'team': stat.get('side'),
                        })
                    
                    return players
                else:
                    logger.error(f"Failed to get players, status: {response.status}")
                    return []
        except Exception as e:
            logger.error(f"Error getting players: {e}")
            return []
    
    async def get_new_logs(self) -> list:
        """Polling disabled. WS-only mode."""
        logger.info("get_new_logs called but polling is disabled (WS-only mode)")
        return []
    
    async def check_for_admin_requests(self):
        """Check for !admin requests AND player responses in threads"""
        try:
            logs = await self.get_new_logs()
            
            if not logs:
                return
            
            for log_entry in logs:
                try:
                    player_name = log_entry.get('player1_name')
                    content = log_entry.get('content', '') or log_entry.get('raw', '')
                    log_id = log_entry.get('id')
                    event_time = log_entry.get('event_time')
                    
                    # Skip if we've already processed this exact log entry
                    if log_id and (log_id in self.processed_log_ids):
                        continue
                    # Mark as processed now
                    if log_id:
                        self.processed_log_ids.add(log_id)

                    # If player already has an active ticket, always forward full message as response
                    if (player_name and content and (player_name in self.active_threads)):
                        # Clean trailing SteamID but keep full message
                        full_msg = re.sub(r'\(76561\d+\)', '', content).strip()
                        if self.player_response_callback:
                            try:
                                await self.player_response_callback(player_name, full_msg, event_time)
                                print(f" Player response sent to Discord thread!")
                            except Exception as callback_error:
                                print(f" Failed to send player response to Discord: {callback_error}")
                        # Skip admin-request handling for this log entry
                        continue
                    
                    # Check if this is an !admin request
                    if player_name and content and 'admin' in content.lower():
                        print(f"🚨 ADMIN REQUEST: {player_name} - {content}")                        
                        # Extract admin message
                        admin_message = ""
                        if 'admin' in content.lower():
                            parts = content.lower().split('admin')
                            if len(parts) > 1:
                                after_admin = parts[1].strip()
                                after_admin = re.sub(r'\(76561\d+\)', '', after_admin).strip()
                                admin_message = after_admin
                        
                        if not admin_message:
                            admin_message = "Player requested admin assistance"
                        
                        if self.message_callback:
                            try:
                                await self.message_callback(player_name, admin_message)
                                print(f" Admin request sent to Discord!")
                            except Exception as callback_error:
                                print(f" Failed to send admin request to Discord: {callback_error}")
                    
                    # Check if this is a response from a player with an active thread
                    # FIXED: Check both CRCON tracking AND Discord bot tracking
                    elif (player_name and content and 
                          (player_name in self.active_threads) and  # CRCON tracking
                          not content.lower().startswith('admin')):
                        
                        print(f" PLAYER RESPONSE (tracked): {player_name} - {content}")
                        
                        if self.player_response_callback:
                            try:
                                await self.player_response_callback(player_name, content, event_time)
                                print(f" Player response sent to Discord thread!")
                            except Exception as callback_error:
                                print(f" Failed to send player response to Discord: {callback_error}")
                    # If player is not being tracked, just log it but don't send to Discord
                    elif player_name and content and not content.lower().startswith('admin'):
                        print(f"💬 Regular chat (not tracked): {player_name} - {content}")

                except Exception as e:
                    logger.error(f"Error processing log entry: {e}")
                    continue
                        
        except Exception as e:
            logger.error(f"Error checking admin requests: {e}")
    
    def set_message_callback(self, callback: Callable):
        """Set callback for admin requests"""
        self.message_callback = callback
        print(f" Admin request callback set!")
    
    def set_player_response_callback(self, callback: Callable):
        """Set callback for player responses"""
        self.player_response_callback = callback
        print(f" Player response callback set!")
    
    async def start_monitoring(self):
        """Start monitoring for admin requests (WebSocket-only)."""
        if not await self.test_connection():
            logger.error("Cannot start monitoring - failed to connect to CRCON API")
            return

        self.monitoring = True
        reconnect_delay = int(self.config.get('crcon.ws_reconnect_initial_seconds', 3))
        max_delay = int(self.config.get('crcon.ws_reconnect_max_seconds', 30))
        logger.info("Starting WebSocket log monitoring (WS-only)")

        while self.monitoring:
            try:
                await self.monitor_via_websocket()
            except Exception as e:
                logger.error(f"WebSocket loop error: {e}")
            if not self.monitoring:
                break
            logger.warning(f"WebSocket disconnected. Reconnecting in {reconnect_delay}s…")
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, max_delay)
    
    def stop_monitoring(self):
        """Stop monitoring"""
        self.monitoring = False
        logger.info("Stopped monitoring for admin requests")

    async def monitor_via_websocket(self):
        """Monitor logs using CRCON WebSocket stream at /ws/logs (WS-only)."""
        await self.create_session()
        ws_url = self.base_url.replace('http://', 'ws://').replace('https://', 'wss://')
        ws_url = ws_url.rstrip('/') + '/ws/logs'

        headers = {"Authorization": f"Bearer {self.api_token}"}
        logger.info(f"Connecting to WebSocket log stream: {ws_url}")

        try:
            async with self.session.ws_connect(ws_url, headers=headers, heartbeat=30) as ws:
                init_payload = {
                    "last_seen_id": self.ws_last_seen_id,
                    "actions": ["CHAT"],
                }
                await ws.send_json(init_payload)
                logger.info("WebSocket stream started (CHAT filter)")

                while self.monitoring:
                    msg = await ws.receive()
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        try:
                            data = json.loads(msg.data)
                        except Exception:
                            try:
                                data = msg.json()
                            except Exception:
                                data = None

                        if not isinstance(data, dict):
                            continue

                        if data.get('error'):
                            logger.error(f"WebSocket server error: {data.get('error')}")
                            # Keep the connection alive; wait briefly and continue
                            await asyncio.sleep(1)
                            continue

                        batch = data.get('logs') or []
                        last_seen = data.get('last_seen_id')

                        # Always process the first batch; rely on ws_seen_ids to dedupe
                        if last_seen:
                            self.ws_last_seen_id = last_seen

                        for entry in batch:
                            sid = entry.get('id')
                            if sid and sid in self.ws_seen_ids:
                                continue
                            if sid:
                                self.ws_seen_ids.add(sid)
                                if len(self.ws_seen_ids) > 5000:
                                    self.ws_seen_ids.clear()

                            log = entry.get('log') or {}
                            action = log.get('action') or ''
                            if not str(action).startswith('CHAT'):
                                continue
                            player_name = log.get('player_name_1')
                            content = log.get('message') or log.get('raw') or ''
                            event_time = log.get('event_time')

                            # Helper: clean trailing SteamID patterns but keep full message
                            def _clean_message(msg: str) -> str:
                                if not msg:
                                    return ""
                                return re.sub(r'\(76561\d+\)', '', msg).strip()

                            try:
                                # If a ticket already exists for this player, always forward the full message
                                if player_name and content and (player_name in self.active_threads):
                                    full_msg = _clean_message(content)
                                    if self.player_response_callback:
                                        await self.player_response_callback(player_name, full_msg, event_time)
                                # Otherwise, only create a new ticket when the message pings admin
                                elif player_name and content and ('admin' in content.lower()):
                                    full_msg = _clean_message(content)
                                    if self.message_callback:
                                        await self.message_callback(player_name, full_msg)
                                # Else: ignore non-admin general chat when no ticket exists
                            except Exception as proc_err:
                                logger.error(f"Error processing WS log line: {proc_err}")

                    elif msg.type == aiohttp.WSMsgType.CLOSED:
                        logger.warning("WebSocket closed by server")
                        break
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        logger.error("WebSocket error encountered")
                        break
        except aiohttp.WSServerHandshakeError as e:
            logger.error(f"WebSocket handshake failed: {e}")
            raise
        except Exception as e:
            logger.error(f"WebSocket connection error: {e}")
            raise

class ClaimTicketView(discord.ui.View):
    def __init__(self, player_name: str, discord_bot):
        super().__init__(timeout=None)
        self.player_name = player_name
        self.discord_bot = discord_bot

    @discord.ui.button(
        label="Claim Ticket",
        style=discord.ButtonStyle.primary,
        custom_id="claim_ticket_button"
    )
    async def claim_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            # Build a light blue claimed embed
            claimed_embed = discord.Embed(
                title="🎛️ Controles Modérateur",
                description=f"{interaction.user.display_name} à pris en charge le ticket.",
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )
            # After claim, show Close button next
            new_view = CloseTicketView(self.player_name, self.discord_bot)
            await interaction.response.edit_message(embed=claimed_embed, view=new_view)

            # Notify player in-game
            try:
                await self.discord_bot.crcon_client.send_message_to_player(
                    self.player_name,
                    "Un modérateur s'occupe maintenant de votre demande."
                )
            except Exception:
                pass
        except Exception:
            try:
                await interaction.response.send_message("Error claiming ticket", ephemeral=True)
            except:
                pass

class CloseTicketView(discord.ui.View):
    def __init__(self, player_name: str, discord_bot):
        super().__init__(timeout=None)
        self.player_name = player_name
        self.discord_bot = discord_bot
    
    @discord.ui.button(
        label="Fermer le ticket", 
        style=discord.ButtonStyle.danger, 
        emoji="🔒",
        custom_id="close_ticket_button"
    )
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer()
            
            thread = interaction.channel
            player_name = self.player_name
            
            # Extract player name from thread title if needed
            if not player_name and isinstance(thread, discord.Thread):
                thread_title = thread.name
                player_name = thread_title.replace("Admin Request - ", "").strip()
            
            if not player_name:
                await interaction.followup.send("Could not determine player name", ephemeral=True)
                return
            
            print(f" Closing ticket for {player_name}")
            
            # Send confirmation message to player
            try:
                await self.discord_bot.crcon_client.send_message_to_player(
                    player_name,
                    "Votre ticket admin a été fermé. Merci !"
                )
                print(f"Sent close confirmation to player: {player_name}")
            except Exception as msg_error:
                print(f" Could not send close confirmation to player: {msg_error}")
            
            # Apply CLOSED tag to forum post
            await self.discord_bot.apply_forum_tag(thread, "CLOSED")
            
            # Remove player from tracking
            if player_name in self.discord_bot.active_threads:
                del self.discord_bot.active_threads[player_name]
                print(f"Discord: Removed {player_name} from active_threads")
            
            if player_name in self.discord_bot.active_button_messages:
                del self.discord_bot.active_button_messages[player_name]
                print(f" Discord: Removed {player_name} from button tracking")
            
            self.discord_bot.crcon_client.unregister_admin_thread(player_name)
            
            # Create confirmation embed as the interaction response (optional informational post)
            closed_embed = discord.Embed(
                title="🔒 Ticket fermé",
                description=f"Le ticket de **{player_name}** a été clôturé par {interaction.user.mention}",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            # Removed extra closed post; controls panel is updated instead

            # Update the existing controls panel (the button message) to closed state in green
            controls_closed = discord.Embed(
                title="🎛️ Controles Modérateur",
                description=f"Le ticket de **{player_name}** est clôturé",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            # We deferred earlier; edit the message the button was attached to
            await interaction.message.edit(embed=controls_closed, view=None)
            
            # Archive and lock the thread
            if isinstance(thread, discord.Thread):
                await thread.edit(archived=True, locked=True)
                print(f"Thread archived and locked for {player_name}")
            
            print(f" Ticket fully closed for {player_name}")
            logger.info(f"Ticket closed for {player_name} by {interaction.user}")
            
        except Exception as e:
            logger.error(f"Error closing ticket: {e}")
            await interaction.followup.send(" Error closing ticket", ephemeral=True)

class DiscordBot:
    def __init__(self, config, crcon_client):
        self.config = config
        self.crcon_client = crcon_client
        self.active_threads: Dict[str, discord.Thread] = {}
        self.active_button_messages: Dict[str, discord.Message] = {}
        
        # Forum tags (will be populated on startup)
        self.forum_tags = {
            'NEW': None,
            'REPLIED': None, 
            'CLOSED': None
        }
        
        # Set up Discord bot
        intents = discord.Intents.default()
        intents.message_content = True
        
        self.bot = commands.Bot(command_prefix='!', intents=intents)
        
        # Set up event handlers
        self.setup_events()
        
        # Set CRCON callbacks
        self.crcon_client.set_message_callback(self.handle_admin_request)
        self.crcon_client.set_player_response_callback(self.handle_player_response)
        
        print(f" Discord bot initialized")
        print(f" Admin channel ID: {self.config.get('discord.admin_channel_id')}")
    
    def setup_events(self):
        """Set up Discord bot events"""
        
        @self.bot.event
        async def on_ready():
            print(f" {self.bot.user} has connected to Discord!")
            logger.info(f'{self.bot.user} has connected to Discord!')
            
            # Add persistent views
            self.bot.add_view(CloseTicketView("", self))
            self.bot.add_view(ClaimTicketView("", self))
            
            # Setup forum tags
            await self.setup_forum_tags()
            
        @self.bot.event
        async def on_message(message):
            if message.author == self.bot.user:
                return
            
            if isinstance(message.channel, discord.Thread):
                await self.handle_thread_message(message)
            
            await self.bot.process_commands(message)
    
    async def setup_forum_tags(self):
        """Setup or get existing forum tags"""
        try:
            channel_id = self.config.get('discord.admin_channel_id')
            if not channel_id:
                print(f" No admin channel ID configured!")
                return
                
            channel = self.bot.get_channel(int(channel_id))
            
            if not channel:
                print(f" Could not find admin channel with ID: {channel_id}")
                return
            
            if not isinstance(channel, discord.ForumChannel):
                print(f"Channel is not a forum channel! Current type: {type(channel)}")
                print(f"Please convert your admin channel to a Forum Channel in Discord")
                return
            
            print(f"Found forum channel: {channel.name}")
            
            # Get existing tags or create them
            existing_tags = {tag.name: tag for tag in channel.available_tags}
            
            for tag_name in ['NEW', 'REPLIED', 'CLOSED']:
                if tag_name in existing_tags:
                    self.forum_tags[tag_name] = existing_tags[tag_name]
                    print(f"Found existing tag: {tag_name}")
                else:
                    # Create the tag
                    emoji_map = {'NEW': '🆕', 'REPLIED': '💬', 'CLOSED': '🔒'}
                    color_map = {'NEW': discord.Color.red(), 'REPLIED': discord.Color.orange(), 'CLOSED': discord.Color.green()}
                    
                    try:
                        new_tag = await channel.create_tag(
                            name=tag_name,
                            emoji=emoji_map[tag_name],
                            moderated=False
                        )
                        self.forum_tags[tag_name] = new_tag
                        print(f"Created new tag: {tag_name}")
                    except Exception as tag_error:
                        print(f"Failed to create tag {tag_name}: {tag_error}")
            
            print(f"Forum tags setup complete!")
            
        except Exception as e:
            print(f" Error setting up forum tags: {e}")
            logger.error(f"Error setting up forum tags: {e}")
    
    async def apply_forum_tag(self, thread: discord.Thread, tag_name: str):
        """Apply a forum tag to a thread"""
        try:
            if tag_name not in self.forum_tags or not self.forum_tags[tag_name]:
                print(f" Tag {tag_name} not available")
                return
            
            tag = self.forum_tags[tag_name]
            
            # Remove all existing status tags first
            current_tags = [t for t in thread.applied_tags if t.name not in ['NEW', 'REPLIED', 'CLOSED']]
            
            # Add the new tag
            new_tags = current_tags + [tag]
            
            await thread.edit(applied_tags=new_tags)
            print(f" Applied {tag_name} tag to thread: {thread.name}")
            
        except Exception as e:
            print(f" Error applying forum tag {tag_name}: {e}")
            logger.error(f"Error applying forum tag: {e}")
    
    async def handle_admin_request(self, player_name: str, admin_message: str):
        """Handle new admin request from game"""
        try:
            print(f" Discord handler called: {player_name} - {admin_message}")
            
            channel_id = self.config.get('discord.admin_channel_id')
            if not channel_id:
                print(f" No admin channel ID configured!")
                return
                
            channel = self.bot.get_channel(int(channel_id))
            
            if not channel:
                print(f"Could not find admin channel with ID: {channel_id}")
                return
            
            if not isinstance(channel, discord.ForumChannel):
                print(f"Channel is not a forum channel!")
                return
            
            # Create forum post (thread)
            thread_name = f"Admin Request - {player_name}"
            
            # Create initial embed
            embed = discord.Embed(
                title="🚨 Besoin d'un modérateur",
                description=f"**Joueur:** {player_name}\n**Message:** {admin_message}",
                color=discord.Color.red(),
                timestamp=discord.utils.utcnow()
            )
            embed.set_footer(text="Repondez dans ce fil de discussion pour envoyer un message directement au joueur.")
            
            print(f"Creating forum post: {thread_name}")
            
            # Create forum post with NEW tag
            new_tag = self.forum_tags.get('NEW')
            initial_tags = [new_tag] if new_tag else []
            
            thread, message = await channel.create_thread(
                name=thread_name,
                embed=embed,
                applied_tags=initial_tags
            )
            
            print(f"Forum post created: {thread.name}")
            
            # Add close button
            view = ClaimTicketView(player_name, self)
            button_message = await thread.send(embed=discord.Embed(
                title="🎛️ Controles modérateurs ",
                description=f"Ticket de **{player_name}** — en attente",
                color=discord.Color.blue()
            ), view=view)
            
            # Store the thread and button message
            self.active_threads[player_name] = thread
            self.active_button_messages[player_name] = button_message
            
            self.crcon_client.register_admin_thread(player_name, {
                'thread_id': thread.id,
                'player_name': player_name
            })
            
            # Send confirmation to player
            try:
                await self.crcon_client.send_message_to_player(
                    player_name, 
                    " RequÃªte admin reÃ§ue ! Les admins ont Ã©tÃ© avertis."
                )
                print(f"Confirmation sent to player")
            except Exception as msg_error:
                print(f" Could not send confirmation to player: {msg_error}")
            
            print(f" Successfully created admin forum post for {player_name}")
            logger.info(f"Created admin forum post for {player_name}")
            
        except Exception as e:
            print(f" Error handling admin request: {e}")
            logger.error(f"Error handling admin request: {e}")
            import traceback
            traceback.print_exc()
    
    async def handle_player_response(self, player_name: str, message: str, event_time: str):
        """Handle player response in game"""
        try:
            print(f" Player response received: {player_name} - {message}")
            
            if player_name not in self.active_threads:
                print(f" No active thread for player: {player_name}")
                return
            
            thread = self.active_threads[player_name]
            
            # Apply NEW tag (player has responded, needs admin attention)
            await self.apply_forum_tag(thread, "NEW")
            
            # Create embed for player response
            response_embed = discord.Embed(
                title="💬 Réponse du joueur",
                description=f"**{player_name}:** {message}",
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )
            
            if event_time:
                response_embed.set_footer(text=f"Game time: {event_time}")
            
            await thread.send(embed=response_embed)
            print(f"Player response posted to Discord forum")
            
            # Move button to bottom
            if player_name in self.active_button_messages:
                try:
                    old_message = self.active_button_messages[player_name]
                    await old_message.edit(view=None)
                except:
                    pass
            
            # Create new button message
            button_embed = discord.Embed(
                title="🎛️ Controles modérateurs",
                description=f"Ticket de **{player_name}** — en attente",
                color=discord.Color.blue()
            )
            
            view = ClaimTicketView(player_name, self)
            new_button_message = await thread.send(embed=button_embed, view=view)
            self.active_button_messages[player_name] = new_button_message
            
        except Exception as e:
            print(f"Error handling player response: {e}")
            logger.error(f"Error handling player response: {e}")
    
    async def handle_thread_message(self, message):
        """Handle admin replies in forum threads"""
        try:
            thread = message.channel
            
            if not isinstance(thread, discord.Thread):
                return
            
            # Extract player name from thread title
            player_name = None
            if "Admin Request -" in thread.name:
                player_name = thread.name.replace("Admin Request -", "").strip()
            
            if player_name and not message.author.bot:
                admin_name = message.author.display_name
                formatted_message = f"[ADMIN {admin_name}]: {message.content}"
                
                # Apply REPLIED tag
                await self.apply_forum_tag(thread, "REPLIED")
                
                success = await self.crcon_client.send_message_to_player(player_name, formatted_message)
                
                if success:
                    await message.add_reaction("âœ…")
                    print(f"Admin message sent to {player_name}")
                else:
                    await message.add_reaction("âŒ")
                    print(f"Failed to send admin message to {player_name}")
                
                logger.info(f"Sent message from {admin_name} to {player_name}: {message.content}")
        
        except Exception as e:
            logger.error(f"Error handling thread message: {e}")
    
    async def start(self):
        """Start the Discord bot"""
        token = self.config.get('discord.token')
        if not token:
            logger.error("Discord token not found in configuration")
            return
        
        try:
            await self.bot.start(token)
        except Exception as e:
            logger.error(f"Failed to start Discord bot: {e}")
