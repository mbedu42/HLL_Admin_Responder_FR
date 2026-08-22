import asyncio
import logging
import signal

from dotenv import load_dotenv


# run.py changes the working directory to src before importing this file.
load_dotenv("../.env")

from crcon.client import CRCONClient
from discord_bot.bot import DiscordBot
from utils.config import Config


async def main():
    config = Config("../config/config.yaml")
    if not config.get("discord.token"):
        raise ValueError("DISCORD_TOKEN is missing")

    servers = config.get_servers()
    log_level = getattr(logging, str(config.get("logging.level", "INFO")).upper())
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    clients = {
        server["id"]: CRCONClient(config, server) for server in servers
    }
    discord_bot = DiscordBot(config, clients)

    logging.info(
        "Starting HLL Admin Responder for %s",
        ", ".join(
            f"{server['name']} ({server['id']})" for server in servers
        ),
    )

    tasks = [
        asyncio.create_task(client.start_monitoring(), name=f"crcon-{server_id}")
        for server_id, client in clients.items()
    ]
    tasks.append(asyncio.create_task(discord_bot.start(), name="discord"))

    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        raise
    finally:
        for client in clients.values():
            client.stop_monitoring()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await discord_bot.close()
        await asyncio.gather(
            *(client.close_session() for client in clients.values()),
            return_exceptions=True,
        )


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal.default_int_handler)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped")
