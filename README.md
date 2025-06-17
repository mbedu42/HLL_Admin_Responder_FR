# Hell Let Loose Admin Responder

Discord bot that automatically creates forum posts when players request admin help in-game. Admins can respond directly from Discord and messages are sent back to players.

## This currently only supports Single Servers. I will work on Multiple Server unless someone beats me to it.

## Features

- **Real-time Monitoring**: Watches HLL server for `!admin` commands
- **Discord Forum Posts**: Auto-creates tickets with tagging (NEW/REPLIED/CLOSED)
- **Two-way Chat**: Reply in Discord → message sent to player in-game
- **Smart Prevention**: One ticket per player, prevents spam
- **Tmux Session**: Run in background with easy log access

## How It Works

1. Player types `!admin` command in-game
2. Bot detects command via CRCON logs
3. Creates Discord forum post with NEW tag
4. Mentions admin roles (if configured)
5. Admin responds in Discord thread
6. Bot sends admin message to player in-game
7. Forum tag changes to REPLIED
8. Player replies via in game chat, no need to use !admin again
9. Admin closes ticket when resolved
10. Player receives close confirmation

## Pre-Installation Setup

### 1. Discord Bot Setup

**Create Discord Bot:**
1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Click "New Application" and give it a name
3. Go to "Bot" section and click "Add Bot"
4. Copy the bot token (you'll need this later)
5. Under "Privileged Gateway Intents" enable:
   - **Message Content Intent**

**Bot Permissions:**
Generate an invite link with these permissions:
- Send Messages
- Create Forum Posts
- Manage Threads
- Use External Emojis
- Add Reactions
- Mention Everyone (for admin role mentions)

**Invite Bot to Server:**
Use the generated invite link to add the bot to your Discord server.

**Create Forum Channel:**
1. Create a new forum channel in your Discord server
2. Right-click the forum channel → "Copy Channel ID"
3. Save this ID (you'll need it for configuration)

### 2. CRCON Access Setup

**Required CRCON Permissions:**
Your CRCON account must have at least:
- **api|rcon user|Can message players**
- **api|logs|Can view logs**

**Information Needed:**
- CRCON server URL (e.g., `http://your-server-ip:8010`)
- CRCON API

## Installation

### 1. Prepare Information

Before starting, have these ready:
- ✅ Discord bot token
- ✅ Discord forum channel ID
- ✅ CRCON server URL
- ✅ CRCON API
- ✅ Admin role IDs (optional)

### 2. Clone the Repository

```bash
git clone https://github.com/SpinexLive/HLL_Admin_Responder
cd HLL_Admin_Responder
```

### 3. Run the Auto-Installer

```bash
chmod +x install.sh
./install.sh
```

The installer will:
- Install dependencies (Python, tmux, etc.)
- Set up virtual environment
- Prompt you to configure `.env`
- Start the bot immediately in a tmux session

### 4. Configure Environment Variables

When prompted (or manually edit):
```bash
nano .env
```

Enter your prepared information:
```env
# RCON Settings
RCON_HOST=your_rcon_host
RCON_PORT=your_rcon_port
RCON_PASSWORD=your_rcon_password

# Discord Settings
DISCORD_TOKEN=your_discord_bot_token
DISCORD_GUILD_ID=your_discord_guild_id
DISCORD_ADMIN_CHANNEL_ID=your_discord_admin_channel_id
DISCORD_ADMIN_ROLES=role_id_1,role_id_2,role_id_3

# CRCON Settings
CRCON_BASE_URL=http://your_crcon_host:port
CRCON_API_TOKEN=your_crcon_api_token
```

> [!IMPORTANT]
> - Save changes with `Ctrl`+`O` (then press `ENTER`)
> - Exit nano with `Ctrl`+`X`

## Bot Management with Tmux

The bot runs in a tmux session for easy management:

```bash
# View bot logs (attach to session)
tmux attach -t hll-admin

# Detach from session (keep bot running)
# Press: Ctrl+B then D

# Check if bot is running
tmux list-sessions

# Restart the bot
tmux kill-session -t hll-admin
tmux new-session -d -s hll-admin -c "$(pwd)" "source venv/bin/activate && python run.py"

# Stop the bot completely
tmux kill-session -t hll-admin
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

## Manual Installation

If you prefer manual setup:

```bash
# Install dependencies
sudo apt update && sudo apt install python3 python3-pip python3-venv tmux -y

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install packages
pip install -r requirements.txt

# Configure environment
cp .env.example .env
nano .env

# Start in tmux session
tmux new-session -d -s hll-admin "source venv/bin/activate && python run.py"
```

## Tmux Quick Reference

```bash
# Attach to bot session
tmux attach -t hll-admin

# Detach from session (keep running)
Ctrl+B then D

# Scroll up in tmux (view logs)
Ctrl+B then [
# Use arrow keys to scroll, press Q to exit scroll mode

# Kill session (stop bot)
tmux kill-session -t hll-admin

# List all sessions
tmux list-sessions

# Create new session
tmux new-session -s session-name
```

## Troubleshooting

**Check if bot is running:**
```bash
tmux list-sessions
```

**View bot logs:**
```bash
tmux attach -t hll-admin
```

**Bot crashed or not responding:**
```bash
# Restart the bot
tmux kill-session -t hll-admin
cd HLL_Admin_Responder
source venv/bin/activate
tmux new-session -d -s hll-admin "python run.py"
```

**CRCON connection issues:**
- Verify URL is accessible: `curl http://your-crcon-server:8010`
- Check API `.env`
- Ensure CRCON API is enabled
- Verify account permissions

**Discord not working:**
- Check bot token is correct
- Verify forum channel ID
- Ensure bot has required permissions
- Check bot is in Discord server

## Getting Discord IDs

**Forum Channel ID:**
1. Right-click forum channel → "Copy Channel ID"
2. If you don't see this option, enable Developer Mode in Discord settings

**Role IDs (for mentions):**
1. Right-click role → "Copy Role ID"
2. Add multiple roles separated by commas in `.env`


## License

This project is licensed under the MIT License.