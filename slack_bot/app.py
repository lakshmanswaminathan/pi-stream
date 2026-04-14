"""Slack bot for controlling the Pi TV stream.

Slash commands:
  /stream <ip>      — VNC mode. Pi connects to your Mac's Screen Sharing.
  /stream hd <ip>   — HD mode. You run an ffmpeg command to stream 1080p to Pi.
  /stream stop      — Stop the current stream and free the TV.
  /stream status    — Check if someone is currently streaming.
"""

import logging
import os
import threading
import time

from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from pi_control import PiController

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# --- Config from env ---
SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_APP_TOKEN = os.environ["SLACK_APP_TOKEN"]  # xapp-... for Socket Mode

PI_LAN_IP = os.environ.get("PI_LAN_IP", "192.168.1.28")
STREAM_PORT = int(os.environ.get("STREAM_PORT", "9999"))
STREAM_TIMEOUT_MINUTES = int(os.environ.get("STREAM_TIMEOUT_MINUTES", "60"))

# --- State ---
_lock = threading.Lock()
_current_stream: dict | None = None

# --- Pi controller (runs locally on Pi) ---
pi = PiController()

# --- Slack app (Socket Mode — no public URL needed) ---
app = App(token=SLACK_BOT_TOKEN)


def _auto_stop_timer(user_id: str, channel: str, timeout: int):
    """Auto-stop stream after timeout to prevent someone forgetting."""
    time.sleep(timeout * 60)
    with _lock:
        global _current_stream
        if _current_stream and _current_stream["user_id"] == user_id:
            pi.stop()
            _current_stream = None
            try:
                app.client.chat_postMessage(
                    channel=channel,
                    text=f":tv: Stream auto-stopped after {timeout} minutes. Run `/stream` to start again.",
                )
            except Exception:
                logger.exception("Failed to send auto-stop message")


def _start_timer(user_id: str, channel: str):
    threading.Thread(
        target=_auto_stop_timer,
        args=(user_id, channel, STREAM_TIMEOUT_MINUTES),
        daemon=True,
    ).start()


@app.command("/stream")
def handle_stream(ack, command, respond):
    ack()

    text = (command.get("text") or "").strip()
    parts = text.split()
    user_id = command["user_id"]
    user_name = command.get("user_name", "someone")
    channel = command["channel_id"]

    # --- /stream stop ---
    if text.lower() == "stop":
        with _lock:
            global _current_stream
            if not _current_stream:
                respond(":tv: No active stream to stop.")
                return
            if _current_stream["user_id"] != user_id:
                respond(
                    f":warning: <@{_current_stream['user_id']}> is currently streaming. "
                    "Only they can stop it (or an admin can restart the bot)."
                )
                return
            pi.stop()
            _current_stream = None
        respond(":tv: Stream stopped. The TV is free.", response_type="in_channel")
        return

    # --- /stream status ---
    if text.lower() == "status":
        with _lock:
            if _current_stream:
                elapsed = int((time.time() - _current_stream["started_at"]) / 60)
                mode = _current_stream.get("mode", "vnc")
                respond(
                    f":tv: <@{_current_stream['user_id']}> has been streaming ({mode}) for {elapsed} min."
                )
            else:
                respond(":tv: No one is streaming. Run `/stream <ip>` or `/stream hd <ip>` to start.")
        return

    # --- Check if already streaming ---
    with _lock:
        if _current_stream:
            respond(
                f":warning: <@{_current_stream['user_id']}> is already streaming. "
                "Ask them to `/stream stop` first."
            )
            return

    # --- /stream hd <ip> ---
    if len(parts) >= 2 and parts[0].lower() == "hd":
        target_ip = parts[1]

        respond(f":hourglass_flowing_sand: Starting HD receiver on the Pi...")
        ok = pi.start_receiver(port=STREAM_PORT)
        if not ok:
            respond(":x: Failed to start receiver on Pi.")
            return

        with _lock:
            _current_stream = {
                "user_id": user_id,
                "user_name": user_name,
                "started_at": time.time(),
                "channel": channel,
                "mode": "hd",
            }

        _start_timer(user_id, channel)

        respond(
            f":tv: *Pi receiver is ready!* Run this on your Mac (from Terminal.app):\n\n"
            f"```\n"
            f"ffmpeg -f avfoundation -framerate 30 -capture_cursor 1 \\\n"
            f"  -i 'Capture screen 0' \\\n"
            f"  -vf 'scale=1920:1080' \\\n"
            f"  -vcodec h264_videotoolbox -realtime 1 \\\n"
            f"  -b:v 5M -profile:v baseline -level 4.1 \\\n"
            f"  -g 60 \\\n"
            f"  -f mpegts 'tcp://{PI_LAN_IP}:{STREAM_PORT}'\n"
            f"```\n"
            f"\n:bulb: Requires `ffmpeg` + Screen Recording permission for Terminal.app.\n"
            f"Run `/stream stop` when done. Auto-stops after {STREAM_TIMEOUT_MINUTES} min."
        )
        return

    # --- /stream <ip> (VNC mode) ---
    target_ip = parts[0] if parts else ""
    if not target_ip:
        respond(
            ":tv: *Usage:*\n"
            "`/stream <ip>` — VNC mode (easy, enable Screen Sharing on Mac)\n"
            "`/stream hd <ip>` — HD mode (1080p, run ffmpeg command on Mac)\n"
            "`/stream stop` — stop streaming\n"
            "`/stream status` — check who's streaming\n\n"
            "*Your IP:* run `ipconfig getifaddr en0` in Terminal"
        )
        return

    respond(f":hourglass_flowing_sand: Connecting to your screen at `{target_ip}`...")
    ok = pi.start_vnc(target_ip)
    if not ok:
        respond(
            ":x: Failed to connect. Check that:\n"
            "1. Screen Sharing is enabled on your Mac\n"
            "2. Your IP is correct (run `ipconfig getifaddr en0`)\n"
            "3. You're on the same network as the Pi"
        )
        return

    with _lock:
        _current_stream = {
            "user_id": user_id,
            "user_name": user_name,
            "started_at": time.time(),
            "channel": channel,
            "mode": "vnc",
            "target_ip": target_ip,
        }

    _start_timer(user_id, channel)

    respond(
        f":tv: *Streaming to the TV!*\n"
        f"Your screen (`{target_ip}`) is now on the office TV.\n"
        f"Run `/stream stop` when you're done. Auto-stops after {STREAM_TIMEOUT_MINUTES} min."
    )


@app.event("app_mention")
def handle_mention(event, say):
    say("Use `/stream <ip>` (VNC) or `/stream hd <ip>` (1080p) to share your screen to the TV.")


def main():
    logger.info("Starting Pi Stream bot (Socket Mode)...")
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    handler.start()


if __name__ == "__main__":
    main()
