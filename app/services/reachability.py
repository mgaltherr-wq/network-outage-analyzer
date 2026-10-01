"""ICMP reachability checks for the configured network devices."""

import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

IS_WINDOWS = sys.platform == "win32"

# Upper bound on ping processes in flight at once. Each one mostly sits idle
# waiting on the network, so this can be far higher than the CPU count; it's
# capped mainly to stay well under per-process file/handle limits.
DEFAULT_MAX_CONCURRENT_PINGS = 64


def _ping_command(ip_address, timeout_seconds):
    if IS_WINDOWS:
        # Windows ping: -n count, -w timeout in milliseconds.
        return ["ping", "-n", "1", "-w", str(int(timeout_seconds * 1000)), ip_address]
    return ["ping", "-n", "-c", "1", "-W", str(timeout_seconds), ip_address]


def is_reachable(ip_address, timeout_seconds=1):
    """Return whether a host replies to one ICMP echo request."""
    try:
        if IS_WINDOWS:
            # Windows ping exits 0 even for "Destination host unreachable"
            # replies relayed by a router, so check for an actual echo reply.
            # CREATE_NO_WINDOW stops each ping flashing a console window in
            # the windowed (no-console) packaged app.
            result = subprocess.run(
                _ping_command(ip_address, timeout_seconds),
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=timeout_seconds + 1,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return result.returncode == 0 and b"TTL=" in result.stdout.upper()

        result = subprocess.run(
            _ping_command(ip_address, timeout_seconds),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=timeout_seconds + 1,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False

    return result.returncode == 0


def check_devices(ip_addresses, timeout_seconds=1, max_concurrent=DEFAULT_MAX_CONCURRENT_PINGS):
    """Return the reachable and unreachable addresses from *ip_addresses*.

    Pings run in parallel (up to *max_concurrent* at once), so a sweep takes
    roughly ceil(len / max_concurrent) * timeout in the worst case instead of
    len * timeout. Both lists keep the input order.
    """
    ip_addresses = list(ip_addresses)
    if not ip_addresses:
        return [], []

    workers = max(1, min(max_concurrent, len(ip_addresses)))
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="ping") as pool:
        results = list(pool.map(lambda ip: is_reachable(ip, timeout_seconds), ip_addresses))

    reachable = [ip for ip, ok in zip(ip_addresses, results) if ok]
    unreachable = [ip for ip, ok in zip(ip_addresses, results) if not ok]
    return reachable, unreachable
