import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app import dashboard


class SnmpSyncTests(unittest.TestCase):
    def test_refresh_persists_discovered_location(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "ip_addresses.json"
            path.write_text(json.dumps([
                {"ip_address": "10.0.0.1", "location": "Old", "location_source": "manual"},
            ]), encoding="utf-8")
            with patch("app.ip_inventory.DEFAULT_IP_LIST_PATH", path), patch(
                "app.dashboard.lookup_location_snmp", return_value="Los Angeles"
            ) as lookup:
                result = dashboard.refresh_device_locations_from_snmp()

            stored = json.loads(path.read_text(encoding="utf-8"))[0]
            self.assertEqual(result["updated"], ["10.0.0.1"])
            self.assertEqual(stored["location"], "Los Angeles")
            self.assertEqual(stored["location_source"], "snmp")
            lookup.assert_called_once_with(
                "10.0.0.1",
                community=dashboard.SNMP_COMMUNITY,
                timeout=dashboard.SNMP_TIMEOUT_SECONDS,
                version=dashboard.SNMP_VERSION,
            )


if __name__ == "__main__":
    unittest.main()
