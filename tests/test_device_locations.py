import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app import dashboard


class DeviceLocationTests(unittest.TestCase):
    def test_groups_devices_at_same_location(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "ip_addresses.json"
            path.write_text(json.dumps([
                {"ip_address": "10.0.0.1", "location": "Los Angeles", "location_source": "manual"},
                {"ip_address": "10.0.0.2", "location": "los angeles", "location_source": "manual"},
                {"ip_address": "10.0.0.3", "location": "", "location_source": "manual"},
            ]), encoding="utf-8")
            coordinates = {
                "latitude": 34.0522,
                "longitude": -118.2437,
                "name": "Los Angeles",
                "state": "California",
                "country": "US",
            }
            with patch("app.ip_inventory.DEFAULT_IP_LIST_PATH", path), patch(
                "app.dashboard._cached_geocode", return_value=coordinates
            ) as geocode, patch(
                "app.dashboard.check_devices", return_value=(["10.0.0.1", "10.0.0.2"], [])
            ) as check:
                result = dashboard.list_device_locations()

            self.assertEqual(result, {"locations": [{
                "location": "Los Angeles",
                "devices": ["10.0.0.1", "10.0.0.2"],
                **coordinates,
                "status": "up",
                "reachable": 2,
                "unreachable": 0,
            }]})
            geocode.assert_called_once_with("Los Angeles")
            check.assert_called_once_with(["10.0.0.1", "10.0.0.2"])
