import importlib
import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import app.ip_inventory as inventory_module

from fastapi.testclient import TestClient

from app import config as config_module
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
        dashboard_module._cached_geocode.cache_clear()
        dashboard_module._active_outage_tickets.clear()

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

    @patch("app.dashboard.check_devices")
    def test_device_status_reports_reachable_and_unreachable(self, check_devices):
        self.path.write_text(json.dumps([
            {"ip_address": "10.0.0.1", "location": "", "location_source": "manual"},
            {"ip_address": "10.0.0.2", "location": "", "location_source": "manual"},
        ]), encoding="utf-8")
        check_devices.return_value = (["10.0.0.1"], ["10.0.0.2"])

        response = self.client.get("/api/devices/status")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"devices": [
            {"ip_address": "10.0.0.1", "reachable": True},
            {"ip_address": "10.0.0.2", "reachable": False},
        ]})
        check_devices.assert_called_once_with(["10.0.0.1", "10.0.0.2"])

    def test_dashboard_page_includes_location_input(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn('id="locationInput"', response.text)
        self.assertIn('Optional location', response.text)

    def test_dashboard_page_includes_outage_analysis_section(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn('id="outageList"', response.text)
        self.assertIn('Outage analysis', response.text)

    @patch("app.dashboard.servicenow.search_or_create_outage_incident")
    @patch("app.dashboard.check_power_outage")
    @patch("app.dashboard.check_network_outage")
    @patch("app.dashboard.get_weather")
    @patch("app.dashboard.check_devices")
    @patch("app.dashboard.geocode_location")
    def test_device_locations_includes_confidence_when_fully_down(
        self, geocode_location, check_devices, get_weather, check_network_outage, check_power_outage, search_or_create_ticket
    ):
        self.path.write_text(json.dumps([
            {"ip_address": "10.0.0.1", "location": "HQ - Core", "location_source": "manual"}
        ]), encoding="utf-8")
        geocode_location.return_value = {
            "latitude": 29.7604, "longitude": -95.3698, "name": "Houston", "state": "Texas", "country": "US",
        }
        check_devices.return_value = ([], ["10.0.0.1"])
        get_weather.return_value = {"condition": "thunderstorm", "wind_mph": 20, "temp_f": 75}
        check_network_outage.return_value = {"checked": True, "detected": True, "detail": "Regional ISP outage"}
        check_power_outage.return_value = {"checked": True, "detected": False, "detail": "No significant power outages reported in Harris County"}
        search_or_create_ticket.return_value = {"sys_id": "abc123", "number": "INC0001", "action": "created"}

        response = self.client.get("/api/device-locations")

        self.assertEqual(response.status_code, 200)
        location = response.json()["locations"][0]
        self.assertEqual(location["confidence"]["weather"]["confidence"], "High")
        self.assertEqual(location["confidence"]["network"], {"confidence": "High", "detail": "Regional ISP outage"})
        self.assertEqual(location["confidence"]["power"]["confidence"], "Low")
        self.assertEqual(location["ticket"], {"sys_id": "abc123", "number": "INC0001", "action": "created"})

    @patch("app.dashboard.servicenow.search_or_create_outage_incident")
    @patch("app.dashboard.check_power_outage")
    @patch("app.dashboard.check_network_outage")
    @patch("app.dashboard.get_weather")
    @patch("app.dashboard.check_devices")
    @patch("app.dashboard.geocode_location")
    def test_device_locations_only_tickets_once_per_outage_episode(
        self, geocode_location, check_devices, get_weather, check_network_outage, check_power_outage, search_or_create_ticket
    ):
        self.path.write_text(json.dumps([
            {"ip_address": "10.0.0.1", "location": "HQ - Core", "location_source": "manual"}
        ]), encoding="utf-8")
        geocode_location.return_value = {
            "latitude": 29.7604, "longitude": -95.3698, "name": "Houston", "state": "Texas", "country": "US",
        }
        get_weather.return_value = {"condition": "thunderstorm", "wind_mph": 20, "temp_f": 75}
        check_network_outage.return_value = {"checked": True, "detected": True, "detail": "Regional ISP outage"}
        check_power_outage.return_value = {"checked": True, "detected": False, "detail": "No significant power outages reported in Harris County"}
        search_or_create_ticket.return_value = {"sys_id": "abc123", "number": "INC0001", "action": "created"}

        # Still down: polling again during the same episode must not re-ticket.
        check_devices.return_value = ([], ["10.0.0.1"])
        self.client.get("/api/device-locations")
        self.client.get("/api/device-locations")
        search_or_create_ticket.assert_called_once()

        # Recovers: episode state clears.
        check_devices.return_value = (["10.0.0.1"], [])
        self.client.get("/api/device-locations")

        # Drops again: a new episode tickets again.
        check_devices.return_value = ([], ["10.0.0.1"])
        self.client.get("/api/device-locations")
        self.assertEqual(search_or_create_ticket.call_count, 2)

    @patch("app.dashboard.get_weather")
    @patch("app.dashboard.check_devices")
    @patch("app.dashboard.geocode_location")
    def test_device_locations_omits_confidence_below_threshold(
        self, geocode_location, check_devices, get_weather
    ):
        self.path.write_text(json.dumps([
            {"ip_address": "10.0.0.1", "location": "HQ - Core", "location_source": "manual"},
            {"ip_address": "10.0.0.2", "location": "HQ - Core", "location_source": "manual"},
        ]), encoding="utf-8")
        geocode_location.return_value = {
            "latitude": 29.7604, "longitude": -95.3698, "name": "Houston", "state": "Texas", "country": "US",
        }
        check_devices.return_value = (["10.0.0.2"], ["10.0.0.1"])

        response = self.client.get("/api/device-locations")

        self.assertEqual(response.status_code, 200)
        location = response.json()["locations"][0]
        self.assertNotIn("confidence", location)
        get_weather.assert_not_called()

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


class SettingsApiTests(unittest.TestCase):
    def setUp(self):
        self.env_backup = dict(os.environ)
        self.temp_dir = TemporaryDirectory()
        self.env_path = Path(self.temp_dir.name) / ".env"
        self.env_path.write_text("", encoding="utf-8")
        self.patcher = patch("app.settings_store.ENV_PATH", self.env_path)
        self.patcher.start()
        self.config_env_patcher = patch("app.config.ENV_PATH", self.env_path)
        self.config_env_patcher.start()
        self.client = TestClient(dashboard_module.app)

    def tearDown(self):
        self.config_env_patcher.stop()
        self.patcher.stop()
        self.temp_dir.cleanup()
        os.environ.clear()
        os.environ.update(self.env_backup)
        importlib.reload(config_module)

    def test_settings_page_is_served(self):
        response = self.client.get("/settings")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Settings", response.text)

    def test_get_settings_lists_masked_fields(self):
        response = self.client.get("/api/settings")

        self.assertEqual(response.status_code, 200)
        keys = [setting["key"] for setting in response.json()["settings"]]
        self.assertIn("WEATHER_API_KEY", keys)
        self.assertIn("SNMP_COMMUNITY", keys)

    def test_put_settings_updates_value_and_applies_live(self):
        response = self.client.put(
            "/api/settings", json={"values": {"WEATHER_API_KEY": "updated-key"}}
        )

        self.assertEqual(response.status_code, 200)
        updated = {s["key"]: s for s in response.json()["settings"]}
        self.assertTrue(updated["WEATHER_API_KEY"]["is_set"])
        self.assertEqual(config_module.WEATHER_API_KEY, "updated-key")

    def test_put_settings_rejects_unknown_key(self):
        response = self.client.put(
            "/api/settings", json={"values": {"NOT_A_SETTING": "x"}}
        )

        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
