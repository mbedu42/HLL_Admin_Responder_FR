# Hell Let Loose Admin Responder

Discord bot that automatically creates forum posts when players request admin help in-game. Admins can respond directly from Discord and messages are sent back to players.

## Features

- **Real-time Monitoring**: Watches HLL server for `!admin` commands
- **Discord Forum Posts**: Auto-creates tickets with tagging (NEW/REPLIED/CLOSED)
- **Two-way Chat**: Reply in Discord → message sent to player in-game
- **Smart Prevention**: One ticket per player, prevents spam
- **Auto-Start**: Runs on boot, restarts if crashed

## Requirements

- Linux VPS (Ubuntu 20.04+)
- Python 3.8+
- 512MB RAM minimum
- CRCON server access
- Discord bot

## Mandatory CRCON Permissions

Your CRCON account must have at least these permissions:
- **api|rcon user|Can message players**
- **api|logs|Can view logs**

## Mandatory Discord Bot Permissions

- Send Messages
- Create Forum Posts
- Manage Threads
- Use External Emojis
- Add Reactions
- Mention Everyone (for admin role mentions)

**Under Bot (Privileged Gateway Intents)**
- Message Content Intent

## Installation

**1. Clone/Upload the Repository**
   
   Upload the project files to your Linux VPS or clone:
   ```bash
   git clone https://github.com/SpinexLive/HLL_Admin_Responder
   cd HLL_Admin_Responder
   ```

**2. Quick Install (Recommended)**
   
   Run the auto-installer:
   ```bash
   chmod +x install.sh
   ./install.sh
   ```

**3. Configure Environment Variables**
   
   Edit the configuration file:
   ```bash
   nano .env
   ```
   
   Configure your settings:
   ```env
   DISCORD_TOKEN=your_discord_bot_token
   DISCORD_ADMIN_CHANNEL_ID=your_forum_channel_id
   CRCON_BASE_URL=http://your-crcon-server:8010
   CRCON_USERNAME=your_crcon_username
   CRCON_PASSWORD=your_crcon_password
   ```

> [!IMPORTANT]
> - Save changes with `Ctrl`+`O` (then press `ENTER`)
> - Exit nano with `Ctrl`+`X`

**4. Start the Service**
   ```bash
   sudo systemctl start hll-admin-responder
   ```

## Discord Setup

1. **Create Discord Bot**
   - Go to [Discord Developer Portal](https://discord.com/developers/applications)
   - Create new application and bot
   - Copy bot token for `.env` file

2. **Invite Bot to Server**
   - Generate invite link with required permissions
   - Add bot to your Discord server

3. **Create Forum Channel**
   - Create a forum channel in Discord
   - Right-click → Copy Channel ID
   - Add ID to `.env` file

## Manual Installation

If you prefer manual setup:

```bash
# Install dependencies
sudo apt update && sudo apt install python3 python3-pip python3-venv -y

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install packages
pip install -r requirements.txt

# Configure environment
cp .env.example .env
nano .env

# Run manually
python run.py
```

## Usage

**Players type in-game:**
- `!admin` - Request admin help
- `!admin I need help with teamkilling` - Request with message
- `!admin stuck in geometry` - Specific issue

**Admin Workflow:**
1. Bot creates Discord forum post
2. Admin replies in forum thread
3. Message automatically sent to player in-game
4. Click "Close Ticket" button when resolved

## Service Management

```bash
# Start the bot
sudo systemctl start hll-admin-responder

# Stop the bot
sudo systemctl stop hll-admin-responder

# Restart the bot
sudo systemctl restart hll-admin-responder

# Check status
sudo systemctl status hll-admin-responder

# View live logs
sudo journalctl -u hll-admin-responder -f

# Enable auto-start (done by installer)
sudo systemctl enable hll-admin-responder
```

## How It Works

1. Player types `!admin` command in-game
2. Bot detects command via CRCON logs
3. Creates Discord forum post with NEW tag
4. Mentions admin roles (if configured)
5. Admin responds in Discord thread
6. Bot sends admin message to player in-game
7. Forum tag changes to REPLIED
8. Admin closes ticket when resolved
9. Player receives close confirmation

## Troubleshooting

**Bot not starting?**
```bash
sudo journalctl -u hll-admin-responder -f
```

**CRCON connection issues?**
- Verify URL is accessible: `curl http://your-crcon-server:8010`
- Check username/password in `.env`
- Ensure CRCON API is enabled
- Verify account permissions

**Discord not working?**
- Check bot token is correct
- Verify forum channel ID
- Ensure bot has required permissions
- Check bot is in Discord server

**Permission errors?**
```bash
# Fix file ownership
sudo chown -R $USER:$USER /path/to/HLL_Admin_Responder/

# Make script executable
chmod +x install.sh
```

## Configuration Options

### Optional Admin Role Mentions

Add admin roles to be mentioned on new tickets:
```env
DISCORD_ADMIN_ROLES=role_id_1,role_id_2,role_id_3
```

### Logging Level

Adjust logging verbosity:
```env
LOGGING_LEVEL=INFO
```

## Project Structure

```
HLL_Admin_Responder/
├── src/
│   ├── main.py               # Application entry point
│   ├── crcon/                # CRCON API client
│   ├── discord_bot/          # Discord bot implementation
│   └── utils/                # Configuration utilities
├── config/
│   └── config.yaml           # Alternative config file
├── install.sh                # Auto-installation script
├── run.py                    # Bot launcher
├── requirements.txt          # Python dependencies
├── .env.example              # Environment template
└── README.md                 # This file
```

## Logging

Logs are accessible via systemd:
```bash
# View recent logs
sudo journalctl -u hll-admin-responder --no-pager

# Follow logs in real-time
sudo journalctl -u hll-admin-responder -f

# View logs from specific time
sudo journalctl -u hll-admin-responder --since "2024-01-01 12:00:00"
```

## License

This project is licensed under