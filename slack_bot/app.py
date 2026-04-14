"""Slack bot for controlling the Pi TV stream.

Slash commands:
  /stream        — Start streaming. Bot starts the Pi receiver and replies with
                   the command you run locally to send your screen.
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

PI_HOST = os.environ.get("PI_HOST", "localhost")
PI_LAN_IP = os.environ.get("PI_LAN_IP", PI_HOST)  # IP shown in ffmpeg commands for streamers
STREAM_UDP_PORT = int(os.environ.get("STREAM_UDP_PORT", "9999"))
STREAM_TIMEOUT_MINUTES = int(os.environ.get("STREAM_TIMEOUT_MINUTES", "60"))

# --- State ---
_lock = threading.Lock()
_current_stream: dict | None = None  # {"user_id": str, "user_name": str, "started_at": float, "channel": str}

# --- Pi controller (runs locally, no SSH) ---
pi = PiController()

# --- Slack app (Socket Mode — no public URL needed) ---
app = App(token=SLACK_BOT_TOKEN)


def _streamer_command(pi_ip: str, port: int) -> dict:
    """Return platform-specific streaming commands."""
    return {
        "macos": (
            f"ffmpeg -f avfoundation -framerate 30 -i '1' "
            f"-vcodec libx264 -preset ultrafast -tune zerolatency "
            f"-b:v 3M -maxrate 3M -bufsize 6M "
            f"-f mpegts 'udp://{pi_ip}:{port}?pkt_size=1316'"
        ),
        "linux": (
            f"ffmpeg -f x11grab -framerate 30 -i :0.0 "
            f"-vcodec libx264 -preset ultrafast -tune zerolatency "
            f"-b:v 3M -maxrate 3M -bufsize 6M "
            f"-f mpegts 'udp://{pi_ip}:{port}?pkt_size=1316'"
        ),
        "windows": (
            f"ffmpeg -f gdigrab -framerate 30 -i desktop "
            f"-vcodec libx264 -preset ultrafast -tune zerolatency "
            f"-b:v 3M -maxrate 3M -bufsize 6M "
            f"-f mpegts \"udp://{pi_ip}:{port}?pkt_size=1316\""
        ),
    }


def _auto_stop_timer(user_id: str, channel: str, timeout: int):
    """Auto-stop stream after timeout to prevent someone forgetting."""
    time.sleep(timeout * 60)
    with _lock:
        global _current_stream
        if _current_stream and _current_stream["user_id"] == user_id:
            pi.stop_receiver()
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

    text = (command.get("text") or "").strip().lower()
    user_id = command["user_id"]
    user_name = command.get("user_name", "someone")
    channel = command["channel_id"]

    # --- /stream stop ---
    if text == "stop":
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
            pi.stop_receiver()
            _current_stream = None
        respond(":tv: Stream stopped. The TV is free.", response_type="in_channel")
        return

    # --- /stream status ---
    if text == "status":
        with _lock:
            if _current_stream:
                elapsed = int((time.time() - _current_stream["started_at"]) / 60)
                respond(
                    f":tv: <@{_current_stream['user_id']}> has been streaming for {elapsed} min."
                )
            else:
                respond(":tv: No one is streaming. Run `/stream` to start.")
        return

    # --- /stream (start) ---
    with _lock:
        if _current_stream:
            respond(
                f":warning: <@{_current_stream['user_id']}> is already streaming. "
                "Ask them to `/stream stop` first."
            )
            return

    # Start receiver on Pi
    respond(":hourglass_flowing_sand: Starting TV receiver on the Pi...")
    ok = pi.start_receiver(udp_port=STREAM_UDP_PORT)
    if not ok:
        respond(":x: Failed to start receiver on Pi. Is it powered on and reachable?")
        return

    with _lock:
        _current_stream = {
            "user_id": user_id,
            "user_name": user_name,
            "started_at": time.time(),
            "channel": channel,
        }

    # Start auto-stop timer
    threading.Thread(
        target=_auto_stop_timer,
        args=(user_id, channel, STREAM_TIMEOUT_MINUTES),
        daemon=True,
    ).start()

    cmds = _streamer_command(PI_LAN_IP, STREAM_UDP_PORT)

    respond(
        f":tv: *Pi receiver is ready!* Run one of these on your machine to start streaming:\n\n"
        f"*macOS:*\n```\n{cmds['macos']}\n```\n"
        f"*Linux:*\n```\n{cmds['linux']}\n```\n"
        f"*Windows:*\n```\n{cmds['windows']}\n```\n"
        f"\n:bulb: Requires `ffmpeg` installed locally. Stream will auto-stop after {STREAM_TIMEOUT_MINUTES} min.\n"
        f"Run `/stream stop` when you're done."
    )



@app.event("app_mention")
def handle_mention(event, say):
    say("Use `/stream` to share your screen to the TV, `/stream stop` to end, `/stream status` to check.")


def main():
    logger.info("Starting Pi Stream bot (Socket Mode)...")
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    handler.start()


if __name__ == "__main__":
    main()
