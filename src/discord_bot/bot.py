import discord
from discord.ext import commands
import logging
from typing import Dict, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)

class CloseTicketView(discord.ui.View):
    def __init__(self, player_name: str, discord_bot):
        super().__init__(timeout=None)
        self.player_name = player_name
        self.discord_bot = discord_bot
    
    @discord.ui.button(
        label="Close Ticket", 
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
                # Remove the date/time part and extract player name
                if " - " in thread_title:
                    parts = thread_title.split(" - ")
                    if len(parts) >= 2:
                        player_name = parts[1].strip()
            
            if not player_name:
                await interaction.followup.send("❌ Could not determine player name", ephemeral=True)
                return
            
            print(f"🔒 Closing ticket for {player_name}")
            
            # Send confirmation message to player
            try:
                await self.discord_bot.crcon_client.send_message_to_player(
                    player_name,
                    f"✅ Your admin ticket has been closed by {interaction.user.display_name}. Thank you!"
                )
                print(f"✅ Sent close confirmation to player: {player_name}")
            except Exception as msg_error:
                print(f"⚠️ Could not send close confirmation to player: {msg_error}")
            
            # Apply CLOSED tag to forum post
            await self.discord_bot.apply_forum_tag(thread, "CLOSED")
            
            # Remove player from tracking
            if player_name in self.discord_bot.active_threads:
                del self.discord_bot.active_threads[player_name]
                print(f"🗑️ Discord: Removed {player_name} from active_threads")
            
            if player_name in self.discord_bot.active_button_messages:
                del self.discord_bot.active_button_messages[player_name]
                print(f"🗑️ Discord: Removed {player_name} from button tracking")
            
            self.discord_bot.crcon_client.unregister_admin_thread(player_name)
            
            # Create closed embed
            closed_embed = discord.Embed(
                title="🔒 Ticket Closed",
                description=f"Admin ticket for **{player_name}** has been closed by {interaction.user.mention}",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            
            await interaction.edit_original_response(embed=closed_embed, view=None)
            
            # Archive and lock the thread
            if isinstance(thread, discord.Thread):
                await thread.edit(archived=True, locked=True)
                print(f"🗃️ Thread archived and locked for {player_name}")
            
            print(f"✅ Ticket fully closed for {player_name}")
            logger.info(f"Ticket closed for {player_name} by {interaction.user}")
            
        except Exception as e:
            logger.error(f"Error closing ticket: {e}")
            await interaction.followup.send("❌ Error closing ticket", ephemeral=True)

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
        
        print(f"🤖 Discord bot initialized")
        print(f"📺 Admin channel ID: {self.config.get('discord.admin_channel_id')}")
    
    def get_admin_mentions(self) -> str:
        """Get admin role mentions"""
        admin_roles = self.config.get('discord.admin_roles', [])
        if not admin_roles:
            return ""
        
        mentions = []
        for role_id in admin_roles:
            mentions.append(f"<@&{role_id}>")
        
        return " ".join(mentions)
    
    def setup_events(self):
        """Set up Discord bot events"""
        
        @self.bot.event
        async def on_ready():
            print(f"🤖 {self.bot.user} has connected to Discord!")
            logger.info(f'{self.bot.user} has connected to Discord!')
            
            # Add persistent view
            self.bot.add_view(CloseTicketView("", self))
            
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
                print(f"❌ No admin channel ID configured!")
                return
                
            channel = self.bot.get_channel(int(channel_id))
            
            if not channel:
                print(f"❌ Could not find admin channel with ID: {channel_id}")
                return
            
            if not isinstance(channel, discord.ForumChannel):
                print(f"⚠️ Channel is not a forum channel! Current type: {type(channel)}")
                print(f"💡 Please convert your admin channel to a Forum Channel in Discord")
                return
            
            print(f"✅ Found forum channel: {channel.name}")
            
            # Get existing tags or create them
            existing_tags = {tag.name: tag for tag in channel.available_tags}
            
            for tag_name in ['NEW', 'REPLIED', 'CLOSED']:
                if tag_name in existing_tags:
                    self.forum_tags[tag_name] = existing_tags[tag_name]
                    print(f"✅ Found existing tag: {tag_name}")
                else:
                    # Create the tag
                    emoji_map = {'NEW': '🆕', 'REPLIED': '💬', 'CLOSED': '🔒'}
                    
                    try:
                        new_tag = await channel.create_tag(
                            name=tag_name,
                            emoji=emoji_map[tag_name],
                            moderated=False
                        )
                        self.forum_tags[tag_name] = new_tag
                        print(f"✅ Created new tag: {tag_name}")
                    except Exception as tag_error:
                        print(f"❌ Failed to create tag {tag_name}: {tag_error}")
            
            print(f"🏷️ Forum tags setup complete!")
            
        except Exception as e:
            print(f"❌ Error setting up forum tags: {e}")
            logger.error(f"Error setting up forum tags: {e}")
    
    async def apply_forum_tag(self, thread: discord.Thread, tag_name: str):
        """Apply a forum tag to a thread"""
        try:
            if tag_name not in self.forum_tags or not self.forum_tags[tag_name]:
                print(f"⚠️ Tag {tag_name} not available")
                return
            
            tag = self.forum_tags[tag_name]
            
            # Remove all existing status tags first
            current_tags = [t for t in thread.applied_tags if t.name not in ['NEW', 'REPLIED', 'CLOSED']]
            
            # Add the new tag
            new_tags = current_tags + [tag]
            
            await thread.edit(applied_tags=new_tags)
            print(f"🏷️ Applied {tag_name} tag to thread: {thread.name}")
            
        except Exception as e:
            print(f"❌ Error applying forum tag {tag_name}: {e}")
            logger.error(f"Error applying forum tag: {e}")
    
    async def handle_admin_request(self, player_name: str, admin_message: str):
        """Handle new admin request from game"""
        try:
            print(f"🎯 Discord handler called: {player_name} - {admin_message}")
            
            channel_id = self.config.get('discord.admin_channel_id')
            if not channel_id:
                print(f"❌ No admin channel ID configured!")
                return
                
            channel = self.bot.get_channel(int(channel_id))
            
            if not channel:
                print(f"❌ Could not find admin channel with ID: {channel_id}")
                return
            
            if not isinstance(channel, discord.ForumChannel):
                print(f"❌ Channel is not a forum channel!")
                return
            
            # Create forum post with date and time
            now = datetime.now()
            date_str = now.strftime("%d-%m-%Y")
            time_str = now.strftime("%H:%M")
            post_name = f"{date_str} {time_str} - {player_name}"
            
            # Create initial message content with admin mentions
            admin_mentions = self.get_admin_mentions()
            initial_content = f"🚨 **NEW ADMIN REQUEST** 🚨\n{admin_mentions}" if admin_mentions else "🚨 **NEW ADMIN REQUEST** 🚨"
            
            print(f"📝 Creating forum post: {post_name}")
            
            # Create forum post with NEW tag
            new_tag = self.forum_tags.get('NEW')
            initial_tags = [new_tag] if new_tag else []
            
            # Create the forum post with content (not empty message)
            thread, message = await channel.create_thread(
                name=post_name,
                content=initial_content,
                applied_tags=initial_tags
            )
            
            print(f"✅ Forum post created: {thread.name}")
            
            # Send the detailed embed with Discord timestamp
            embed = discord.Embed(
                title="🚨 Admin Request Details",
                description=f"**Player:** {player_name}\n**Message:** {admin_message}",
                color=discord.Color.red(),
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(
                name="📅 Request Time", 
                value=f"<t:{int(datetime.now().timestamp())}:F>", 
                inline=False
            )
            embed.set_footer(text="Reply in this thread to send messages directly to the player")
            
            await thread.send(embed=embed)
            
            # Add close button
            view = CloseTicketView(player_name, self)
            button_embed = discord.Embed(
                title="🎛️ Admin Controls",
                color=discord.Color.orange()
            )
            button_message = await thread.send(embed=button_embed, view=view)
            
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
                    "✅ Admin request received! Admins have been notified on Discord."
                )
                print(f"✅ Confirmation sent to player")
            except Exception as msg_error:
                print(f"⚠️ Could not send confirmation to player: {msg_error}")
            
            print(f"🎉 Successfully created admin forum post for {player_name}")
            logger.info(f"Created admin forum post for {player_name}")
            
        except Exception as e:
            print(f"❌ Error handling admin request: {e}")
            logger.error(f"Error handling admin request: {e}")
            import traceback
            traceback.print_exc()
    
    async def handle_player_response(self, player_name: str, message: str, event_time: str):
        """Handle player response in game"""
        try:
            print(f"💬 Player response received: {player_name} - {message}")
            
            if player_name not in self.active_threads:
                print(f"⚠️ No active thread for player: {player_name}")
                return
            
            thread = self.active_threads[player_name]
            
            # Apply NEW tag (player has responded, needs admin attention)
            await self.apply_forum_tag(thread, "NEW")
            
            # Create embed for player response (without redundant player name)
            response_embed = discord.Embed(
                title="💬 Player Response",
                description=message,  # Just the message, no player name since it's already in the thread title
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )
            
            if event_time:
                response_embed.set_footer(text=f"Game time: {event_time}")
            
            await thread.send(embed=response_embed)
            print(f"✅ Player response posted to Discord forum")
            
            # Move button to bottom
            if player_name in self.active_button_messages:
                try:
                    old_message = self.active_button_messages[player_name]
                    await old_message.edit(view=None)
                except:
                    pass
            
            # Create new button message
            button_embed = discord.Embed(
                title="🎛️ Admin Controls",
                description=f"Ticket for **{player_name}** is active",
                color=discord.Color.orange()
            )
            
            view = CloseTicketView(player_name, self)
            new_button_message = await thread.send(embed=button_embed, view=view)
            self.active_button_messages[player_name] = new_button_message
            
        except Exception as e:
            print(f"❌ Error handling player response: {e}")
            logger.error(f"Error handling player response: {e}")
    
    async def handle_thread_message(self, message):
        """Handle admin replies in forum posts"""
        try:
            thread = message.channel
            
            if not isinstance(thread, discord.Thread):
                return
            
            # Extract player name from thread title (format: "YYYY-MM-DD - PlayerName")
            player_name = None
            if " - " in thread.name:
                parts = thread.name.split(" - ")
                if len(parts) >= 2:
                    player_name = parts[1].strip()
            
            if player_name and not message.author.bot:
                admin_name = message.author.display_name
                formatted_message = f"[ADMIN {admin_name}]: {message.content}"
                
                # Apply REPLIED tag
                await self.apply_forum_tag(thread, "REPLIED")
                
                success = await self.crcon_client.send_message_to_player(player_name, formatted_message)
                
                if success:
                    await message.add_reaction("✅")
                    print(f"✅ Admin message sent to {player_name}")
                else:
                    await message.add_reaction("❌")
                    print(f"❌ Failed to send admin message to {player_name}")
                
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