"""Local control for the Raspberry Pi receiver (no SSH, runs directly on the Pi)."""

import logging
import os
import signal
import subprocess
import time

logger = logging.getLogger(__name__)


class PiController:
    """Manages ffplay receiver directly as a local subprocess."""

    def __init__(self, **_kwargs):
        self._proc: subprocess.Popen | None = None

    def start_receiver(self, udp_port: int = 9999) -> bool:
        """Start ffplay fullscreen on HDMI, listening for UDP stream."""
        try:
            # Kill any existing receiver first
            subprocess.run(["pkill", "-f", "ffplay.*udp://"], capture_output=True)
            time.sleep(0.5)

            env = {**os.environ, "DISPLAY": ":0"}
            self._proc = subprocess.Popen(
                [
                    "ffplay", "-fs", "-an",
                    "-fflags", "nobuffer",
                    "-flags", "low_delay",
                    "-analyzeduration", "100000",
                    "-probesize", "100000",
                    "-i", f"udp://@:{udp_port}?overrun_nonfatal=1&fifo_size=50000000",
                    "-loglevel", "warning",
                ],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=open("/tmp/pi-stream-receiver.log", "w"),
            )
            logger.info("Receiver started with PID %s", self._proc.pid)
            return True

        except FileNotFoundError:
            logger.error("ffplay not found — install ffmpeg: sudo apt install ffmpeg")
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
                subprocess.run(["pkill", "-f", "ffplay.*udp://"], capture_output=True)
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
        result = subprocess.run(["pgrep", "-f", "ffplay.*udp://"], capture_output=True)
        return result.returncode == 0

    def clear_screen(self) -> bool:
        """Kill any display processes."""
        subprocess.run(["pkill", "-f", "ffplay.*udp://"], capture_output=True)
        self._proc = None
        return True
