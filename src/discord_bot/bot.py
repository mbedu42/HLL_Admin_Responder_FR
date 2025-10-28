﻿import discord
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
        label="Fermer le ticket", 
        style=discord.ButtonStyle.danger, 
        emoji="ðŸ”’",
        custom_id="close_ticket_button"
    )
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            # Apply CLOSED tag to thread
            await self.discord_bot.apply_forum_tag(interaction.message.channel, 'CLOSED')
            
            # Update the controls embed to show closed state in green and remove controls
            closed_embed = discord.Embed(
                title="ðŸŽ›ï¸ Controles ModÃ©rateur",
                description=f"Le ticket de **{self.player_name}** est clÃ´turÃ©",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            # Disable the button and update embed on the message with the component
            self.clear_items()
            await interaction.response.edit_message(embed=closed_embed, view=None)
            
            # Remove player from active tickets tracking (Discord bot)
            if self.player_name in self.discord_bot.player_tickets:
                del self.discord_bot.player_tickets[self.player_name]
            
            # Remove from active threads (Discord bot)
            if self.player_name in self.discord_bot.active_threads:
                del self.discord_bot.active_threads[self.player_name]
                
            # Remove from active button messages (Discord bot)
            if self.player_name in self.discord_bot.active_button_messages:
                del self.discord_bot.active_button_messages[self.player_name]
            
            # FIXED: Also clean up CRCON client tracking
            self.discord_bot.crcon_client.unregister_admin_thread(self.player_name)

            # Archive and lock the thread to match CRCON behavior
            try:
                thread = interaction.message.channel
                if isinstance(thread, discord.Thread):
                    await thread.edit(archived=True, locked=True)
            except Exception:
                pass
            
            # Send confirmation message to player
            try:
                if hasattr(self.discord_bot, 'crcon_client') and self.discord_bot.crcon_client:
                    await self.discord_bot.crcon_client.send_message_to_player(
                        self.player_name,
                        f"Votre ticket admin a Ã©tÃ© fermÃ© par un modÃ©rateur. Merci !"
                    )
                    print(f"âœ…. Sent close confirmation to player: {self.player_name}")
                else:
                    print(f"âš ï¸ CRCON client not available to send close confirmation")
            except Exception as msg_error:
                print(f"âš ï¸ Could not send close confirmation to player: {msg_error}")
                
            print(f"ðŸ”§ Ticket closed for {self.player_name} by {interaction.user.display_name}")

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
            claimed_embed = discord.Embed(
                title="🎛️ Controles Modérateur",
                description=f"{interaction.user.display_name} has claimed the ticket.",
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )
            new_view = CloseTicketView(self.player_name, self.discord_bot)
            await interaction.response.edit_message(embed=claimed_embed, view=new_view)

            # Notify player in-game via CRCON
            try:
                if hasattr(self.discord_bot, 'crcon_client') and self.discord_bot.crcon_client:
                    await self.discord_bot.crcon_client.send_message_to_player(
                        self.player_name,
                        "âœ… An admin is now taking care of your demand."
                    )
            except Exception:
                pass
            # Record claimer for future panels
            try:
                self.discord_bot.claimed_by[self.player_name] = interaction.user.display_name
            except Exception:
                pass
        except Exception:
            try:
                await interaction.response.send_message("Error claiming ticket", ephemeral=True)
            except:
                pass
    
class DiscordBot:
    def __init__(self, config, crcon_client):
        self.config = config
        self.crcon_client = crcon_client
        self.active_threads: Dict[str, discord.Thread] = {}
        self.active_button_messages: Dict[str, discord.Message] = {}
        self.player_tickets: Dict[str, bool] = {}  # Track players with active tickets
        self.claimed_by: Dict[str, str] = {}  # Track who claimed a ticket
        
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
        
        print(f"ðŸ¤– Discord bot initialized")
        print(f"ðŸ“º Admin channel ID: {self.config.get('discord.admin_channel_id')}")
    
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
            print(f"ðŸ¤– {self.bot.user} has connected to Discord!")
            logger.info(f'{self.bot.user} has connected to Discord!')
            
            # Setup forum tags
            await self.setup_forum_tags()
            
        @self.bot.event
        async def on_message(message):
            if message.author == self.bot.user:
                return
            
            if isinstance(message.channel, discord.Thread):
                await self.handle_thread_message(message)
            
            await self.bot.process_commands(message)
        
        # Add cleanup command
        @self.bot.command(name='cleanup_tickets')
        @commands.has_permissions(administrator=True)
        async def cleanup_tickets(ctx):
            """Clean up tracking for deleted threads - Admin only"""
            cleaned = 0
            to_remove = []
            
            for player_name, thread in self.active_threads.items():
                try:
                    await thread.fetch()
                except (discord.NotFound, discord.Forbidden):
                    to_remove.append(player_name)
                    cleaned += 1
            
            # Remove all the invalid entries
            for player_name in to_remove:
                if player_name in self.player_tickets:
                    del self.player_tickets[player_name]
                if player_name in self.active_threads:
                    del self.active_threads[player_name]
                if player_name in self.active_button_messages:
                    del self.active_button_messages[player_name]
            
            await ctx.send(f"ðŸ§¹ Cleaned up {cleaned} deleted ticket(s)")
    
    async def setup_forum_tags(self):
        """Setup or get existing forum tags"""
        try:
            channel_id = self.config.get('discord.admin_channel_id')
            if not channel_id:
                print(f"âŒ No admin channel ID configured!")
                return
                
            channel = self.bot.get_channel(int(channel_id))
            
            if not channel:
                print(f"âŒ Could not find admin channel with ID: {channel_id}")
                return
            
            if not isinstance(channel, discord.ForumChannel):
                print(f"âš ï¸ Channel is not a forum channel! Current type: {type(channel)}")
                print(f"ðŸ’¡ Please convert your admin channel to a Forum Channel in Discord")
                return
            
            print(f"âœ… Found forum channel: {channel.name}")
            
            # Get existing tags or create them
            existing_tags = {tag.name: tag for tag in channel.available_tags}
            
            for tag_name in ['NEW', 'REPLIED', 'CLOSED']:
                if tag_name in existing_tags:
                    self.forum_tags[tag_name] = existing_tags[tag_name]
                    print(f"âœ… Found existing tag: {tag_name}")
                else:
                    # Create the tag
                    emoji_map = {'NEW': 'ðŸ†•', 'REPLIED': 'ðŸ’¬', 'CLOSED': 'ðŸ”’'}
                    
                    try:
                        new_tag = await channel.create_tag(
                            name=tag_name,
                            emoji=emoji_map[tag_name],
                            moderated=False
                        )
                        self.forum_tags[tag_name] = new_tag
                        print(f"âœ… Created new tag: {tag_name}")
                    except Exception as tag_error:
                        print(f"âŒ Failed to create tag {tag_name}: {tag_error}")
            
            print(f"ðŸ·ï¸ Forum tags setup complete!")
            
        except Exception as e:
            print(f"âŒ Error setting up forum tags: {e}")
            logger.error(f"Error setting up forum tags: {e}")
    
    async def apply_forum_tag(self, thread: discord.Thread, tag_name: str):
        """Apply a forum tag to a thread"""
        try:
            if tag_name not in self.forum_tags or not self.forum_tags[tag_name]:
                print(f"âš ï¸ Tag {tag_name} not available")
                return
            
            tag = self.forum_tags[tag_name]
            
            # Remove all existing status tags first
            current_tags = [t for t in thread.applied_tags if t.name not in ['NEW', 'REPLIED', 'CLOSED']]
            
            # Add the new tag
            new_tags = current_tags + [tag]
            
            await thread.edit(applied_tags=new_tags)
            print(f"ðŸ·ï¸ Applied {tag_name} tag to thread: {thread.name}")
            
        except Exception as e:
            print(f"âŒ Error applying forum tag {tag_name}: {e}")
            logger.error(f"Error applying forum tag: {e}")
    
    async def handle_admin_request(self, player_name: str, admin_message: str):
        """Handle new admin request from game"""
        try:
            print(f"ðŸŽ¯ Discord handler called: {player_name} - {admin_message}")
            
            # Check if player already has an active ticket
            if player_name in self.player_tickets and self.player_tickets[player_name]:
                print(f"âš ï¸ Player {player_name} already has an active ticket")
                
                # Add their message to the existing ticket if they provided one
                if admin_message and admin_message.strip() and player_name in self.active_threads:
                    try:
                        thread = self.active_threads[player_name]
                        
                        # Create embed for the additional message
                        now = datetime.now()
                        embed = discord.Embed(
                            title="ðŸ’¬ Message additionnel du joueur",
                            description=admin_message,
                            color=discord.Color.blue(),
                            timestamp=now
                        )
                        embed.set_footer(text=f"From: {player_name}")
                        
                        await thread.send(embed=embed)
                        print(f"âœ… Added player message to existing ticket: {player_name}")
                        
                    except Exception as thread_error:
                        print(f"âŒ Could not add message to existing thread: {thread_error}")
                
                # Send active ticket message
                try:
                    await self.crcon_client.send_message_to_player(
                        player_name,
                        "Vous avez dÃ©jÃ  un ticket admin actif. Vous pouvez rÃ©pondre Ã  votre demande en Ã©crivant dans le chat sans rÃ©utiliser !admin."
                    )
                except Exception as msg_error:
                    print(f"âŒ Could not send duplicate ticket message to player: {msg_error}")
                return
            
            channel_id = self.config.get('discord.admin_channel_id')
            if not channel_id:
                print("âŒ No admin channel ID configured")
                return
                
            channel = self.bot.get_channel(int(channel_id))
            
            if not channel:
                print(f"âŒ Could not find channel with ID: {channel_id}")
                return
            
            if not isinstance(channel, discord.ForumChannel):
                print(f"âŒ Channel {channel_id} is not a forum channel")
                return
            
            # Create forum post with date and time
            now = datetime.now()
            date_str = now.strftime("%Y-%m-%d")
            time_str = now.strftime("%H:%M")
            post_name = f"{date_str} {time_str} - {player_name}"
            
            # Create initial message content with admin mentions
            admin_mentions = self.get_admin_mentions()
            initial_content = f"ðŸš¨ **Nouveau ping MODO** ðŸš¨\n{admin_mentions}" if admin_mentions else "ðŸš¨ **Nouveau ping MODO** ðŸš¨"
            
            print(f"ðŸ“ Creating forum post: {post_name}")
            
            # Create forum post with NEW tag
            new_tag = self.forum_tags.get('NEW')
            initial_tags = [new_tag] if new_tag else []
            
            # Create the forum post with content (not empty message)
            thread, message = await channel.create_thread(
                name=post_name,
                content=initial_content,
                applied_tags=initial_tags
            )

            # Mark player as having an active ticket
            self.player_tickets[player_name] = True
            
            # Store thread reference
            self.active_threads[player_name] = thread
            
            # Register with CRCON client
            self.crcon_client.register_admin_thread(player_name, {
                'thread_id': thread.id,
                'player_name': player_name
            })
            
            # Create detailed embed with player info and request
            embed = discord.Embed(
                title="ðŸš¨ Ping MODO",
                color=discord.Color.red(),
                timestamp=now
            )
            
            embed.add_field(name="ðŸ‘¤ Player", value=player_name, inline=True)
            embed.add_field(name="ðŸ• Time", value=f"{date_str} {time_str}", inline=True)
            embed.add_field(name="ðŸ’¬ Message", value=admin_message or "No additional message", inline=False)
            
            # Post the detailed embed without controls
            await thread.send(embed=embed)

            # Send initial controls panel (claim stage)
            controls_embed = discord.Embed(
                title="ðŸŽ›ï¸ Controles ModÃ©rateur",
                title="??? Controles Modérateur",
                description=f"Ticket de **{player_name}** - en attente",
                timestamp=now
            )
            view = ClaimTicketView(player_name, self)
            button_message = await thread.send(embed=controls_embed, view=view)
            self.active_button_messages[player_name] = button_message
            
            print(f"âœ… Created admin request thread for {player_name}")
            
            # Send confirmation to player
            try:
                await self.crcon_client.send_message_to_player(
                    player_name,
                    "Votre requÃªte admin a bien Ã©tÃ© reÃ§ue ! Vous pouvez rÃ©pondre Ã  ce ticket en Ã©crivant dans le chat (inutile de rÃ©utiliser !admin)."
                )
                print(f"âœ… Sent confirmation to player: {player_name}")
            except Exception as msg_error:
                print(f"âŒ Could not send confirmation to player: {msg_error}")
            
        except Exception as e:
            print(f"âŒ Error handling admin request: {e}")
            logger.error(f"Error handling admin request: {e}")

    async def handle_player_response(self, player_name: str, message: str, event_time: str):
        """Handle player response in game"""
        try:
            print(f"ðŸ’¬ Player response received: {player_name} - {message}")
            
            if player_name not in self.active_threads:
                print(f"âš ï¸ No active thread for player: {player_name}")
                return
            
            thread = self.active_threads[player_name]
            
            # Check if thread still exists by trying to send a message
            # (Forum posts/threads don't have .fetch() method)
            try:
                # Try to get the thread's parent (this will fail if thread is deleted)
                parent = thread.parent
                if not parent:
                    raise discord.NotFound("Thread parent not found")
                    
            except (discord.NotFound, discord.Forbidden, AttributeError):
                print(f"ðŸ—‘ï¸ Thread for {player_name} was deleted, cleaning up tracking...")
                # Clean up all tracking for this player
                if player_name in self.player_tickets:
                    del self.player_tickets[player_name]
                if player_name in self.active_threads:
                    del self.active_threads[player_name]
                if player_name in self.active_button_messages:
                    del self.active_button_messages[player_name]
                
                # Clean up CRCON tracking
                self.crcon_client.unregister_admin_thread(player_name)
                
                print(f"âœ… Cleaned up tracking for {player_name}, they can create new tickets now")
                return
            
            # Apply NEW tag (player has responded, needs admin attention)
            await self.apply_forum_tag(thread, "NEW")
            
            # Create embed for player response (without redundant player name)
            response_embed = discord.Embed(
                title="ðŸ’¬ RÃ©ponse du joueur",
                description=message,  # Just the message, no player name since it's already in the thread title
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )
            
            if event_time:
                response_embed.set_footer(text=f"Game time: {event_time}")
            
            await thread.send(embed=response_embed)
            print(f"âœ… Player response posted to Discord forum")
            
            # Move button to bottom
            if player_name in self.active_button_messages:
                try:
                    old_message = self.active_button_messages[player_name]
                    await old_message.edit(view=None)
                except:
                    pass
            
            # Create new button message
            # Create new controls message
            button_embed = discord.Embed(
                title="🎛️ Controles Modérateur",
                description=f"Ticket de **{player_name}** - en attente",
                color=discord.Color.blue()
            )
            view = ClaimTicketView(player_name, self)
            new_button_message = await thread.send(embed=button_embed, view=view)
            self.active_button_messages[player_name] = new_button_message
            self.active_button_messages[player_name] = new_button_message
        except Exception as e:
            print(f"âŒ Error handling player response: {e}")
            logger.error(f"Error handling player response: {e}")

    async def handle_thread_message(self, message: discord.Message):
        """Handle messages in admin threads"""
        try:
            # Skip if message is from bot
            if message.author == self.bot.user:
                return
            
            # Skip if not in a thread
            if not isinstance(message.channel, discord.Thread):
                return
            
            # Find which player this thread belongs to
            player_name = None
            for name, thread in self.active_threads.items():
                if thread.id == message.channel.id:
                    player_name = name
                    break
            
            if not player_name:
                print(f"âš ï¸ Could not find player for thread: {message.channel.name}")
                return
            
            # Skip system messages and embeds
            if message.type != discord.MessageType.default or message.embeds:
                return
            
            # Send admin response to player
            admin_message = f"[ADMIN]: {message.content}"
            
            try:
                await self.crcon_client.send_message_to_player(player_name, admin_message)
                print(f"Sent admin response to {player_name}: {message.content}")
                
                # Apply REPLIED tag
                await self.apply_forum_tag(message.channel, 'REPLIED')
                
                # Add reaction to confirm message was sent
                await message.add_reaction("âœ…")
                
            except Exception as e:
                print(f"âŒ Failed to send message to player {player_name}: {e}")
                await message.add_reaction("âŒ")
                
        except Exception as e:
            print(f"âŒ Error handling thread message: {e}")
            logger.error(f"Error handling thread message: {e}")

    async def start(self):
        """Start the Discord bot"""
        try:
            token = self.config.get('discord.token')
            if not token:
                raise ValueError("Discord token not found in config")
            
            print(f"ðŸš€ Starting Discord bot...")
            await self.bot.start(token)
            
        except Exception as e:
            print(f"âŒ Failed to start Discord bot: {e}")
            logger.error(f"Failed to start Discord bot: {e}")
            raise
