#!/usr/bin/env python3
"""Standalone receiver script for the Raspberry Pi.

This is an alternative to the SSH-based approach — you can run this directly
on the Pi as a persistent service. It listens for a simple TCP "start"/"stop"
signal and manages ffplay accordingly.

For the SSH approach (recommended), you don't need this file — the Slack bot
controls ffplay over SSH directly.
"""

import logging
import os
import signal
import socket
import subprocess
import sys
import threading

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

UDP_PORT = int(os.environ.get("STREAM_UDP_PORT", "9999"))
CONTROL_PORT = int(os.environ.get("CONTROL_PORT", "9998"))

_ffplay_proc: subprocess.Popen | None = None
_lock = threading.Lock()


def start_receiver():
    global _ffplay_proc
    with _lock:
        if _ffplay_proc and _ffplay_proc.poll() is None:
            logger.info("Receiver already running (PID %s)", _ffplay_proc.pid)
            return True

        env = {**os.environ, "DISPLAY": ":0"}
        try:
            _ffplay_proc = subprocess.Popen(
                [
                    "ffplay", "-fs", "-an",
                    "-fflags", "nobuffer",
                    "-flags", "low_delay",
                    "-analyzeduration", "100000",
                    "-probesize", "100000",
                    "-i", f"udp://@:{UDP_PORT}?overrun_nonfatal=1&fifo_size=50000000",
                    "-loglevel", "warning",
                ],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            logger.info("Receiver started (PID %s) on UDP port %s", _ffplay_proc.pid, UDP_PORT)
            return True
        except FileNotFoundError:
            logger.error("ffplay not found — install ffmpeg: sudo apt install ffmpeg")
            return False


def stop_receiver():
    global _ffplay_proc
    with _lock:
        if _ffplay_proc and _ffplay_proc.poll() is None:
            _ffplay_proc.terminate()
            _ffplay_proc.wait(timeout=5)
            logger.info("Receiver stopped")
        _ffplay_proc = None


def control_listener():
    """Simple TCP control socket — accepts 'start' or 'stop' commands."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", CONTROL_PORT))
    srv.listen(1)
    logger.info("Control listener on port %s", CONTROL_PORT)

    while True:
        conn, addr = srv.accept()
        try:
            data = conn.recv(64).decode().strip().lower()
            if data == "start":
                ok = start_receiver()
                conn.sendall(b"ok\n" if ok else b"error\n")
            elif data == "stop":
                stop_receiver()
                conn.sendall(b"ok\n")
            elif data == "status":
                running = _ffplay_proc and _ffplay_proc.poll() is None
                conn.sendall(b"running\n" if running else b"stopped\n")
            else:
                conn.sendall(b"unknown command\n")
        except Exception:
            logger.exception("Control socket error")
        finally:
            conn.close()


def main():
    def _shutdown(sig, frame):
        logger.info("Shutting down...")
        stop_receiver()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    # Start receiver immediately so TV shows ffplay waiting screen
    start_receiver()

    # Listen for control commands
    control_listener()


if __name__ == "__main__":
    main()
