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

# Install required packages
echo "📦 Installing Python and dependencies..."
sudo apt install python3 python3-pip python3-venv git -y

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
fi

# Create systemd service file
echo "🔧 Setting up systemd service..."
sudo tee /etc/systemd/system/hll-admin-responder.service > /dev/null << EOF
[Unit]
Description=HLL Admin Responder Bot
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$PWD
Environment=PATH=$PWD/venv/bin
ExecStart=$PWD/venv/bin/python run.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd and enable service
echo "🔄 Enabling auto-start service..."
sudo systemctl daemon-reload
sudo systemctl enable hll-admin-responder

echo "✅ Installation complete!"
echo ""
echo "Next steps:"
echo "1. Edit .env file with your configuration: nano .env"
echo "2. Start the bot: sudo systemctl start hll-admin-responder"
echo "3. Check status: sudo systemctl status hll-admin-responder"
echo "4. View logs: sudo journalctl -u hll-admin-responder -f"
echo ""
echo "The bot will automatically start on system reboot."