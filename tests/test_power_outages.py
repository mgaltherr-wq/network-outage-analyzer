import unittest
from unittest.mock import patch

from app.services.power_outages import check_power_outage, lookup_us_county


class LookupUsCountyTests(unittest.TestCase):
    @patch("app.services.power_outages.requests.get")
    def test_strips_county_suffix(self, get):
        get.return_value.json.return_value = {
            "County": {"FIPS": "48201", "name": "Harris County"},
            "State": {"FIPS": "48", "code": "TX", "name": "Texas"},
        }

        county, state = lookup_us_county(29.7604, -95.3698)

        self.assertEqual(county, "Harris")
        self.assertEqual(state, "Texas")

    @patch("app.services.power_outages.requests.get")
    def test_returns_none_when_unresolvable(self, get):
        get.return_value.json.return_value = {}

        county, state = lookup_us_county(0, 0)

        self.assertIsNone(county)
        self.assertIsNone(state)


class CheckPowerOutageTests(unittest.TestCase):
    @patch("app.services.power_outages.requests.get")
    def test_returns_unresolvable_when_county_lookup_fails(self, get):
        get.return_value.json.return_value = {}

        result = check_power_outage(0, 0)

        self.assertEqual(result, {
            "checked": False,
            "detected": False,
            "detail": "Could not resolve a US county for these coordinates",
        })
        get.assert_called_once()

    @patch("app.services.power_outages.requests.get")
    def test_detects_outage_from_meters_affected(self, get):
        fcc_response = {
            "County": {"name": "Harris County"},
            "State": {"name": "Texas"},
        }
        odin_response = {"records": [{"fields": {"metersaffected": 4200}}]}
        get.return_value.json.side_effect = [fcc_response, odin_response]

        result = check_power_outage(29.7604, -95.3698)

        self.assertEqual(result, {
            "checked": True,
            "detected": True,
            "detail": "4200 meters without power in Harris County",
        })

    @patch("app.services.power_outages.requests.get")
    def test_no_outage_when_no_meters_affected(self, get):
        fcc_response = {
            "County": {"name": "Harris County"},
            "State": {"name": "Texas"},
        }
        odin_response = {"records": []}
        get.return_value.json.side_effect = [fcc_response, odin_response]

        result = check_power_outage(29.7604, -95.3698)

        self.assertEqual(result, {
            "checked": True,
            "detected": False,
            "detail": "No significant power outages reported in Harris County",
        })


if __name__ == "__main__":
    unittest.main()
