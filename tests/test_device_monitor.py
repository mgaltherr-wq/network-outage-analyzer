import threading
import unittest

from app.services.device_monitor import ReachabilityMonitor


class ReachabilityMonitorTests(unittest.TestCase):
    def test_snapshot_reports_pending_before_first_sweep(self):
        monitor = ReachabilityMonitor(lambda: ["10.0.0.1"], lambda ips: (ips, []))

        self.assertEqual(monitor.snapshot(["10.0.0.1"]), {"10.0.0.1": None})

    def test_sweep_caches_results_and_drops_removed_devices(self):
        addresses = ["10.0.0.1", "10.0.0.2"]
        monitor = ReachabilityMonitor(lambda: list(addresses), lambda ips: (["10.0.0.1"], ["10.0.0.2"]))

        monitor.sweep()
        self.assertEqual(monitor.snapshot(["10.0.0.1", "10.0.0.2"]), {"10.0.0.1": True, "10.0.0.2": False})

        addresses.remove("10.0.0.2")
        monitor.sweep()
        self.assertEqual(monitor.snapshot(["10.0.0.2"]), {"10.0.0.2": None})

    def test_background_thread_sweeps_and_request_sweep_wakes_it(self):
        sweeps = []
        swept = threading.Event()

        def check(ips):
            sweeps.append(list(ips))
            swept.set()
            return ips, []

        # A long interval: the second sweep only happens if request_sweep wakes it.
        monitor = ReachabilityMonitor(lambda: ["10.0.0.1"], check, interval_seconds=lambda: 3600)
        monitor.start()
        self.addCleanup(monitor.stop)

        self.assertTrue(swept.wait(5))
        self.assertTrue(monitor.running)
        swept.clear()
        monitor.request_sweep()
        self.assertTrue(swept.wait(5))
        self.assertEqual(len(sweeps), 2)
        self.assertEqual(monitor.snapshot(["10.0.0.1"]), {"10.0.0.1": True})

        monitor.stop()
        self.assertFalse(monitor.running)

    def test_failed_sweep_does_not_kill_the_thread(self):
        calls = []
        recovered = threading.Event()

        def check(ips):
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("boom")
            recovered.set()
            return ips, []

        monitor = ReachabilityMonitor(lambda: ["10.0.0.1"], check, interval_seconds=0.01)
        monitor.start()
        self.addCleanup(monitor.stop)

        self.assertTrue(recovered.wait(5))
        self.assertEqual(monitor.snapshot(["10.0.0.1"]), {"10.0.0.1": True})


if __name__ == "__main__":
    unittest.main()
