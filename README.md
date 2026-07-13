# Hell Let Loose Admin Responder

Discord bot that automatically creates forum posts when players request admin help in-game. Admins can respond directly from Discord and messages are sent back to players.

## This currently only supports Single Servers. I will work on Multiple Server unless someone beats me to it.

## Features

- **Real-time Monitoring**: Watches HLL server for `!admin` commands
- **Discord Forum Posts**: Auto-creates tickets with tagging (NEW/REPLIED/CLOSED)
- **Two-way Chat**: Reply in Discord → message sent to player in-game
- **Smart Prevention**: One ticket per player, prevents spam
- **Auto Close**: Tickets close automatically after 90 minutes of inactivity
- **Background Service**: Run with systemd or tmux

## How It Works

1. Player types `admin` command in-game
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

### Ticket Auto-Close Settings

In `config/config.yaml` you can control the inactivity timer:

```yaml
tickets:
  auto_close_minutes: 90        # minutes of silence before a ticket closes
  inactivity_check_interval_seconds: 60
```

The defaults close tickets after 90 minutes without any chat from the player or admins. Lower the number if you want faster cleanup, or raise it for longer-running investigations.

> [!IMPORTANT]
> - Save changes with `Ctrl`+`O` (then press `ENTER`)
> - Exit nano with `Ctrl`+`X`

## Bot Management

Use **one launch method only**. Do not run `python run.py`, `python main.py`, or
start a tmux copy while the systemd service is active; doing so creates duplicate
Discord notifications.

### Identify the Launch Method

Run these commands from any directory:

```bash
# This VPS normally uses systemd. "active" means use the systemd commands below.
systemctl is-active hll-admin

# Only check tmux when the systemd command reports "inactive" or "unknown".
tmux -L hll list-sessions
```

An empty tmux session list is normal when systemd is running the bot.

### Systemd (Current VPS)

These are the commands to use on the current VPS:

```bash
# Status
systemctl status hll-admin --no-pager

# Show the latest 100 log lines
journalctl -u hll-admin -n 100 --no-pager

# Follow logs live (Ctrl+C exits the log view without stopping the bot)
journalctl -u hll-admin -f

# Restart after a configuration or code change
sudo systemctl restart hll-admin

# Stop and start
sudo systemctl stop hll-admin
sudo systemctl start hll-admin
```

To update the code and restart cleanly:

```bash
cd ~/HLL_Admin_Responder_FR
sudo systemctl stop hll-admin
git pull --ff-only
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl start hll-admin
systemctl status hll-admin --no-pager
```

### Tmux (Alternative Only)

Use this section only on an installation without an active systemd service.
`start.py --detached` uses the tmux socket named `hll`:

```bash
cd ~/HLL_Admin_Responder_FR

# Start or restart in the background
venv/bin/python start.py --detached

# Check status
tmux -L hll list-sessions

# View the bot console
tmux -L hll attach -t hll-admin

# Detach without stopping: press Ctrl+B, then D

# Stop
tmux -L hll kill-session -t hll-admin

# Follow the persistent log
tail -f logs/tmux-hll-admin.log
```

### Check for Duplicate Bots

The normal systemd process tree includes the `start.py` and `run.py` wrappers,
but there must be only one `main.py` bot process:

```bash
pgrep -af '[p]ython.*main\.py'
```

If this prints more than one line, restart the managed service instead of
starting another copy:

```bash
sudo systemctl restart hll-admin
pgrep -af '[p]ython.*main\.py'
```

## Usage

**Players type in-game:**
- `admin` - Request admin help
- `admin I need help with teamkilling` - Request with message
- `admin stuck in geometry` - Specific issue

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

# Start in a managed tmux session
venv/bin/python start.py --detached
```

Use the commands in **Bot Management > Tmux (Alternative Only)** afterward.

## Troubleshooting

**Check the current VPS:**
```bash
systemctl status hll-admin --no-pager
journalctl -u hll-admin -n 100 --no-pager
pgrep -af '[p]ython.*main\.py'
```

**Restart the current VPS bot:**
```bash
sudo systemctl restart hll-admin
systemctl status hll-admin --no-pager
```

**The service is inactive:**
```bash
sudo systemctl start hll-admin
journalctl -u hll-admin -n 100 --no-pager
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
