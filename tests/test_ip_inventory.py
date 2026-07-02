import json
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from app.ip_inventory import (
    add_ip_address,
    load_ip_addresses,
    remove_ip_address,
    save_ip_addresses,
)


class IPInventoryTests(unittest.TestCase):
    def test_load_missing_file_returns_empty_list(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "ip_addresses.json"

            self.assertEqual(load_ip_addresses(path), [])

    def test_save_normalizes_sorts_and_deduplicates_ip_addresses(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "ip_addresses.json"

            saved = save_ip_addresses(["192.168.1.10", "10.0.0.5", "192.168.1.10"], path)

            self.assertEqual(saved, ["10.0.0.5", "192.168.1.10"])
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), saved)

    def test_add_ip_address_rejects_duplicates(self):
        updated, added = add_ip_address(["10.0.0.1"], "10.0.0.1")

        self.assertFalse(added)
        self.assertEqual(updated, ["10.0.0.1"])

    def test_add_ip_address_adds_valid_address(self):
        updated, added = add_ip_address(["10.0.0.1"], "192.168.1.1")

        self.assertTrue(added)
        self.assertEqual(updated, ["10.0.0.1", "192.168.1.1"])

    def test_remove_ip_address_removes_existing_address(self):
        updated, removed = remove_ip_address(["10.0.0.1", "192.168.1.1"], "10.0.0.1")

        self.assertTrue(removed)
        self.assertEqual(updated, ["192.168.1.1"])


if __name__ == "__main__":
    unittest.main()
