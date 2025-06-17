# Hell Let Loose Admin Responder

Discord bot that automatically creates forum posts when players request admin help in-game. Admins can respond directly from Discord and messages are sent back to players.

## Features

- **Real-time Monitoring**: Watches HLL server for `!admin` commands
- **Discord Forum Posts**: Auto-creates tickets with tagging (NEW/REPLIED/CLOSED)
- **Two-way Chat**: Reply in Discord → message sent to player in-game
- **Smart Prevention**: One ticket per player, prevents spam
- **Tmux Session**: Run in background with easy log access

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

**2. Run the Auto-Installer**
   
   ```bash
   chmod +x install.sh
   ./install.sh
   ```
   
   The installer will:
   - Install dependencies (Python, tmux, etc.)
   - Set up virtual environment
   - Prompt you to configure `.env`
   - Start the bot immediately in a tmux session

**3. Configure Environment Variables**
   
   If you didn't configure during install:
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
- Check username/password in `.env`
- Ensure CRCON API is enabled
- Verify account permissions

**Discord not working:**
- Check bot token is correct
- Verify forum channel ID
- Ensure bot has required permissions
- Check bot is in Discord server

## Configuration Options

### Optional Admin Role Mentions

Add admin roles to be mentioned on new tickets:
```env
DISCORD_ADMIN_ROLES=role_id_1,role_id_2,role_id_3
```

## Quick Start Summary

1. Upload project files to VPS
2. Run `chmod +x install.sh && ./install.sh`
3. Configure `.env` when prompted
4. Bot starts automatically in tmux
5. Use `tmux attach -t hll-admin` to view logs
6. Press `Ctrl+B then D` to detach and keep bot running

## License

This project is licensed under the MIT License.