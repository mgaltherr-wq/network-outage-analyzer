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
            "result": {"annotations": [{"description": "Regional ISP outage"}]}
        }

        result = check_network_outage("US")

        self.assertEqual(result, {
            "checked": True,
            "detected": True,
            "detail": "Regional ISP outage",
        })
        get.assert_called_once_with(
            "https://api.cloudflare.com/client/v4/radar/annotations/outages",
            headers={"Authorization": "Bearer test-token"},
            params={"location": "US", "limit": 5},
            timeout=10,
        )

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


if __name__ == "__main__":
    unittest.main()
