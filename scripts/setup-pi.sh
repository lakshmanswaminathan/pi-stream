#!/bin/bash
# Run this on the Raspberry Pi to set up everything.
# Usage: bash setup-pi.sh

set -euo pipefail

echo "=== Pi Stream Setup ==="

# Install dependencies
echo "[1/4] Installing dependencies..."
sudo apt update -qq
sudo apt install -y ffmpeg mpv tigervnc-viewer tigervnc-common expect python3-venv

# Clone repo
echo "[2/4] Cloning repo..."
if [ -d ~/pi-stream ]; then
    cd ~/pi-stream && git pull
else
    git clone https://github.com/lakshmanswaminathan/pi-stream.git ~/pi-stream
fi

# Python venv + deps
echo "[3/4] Setting up Python environment..."
cd ~/pi-stream
python3 -m venv .venv
source .venv/bin/activate
pip install -q -r slack_bot/requirements.txt

# Create .env if missing
if [ ! -f slack_bot/.env ]; then
    echo "[4/4] Creating .env file..."
    echo "Enter your Slack Bot Token (xoxb-...):"
    read -r BOT_TOKEN
    echo "Enter your Slack App Token (xapp-...):"
    read -r APP_TOKEN
    echo "Enter VNC password (default: stream):"
    read -r VNC_PASS
    VNC_PASS=${VNC_PASS:-stream}

    # Detect LAN IP (prefer ethernet)
    LAN_IP=$(ip -4 addr show eth0 2>/dev/null | grep -oP 'inet \K[\d.]+' || ip -4 addr show wlan0 2>/dev/null | grep -oP 'inet \K[\d.]+' || echo "192.168.1.28")

    cat > slack_bot/.env << EOF
SLACK_BOT_TOKEN=${BOT_TOKEN}
SLACK_APP_TOKEN=${APP_TOKEN}
PI_HOST=localhost
PI_LAN_IP=${LAN_IP}
VNC_PASSWORD=${VNC_PASS}
STREAM_PORT=9999
STREAM_TIMEOUT_MINUTES=60
EOF
    echo "Wrote slack_bot/.env with PI_LAN_IP=${LAN_IP}"
else
    echo "[4/4] .env already exists, skipping."
fi

# Create start script
cat > ~/start-bot.sh << 'SCRIPT'
#!/bin/bash
cd ~/pi-stream
source .venv/bin/activate
cd slack_bot
python3 app.py >> /tmp/pi-stream-bot.log 2>&1
SCRIPT
chmod +x ~/start-bot.sh

# Create systemd service
sudo tee /etc/systemd/system/pi-stream.service > /dev/null << SERVICE
[Unit]
Description=Pi Stream Slack Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$(whoami)
Environment=DISPLAY=:0
WorkingDirectory=$(echo ~)/pi-stream/slack_bot
ExecStart=$(echo ~)/pi-stream/.venv/bin/python3 app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SERVICE

echo ""
echo "=== Setup complete! ==="
echo ""
echo "To start manually:  ~/start-bot.sh"
echo "To start as service: sudo systemctl enable --now pi-stream"
echo ""
echo "Then in Slack:"
echo "  /stream <mac-ip>       — VNC mode"
echo "  /stream hd <mac-ip>   — HD 1080p mode (run ffmpeg on Mac)"
echo "  /stream stop           — stop streaming"
