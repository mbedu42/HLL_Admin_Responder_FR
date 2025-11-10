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
        
        # Initialize with current logs to avoid processing old ones
        self.highest_log_id = 0
        # For recent logs API: track last seen timestamp in ms
        self.last_seen_timestamp_ms = 0
        
        logger.info(f"CRCON Config - URL: {self.base_url}")
    
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
        """Initialize tracking using recent logs to avoid processing old ones"""
        try:
            await self.create_session()
            url = f'{self.base_url}/api/get_recent_logs'
            payload = {
                'start': 0,
                'end': 1000,
                'filter_action': ['CHAT'],
                'exact_action': False,
                'inclusive_filter': True
            }
            async with self.session.post(url, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    res = data.get('result', {}) or {}
                    logs = res.get('logs', [])
                    if logs:
                        # Keep the highest timestamp to start after existing logs
                        self.last_seen_timestamp_ms = max(l.get('timestamp_ms', 0) for l in logs)
                        print(f" Initialized recent log tracking. Starting from ts_ms: {self.last_seen_timestamp_ms}")
                    else:
                        print(f" No logs found during initialization")
                else:
                    logger.error(f"API init (recent logs) failed with status: {response.status}")
        except Exception as e:
            logger.error(f"Error initializing log tracking: {e}")
    
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
                            'steam_id_64': stat.get('player_id')
                        })
                    
                    return players
                else:
                    logger.error(f"Failed to get players, status: {response.status}")
                    return []
        except Exception as e:
            logger.error(f"Error getting players: {e}")
            return []
    
    async def get_new_logs(self) -> list:
        """Get NEW chat logs using recent logs API and last seen timestamp."""
        try:
            await self.create_session()
            url = f'{self.base_url}/api/get_recent_logs'
            # Use a small epsilon to exclude logs with the exact same timestamp
            min_ts = (self.last_seen_timestamp_ms / 1000.0 + 0.001) if self.last_seen_timestamp_ms else None
            payload = {
                'start': 0,
                'end': 5000,
                'filter_action': ['CHAT'],
                'exact_action': False,
                'inclusive_filter': True
            }
            if min_ts:
                payload['min_timestamp'] = float(min_ts)
            async with self.session.post(url, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    res = data.get('result', {}) or {}
                    logs = res.get('logs', [])
                    if self.active_threads:
                        print(f" Currently tracking responses for: {list(self.active_threads.keys())}")
                    
                    # Filter and normalize new logs strictly greater than last_seen_timestamp_ms
                    new_logs = []
                    new_highest_ts = self.last_seen_timestamp_ms
                    for log in logs:
                        ts_ms = log.get('timestamp_ms', 0)
                        action = log.get('action', '') or ''
                        if not action.startswith('CHAT'):
                            continue
                        if ts_ms and ts_ms > self.last_seen_timestamp_ms:
                            # Normalize shape to match downstream usage
                            normalized = {
                                'player1_name': log.get('player_name_1'),
                                'content': log.get('message') or log.get('raw', ''),
                                'id': ts_ms,  # surrogate id for logging; not persisted
                                'event_time': log.get('event_time'),
                                'type': action,
                            }
                            new_logs.append(normalized)
                            if ts_ms > new_highest_ts:
                                new_highest_ts = ts_ms
                    
                    if new_highest_ts > self.last_seen_timestamp_ms:
                        self.last_seen_timestamp_ms = new_highest_ts
                    
                    fetched_from = f"{min_ts:.3f}s" if min_ts else "startup"
                    print(f" Fetched {len(logs)} recent logs since {fetched_from} (new: {len(new_logs)})")
                    return new_logs
                else:
                    logger.error(f"Failed to get recent logs, status: {response.status}")
                    return []
        except Exception as e:
            logger.error(f"Error getting recent logs: {e}")
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
                    
                    # Mark as processed
                    if log_id:
                        self.processed_log_ids.add(log_id)

                    # If player already has an active ticket and sends another 'admin' message,
                    # treat it as a continuation in the same thread with a normalized text.
                    if (player_name and content and 'admin' in content.lower() and 
                        (player_name in self.active_threads)):
                        normalized_message = "Player requested admin assistance"
                        print(f" CONTINUATION: {player_name} sent another admin message; treating as response")
                        if self.player_response_callback:
                            try:
                                await self.player_response_callback(player_name, normalized_message, event_time)
                                print(f" Player response (normalized) sent to Discord thread!")
                            except Exception as callback_error:
                                print(f" Failed to send normalized player response to Discord: {callback_error}")
                        # Skip standard admin request handling for this log entry
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
        """Start monitoring for admin requests"""
        if not await self.test_connection():
            logger.error("Cannot start monitoring - failed to connect to CRCON API")
            return
        
        await self.initialize_log_tracking()
        
        self.monitoring = True
        print(f" Started monitoring for admin requests and player responses")
        logger.info("Started monitoring for admin requests via CRCON API")
        
        # Polling configuration (defaults if not set)
        poll_interval = int(self.config.get('crcon.poll_interval_seconds', 5))
        error_backoff = int(self.config.get('crcon.error_backoff_seconds', 10))
        
        while self.monitoring:
            try:
                await self.check_for_admin_requests()
                await asyncio.sleep(poll_interval)
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(error_backoff)
    
    def stop_monitoring(self):
        """Stop monitoring"""
        self.monitoring = False
        logger.info("Stopped monitoring for admin requests")

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
