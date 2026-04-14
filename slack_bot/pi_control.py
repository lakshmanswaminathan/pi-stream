"""Local control for the Raspberry Pi display (VNC viewer + ffmpeg receiver)."""

import logging
import os
import subprocess
import time

logger = logging.getLogger(__name__)

VNC_PASSWORD = os.environ.get("VNC_PASSWORD", "stream")


class PiController:
    """Manages VNC viewer and ffmpeg/mpv receiver on the Pi."""

    def __init__(self, **_kwargs):
        self._proc: subprocess.Popen | None = None
        self._mode: str | None = None  # "vnc" or "hd"

    # --- Generic stop ---

    def stop(self) -> bool:
        """Stop whatever is running."""
        if self._mode == "vnc":
            return self._stop_vnc()
        elif self._mode == "hd":
            return self._stop_receiver()
        # Kill everything just in case
        subprocess.run(["pkill", "-f", "pi-stream-vnc-loop"], capture_output=True)
        subprocess.run(["pkill", "-f", "tigervncviewer"], capture_output=True)
        subprocess.run(["pkill", "-f", "pi-stream-receiver"], capture_output=True)
        subprocess.run(["pkill", "-f", "mpv.*tcp://"], capture_output=True)
        subprocess.run(["pkill", "-f", "ffplay.*tcp://"], capture_output=True)
        self._proc = None
        self._mode = None
        return True

    # --- VNC mode ---

    def _create_reconnect_script(self, target_ip: str, password: str, port: int) -> str:
        script = f"""#!/bin/bash
# Auto-reconnecting VNC viewer
while true; do
    expect -c '
        set timeout -1
        spawn xtigervncviewer -FullScreen -ViewOnly -PreferredEncoding=Tight -QualityLevel=5 -CompressLevel=2 -AutoSelect=0 {target_ip}::{port}
        expect "Password:"
        send "{password}\\r"
        expect eof
    ' >> /tmp/pi-stream-receiver.log 2>&1

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
            self.stop()
            time.sleep(0.5)

            env = {**os.environ, "DISPLAY": ":0"}

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
                self._mode = "vnc"
                logger.info("VNC viewer loop started with PID %s", self._proc.pid)
                return True

            logger.error("VNC viewer loop exited immediately")
            return False

        except Exception:
            logger.exception("Failed to start VNC viewer")
            return False

    def _stop_vnc(self) -> bool:
        try:
            with open("/tmp/pi-stream-stop", "w") as f:
                f.write("stop")

            subprocess.run(["pkill", "-f", "pi-stream-vnc-loop"], capture_output=True)
            subprocess.run(["pkill", "-f", "tigervncviewer"], capture_output=True)

            if self._proc and self._proc.poll() is None:
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._proc.kill()

            self._proc = None
            self._mode = None
            logger.info("VNC viewer stopped")
            return True
        except Exception:
            logger.exception("Failed to stop VNC viewer")
            return False

    # --- HD (ffmpeg) mode ---

    def _has_mpv(self) -> bool:
        return subprocess.run(["which", "mpv"], capture_output=True).returncode == 0

    def start_receiver(self, port: int = 9999) -> bool:
        """Start mpv/ffplay TCP receiver for HD streaming."""
        try:
            self.stop()
            time.sleep(0.5)

            env = {**os.environ, "DISPLAY": ":0"}

            if self._has_mpv():
                cmd = [
                    "mpv",
                    "--title=pi-stream-receiver",
                    "--fullscreen",
                    "--no-audio",
                    "--profile=low-latency",
                    "--no-cache",
                    "--untimed",
                    "--no-demuxer-thread",
                    "--framedrop=vo",
                    "--video-latency-hacks=yes",
                    "--vo=gpu",
                    "--hwdec=auto",
                    f"tcp://0.0.0.0:{port}?listen",
                ]
            else:
                cmd = [
                    "ffplay",
                    "-window_title", "pi-stream-receiver",
                    "-fs", "-an",
                    "-fflags", "nobuffer",
                    "-flags", "low_delay",
                    "-framedrop",
                    "-analyzeduration", "100000",
                    "-probesize", "100000",
                    "-i", f"tcp://0.0.0.0:{port}?listen",
                    "-loglevel", "warning",
                ]

            self._proc = subprocess.Popen(
                cmd,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=open("/tmp/pi-stream-receiver.log", "w"),
            )

            self._mode = "hd"
            logger.info("HD receiver started with PID %s (%s)", self._proc.pid, "mpv" if self._has_mpv() else "ffplay")
            return True

        except Exception:
            logger.exception("Failed to start HD receiver")
            return False

    def _stop_receiver(self) -> bool:
        try:
            if self._proc and self._proc.poll() is None:
                self._proc.terminate()
                self._proc.wait(timeout=5)
            else:
                subprocess.run(["pkill", "-f", "pi-stream-receiver"], capture_output=True)
                subprocess.run(["pkill", "-f", "mpv.*tcp://"], capture_output=True)
                subprocess.run(["pkill", "-f", "ffplay.*tcp://"], capture_output=True)

            self._proc = None
            self._mode = None
            logger.info("HD receiver stopped")
            return True
        except Exception:
            logger.exception("Failed to stop HD receiver")
            return False
