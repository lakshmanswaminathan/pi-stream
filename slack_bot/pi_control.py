"""SSH control for the Raspberry Pi receiver."""

import logging
import time

import paramiko

logger = logging.getLogger(__name__)


class PiController:
    """Manages SSH connections to the Pi and controls the stream receiver."""

    def __init__(self, host: str, username: str, key_path: str | None = None, password: str | None = None, port: int = 22):
        self.host = host
        self.username = username
        self.key_path = key_path
        self.password = password
        self.port = port
        self._receiver_pid: int | None = None

    def _connect(self) -> paramiko.SSHClient:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        connect_kwargs: dict = {
            "hostname": self.host,
            "port": self.port,
            "username": self.username,
        }
        if self.key_path:
            connect_kwargs["key_filename"] = self.key_path
        elif self.password:
            connect_kwargs["password"] = self.password
        client.connect(**connect_kwargs)
        return client

    def start_receiver(self, udp_port: int = 9999) -> bool:
        """SSH into Pi and start ffplay fullscreen on HDMI, listening for UDP stream."""
        try:
            client = self._connect()

            # Kill any existing receiver first
            client.exec_command("pkill -f 'ffplay.*udp://'")
            time.sleep(0.5)

            # Start ffplay fullscreen on the Pi's display
            # DISPLAY=:0 targets the Pi's HDMI output
            # -fs = fullscreen, -an = no audio decode (lower latency)
            # -fflags nobuffer + low analyzeduration/probesize = minimal latency
            cmd = (
                "DISPLAY=:0 nohup ffplay -fs -an "
                "-fflags nobuffer -flags low_delay "
                "-analyzeduration 100000 -probesize 100000 "
                f"-i 'udp://@:{udp_port}?overrun_nonfatal=1&fifo_size=50000000' "
                "-loglevel warning "
                "> /tmp/pi-stream-receiver.log 2>&1 & echo $!"
            )
            _, stdout, stderr = client.exec_command(cmd)
            pid_str = stdout.read().decode().strip()

            if pid_str.isdigit():
                self._receiver_pid = int(pid_str)
                logger.info("Receiver started on Pi with PID %s", self._receiver_pid)
                client.close()
                return True

            err = stderr.read().decode().strip()
            logger.error("Failed to start receiver: %s", err)
            client.close()
            return False

        except Exception:
            logger.exception("SSH connection to Pi failed")
            return False

    def stop_receiver(self) -> bool:
        """Kill the receiver process on the Pi."""
        try:
            client = self._connect()
            client.exec_command("pkill -f 'ffplay.*udp://'")
            self._receiver_pid = None
            logger.info("Receiver stopped on Pi")
            client.close()
            return True
        except Exception:
            logger.exception("Failed to stop receiver on Pi")
            return False

    def is_receiver_running(self) -> bool:
        """Check if the receiver is currently running on the Pi."""
        try:
            client = self._connect()
            _, stdout, _ = client.exec_command("pgrep -f 'ffplay.*udp://'")
            result = stdout.read().decode().strip()
            client.close()
            return bool(result)
        except Exception:
            logger.exception("Failed to check receiver status")
            return False

    def show_message(self, message: str) -> bool:
        """Display a text message on the Pi's screen (e.g., 'Waiting for stream...')."""
        try:
            client = self._connect()
            # Use feh to display a generated image, or fall back to terminal message
            cmd = (
                f"DISPLAY=:0 xterm -fullscreen -fa 'Monospace' -fs 36 "
                f"-e 'echo \"{message}\" && sleep 86400' &"
            )
            client.exec_command(cmd)
            client.close()
            return True
        except Exception:
            logger.exception("Failed to show message on Pi")
            return False

    def clear_screen(self) -> bool:
        """Kill any display processes on the Pi."""
        try:
            client = self._connect()
            client.exec_command("pkill -f 'ffplay.*udp://'")
            client.exec_command("pkill -f 'xterm.*fullscreen'")
            client.close()
            return True
        except Exception:
            logger.exception("Failed to clear Pi screen")
            return False
