import unittest
from unittest.mock import patch

from app.services.weather import geocode_location


class GeocodeLocationTests(unittest.TestCase):
    @patch("app.services.weather.WEATHER_API_KEY", "test-key")
    @patch("app.services.weather.requests.get")
    def test_geocode_location_returns_first_match(self, get):
        get.return_value.json.return_value = [{
            "name": "Los Angeles",
            "lat": 34.0522,
            "lon": -118.2437,
            "country": "US",
            "state": "California",
        }]

        result = geocode_location("Los Angeles")

        self.assertEqual(result["latitude"], 34.0522)
        self.assertEqual(result["longitude"], -118.2437)
        get.assert_called_once_with(
            "https://api.openweathermap.org/geo/1.0/direct",
            params={"q": "Los Angeles", "limit": 1, "appid": "test-key"},
            timeout=5,
        )


if __name__ == "__main__":
    unittest.main()
