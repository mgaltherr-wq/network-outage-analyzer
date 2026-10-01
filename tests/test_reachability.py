import subprocess
import threading
import time
import unittest
from unittest.mock import patch

from app.services.reachability import check_devices, is_reachable


class ReachabilityTests(unittest.TestCase):
    @patch("app.services.reachability.subprocess.run")
    def test_is_reachable_when_ping_succeeds(self, run):
        run.return_value = subprocess.CompletedProcess([], 0)

        self.assertTrue(is_reachable("192.168.42.205"))
        run.assert_called_once_with(
            ["ping", "-n", "-c", "1", "-W", "1", "192.168.42.205"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=2,
        )

    @patch("app.services.reachability.subprocess.run")
    def test_is_reachable_when_ping_fails(self, run):
        run.return_value = subprocess.CompletedProcess([], 1)

        self.assertFalse(is_reachable("192.168.42.205"))

    @patch("app.services.reachability.is_reachable", side_effect=[True, False])
    def test_check_devices_splits_reachable_and_unreachable(self, _is_reachable):
        reachable, unreachable = check_devices(["192.168.42.205", "192.168.42.206"])

        self.assertEqual(reachable, ["192.168.42.205"])
        self.assertEqual(unreachable, ["192.168.42.206"])

    @patch("app.services.reachability.IS_WINDOWS", True)
    @patch("app.services.reachability.subprocess.run")
    def test_windows_uses_windows_flags_and_requires_echo_reply(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, stdout=b"Reply from 10.0.0.1: bytes=32 time=1ms TTL=64")

        self.assertTrue(is_reachable("10.0.0.1", timeout_seconds=2))
        args, kwargs = run.call_args
        self.assertEqual(args[0], ["ping", "-n", "1", "-w", "2000", "10.0.0.1"])
        self.assertIn("creationflags", kwargs)

        # Windows exits 0 for "Destination host unreachable" relayed by a router.
        run.return_value = subprocess.CompletedProcess(
            [], 0, stdout=b"Reply from 10.0.0.254: Destination host unreachable."
        )
        self.assertFalse(is_reachable("10.0.0.1"))

    def test_check_devices_pings_in_parallel(self):
        barrier = threading.Barrier(4, timeout=5)

        def fake_is_reachable(ip, _timeout):
            # Every ping blocks until all four are in flight at once, so this
            # deadlocks (BrokenBarrierError -> False) if they run sequentially.
            try:
                barrier.wait()
            except threading.BrokenBarrierError:
                return False
            return ip != "10.0.0.3"

        with patch("app.services.reachability.is_reachable", side_effect=fake_is_reachable):
            reachable, unreachable = check_devices(["10.0.0.1", "10.0.0.2", "10.0.0.3", "10.0.0.4"])

        self.assertEqual(reachable, ["10.0.0.1", "10.0.0.2", "10.0.0.4"])
        self.assertEqual(unreachable, ["10.0.0.3"])

    def test_check_devices_respects_concurrency_limit(self):
        in_flight = 0
        peak = 0
        lock = threading.Lock()

        def fake_is_reachable(_ip, _timeout):
            nonlocal in_flight, peak
            with lock:
                in_flight += 1
                peak = max(peak, in_flight)
            time.sleep(0.02)
            with lock:
                in_flight -= 1
            return True

        with patch("app.services.reachability.is_reachable", side_effect=fake_is_reachable):
            reachable, _ = check_devices([f"10.0.0.{i}" for i in range(1, 21)], max_concurrent=3)

        self.assertEqual(len(reachable), 20)
        self.assertLessEqual(peak, 3)

    def test_check_devices_with_no_addresses(self):
        self.assertEqual(check_devices([]), ([], []))


if __name__ == "__main__":
    unittest.main()
