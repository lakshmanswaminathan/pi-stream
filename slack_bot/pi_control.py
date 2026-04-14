"""Local control for the Raspberry Pi VNC viewer (runs directly on the Pi)."""

import logging
import os
import subprocess
import time
import tempfile

logger = logging.getLogger(__name__)

VNC_PASSWORD = os.environ.get("VNC_PASSWORD", "stream")


class PiController:
    """Manages VNC viewer on the Pi to connect to a Mac's Screen Sharing."""

    def __init__(self, **_kwargs):
        self._proc: subprocess.Popen | None = None

    def _create_expect_script(self, target_ip: str, password: str, port: int) -> str:
        """Create an expect script that auto-enters the VNC password."""
        script = f"""#!/usr/bin/expect -f
set timeout 30
spawn xtigervncviewer -FullScreen -ViewOnly -QualityLevel=5 -CompressLevel=6 -PreferredEncoding=ZRLE -LowColorLevel=1 {target_ip}::{port}
expect "Password:"
send "{password}\\r"
expect eof
"""
        path = "/tmp/pi-stream-vnc-connect.exp"
        with open(path, "w") as f:
            f.write(script)
        os.chmod(path, 0o700)
        return path

    def start_vnc(self, target_ip: str, port: int = 5900) -> bool:
        """Launch VNC viewer fullscreen, connecting to the target Mac."""
        try:
            self.stop_vnc()
            time.sleep(0.5)

            env = {**os.environ, "DISPLAY": ":0"}

            # Check if expect is available
            has_expect = subprocess.run(["which", "expect"], capture_output=True).returncode == 0

            if has_expect:
                script = self._create_expect_script(target_ip, VNC_PASSWORD, port)
                self._proc = subprocess.Popen(
                    ["expect", script],
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=open("/tmp/pi-stream-receiver.log", "w"),
                )
            else:
                # Fallback: launch xtigervncviewer directly (user must enter password manually)
                self._proc = subprocess.Popen(
                    [
                        "xtigervncviewer",
                        "-FullScreen",
                        "-ViewOnly",
                        "-QualityLevel=9",
                        "-CompressLevel=1",
                        f"{target_ip}::{port}",
                    ],
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=open("/tmp/pi-stream-receiver.log", "w"),
                )

            time.sleep(3)
            if self._proc.poll() is None:
                logger.info("VNC viewer started with PID %s", self._proc.pid)
                return True

            logger.error("VNC viewer exited immediately")
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
            subprocess.run(["pkill", "-f", "tigervncviewer"], capture_output=True)
            subprocess.run(["pkill", "-f", "pi-stream-vnc"], capture_output=True)
            subprocess.run(["pkill", "-f", "remmina"], capture_output=True)
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
        r = subprocess.run(["pgrep", "-f", "tigervncviewer"], capture_output=True)
        return r.returncode == 0
