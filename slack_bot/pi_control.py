"""Local control for the Raspberry Pi VNC viewer (runs directly on the Pi)."""

import logging
import os
import subprocess
import threading
import time

logger = logging.getLogger(__name__)

VNC_PASSWORD = os.environ.get("VNC_PASSWORD", "stream")


class PiController:
    """Manages VNC viewer on the Pi to connect to a Mac's Screen Sharing."""

    def __init__(self, **_kwargs):
        self._proc: subprocess.Popen | None = None
        self._reconnect_thread: threading.Thread | None = None
        self._should_run = False
        self._target_ip: str | None = None
        self._port: int = 5900

    def _create_reconnect_script(self, target_ip: str, password: str, port: int) -> str:
        """Create a bash script that auto-reconnects VNC with expect for password."""
        script = f"""#!/bin/bash
# Auto-reconnecting VNC viewer
while true; do
    expect -c '
        set timeout -1
        spawn xtigervncviewer -FullScreen -ViewOnly -PreferredEncoding=Tight -QualityLevel=3 -CompressLevel=1 -AutoSelect=0 -LowColorLevel=1 -FullColor=0 {target_ip}::{port}
        expect "Password:"
        send "{password}\\r"
        expect eof
    ' >> /tmp/pi-stream-receiver.log 2>&1

    # Check if stop file exists (signals we should quit)
    if [ -f /tmp/pi-stream-stop ]; then
        rm -f /tmp/pi-stream-stop
        exit 0
    fi

    echo "$(date): VNC disconnected, reconnecting in 2s..." >> /tmp/pi-stream-receiver.log
    sleep 2
done
"""
        path = "/tmp/pi-stream-vnc-loop.sh"
        with open(path, "w") as f:
            f.write(script)
        os.chmod(path, 0o700)
        return path

    def start_vnc(self, target_ip: str, port: int = 5900) -> bool:
        """Launch VNC viewer with auto-reconnect."""
        try:
            self.stop_vnc()
            time.sleep(0.5)

            self._target_ip = target_ip
            self._port = port
            self._should_run = True

            env = {**os.environ, "DISPLAY": ":0"}

            # Remove stop signal file
            try:
                os.remove("/tmp/pi-stream-stop")
            except FileNotFoundError:
                pass

            script = self._create_reconnect_script(target_ip, VNC_PASSWORD, port)
            self._proc = subprocess.Popen(
                ["bash", script],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            time.sleep(4)
            if self._proc.poll() is None:
                logger.info("VNC viewer loop started with PID %s", self._proc.pid)
                return True

            logger.error("VNC viewer loop exited immediately")
            return False

        except Exception:
            logger.exception("Failed to start VNC viewer")
            return False

    def stop_vnc(self) -> bool:
        """Kill the VNC viewer and stop reconnect loop."""
        try:
            self._should_run = False

            # Signal the loop script to stop
            with open("/tmp/pi-stream-stop", "w") as f:
                f.write("stop")

            # Kill the processes
            subprocess.run(["pkill", "-f", "pi-stream-vnc-loop"], capture_output=True)
            subprocess.run(["pkill", "-f", "tigervncviewer"], capture_output=True)
            subprocess.run(["pkill", "-f", "remmina"], capture_output=True)

            if self._proc and self._proc.poll() is None:
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._proc.kill()

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
