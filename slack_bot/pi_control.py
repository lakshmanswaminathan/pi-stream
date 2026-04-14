"""Local control for the Raspberry Pi receiver (no SSH, runs directly on the Pi)."""

import logging
import os
import subprocess
import time

logger = logging.getLogger(__name__)

PLAYER_PROCESS_NAME = "pi-stream-receiver"


class PiController:
    """Manages stream receiver directly as a local subprocess."""

    def __init__(self, **_kwargs):
        self._proc: subprocess.Popen | None = None

    def _has_mpv(self) -> bool:
        return subprocess.run(["which", "mpv"], capture_output=True).returncode == 0

    def start_receiver(self, udp_port: int = 9999) -> bool:
        """Start receiver fullscreen on HDMI, listening for TCP stream."""
        try:
            # Kill any existing receiver first
            subprocess.run(["pkill", "-f", PLAYER_PROCESS_NAME], capture_output=True)
            time.sleep(0.5)

            env = {**os.environ, "DISPLAY": ":0"}

            if self._has_mpv():
                cmd = [
                    "mpv",
                    f"--title={PLAYER_PROCESS_NAME}",
                    "--fullscreen",
                    "--no-audio",
                    "--profile=low-latency",
                    "--no-cache",
                    "--untimed",
                    "--no-demuxer-thread",
                    "--framedrop=vo",
                    "--video-latency-hacks=yes",
                    "--demuxer-lavf-o=fflags=+nobuffer+fastseek",
                    "--demuxer-lavf-analyzeduration=0.1",
                    "--demuxer-lavf-probesize=100000",
                    "--vo=gpu",
                    "--hwdec=auto",
                    f"tcp://0.0.0.0:{udp_port}?listen",
                ]
            else:
                cmd = [
                    "ffplay",
                    "-window_title", PLAYER_PROCESS_NAME,
                    "-fs", "-an",
                    "-fflags", "nobuffer",
                    "-flags", "low_delay",
                    "-framedrop",
                    "-analyzeduration", "100000",
                    "-probesize", "100000",
                    "-i", f"tcp://0.0.0.0:{udp_port}?listen",
                    "-loglevel", "warning",
                ]

            self._proc = subprocess.Popen(
                cmd,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=open("/tmp/pi-stream-receiver.log", "w"),
            )
            logger.info("Receiver started with PID %s (player: %s)", self._proc.pid, "mpv" if self._has_mpv() else "ffplay")
            return True

        except FileNotFoundError:
            logger.error("No player found — install mpv or ffmpeg: sudo apt install mpv")
            return False
        except Exception:
            logger.exception("Failed to start receiver")
            return False

    def stop_receiver(self) -> bool:
        """Kill the receiver process."""
        try:
            if self._proc and self._proc.poll() is None:
                self._proc.terminate()
                self._proc.wait(timeout=5)
            else:
                subprocess.run(["pkill", "-f", PLAYER_PROCESS_NAME], capture_output=True)
            self._proc = None
            logger.info("Receiver stopped")
            return True
        except Exception:
            logger.exception("Failed to stop receiver")
            return False

    def is_receiver_running(self) -> bool:
        """Check if the receiver is currently running."""
        if self._proc and self._proc.poll() is None:
            return True
        result = subprocess.run(["pgrep", "-f", PLAYER_PROCESS_NAME], capture_output=True)
        return result.returncode == 0

    def clear_screen(self) -> bool:
        """Kill any display processes."""
        subprocess.run(["pkill", "-f", PLAYER_PROCESS_NAME], capture_output=True)
        self._proc = None
        return True
