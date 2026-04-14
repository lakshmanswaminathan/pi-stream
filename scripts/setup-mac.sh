#!/bin/bash
# Run this on your Mac to configure Screen Sharing + install ffmpeg.
# Usage: bash setup-mac.sh

set -euo pipefail

echo "=== Mac Setup for Pi Stream ==="

# Install ffmpeg
echo "[1/3] Installing ffmpeg..."
if command -v ffmpeg &>/dev/null; then
    echo "ffmpeg already installed."
else
    brew install ffmpeg
fi

# Enable Screen Sharing
echo "[2/3] Enabling Screen Sharing..."
echo "  -> Opening System Settings. Enable Screen Sharing manually:"
echo "     System Settings → General → Sharing → Screen Sharing → ON"
echo "     Click (i) → Check 'VNC viewers may control screen with password'"
echo "     Set password to: stream (or whatever you want)"
echo ""
read -p "Press Enter once Screen Sharing is enabled..."

# Disable VNC timeouts
echo "[3/3] Disabling VNC timeouts..."
sudo defaults write /Library/Preferences/com.apple.RemoteManagement VNCIdleTimeout -int 0
sudo defaults write /Library/Preferences/com.apple.RemoteManagement VNCInactiveTimeout -int 0
sudo defaults write /Library/Preferences/com.apple.RemoteManagement ScreenSharingReqPermEnabled -bool false
sudo /System/Library/CoreServices/RemoteManagement/ARDAgent.app/Contents/Resources/kickstart -restart -agent -console 2>/dev/null || true

MY_IP=$(ipconfig getifaddr en0 2>/dev/null || echo "unknown")

echo ""
echo "=== Mac setup complete! ==="
echo ""
echo "Your IP: ${MY_IP}"
echo ""
echo "In Slack:"
echo "  /stream ${MY_IP}       — VNC mode"
echo "  /stream hd ${MY_IP}   — HD 1080p mode"
echo ""
echo "For HD mode, run the ffmpeg command from Terminal.app (not Ghostty)."
echo "Grant Screen Recording permission: System Settings → Privacy → Screen Recording → Terminal"
