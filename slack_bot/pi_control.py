"""Local control for the Raspberry Pi VNC viewer (runs directly on the Pi)."""

import logging
import os
import subprocess
import time

logger = logging.getLogger(__name__)

PROCESS_NAME = "pi-stream-vnc"


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

            # Try vncviewer (TigerVNC/RealVNC), fall back to remmina
            for viewer_cmd in [
                [
                    "vncviewer",
                    "-FullScreen",
                    "-ViewOnly",
                    "-QualityLevel=9",
                    "-CompressLevel=1",
                    f"{target_ip}:{port}",
                ],
                [
                    "xtigervncviewer",
                    "-FullScreen",
                    "-ViewOnly",
                    "-QualityLevel=9",
                    "-CompressLevel=1",
                    f"{target_ip}:{port}",
                ],
            ]:
                binary = viewer_cmd[0]
                if subprocess.run(["which", binary], capture_output=True).returncode == 0:
                    self._proc = subprocess.Popen(
                        viewer_cmd,
                        env=env,
                        stdout=subprocess.DEVNULL,
                        stderr=open("/tmp/pi-stream-receiver.log", "w"),
                    )
                    # Wait a moment to see if it crashes immediately
                    time.sleep(2)
                    if self._proc.poll() is None:
                        logger.info("VNC viewer started with PID %s (%s)", self._proc.pid, binary)
                        return True
                    else:
                        logger.warning("%s exited immediately, trying next viewer", binary)
                        continue

            logger.error("No VNC viewer found — install: sudo apt install tigervnc-viewer")
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
            # Also kill any stray VNC viewers
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
        result = subprocess.run(["pgrep", "-f", "vncviewer"], capture_output=True)
        return result.returncode == 0
