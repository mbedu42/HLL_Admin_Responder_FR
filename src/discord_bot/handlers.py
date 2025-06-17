import discord
import logging
import asyncio
from typing import Optional
from discord import Thread, Message
from discord.ext import commands
from crcon.client import RCONClient

logger = logging.getLogger(__name__)

class AdminRequestHandler:
    """Handler for admin request threads"""
    
    def __init__(self, bot, rcon_client):
        self.bot = bot
        self.rcon_client = rcon_client
    
    async def create_admin_embed(self, player_name: str, message: str) -> discord.Embed:
        """Create embed for admin request"""
        embed = discord.Embed(
            title="🚨 Admin Request",
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow()
        )
        
        embed.add_field(name="Player", value=player_name, inline=True)
        embed.add_field(name="Server", value="Hell Let Loose", inline=True)
        embed.add_field(name="Message", value=message or "No message provided", inline=False)
        
        embed.set_footer(text="Reply in this thread to communicate with the player")
        
        return embed
    
    async def send_player_notification(self, player_name: str, success: bool = True):
        """Send notification to player about their request"""
        if success:
            message = "✅ Admin request received! Admins have been notified and will assist you shortly."
        else:
            message = "❌ There was an issue processing your admin request. Please try again."
        
        await self.rcon_client.send_message_to_player(player_name, message)
    
    def extract_player_from_thread_name(self, thread_name: str) -> Optional[str]:
        """Extract player name from thread name"""
        if "Admin Request -" in thread_name:
            return thread_name.replace("Admin Request -", "").strip()
        return None
    
    async def archive_thread_after_delay(self, thread: discord.Thread, delay_minutes: int = 30):
        """Archive thread after specified delay"""
        import asyncio
        
        await asyncio.sleep(delay_minutes * 60)
        
        try:
            if not thread.archived:
                await thread.edit(archived=True)
                logger.info(f"Auto-archived thread: {thread.name}")
        except Exception as e:
            logger.error(f"Failed to archive thread {thread.name}: {e}")

class DiscordHandlers:
    def __init__(self, bot: commands.Bot, rcon_client: RCONClient):
        self.bot = bot
        self.rcon_client = rcon_client

    async def on_admin_command(self, message: Message):
        if message.content.startswith('!admin'):
            thread = await message.channel.create_thread(name=f"Admin Thread - {message.author.name}", auto_archive_duration=60)
            await thread.send(f"Admin command received from {message.author.name}. Please respond here.")

            def check(response: Message):
                return response.channel == thread and response.author == message.author

            try:
                response = await self.bot.wait_for('message', check=check, timeout=300)
                await self.handle_admin_response(response, message.author)
            except asyncio.TimeoutError:
                await thread.send("No response received in time.")

    async def handle_admin_response(self, response: Message, player):
        command = response.content
        result = self.rcon_client.send_command(command)
        await response.channel.send(f"Response to {player.name}: {result}")