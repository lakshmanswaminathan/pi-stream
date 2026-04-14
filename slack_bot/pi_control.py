"""Local control for the Raspberry Pi VNC viewer (runs directly on the Pi)."""

import base64
import logging
import os
import subprocess
import time

logger = logging.getLogger(__name__)

VNC_PASSWORD = os.environ.get("VNC_PASSWORD", "stream")
REMMINA_FILE = "/tmp/pi-stream.remmina"


def _write_remmina_profile(target_ip: str, password: str, port: int = 5900):
    """Write a remmina connection profile file."""
    # Remmina stores passwords as base64
    b64_pass = base64.b64encode(password.encode()).decode()
    content = f"""[remmina]
name=pi-stream
protocol=VNC
server={target_ip}:{port}
password={b64_pass}
quality=2
viewmode=4
viewonly=1
disableencryption=1
colordepth=32
"""
    with open(REMMINA_FILE, "w") as f:
        f.write(content)


class PiController:
    """Manages VNC viewer on the Pi to connect to a Mac's Screen Sharing."""

    def __init__(self, **_kwargs):
        self._proc: subprocess.Popen | None = None

    def start_vnc(self, target_ip: str, port: int = 5900) -> bool:
        """Launch VNC viewer fullscreen, connecting to the target Mac."""
        try:
            self.stop_vnc()
            time.sleep(0.5)

            env = {**os.environ, "DISPLAY": ":0"}

            _write_remmina_profile(target_ip, VNC_PASSWORD, port)

            self._proc = subprocess.Popen(
                ["remmina", "-c", REMMINA_FILE, "--no-tray-icon"],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=open("/tmp/pi-stream-receiver.log", "w"),
            )

            time.sleep(3)
            if self._proc.poll() is None:
                logger.info("Remmina VNC started with PID %s", self._proc.pid)
                return True

            # Fallback: try xtigervncviewer
            logger.warning("Remmina failed, trying xtigervncviewer")
            self._proc = subprocess.Popen(
                [
                    "xtigervncviewer",
                    "-FullScreen",
                    "-ViewOnly",
                    "-SecurityTypes=VncAuth",
                    f"{target_ip}::{port}",
                ],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=open("/tmp/pi-stream-receiver.log", "w"),
            )
            time.sleep(2)
            if self._proc.poll() is None:
                logger.info("TigerVNC started with PID %s", self._proc.pid)
                return True

            logger.error("All VNC viewers failed")
            return False

        except Exception:
            logger.exception("Failed to start VNC viewer")
            return False

    def stop_vnc(self) -> bool:
        """Kill the VNC viewer."""
        try:
            if self._proc and self._proc.poll() is None:
                self._proc.terminate()
                self._proc.wait(timeout=5)
            subprocess.run(["pkill", "-f", "remmina"], capture_output=True)
            subprocess.run(["pkill", "-f", "vncviewer"], capture_output=True)
            self._proc = None
            logger.info("VNC viewer stopped")
            return True
        except Exception:
            logger.exception("Failed to stop VNC viewer")
            return False

    def is_running(self) -> bool:
        """Check if VNC viewer is running."""
        if self._proc and self._proc.poll() is None:
            return True
        r1 = subprocess.run(["pgrep", "-f", "remmina"], capture_output=True)
        r2 = subprocess.run(["pgrep", "-f", "vncviewer"], capture_output=True)
        return r1.returncode == 0 or r2.returncode == 0
