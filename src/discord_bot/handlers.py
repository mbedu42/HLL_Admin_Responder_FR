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
            title="🚨 Ping MODO",
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow()
        )
        
        embed.add_field(name="Joueur", value=player_name, inline=True)
        embed.add_field(name="Serveur", value="Hell Let Loose", inline=True)
        embed.add_field(name="Message", value=message or "Aucun message fourni", inline=False)
        
        embed.set_footer(text="Répondez dans ce fil pour communiquer avec le joueur")
        
        return embed
    
    async def send_player_notification(self, player_name: str, success: bool = True):
        """Send notification to player about their request"""
        if success:
            message = "Requête admin reçue ! Les admins ont été avertis sur Discord, et vont vous assister sous peu."
        else:
            message = "Un problème est survenu lors du traitement de votre requête admin. Veuillez réessayer."
        
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
            thread = await message.channel.create_thread(name=f"Fil Admin - {message.author.name}", auto_archive_duration=60)
            await thread.send(f"Commande admin reçue de {message.author.name}. Merci de répondre ici.")

            def check(response: Message):
                return response.channel == thread and response.author == message.author

            try:
                response = await self.bot.wait_for('message', check=check, timeout=300)
                await self.handle_admin_response(response, message.author)
            except asyncio.TimeoutError:
                await thread.send("Aucune réponse reçue à temps.")

    async def handle_admin_response(self, response: Message, player):
        command = response.content
        result = self.rcon_client.send_command(command)
        await response.channel.send(f"Réponse à {player.name} : {result}")
