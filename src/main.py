# main.py

import asyncio
import logging
import signal
import sys
from dotenv import load_dotenv
import os

# Load environment variables from .env file (look in parent directory)
load_dotenv('../.env')

from utils.config import Config
from crcon.client import CRCONClient
from discord_bot.bot import DiscordBot

async def main():
    # Load configuration from the config folder (go up one level from src)
    config = Config("../config/config.yaml")
    
    # Verify critical config is loaded
    if not config.get('discord.token'):
        print("Discord token not found in configuration or environment variables")
        print("Make sure you have created a .env file with your Discord token")
        return
    
    if not config.get('crcon.base_url'):
        print("CRCON base URL not found in configuration or environment variables")
        print("Make sure you have set CRCON_BASE_URL in your .env file")
        return
    
    print(f" Configuration loaded successfully")
    print(f" RCON Host: {config.get('rcon.host')}")
    print(f" Discord Guild ID: {config.get('discord.guild_id')}")
    print(f" Admin Channel ID: {config.get('discord.admin_channel_id')}")
    print(f" Admin Roles: {config.get('discord.admin_roles')}")
    
    # Setup logging
    log_level = getattr(logging, config.get('logging.level', 'INFO').upper())
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Initialize CRCON client
    crcon_client = CRCONClient(config)
    
    # Initialize Discord bot
    discord_bot = DiscordBot(config, crcon_client)
    
    print(f" Starting HLL RCON Discord Bot...")
    
    # Start both services concurrently
    try:
        await asyncio.gather(
            crcon_client.start_monitoring(),
            discord_bot.start()
        )
        
    except KeyboardInterrupt:
        print("\n Shutdown requested by user")
    except asyncio.CancelledError:
        print("\n Tasks cancelled during shutdown")
    except Exception as e:
        print(f"\n Unexpected error: {e}")
    finally:
        print(" Cleaning up...")
        # Add any cleanup code here if needed
        print(" Shutdown complete")

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    print(f"\n Received signal {signum}, shutting down...")
    sys.exit(0)

if __name__ == "__main__":
    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n Bot stopped successfully")
    except Exception as e:
        print(f"\n Fatal error: {e}")
