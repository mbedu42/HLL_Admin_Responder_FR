#!/bin/bash

# HLL Admin Responder Installation Script for Linux VPS

set -e

echo "🚀 Starting HLL Admin Responder installation..."

# Update system packages
echo "📦 Updating system packages..."
sudo apt update && sudo apt upgrade -y

# Install required packages (including tmux)
echo "📦 Installing Python, tmux and dependencies..."
sudo apt install python3 python3-pip python3-venv git tmux -y

# Create virtual environment
echo "🐍 Creating Python virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
echo "📦 Installing Python packages..."
pip install -r requirements.txt

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "⚙️  Creating environment configuration..."
    cp .env.example .env
    echo "⚠️  Please edit .env file with your configuration before starting the bot"
    echo ""
    echo "Edit the configuration now? (y/n)"
    read -p "Choice: " choice
    if [[ $choice == "y" || $choice == "Y" ]]; then
        nano .env
    fi
fi

echo "✅ Installation complete!"
echo ""
echo "🚀 Starting bot in tmux session..."

# Start through the shared launcher so cleanup and tmux socket naming stay
# consistent with the documented management commands.
venv/bin/python start.py --detached

echo "✅ Bot started in tmux session 'hll-admin'"
echo ""
echo "Commands to manage the bot:"
echo "  📺 View bot logs: tmux -L hll attach -t hll-admin"
echo "  🔌 Detach from session: Ctrl+B then D"
echo "  🔄 Restart bot: venv/bin/python start.py --detached"
echo "  🛑 Stop bot: tmux -L hll kill-session -t hll-admin"
echo "  📋 List sessions: tmux -L hll list-sessions"
echo ""
echo "🎯 The bot is now running! Use 'tmux -L hll attach -t hll-admin' to view logs."
