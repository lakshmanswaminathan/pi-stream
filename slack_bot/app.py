"""Slack bot for controlling the Pi TV stream.

Slash commands:
  /stream <ip>   — Stream your screen to the TV. Provide your Mac's IP.
                   Pi connects to your Mac via VNC and displays fullscreen.
  /stream stop   — Stop the current stream and free the TV.
  /stream status — Check if someone is currently streaming.
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

STREAM_TIMEOUT_MINUTES = int(os.environ.get("STREAM_TIMEOUT_MINUTES", "60"))

# --- State ---
_lock = threading.Lock()
_current_stream: dict | None = None  # {"user_id": str, "user_name": str, "started_at": float, "channel": str}

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
            pi.stop_vnc()
            _current_stream = None
            try:
                app.client.chat_postMessage(
                    channel=channel,
                    text=f":tv: Stream auto-stopped after {timeout} minutes. Run `/stream` to start again.",
                )
            except Exception:
                logger.exception("Failed to send auto-stop message")


@app.command("/stream")
def handle_stream(ack, command, respond):
    ack()

    text = (command.get("text") or "").strip()
    text_lower = text.lower()
    user_id = command["user_id"]
    user_name = command.get("user_name", "someone")
    channel = command["channel_id"]

    # --- /stream stop ---
    if text_lower == "stop":
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
            pi.stop_vnc()
            _current_stream = None
        respond(":tv: Stream stopped. The TV is free.", response_type="in_channel")
        return

    # --- /stream status ---
    if text_lower == "status":
        with _lock:
            if _current_stream:
                elapsed = int((time.time() - _current_stream["started_at"]) / 60)
                respond(
                    f":tv: <@{_current_stream['user_id']}> has been streaming for {elapsed} min."
                )
            else:
                respond(":tv: No one is streaming. Run `/stream <your-ip>` to start.")
        return

    # --- /stream <ip> (start) ---
    with _lock:
        if _current_stream:
            respond(
                f":warning: <@{_current_stream['user_id']}> is already streaming. "
                "Ask them to `/stream stop` first."
            )
            return

    # Validate IP
    target_ip = text.strip()
    if not target_ip:
        respond(
            ":tv: *Usage:* `/stream <your-mac-ip>`\n\n"
            "*Setup (one-time):*\n"
            "1. Open *System Settings > General > Sharing*\n"
            "2. Enable *Screen Sharing* (VNC)\n"
            "3. Find your IP: run `ipconfig getifaddr en0` in Terminal\n\n"
            "*Then:* `/stream 192.168.1.xxx`"
        )
        return

    # Start VNC viewer on Pi
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
            "target_ip": target_ip,
        }

    # Start auto-stop timer
    threading.Thread(
        target=_auto_stop_timer,
        args=(user_id, channel, STREAM_TIMEOUT_MINUTES),
        daemon=True,
    ).start()

    respond(
        f":tv: *Streaming to the TV!*\n"
        f"Your screen (`{target_ip}`) is now on the office TV.\n"
        f"Run `/stream stop` when you're done. Auto-stops after {STREAM_TIMEOUT_MINUTES} min."
    )


@app.event("app_mention")
def handle_mention(event, say):
    say("Use `/stream <your-ip>` to share your screen to the TV, `/stream stop` to end, `/stream status` to check.")


def main():
    logger.info("Starting Pi Stream bot (Socket Mode)...")
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    handler.start()


if __name__ == "__main__":
    main()
