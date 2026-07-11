"""ICMP reachability checks for the configured network devices."""

import subprocess


def is_reachable(ip_address, timeout_seconds=1):
    """Return whether a host replies to one ICMP echo request."""
    try:
        result = subprocess.run(
            ["ping", "-n", "-c", "1", "-W", str(timeout_seconds), ip_address],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=timeout_seconds + 1,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False

    return result.returncode == 0


def check_devices(ip_addresses, timeout_seconds=1):
    """Return the reachable and unreachable addresses from *ip_addresses*."""
    reachable = []
    unreachable = []

    for ip_address in ip_addresses:
        target = reachable if is_reachable(ip_address, timeout_seconds) else unreachable
        target.append(ip_address)

    return reachable, unreachable
