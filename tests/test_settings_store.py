import importlib
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app import config as config_module
from app import settings_store


class SettingsStoreTests(unittest.TestCase):
    def setUp(self):
        self.env_backup = dict(os.environ)
        self.temp_dir = TemporaryDirectory()
        self.env_path = Path(self.temp_dir.name) / ".env"
        self.env_path.write_text("", encoding="utf-8")
        self.patcher = patch("app.settings_store.ENV_PATH", self.env_path)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.temp_dir.cleanup()
        os.environ.clear()
        os.environ.update(self.env_backup)
        importlib.reload(config_module)

    def test_get_settings_masks_secret_values(self):
        settings_store.update_settings({"WEATHER_API_KEY": "abcd1234efgh"})

        settings = {s["key"]: s for s in settings_store.get_settings()}

        self.assertTrue(settings["WEATHER_API_KEY"]["secret"])
        self.assertTrue(settings["WEATHER_API_KEY"]["is_set"])
        self.assertEqual(settings["WEATHER_API_KEY"]["value"], "********efgh")

    def test_get_settings_shows_plain_values_for_non_secret_fields(self):
        settings_store.update_settings({"SNMP_VERSION": "1"})

        settings = {s["key"]: s for s in settings_store.get_settings()}

        self.assertFalse(settings["SNMP_VERSION"]["secret"])
        self.assertEqual(settings["SNMP_VERSION"]["value"], "1")

    def test_update_settings_persists_to_env_file(self):
        settings_store.update_settings({"WEATHER_API_KEY": "new-key"})

        contents = self.env_path.read_text(encoding="utf-8")
        self.assertIn("WEATHER_API_KEY=new-key", contents)

    def test_update_settings_applies_live_without_restart(self):
        settings_store.update_settings({"WEATHER_API_KEY": "new-key"})

        self.assertEqual(config_module.WEATHER_API_KEY, "new-key")

    def test_update_settings_blank_value_clears_setting(self):
        settings_store.update_settings({"SNMP_COMMUNITY": "private"})
        settings_store.update_settings({"SNMP_COMMUNITY": ""})

        settings = {s["key"]: s for s in settings_store.get_settings()}
        self.assertFalse(settings["SNMP_COMMUNITY"]["is_set"])
        self.assertEqual(config_module.SNMP_COMMUNITY, "public")

    def test_update_settings_rejects_unknown_key(self):
        with self.assertRaises(ValueError):
            settings_store.update_settings({"NOT_A_REAL_SETTING": "x"})


if __name__ == "__main__":
    unittest.main()
