"""Local control for the Raspberry Pi VNC viewer (runs directly on the Pi)."""

import logging
import os
import subprocess
import time

logger = logging.getLogger(__name__)

PROCESS_NAME = "pi-stream-vnc"
VNC_PASSWORD = os.environ.get("VNC_PASSWORD", "stream")


def _create_tiger_passwd_file(password: str, path: str):
    """Create a TigerVNC-compatible password file (DES-obfuscated)."""
    def reverse_bits(b):
        r = 0
        for i in range(8):
            if b & (1 << i):
                r |= 1 << (7 - i)
        return r

    # VNC fixed key with bit-reversed bytes
    key = bytes([reverse_bits(b) for b in [23, 82, 107, 6, 35, 78, 88, 7]])
    pwd = password.encode()[:8].ljust(8, b"\x00")

    # Use openssl CLI for DES-ECB encryption
    result = subprocess.run(
        ["openssl", "enc", "-des-ecb", "-nopad", "-nosalt", "-K", key.hex()],
        input=pwd,
        capture_output=True,
    )
    if result.returncode == 0 and result.stdout:
        with open(path, "wb") as f:
            f.write(result.stdout)
        os.chmod(path, 0o600)
        return True
    return False


class PiController:
    """Manages VNC viewer on the Pi to connect to a Mac's Screen Sharing."""

    def __init__(self, **_kwargs):
        self._proc: subprocess.Popen | None = None
        self._passwd_file = "/tmp/pi-stream-vncpasswd"
        _create_tiger_passwd_file(VNC_PASSWORD, self._passwd_file)

    def start_vnc(self, target_ip: str, port: int = 5900) -> bool:
        """Launch VNC viewer fullscreen, connecting to the target Mac."""
        try:
            self.stop_vnc()
            time.sleep(0.5)

            env = {**os.environ, "DISPLAY": ":0"}

            for viewer_cmd in [
                [
                    "xtigervncviewer",
                    "-FullScreen",
                    "-ViewOnly",
                    "-QualityLevel=9",
                    "-CompressLevel=1",
                    f"-PasswordFile={self._passwd_file}",
                    f"{target_ip}::{port}",
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
