import unittest
from unittest.mock import patch

from app.services.servicenow import (
    build_outage_note,
    create_incident,
    find_recent_incident_for_ips,
    search_or_create_outage_incident,
)


class BuildOutageNoteTests(unittest.TestCase):
    def test_includes_location_ips_and_percent_down(self):
        note = build_outage_note("HQ - Core", ["10.0.0.1", "10.0.0.2"], 0.92, None)

        self.assertIn("Location: HQ - Core", note)
        self.assertIn("Devices down: 92% (10.0.0.1, 10.0.0.2)", note)

    def test_includes_confidence_breakdown_when_present(self):
        confidence = {
            "weather": {"confidence": "High", "detail": "Severe Weather (Thunderstorm)"},
            "network": {"confidence": "Low", "detail": "No verified outages reported"},
            "power": {"confidence": "Unknown", "detail": "Power outage check failed"},
        }

        note = build_outage_note("HQ - Core", ["10.0.0.1"], 1.0, confidence)

        self.assertIn("Weather: High — Severe Weather (Thunderstorm)", note)
        self.assertIn("Network outage: Low — No verified outages reported", note)
        self.assertIn("Power outage: Unknown — Power outage check failed", note)

    def test_omits_confidence_section_when_none(self):
        note = build_outage_note("HQ - Core", ["10.0.0.1"], 0.9, None)

        self.assertNotIn("Weather:", note)


class FindRecentIncidentForIpsTests(unittest.TestCase):
    def setUp(self):
        self.auth_patcher = patch("app.services.servicenow._auth", return_value=("user", "pass"))
        self.auth_patcher.start()
        self.addCleanup(self.auth_patcher.stop)

    @patch("app.services.servicenow.requests.get")
    def test_matches_ip_in_short_description(self, get):
        get.return_value.json.return_value = {"result": [
            {"sys_id": "abc123", "number": "INC0001", "short_description": "Outage affecting 10.0.0.1", "description": ""},
        ]}

        result = find_recent_incident_for_ips(["10.0.0.1", "10.0.0.2"])

        self.assertEqual(result["number"], "INC0001")

    @patch("app.services.servicenow.requests.get")
    def test_matches_ip_in_description(self, get):
        get.return_value.json.return_value = {"result": [
            {"sys_id": "abc123", "number": "INC0001", "short_description": "", "description": "device 10.0.0.2 down"},
        ]}

        result = find_recent_incident_for_ips(["10.0.0.1", "10.0.0.2"])

        self.assertEqual(result["number"], "INC0001")

    @patch("app.services.servicenow.requests.get")
    def test_returns_none_when_no_ip_matches(self, get):
        get.return_value.json.return_value = {"result": [
            {"sys_id": "abc123", "number": "INC0001", "short_description": "Unrelated ticket", "description": ""},
        ]}

        result = find_recent_incident_for_ips(["10.0.0.1"])

        self.assertIsNone(result)

    @patch("app.services.servicenow.requests.get")
    def test_queries_within_configured_hour_window(self, get):
        get.return_value.json.return_value = {"result": []}

        find_recent_incident_for_ips(["10.0.0.1"], hours=4)

        query = get.call_args.kwargs["params"]["sysparm_query"]
        self.assertIn("gs.hoursAgoStart(4)", query)


class SearchOrCreateOutageIncidentTests(unittest.TestCase):
    @patch("app.services.servicenow.add_comment")
    @patch("app.services.servicenow.find_recent_incident_for_ips")
    def test_updates_existing_incident_instead_of_creating(self, find, add_comment):
        find.return_value = {"sys_id": "abc123", "number": "INC0001"}

        result = search_or_create_outage_incident("HQ - Core", ["10.0.0.1"], 0.95, None)

        add_comment.assert_called_once()
        self.assertEqual(add_comment.call_args.args[0], "abc123")
        self.assertEqual(result["action"], "updated")
        self.assertEqual(result["number"], "INC0001")

    @patch("app.services.servicenow.create_incident")
    @patch("app.services.servicenow.find_recent_incident_for_ips", return_value=None)
    def test_creates_high_priority_incident_when_none_found(self, find, create):
        create.return_value = {"sys_id": "def456", "number": "INC0002"}

        result = search_or_create_outage_incident("HQ - Core", ["10.0.0.1"], 0.95, None)

        create.assert_called_once()
        short_description, description = create.call_args.args
        self.assertIn("HQ - Core", short_description)
        self.assertIn("95%", short_description)
        self.assertEqual(result["action"], "created")
        self.assertEqual(result["number"], "INC0002")


class CreateIncidentTests(unittest.TestCase):
    def setUp(self):
        self.auth_patcher = patch("app.services.servicenow._auth", return_value=("user", "pass"))
        self.auth_patcher.start()
        self.addCleanup(self.auth_patcher.stop)

    @patch("app.services.servicenow.requests.post")
    def test_sets_high_priority(self, post):
        post.return_value.json.return_value = {"result": {"sys_id": "abc123", "number": "INC0001"}}

        create_incident("Possible outage", "details")

        self.assertEqual(post.call_args.kwargs["json"]["priority"], "2")


if __name__ == "__main__":
    unittest.main()
