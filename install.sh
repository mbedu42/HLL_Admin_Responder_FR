#!/bin/bash

# HLL Admin Responder Installation Script for Linux VPS

set -e

echo "🚀 Starting HLL Admin Responder installation..."

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    echo "⚠️  Please do not run this script as root"
    exit 1
fi

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

# Kill existing session if it exists
tmux kill-session -t hll-admin 2>/dev/null || true

# Start new tmux session with the bot
tmux new-session -d -s hll-admin -c "$PWD" "source venv/bin/activate && python run.py"

echo "✅ Bot started in tmux session 'hll-admin'"
echo ""
echo "Commands to manage the bot:"
echo "  📺 View bot logs: tmux attach -t hll-admin"
echo "  🔌 Detach from session: Ctrl+B then D"
echo "  🔄 Restart bot: tmux kill-session -t hll-admin && tmux new-session -d -s hll-admin -c '$PWD' 'source venv/bin/activate && python run.py'"
echo "  🛑 Stop bot: tmux kill-session -t hll-admin"
echo "  📋 List sessions: tmux list-sessions"
echo ""
echo "🎯 The bot is now running! Use 'tmux attach -t hll-admin' to view logs."