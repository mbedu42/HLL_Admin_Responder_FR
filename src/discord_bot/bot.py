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
        label="Fermer le ticket", 
        style=discord.ButtonStyle.danger, 
        emoji="🔒",
        custom_id="close_ticket_button"
    )
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            # Apply CLOSED tag to thread
            await self.discord_bot.apply_forum_tag(interaction.message.channel, 'CLOSED')
            
            # Update the controls embed to show closed state in green and remove controls
            closed_embed = discord.Embed(
                title="🎛️ Statut du ticket",
                description=f"Le ticket de **{self.player_name}** est clôturé par **{interaction.user.display_name}**",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            # Disable the button and update embed on the message with the component
            self.clear_items()
            await interaction.response.edit_message(embed=closed_embed, view=None)
            # Then delete it and re-post at the bottom so it appears last
            try:
                await interaction.message.delete()
            except Exception:
                pass
            try:
                new_msg = await interaction.message.channel.send(embed=closed_embed)
                # Track the final status window id
                self.discord_bot.current_status_message[self.player_name] = new_msg.id
                self.discord_bot.status_messages[self.player_name] = [new_msg.id]
            except Exception:
                pass

            
            # Remove player from active tickets tracking (Discord bot)
            if self.player_name in self.discord_bot.player_tickets:
                del self.discord_bot.player_tickets[self.player_name]
            
            # Remove from active threads (Discord bot)
            if self.player_name in self.discord_bot.active_threads:
                del self.discord_bot.active_threads[self.player_name]
                
            # Remove from active button messages (Discord bot)
            if self.player_name in self.discord_bot.active_button_messages:
                del self.discord_bot.active_button_messages[self.player_name]

            # Clear claimed state for this player (so future tickets start fresh)
            if self.player_name in self.discord_bot.claimed_by:
                del self.discord_bot.claimed_by[self.player_name]
            
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
                        f"Votre ticket admin a été fermé par un modérateur. Merci !"
                    )
                    print(f"✅. Sent close confirmation to player: {self.player_name}")
                else:
                    print(f"⚠️ CRCON client not available to send close confirmation")
            except Exception as msg_error:
                print(f"⚠️ Could not send close confirmation to player: {msg_error}")
                
            print(f"🔧 Ticket closed for {self.player_name} by {interaction.user.display_name}")

        except Exception as e:
            print(f"Error closing ticket: {e}")
            try:
                await interaction.response.send_message("Error closing ticket", ephemeral=True)
            except Exception:
                pass
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
                title="🎛️ Statut du ticket",
                description=f"{interaction.user.display_name} s'est attribué le ticket.",
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
                        "Un modérateur s'occupe maintenant de votre demande."
                    )
            except Exception:
                pass
            # Record claimer for future panels and normalize status windows: keep only this message
            try:
                self.discord_bot.claimed_by[self.player_name] = interaction.user.display_name
                msg_id = interaction.message.id
                self.discord_bot.current_status_message[self.player_name] = msg_id
                # Delete any other previous status messages
                thread = interaction.message.channel
                try:
                    ids = self.discord_bot.status_messages.get(self.player_name, [])
                    for mid in ids:
                        if mid == msg_id:
                            continue
                        try:
                            msg_obj = await thread.fetch_message(mid)
                            await msg_obj.delete()
                        except Exception:
                            pass
                except Exception:
                    pass
                # Reset tracking to only this one
                self.discord_bot.status_messages[self.player_name] = [msg_id]
            except Exception:
                pass
        except Exception:
            try:
                await interaction.response.send_message("Error claiming ticket", ephemeral=True)
            except:
                pass
    
    @discord.ui.button(
        label="Fermer le ticket", 
        style=discord.ButtonStyle.danger, 
        emoji="🔒",
        custom_id="close_ticket_button"
    )
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            # Apply CLOSED tag to thread
            await self.discord_bot.apply_forum_tag(interaction.message.channel, 'CLOSED')
            
            # Update the controls embed to show closed state in green and remove controls
            closed_embed = discord.Embed(
                title="🎛️ Statut du ticket",
                description=f"Le ticket de **{self.player_name}** est clôturé",
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
                        f"Votre ticket admin a été fermé par un modérateur. Merci !"
                    )
                    print(f"Sent close confirmation to player: {self.player_name}")
                else:
                    print(f" CRCON client not available to send close confirmation")
            except Exception as msg_error:
                print(f" Could not send close confirmation to player: {msg_error}")
                
            print(f" Ticket closed for {self.player_name} by {interaction.user.display_name}")
            
        except Exception as e:
            print(f" Error closing ticket: {e}")
            try:
                await interaction.response.send_message(" Error closing ticket", ephemeral=True)
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
        # Track status window messages per player so we can delete older ones
        self.status_messages: Dict[str, List[int]] = {}
        # Track the preserved claimed-status message id per player
        self.claim_status_message: Dict[str, int] = {}
        # Track the current dynamic status message (latest) to delete before posting a new one
        self.current_status_message: Dict[str, int] = {}
        
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
        
        print(f"Discord bot initialized")
        print(f"Admin channel ID: {self.config.get('discord.admin_channel_id')}")
    
    def get_admin_mentions(self) -> str:
    #"""Get admin role mentions"""
        admin_roles = self.config.get('discord.admin_roles', [])
        if not admin_roles:
            return ""
        
        mentions = []
        for role_id in admin_roles:
            mentions.append(f"<@&{role_id}>")
        
        return " ".join(mentions)
    
    def setup_events(self):
    #"""Set up Discord bot events"""
        
        @self.bot.event
        async def on_ready():
            print(f"{self.bot.user} has connected to Discord!")
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
        #"""Clean up tracking for deleted threads - Admin only"""
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
            
            await ctx.send(f"Cleaned up {cleaned} deleted ticket(s)")
    
    async def setup_forum_tags(self):
    #"""Setup or get existing forum tags"""
        try:
            channel_id = self.config.get('discord.admin_channel_id')
            if not channel_id:
                print(f"No admin channel ID configured!")
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
                    
                    try:
                        new_tag = await channel.create_tag(
                            name=tag_name,
                            moderated=False
                        )
                        self.forum_tags[tag_name] = new_tag
                        print(f"Created new tag: {tag_name}")
                    except Exception as tag_error:
                        print(f"Failed to create tag {tag_name}: {tag_error}")
            
            print(f"Forum tags setup complete!")
            
        except Exception as e:
            print(f"Error setting up forum tags: {e}")
            logger.error(f"Error setting up forum tags: {e}")
    
    async def apply_forum_tag(self, thread: discord.Thread, tag_name: str):
