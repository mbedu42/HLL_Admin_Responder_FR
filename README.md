# Hell Let Loose Admin Responder

Discord bot that creates forum posts when players request admin help in-game. It
can monitor several CRCON instances at once and route each game server to its own
Discord forum.

## Features

- **Multi-server routing**: one CRCON WebSocket and one Discord forum per server
- **Stable player tracking**: tickets use CRCON `player_id`, not the display name
- **Real-time Monitoring**: Watches HLL servers for `!admin` commands
- **Discord Forum Posts**: Auto-creates tickets with tagging (NEW/REPLIED/CLOSED)
- **Two-way Chat**: Reply in Discord → message sent to player in-game
- **Smart Prevention**: One ticket per player, prevents spam
- **Auto Close**: Tickets close automatically after 90 minutes of inactivity
- **Outage Tickets**: CRCON/API/log-stream failures create one deduplicated
  Discord incident thread, ping the configured outage contacts, add diagnostic
  details, and close after a verified recovery
- **Background Service**: Run with systemd or tmux

## How It Works

1. Player types `admin` command in-game
2. Bot reads both `player_id` and the current display name from the CRCON log
3. Creates a post in the forum configured for that game server, with the NEW tag
4. Mentions admin roles (if configured)
5. Admin responds in Discord thread
6. Bot sends admin message to player in-game
7. Forum tag changes to REPLIED
8. Player replies via in game chat, no need to use !admin again
9. Admin closes ticket when resolved
10. Player receives close confirmation

### Outage Monitoring

Each CRCON client reports health transitions to its configured Discord forum.
The first API, WebSocket, malformed-payload, or server-reported log-stream
failure creates an `OUTAGE` thread and mentions only that server's configured
outage contacts.
Repeated identical failures are counted without creating duplicate tickets. If
the failure changes (for example, an HTTP 502 becomes "Log stream is not
enabled"), the existing incident receives an update. After the WebSocket sends
a valid payload, the bot posts the outage duration and error count, applies the
`CLOSED` tag, and archives the incident.

Discord cannot receive an alert while Discord itself is unreachable. Health
events are therefore queued and delivered in order when the bot reconnects.

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

**Create Forum Channels:**
1. Create one forum channel for each game server
2. Right-click the forum channel → "Copy Channel ID"
3. Save this ID (you'll need it for configuration)

### 2. CRCON Access Setup

**Required CRCON Permissions:**
The API user on every CRCON instance needs:

- `api.can_view_get_status`
- `api.can_view_structured_logs`
- `api.can_message_players`

The same raw API key may be registered on several CRCON instances. Separate keys
are preferable when operational key rotation needs to be independent.

**Information Needed:**
- One HTTPS CRCON URL per game server
- An API key registered on every configured CRCON

## Installation

### 1. Prepare Information

Before starting, have these ready:
- ✅ Discord bot token
- ✅ One Discord forum channel ID per game server
- ✅ One CRCON URL per game server
- ✅ CRCON API key(s)
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
# Discord account shared by all game servers
DISCORD_TOKEN=your_discord_bot_token
DISCORD_GUILD_ID=your_discord_guild_id
DISCORD_ADMIN_ROLES=role_id_1,role_id_2,role_id_3
DISCORD_OUTAGE_USER_IDS=user_id_1,user_id_2

# Dynamic array: each object is one complete game-server route
GAME_SERVERS='[
  {
    "id": "ww2",
    "name": "HLL Classique",
    "rcon": {
      "host": "game-server.example.com",
      "port": 7777,
      "password": "your_ww2_rcon_password"
    },
    "crcon": {
      "base_url": "https://modo.ww2.example.com",
      "api_token": "your_ww2_crcon_api_token"
    },
    "discord": {
      "channel_id": "your_ww2_forum_channel_id"
    }
  },
  {
    "id": "vietnam",
    "name": "HLL Vietnam",
    "rcon": {
      "host": "vietnam-game-server.example.com",
      "port": 7777,
      "password": "your_vietnam_rcon_password"
    },
    "crcon": {
      "base_url": "https://modo.viet.example.com",
      "api_token": "your_vietnam_crcon_api_token"
    },
    "discord": {
      "channel_id": "your_vietnam_forum_channel_id"
    }
  }
]'
```

`GAME_SERVERS` is the only server inventory. Add, remove or reorder complete
objects to change the monitored servers; no Python or YAML change is needed.
Every object must contain:

- a unique `id` using lowercase letters, digits, `_` or `-`;
- the game server's RCON `host`, `port` and `password`;
- its CRCON `base_url` and `api_token`;
- the target Discord forum `channel_id`.

`name` is optional and controls the server label shown in Discord. A per-server
`discord.admin_roles` array may override the global `DISCORD_ADMIN_ROLES` list.
Likewise, `discord.outage_user_ids` may override `DISCORD_OUTAGE_USER_IDS`.
Outage alerts mention these individual users instead of the ticket admin roles.
The `.env` value is JSON: keep its outer single quotes and JSON double quotes.

The old global `RCON_*`, `CRCON_BASE_URL`, `CRCON_API_TOKEN` and per-server URL
variables are no longer needed. Legacy YAML configuration is still understood
by the code for compatibility, but `GAME_SERVERS` takes priority when present.

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
- Verify each status endpoint with the matching bearer token
- Verify that HTTPS and `wss://.../ws/logs` are accessible
- Check every server entry and environment variable
- Verify all three required CRCON permissions listed above

Successful startup logs contain one `Connected to CRCON API` and one
`WebSocket stream started` line per configured server.

**Discord not working:**
- Check bot token is correct
- Verify forum channel ID
- Ensure bot has required permissions
- Check bot is in Discord server

## Getting Discord IDs

**Forum Channel IDs:**
1. Right-click each forum channel → "Copy Channel ID"
2. If you don't see this option, enable Developer Mode in Discord settings

**Role IDs (for mentions):**
1. Right-click role → "Copy Role ID"
2. Add multiple roles separated by commas in `.env`


## License

This project is licensed under the MIT License.
