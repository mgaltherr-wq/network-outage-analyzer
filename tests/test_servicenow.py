import unittest

from app.services.servicenow import build_weather_note


class ServiceNowNoteTests(unittest.TestCase):
    def test_build_weather_note_includes_weather_and_analysis(self):
        weather = {
            "condition": "thunderstorm",
            "wind_mph": 22,
            "temp_f": 74,
        }
        analysis = {
            "potential_cause": "Severe Weather (Thunderstorm)",
            "confidence": "High",
        }

        note = build_weather_note(weather, analysis, 0.92)

        self.assertIn("Devices down: 92%", note)
        self.assertIn("Weather condition: thunderstorm", note)
        self.assertIn("Wind speed: 22 mph", note)
        self.assertIn("Temperature: 74 F", note)
        self.assertIn("Potential cause: Severe Weather (Thunderstorm)", note)
        self.assertIn("Confidence: High", note)


if __name__ == "__main__":
    unittest.main()