#"""Apply a forum tag to a thread"""
        try:
            if tag_name not in self.forum_tags or not self.forum_tags[tag_name]:
                print(f"Tag {tag_name} not available")
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
    #"""Handle new admin request from game"""
        try:
            print(f" Discord handler called: {player_name} - {admin_message}")
            
            # Check if player already has an active ticket
            if player_name in self.player_tickets and self.player_tickets[player_name]:
                print(f" Player {player_name} already has an active ticket")
                
                # Add their message to the existing ticket if they provided one
                if admin_message and admin_message.strip() and player_name in self.active_threads:
                    try:
                        thread = self.active_threads[player_name]
                        
                        # Create embed for the additional message
                        now = datetime.now()
                        embed = discord.Embed(
                            title="💬 Message additionnel du joueur",
                            description=admin_message,
                            color=discord.Color.blue(),
                            timestamp=now
                        )
                        embed.set_footer(text=f"From: {player_name}")
                        
                        await thread.send(embed=embed)
                        print(f"Added player message to existing ticket: {player_name}")
                        
                    except Exception as thread_error:
                        print(f"Could not add message to existing thread: {thread_error}")
                
                # Send active ticket message
                try:
                    await self.crcon_client.send_message_to_player(
                        player_name,
                        "Vous avez déjà un ticket admin actif. Vous pouvez répondre à votre demande en écrivant dans le chat sans réutiliser !admin."
                    )
                except Exception as msg_error:
                    print(f"Could not send duplicate ticket message to player: {msg_error}")
                return
            
            channel_id = self.config.get('discord.admin_channel_id')
            if not channel_id:
                print("No admin channel ID configured")
                return
                
            channel = self.bot.get_channel(int(channel_id))
            
            if not channel:
                print(f"Could not find channel with ID: {channel_id}")
                return
            
            if not isinstance(channel, discord.ForumChannel):
                print(f"Channel {channel_id} is not a forum channel")
                return
            
            # Create forum post with date/time and append player platform ID if available
            now = datetime.now()
            date_str = now.strftime("%Y-%m-%d")
            time_str = now.strftime("%H:%M")
            id_suffix = ""
            player_team = None
            try:
                players = await self.crcon_client.get_players()
                for p in players:
                    if p.get('name') == player_name:
                        platform_id = p.get('player_id') or p.get('steam_id_64')
                        player_team = p.get('side')
                        if platform_id:
                            id_suffix = f" ({platform_id})"
                        break
            except Exception:
                # If we fail to fetch players, just omit the ID
                pass
            post_name = f"{date_str} {time_str} - {player_name}{id_suffix}"
            
            # Create initial message content with admin mentions
            admin_mentions = self.get_admin_mentions()
            initial_content = f"🚨 **Nouveau ping MODO** 🚨\n{admin_mentions}" if admin_mentions else "🚨 **Nouveau ping MODO** 🚨"
            print(f"Creating forum post: {post_name}")
            
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
                title="🚨 Ping MODO",
                color=discord.Color.red(),
                timestamp=now
            )

            # Add role mentions to the title to re-ping
            role_title = f"Ping {admin_mentions}" if admin_mentions else "Ping MODO"
            embed.title = f"🚨 {role_title} 🚨"

            embed.add_field(name="👤 Joueur", value=player_name, inline=True)
            embed.add_field(name="🕐 Heure", value=f"{date_str} {time_str}", inline=True)
            embed.add_field(name="💬 Message", value=admin_message or "No additional message", inline=False)
            
            # Add player side if available
            if player_team:
                try:
                    embed.add_field(name="⚑ Team", value=player_team, inline=True)
                except Exception:
                    pass
            # Post the detailed embed without controls
            await thread.send(embed=embed)

                        # Send initial controls panel (claim stage or already claimed)
            claimer = self.claimed_by.get(player_name)
            if claimer:
                controls_embed = discord.Embed(
                    title="🎛️ Statut du ticket",
                    description=f"Ticket de **{player_name}** - pris en charge par **{claimer}**",
                    timestamp=now
                )
                view = CloseTicketView(player_name, self)
            else:
                controls_embed = discord.Embed(
                    title="🎛️ Statut du ticket",
                    description=f"Ticket de **{player_name}** - en attente",
                    timestamp=now
                )
                view = ClaimTicketView(player_name, self)
            button_message = await thread.send(embed=controls_embed, view=view)
            self.active_button_messages[player_name] = button_message
            # This is the baseline status window; track only this one
            self.current_status_message[player_name] = button_message.id
            self.status_messages[player_name] = [button_message.id]
            
            print(f"Created admin request thread for {player_name}")
            
            # Send confirmation to player
            try:
                await self.crcon_client.send_message_to_player(
                    player_name,
                    "Votre ticket admin a bien été reçu ! Vous pouvez répondre à ce ticket en écrivant dans le chat (inutile de réutiliser !admin)."
                )
                print(f"Sent confirmation to player: {player_name}")
            except Exception as msg_error:
                print(f"Could not send confirmation to player: {msg_error}")
            
        except Exception as e:
            print(f"Error handling admin request: {e}")
            logger.error(f"Error handling admin request: {e}")

    async def handle_player_response(self, player_name: str, message: str, event_time: str):
    #"""Handle player response in game"""
        try:
            print(f"Player response received: {player_name} - {message}")
            
            if player_name not in self.active_threads:
                print(f"No active thread for {player_name}. Creating a new ticket with player's message…")
                await self.handle_admin_request(player_name, message)
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
                print(f"Thread for {player_name} was deleted, cleaning up tracking and recreating ticket…")
                # Clean up all tracking for this player
                if player_name in self.player_tickets:
                    del self.player_tickets[player_name]
                if player_name in self.active_threads:
                    del self.active_threads[player_name]
                if player_name in self.active_button_messages:
                    del self.active_button_messages[player_name]
                
                # Clean up CRCON tracking
                self.crcon_client.unregister_admin_thread(player_name)
                
                print(f"Recreating ticket for {player_name} with latest message…")
                await self.handle_admin_request(player_name, message)
                return
            
            # Apply NEW tag (player has responded, needs admin attention)
            await self.apply_forum_tag(thread, "NEW")
            
            # Create embed for player response (without redundant player name)
            response_embed = discord.Embed(
                title="💬 Réponse du joueur",
                description=message,  # Just the message, no player name since it's already in the thread title
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )
            
            if event_time:
                response_embed.set_footer(text=f"Game time: {event_time}")
            
            await thread.send(embed=response_embed)
            print(f"Player response posted to Discord forum")
            
            # Before adding a new status window, remove previous ones except the preserved claimed-status
            try:
                preserved_id = self.claim_status_message.get(player_name)
                ids = self.status_messages.get(player_name, [])
                keep: List[int] = []
                for mid in ids:
                    if preserved_id and mid == preserved_id:
                        keep.append(mid)
                        continue
                    try:
                        msg_obj = await thread.fetch_message(mid)
                        await msg_obj.delete()
                    except Exception:
                        pass
                self.status_messages[player_name] = keep
            except Exception:
                pass

            # Move button to bottom (no-op now; we edit the single status window)
            
            # Create new button message
                        # Create new controls message (respect claimed state)
            claimer = self.claimed_by.get(player_name)
            if claimer:
                button_embed = discord.Embed(
                    title="🎛️ Statut du ticket",
                    description=f"Ticket de **{player_name}** - pris en charge par **{claimer}**",
                    color=discord.Color.blue()
                )
                view = CloseTicketView(player_name, self)
            else:
                button_embed = discord.Embed(
                    title="🎛️ Statut du ticket",
                    description=f"Ticket de **{player_name}** - en attente",
                    color=discord.Color.blue()
                )
                view = ClaimTicketView(player_name, self)
            updated_msg = None
            msg_id = self.current_status_message.get(player_name)
            if msg_id:
                try:
                    existing = await thread.fetch_message(msg_id)
                    await existing.edit(embed=button_embed, view=view)
                    updated_msg = existing
                except Exception:
                    updated_msg = None
            if updated_msg is None:
                updated_msg = await thread.send(embed=button_embed, view=view)
            self.active_button_messages[player_name] = updated_msg
            self.current_status_message[player_name] = updated_msg.id
            # Delete any other previous status windows and track only this one
            try:
                ids = self.status_messages.get(player_name, [])
                for mid in ids:
                    if mid == updated_msg.id:
                        continue
                    try:
                        msg_obj = await thread.fetch_message(mid)
                        await msg_obj.delete()
                    except Exception:
                        pass
            except Exception:
                pass
            self.status_messages[player_name] = [updated_msg.id]
            
        except Exception as e:
            print(f"Error handling player response: {e}")
            logger.error(f"Error handling player response: {e}")
            # Fallback: if the thread/channel is gone, recreate a fresh ticket and post there
            try:
                if isinstance(e, discord.NotFound) or "Unknown Channel" in str(e):
                    print(f"Fallback: recreating ticket for {player_name} due to missing channel/thread")
                    # Cleanup stale tracking
                    if player_name in self.player_tickets:
                        del self.player_tickets[player_name]
                    if player_name in self.active_threads:
                        del self.active_threads[player_name]
                    if player_name in self.active_button_messages:
                        del self.active_button_messages[player_name]
                    self.crcon_client.unregister_admin_thread(player_name)
                    await self.handle_admin_request(player_name, message)
            except Exception as fallback_err:
                print(f"Fallback failed: {fallback_err}")

    async def handle_thread_message(self, message: discord.Message):
    #"""Handle messages in admin threads"""
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
                print(f"Could not find player for thread: {message.channel.name}")
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
                await message.add_reaction("✅")
                
            except Exception as e:
                print(f"Failed to send message to player {player_name}: {e}")
                await message.add_reaction("❌")
            
            # Auto-claim on first admin reply if not already claimed
            if player_name not in self.claimed_by:
                claimer = message.author.display_name
                self.claimed_by[player_name] = claimer
                
                # Update controls panel to reflect claimed state
                try:
                    # Remove previous controls if present
                    if player_name in self.active_button_messages:
                        try:
                            old_msg = self.active_button_messages[player_name]
                            await old_msg.edit(view=None)
                        except Exception:
                            pass
                    # Post claimed controls with Close button only
                    controls_embed = discord.Embed(
                        title="🎛️ Statut du ticket",
                        description=f"Ticket de **{player_name}** - pris en charge par **{claimer}**",
                        color=discord.Color.blue(),
                        timestamp=discord.utils.utcnow()
                    )
                    view = CloseTicketView(player_name, self)
                    new_msg = await message.channel.send(embed=controls_embed, view=view)
                    self.active_button_messages[player_name] = new_msg
                    # Preserve claimed status window and track it
                    try:
                        self.claim_status_message[player_name] = new_msg.id
                        arr = self.status_messages.get(player_name, [])
                        arr.append(new_msg.id)
                        self.status_messages[player_name] = arr
                    except Exception:
                        pass
                except Exception as panel_err:
                    print(f"? Failed to update claimed controls panel: {panel_err}")
        except Exception as e:
            print(f"Error handling thread message: {e}")
            logger.error(f"Error handling thread message: {e}")

    async def start(self):
    #"""Start the Discord bot"""
        try:
            token = self.config.get('discord.token')
            if not token:
                raise ValueError("Discord token not found in config")
            
            print(f"Starting Discord bot...")
            await self.bot.start(token)
            
        except Exception as e:
            print(f"Failed to start Discord bot: {e}")
            logger.error(f"Failed to start Discord bot: {e}")
            raise

