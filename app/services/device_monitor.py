"""Background reachability sweeps, shared by every dashboard request.

Without this, each browser tab's polling pinged the whole inventory itself, so
request latency grew with device count and the network load grew with the
number of open tabs. Instead, one background thread sweeps every device on a
fixed interval and caches the results; API handlers just read the cache.
"""

import logging
import threading
import time

log = logging.getLogger(__name__)


class ReachabilityMonitor:
    def __init__(self, get_addresses, check, interval_seconds=15):
        """*get_addresses* returns the IPs to sweep; *check* takes a list of
        IPs and returns (reachable, unreachable), like
        reachability.check_devices. *interval_seconds* may be a number or a
        callable, re-read before every wait so settings changes apply live."""
        self._get_addresses = get_addresses
        self._check = check
        self._interval = interval_seconds
        self._results = {}  # ip -> (reachable: bool, checked_at: float)
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread = None
        self.last_sweep_seconds = None

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self):
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="reachability-monitor", daemon=True)
        self._thread.start()

    def stop(self, timeout=5):
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout)
        self._thread = None

    def request_sweep(self):
        """Run the next sweep now instead of waiting out the interval (e.g.
        right after a device is added, so it doesn't sit as pending)."""
        self._wake.set()

    def snapshot(self, ip_addresses):
        """Return {ip: True/False/None} — None means not checked yet."""
        with self._lock:
            return {ip: self._results[ip][0] if ip in self._results else None for ip in ip_addresses}

    def sweep(self):
        addresses = list(dict.fromkeys(self._get_addresses()))
        started = time.monotonic()
        reachable, _ = self._check(addresses)
        checked_at = time.time()
        reachable_set = set(reachable)

        with self._lock:
            # Rebuild rather than update, so removed devices drop out.
            self._results = {ip: (ip in reachable_set, checked_at) for ip in addresses}
        self.last_sweep_seconds = time.monotonic() - started

    def _run(self):
        while not self._stop.is_set():
            self._wake.clear()
            started = time.monotonic()
            try:
                self.sweep()
            except Exception:
                log.exception("Reachability sweep failed")

            # The interval is start-to-start; a sweep that overruns it (very
            # large inventory) just starts the next one immediately.
            interval = self._interval() if callable(self._interval) else self._interval
            remaining = interval - (time.monotonic() - started)
            if remaining > 0:
                self._wake.wait(remaining)
