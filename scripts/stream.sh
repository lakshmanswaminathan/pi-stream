#!/usr/bin/env bash
# Quick-start script for streaming your screen to the Pi.
# Usage: ./stream.sh [PI_IP] [PORT]
#
# Requires: ffmpeg installed locally
#   macOS: brew install ffmpeg
#   Linux: sudo apt install ffmpeg

set -euo pipefail

PI_IP="${1:-${PI_HOST:-192.168.1.100}}"
PORT="${2:-9999}"

if ! command -v ffmpeg &>/dev/null; then
    echo "Error: ffmpeg not found. Install it first."
    echo "  macOS:  brew install ffmpeg"
    echo "  Linux:  sudo apt install ffmpeg"
    exit 1
fi

OS="$(uname -s)"
case "$OS" in
    Darwin)
        echo "Streaming screen to $PI_IP:$PORT (macOS)"
        echo "Press Ctrl+C to stop."
        echo ""
        # List available screens (device index 1 is usually the main display)
        # Change -i "1" to -i "2", etc. for other displays
        ffmpeg -f avfoundation -framerate 30 -i "1" \
            -vcodec libx264 -preset ultrafast -tune zerolatency \
            -b:v 3M -maxrate 3M -bufsize 6M \
            -f mpegts "udp://${PI_IP}:${PORT}?pkt_size=1316"
        ;;
    Linux)
        echo "Streaming screen to $PI_IP:$PORT (Linux)"
        echo "Press Ctrl+C to stop."
        echo ""
        ffmpeg -f x11grab -framerate 30 -i :0.0 \
            -vcodec libx264 -preset ultrafast -tune zerolatency \
            -b:v 3M -maxrate 3M -bufsize 6M \
            -f mpegts "udp://${PI_IP}:${PORT}?pkt_size=1316"
        ;;
    *)
        echo "Unsupported OS: $OS. Use the Windows .bat script or run ffmpeg manually."
        exit 1
        ;;
esac
