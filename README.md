# Hell Let Loose RCON Discord Bot

This project is a tool that integrates a Hell Let Loose RCON client with a Discord bot. It allows players to interact with the game server through Discord, specifically enabling an admin command that creates a thread in Discord for in-game administration.

## Features

- Connects to a Hell Let Loose server via RCON
- Listens for the `!admin` command in-game chat
- Creates a dedicated Discord thread for each admin request
- Sends replies from Discord directly back to the in-game player
- Automatic thread archiving after inactivity
- In-memory tracking to prevent duplicate requests

## Project Structure

```
hll-rcon-discord-bot/
├── src/
│   ├── main.py               # Entry point of the application
│   ├── rcon/                 # RCON client module
│   │   ├── __init__.py
│   │   ├── client.py         # Handles RCON connection and monitoring
│   │   └── commands.py       # RCON command helpers
│   ├── discord_bot/          # Discord bot module
│   │   ├── __init__.py
│   │   ├── bot.py            # Discord bot implementation
│   │   └── handlers.py       # Discord event handlers
│   └── utils/                # Utility functions
│       ├── __init__.py
│       └── config.py         # Configuration loader
├── config/
│   └── config.yaml           # Configuration file
├── requirements.txt          # Python dependencies
├── .env.example             # Environment variables template
└── README.md                # This file
```

## Installation

1. **Clone or download the project:**
   ```bash
   git clone <repository-url>
   cd hll-rcon-discord-bot
   ```

2. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Create Discord Bot:**
   - Go to [Discord Developer Portal](https://discord.com/developers/applications)
   - Create a new application and bot
   - Copy the bot token
   - Invite the bot to your server with permissions:
     - Send Messages
     - Create Public Threads
     - Manage Threads
     - Add Reactions

4. **Configure the bot:**
   
   **Option A: Using config.yaml**
   ```yaml
   # config/config.yaml
   discord:
     token: "YOUR_DISCORD_BOT_TOKEN"
     guild_id: YOUR_DISCORD_SERVER_ID
     admin_channel_id: YOUR_ADMIN_CHANNEL_ID
   
   rcon:
     host: "YOUR_HLL_SERVER_IP"
     port: 27015
     password: "YOUR_RCON_PASSWORD"
   
   logging:
     level: "INFO"
   ```
   
   **Option B: Using environment variables**
   ```bash
   # Copy .env.example to .env and fill in your values
   cp .env.example .env
   ```
   ```env
   # .env
   DISCORD_TOKEN=your_discord_bot_token_here
   DISCORD_GUILD_ID=your_guild_id_here
   DISCORD_ADMIN_CHANNEL_ID=your_admin_channel_id_here
   RCON_HOST=your_hll_server_ip_here
   RCON_PORT=27015
   RCON_PASSWORD=your_rcon_password_here
   ```

## Configuration Details

### Discord Settings
- **token**: Your Discord bot token from the Developer Portal
- **guild_id**: Your Discord server ID (right-click server → Copy Server ID)
- **admin_channel_id**: Channel ID where admin threads will be created

### RCON Settings
- **host**: IP address of your Hell Let Loose server
- **port**: RCON port (usually 27015)
- **password**: RCON password set in your server config

## Usage

1. **Start the bot:**
   ```bash
   cd src
   python main.py
   ```

2. **In-game usage:**
   - Players type `!admin` in chat to request help
   - Players can add a message: `!admin I'm stuck in geometry`
   - Bot automatically detects these requests and creates Discord threads

3. **Discord usage:**
   - Admin threads are created in your specified channel
   - Reply in the thread to send messages directly to the player
   - Messages are prefixed with `[ADMIN YourName]:` in-game
   - Bot adds ✅ reaction to confirm messages were sent

## How It Works

1. **Monitoring**: Bot continuously monitors HLL chat logs via RCON
2. **Detection**: When `!admin` is found, creates a Discord thread
3. **Communication**: Discord replies are sent directly to the player in-game
4. **Tracking**: In-memory tracking prevents duplicate requests
5. **Cleanup**: Threads auto-archive after 1 hour of inactivity

## Troubleshooting

### Common Issues

**Bot not connecting to RCON:**
- Verify server IP, port, and password
- Check if RCON is enabled in server config
- Ensure firewall allows RCON connections

**Bot not creating threads:**
- Verify Discord permissions
- Check channel ID is correct
- Ensure bot is in the server

**Messages not sending to players:**
- Check RCON connection status
- Verify player names match exactly
- Check server logs for RCON errors

### Logs
The bot logs important events. Check console output for:
- Connection status
- Admin requests detected
- Messages sent/received
- Errors and warnings

## Contributing

Contributions are welcome! Please feel free to submit a pull request or open an issue for any enhancements or bug fixes.

## License

This project is licensed under the MIT License. See the LICENSE file for details.