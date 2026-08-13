import unittest
from unittest.mock import patch

from app.services.network_outages import check_network_outage


class CheckNetworkOutageTests(unittest.TestCase):
    @patch("app.services.network_outages.CLOUDFLARE_API_TOKEN", None)
    def test_returns_unconfigured_when_no_token(self):
        result = check_network_outage("US")

        self.assertEqual(result, {
            "checked": False,
            "detected": False,
            "detail": "Cloudflare Radar not configured",
        })

    @patch("app.services.network_outages.CLOUDFLARE_API_TOKEN", "test-token")
    @patch("app.services.network_outages.requests.get")
    def test_detects_outage_from_annotations(self, get):
        get.return_value.json.return_value = {
            "result": {"annotations": [{"description": "Regional ISP outage", "locations": ["US"]}]}
        }

        result = check_network_outage("US")

        self.assertEqual(result, {
            "checked": True,
            "detected": True,
            "detail": "Regional ISP outage",
        })
        get.assert_called_once()
        call = get.call_args
        self.assertEqual(call.args[0], "https://api.cloudflare.com/client/v4/radar/annotations/outages")
        self.assertEqual(call.kwargs["headers"], {"Authorization": "Bearer test-token"})
        self.assertEqual(call.kwargs["timeout"], 10)
        self.assertEqual(call.kwargs["params"]["limit"], 20)
        self.assertIn("dateStart", call.kwargs["params"])
        self.assertIn("dateEnd", call.kwargs["params"])
        self.assertLess(call.kwargs["params"]["dateStart"], call.kwargs["params"]["dateEnd"])

    @patch("app.services.network_outages.CLOUDFLARE_API_TOKEN", "test-token")
    @patch("app.services.network_outages.requests.get")
    def test_no_outage_when_annotations_empty(self, get):
        get.return_value.json.return_value = {"result": {"annotations": []}}

        result = check_network_outage("US")

        self.assertEqual(result, {
            "checked": True,
            "detected": False,
            "detail": "No verified outages reported",
        })

    @patch("app.services.network_outages.CLOUDFLARE_API_TOKEN", "test-token")
    @patch("app.services.network_outages.requests.get")
    def test_no_outage_when_annotations_dont_match_country(self, get):
        get.return_value.json.return_value = {
            "result": {"annotations": [{"description": "Regional ISP outage", "locations": ["FR"]}]}
        }

        result = check_network_outage("US")

        self.assertEqual(result, {
            "checked": True,
            "detected": False,
            "detail": "No verified outages reported",
        })


if __name__ == "__main__":
    unittest.main()
