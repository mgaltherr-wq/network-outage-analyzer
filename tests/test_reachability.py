import subprocess
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


if __name__ == "__main__":
    unittest.main()
