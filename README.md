# Hell Let Loose Admin Responder

This project integrates a Hell Let Loose CRCON client with a Discord bot to provide seamless admin support. It monitors in-game chat for admin requests and creates Discord forum posts for efficient admin response management.

## Features

- **Real-time Monitoring**: Continuously monitors HLL server logs via CRCON API
- **Forum Integration**: Creates Discord forum posts for each admin request with automatic tagging
- **Two-way Communication**: Send replies from Discord directly back to players in-game
- **Admin Controls**: Close ticket button with confirmation messages
- **Smart Tagging**: Automatic forum tags (NEW → REPLIED → CLOSED)
- **Admin Mentions**: Configurable role mentions for urgent requests
- **Duplicate Prevention**: Intelligent tracking to prevent spam requests
- **Timestamped Requests**: All requests include detailed timestamps

## Project Structure

```
HLL_Admin_Responder/
├── src/
│   ├── main.py               # Application entry point
│   ├── crcon/                # CRCON client module
│   │   ├── __init__.py
│   │   └── client.py         # CRCON API integration
│   ├── discord_bot/          # Discord bot module
│   │   ├── __init__.py
│   │   └── bot.py            # Discord forum bot implementation
│   └── utils/                # Utility functions
│       ├── __init__.py
│       └── config.py         # Configuration management
├── config/
│   └── config.yaml           # Main configuration file
├── run.py                    # Bot launcher script
├── requirements.txt          # Python dependencies
├── .env.example             # Environment variables template
└── README.md                # This documentation
```

## Installation

1. **Download the project:**
   ```bash
   # Extract to your desired location
   cd HLL_Admin_Responder
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
     - Create Forum Posts
     - Manage Threads
     - Use External Emojis
     - Add Reactions
     - Mention Everyone (for admin role mentions)

4. **Set up Discord Forum Channel:**
   - Create a forum channel in your Discord server
   - Copy the channel ID (right-click channel → Copy Channel ID)
   - The bot will automatically create forum tags: NEW, REPLIED, CLOSED

## Configuration

### Using Environment Variables
```bash
# Copy .env.example to .env and configure
cp .env.example .env
```
```env
# .env
DISCORD_TOKEN=your_discord_bot_token_here
DISCORD_ADMIN_CHANNEL_ID=your_forum_channel_id_here
CRCON_BASE_URL=http://your_crcon_server:8010
CRCON_USERNAME=your_crcon_username
CRCON_PASSWORD=your_crcon_password
```

## Configuration Details

### Discord Settings
- **token**: Your Discord bot token from the Developer Portal
- **admin_channel_id**: Forum channel ID where admin posts will be created
- **admin_roles**: Array of role IDs to mention on new requests (optional)

### CRCON Settings
- **base_url**: Your CRCON web interface URL (e.g., `http://localhost:8010`)
- **username**: CRCON username with appropriate permissions
- **password**: CRCON password

## Usage

### Starting the Bot
```bash
# Option 1: Using the launcher (recommended)
python run.py

```

### In-Game Usage
Players can request admin help using:
- `!admin` - Basic admin request
- `!admin I need help with teamkilling` - Request with message

### Discord Admin Workflow
1. **New Request**: Bot creates forum post with NEW tag and admin mentions
2. **Admin Response**: Reply in the forum post to send message to player
3. **Status Updates**: Tags automatically change: NEW → REPLIED → CLOSED
4. **Close Ticket**: Use the "Close Ticket" button to end the conversation

## How It Works

### Request Flow
1. **Detection**: Bot monitors CRCON logs for `!admin` commands
2. **Forum Creation**: Creates timestamped forum post with player details
3. **Admin Notification**: Mentions configured admin roles
4. **Response Handling**: Discord replies are sent directly to player in-game
5. **Player Response Handling**: Player can respond in chat without needing to use "!admin"
6. **Status Tracking**: Forum tags reflect current ticket status
7. **Closure**: Admins can close tickets with confirmation to player

### Message Format
- **To Player**: `[ADMIN AdminName]: Your message here`
- **Close Confirmation**: `✅ Your admin ticket has been closed by AdminName. Thank you!`

### Forum Post Format
- **Title**: `YYYY-MM-DD HH:MM - PlayerName`
- **Content**: Detailed embed with request information and timestamp
- **Tags**: Automatic status tracking (NEW/REPLIED/CLOSED)

## Features in Detail

### Smart Duplicate Prevention
- Tracks active requests per player
- Prevents spam while allowing legitimate follow-ups
- Memory-based tracking for optimal performance

### Forum Tag Management
- **NEW**: Fresh admin requests awaiting response
- **REPLIED**: Admin has responded, awaiting resolution
- **CLOSED**: Ticket completed and closed

### Admin Controls
- Close ticket button with confirmation
- Automatic status updates
- Player notification on closure

## Troubleshooting

### Common Issues

**Bot not connecting to CRCON:**
- Verify CRCON URL is accessible
- Check username/password credentials
- Ensure CRCON API is enabled

**Bot not creating forum posts:**
- Verify Discord bot permissions
- Check forum channel ID is correct
- Ensure bot is in the Discord server

**Messages not reaching players:**
- Check CRCON connection status
- Verify player is still online
- Check CRCON message permissions

**Forum tags not working:**
- Bot auto-creates missing tags
- Check bot has Manage Threads permission
- Restart bot if tags appear corrupted

### Debug Information
Monitor console output for:
- ✅ Connection confirmations
- 🎯 Admin request detections  
- 📝 Forum post creations
- 🔄 Message transmissions
- ❌ Errors and warnings

### Log Files
The bot provides detailed console logging:
- CRCON connection status
- Discord bot events
- Admin request processing
- Error diagnostics

## System Requirements

- Python 3.8+
- Active CRCON server
- Discord bot with forum permissions
- Stable internet connection

## Support

For issues and feature requests:
1. Check the troubleshooting section
2. Review console logs for errors
3. Verify configuration settings
4. Test with minimal setup

## Contributing

Contributions welcome! Areas for improvement:
- Additional Discord integrations
- Enhanced admin tools
- Performance optimizations
- Extended logging capabilities

## License

This project is licensed under the MIT License.