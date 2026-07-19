import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import app.ip_inventory as inventory_module

from fastapi.testclient import TestClient

from app import dashboard as dashboard_module


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / "ip_addresses.json"
        self.patcher = patch("app.ip_inventory.DEFAULT_IP_LIST_PATH", self.path)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.client = TestClient(dashboard_module.app)
        inventory_module.load_devices.cache_clear() if hasattr(inventory_module.load_devices, "cache_clear") else None

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_list_devices_returns_device_records(self):
        self.path.write_text(json.dumps([
            {"ip_address": "10.0.0.1", "location": "HQ - Core", "location_source": "manual"}
        ]), encoding="utf-8")

        response = self.client.get("/api/devices")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "devices": [{"ip_address": "10.0.0.1", "location": "HQ - Core", "location_source": "manual"}]
        })

    def test_dashboard_page_includes_location_input(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn('id="locationInput"', response.text)
        self.assertIn('Optional location', response.text)

    def test_create_device_persists_as_device_record(self):
        response = self.client.post(
            "/api/devices",
            json={"ip_address": "192.168.1.10", "location": "Branch Office"},
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["devices"], [{
            "ip_address": "192.168.1.10",
            "location": "Branch Office",
            "location_source": "manual",
        }])


if __name__ == "__main__":
    unittest.main()
