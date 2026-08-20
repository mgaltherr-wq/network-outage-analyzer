"""Packaged-app entry point: start the dashboard and open a browser to it.

This is what the Windows/Linux installers actually launch (via
packaging/windows.spec and packaging/linux.spec) instead of `run.py` or the
`uvicorn` CLI, since neither exists as a separate executable inside a frozen
PyInstaller bundle. It has no console window once packaged, so logging to a
file is the only diagnostic channel if something goes wrong.
"""

import logging
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser

from app.paths import user_data_dir

HOST = "127.0.0.1"
PORT = 8000
BASE_URL = f"http://{HOST}:{PORT}/"
STARTUP_TIMEOUT_SECONDS = 15

log = logging.getLogger("launcher")


def _configure_logging():
    log_path = user_data_dir() / "launcher.log"
    logging.basicConfig(
        filename=log_path,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    return log_path


def _port_is_open():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((HOST, PORT)) == 0


def _looks_like_our_server():
    try:
        with urllib.request.urlopen(BASE_URL, timeout=2) as response:
            return response.status == 200
    except OSError:
        return False


def _wait_until_serving(timeout_seconds):
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if _looks_like_our_server():
            return True
        time.sleep(0.3)
    return False


def _run_server():
    import uvicorn

    config = uvicorn.Config(
        "app.dashboard:app", host=HOST, port=PORT, log_level="info"
    )
    server = uvicorn.Server(config)
    server.run()


def _notify_failure(message):
    log.error(message)
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(0, message, "Network Outage Analyzer", 0x10)
        except Exception:
            log.exception("Failed to show Windows error dialog")
    else:
        try:
            subprocess.run(
                ["notify-send", "Network Outage Analyzer", message],
                check=False,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            pass


def selftest():
    """Import the app and pysnmp without binding a port or opening a browser.

    Used by CI to catch PyInstaller hiddenimports gaps in the frozen build.
    `app.dashboard` alone won't do it: pysnmp is imported lazily inside
    `lookup_location_snmp`, so it's imported explicitly here too.
    """
    import app.dashboard  # noqa: F401
    from pysnmp.hlapi.v3arch.asyncio import (  # noqa: F401
        CommunityData,
        ContextData,
        ObjectIdentity,
        ObjectType,
        SnmpEngine,
        UdpTransportTarget,
        get_cmd,
    )

    print("selftest OK")
    return 0


def main():
    log_path = _configure_logging()
    log.info("Starting, log file at %s", log_path)

    try:
        if _port_is_open():
            log.info("Port %s already in use; checking if it's us", PORT)
            if _looks_like_our_server():
                log.info("Dashboard already running, opening browser")
                webbrowser.open(BASE_URL)
                return 0
            _notify_failure(
                f"Port {PORT} is already in use by another program.\n"
                f"Close it and try again, or see the log at {log_path}."
            )
            return 1

        server_thread = threading.Thread(target=_run_server, daemon=True)
        server_thread.start()

        if not _wait_until_serving(STARTUP_TIMEOUT_SECONDS):
            _notify_failure(
                f"The dashboard did not start in time.\nSee the log at {log_path}."
            )
            return 1

        log.info("Dashboard is up, opening browser")
        webbrowser.open(BASE_URL)
        server_thread.join()
        return 0
    except Exception:
        log.exception("Unhandled error during startup")
        _notify_failure(
            f"Network Outage Analyzer failed to start.\nSee the log at {log_path}."
        )
        return 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    sys.exit(main())
