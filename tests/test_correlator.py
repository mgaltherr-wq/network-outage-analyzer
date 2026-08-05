import unittest

from app.analysis.correlator import CAUSE_KEY, NOTIFY_KEY, analyze_outage, assess_outage_sources


class AnalyzeOutageTests(unittest.TestCase):
    def test_flags_severe_weather_at_full_outage(self):
        weather = {"condition": "thunderstorm", "wind_mph": 5, "temp_f": 70}

        result = analyze_outage(weather, 0.95)

        self.assertEqual(result[CAUSE_KEY], "Severe Weather (Thunderstorm)")
        self.assertEqual(result["confidence"], "High")
        self.assertTrue(result[NOTIFY_KEY])

    def test_partial_outage_is_not_actionable(self):
        weather = {"condition": "clear sky", "wind_mph": 5, "temp_f": 70}

        result = analyze_outage(weather, 0.5)

        self.assertEqual(result[CAUSE_KEY], "Likely Device/Network Issue")
        self.assertFalse(result[NOTIFY_KEY])


class AssessOutageSourcesTests(unittest.TestCase):
    def test_weather_signal_reuses_cause_rules(self):
        weather = {"condition": "thunderstorm", "wind_mph": 5, "temp_f": 70}
        not_checked = {"checked": False, "detected": False, "detail": "not configured"}

        result = assess_outage_sources(weather, not_checked, not_checked)

        self.assertEqual(result["weather"], {"confidence": "High", "detail": "Severe Weather (Thunderstorm)"})

    def test_network_and_power_high_confidence_when_detected(self):
        weather = {"condition": "clear sky", "wind_mph": 2, "temp_f": 70}
        detected = {"checked": True, "detected": True, "detail": "Regional ISP outage"}

        result = assess_outage_sources(weather, detected, detected)

        self.assertEqual(result["network"], {"confidence": "High", "detail": "Regional ISP outage"})
        self.assertEqual(result["power"], {"confidence": "High", "detail": "Regional ISP outage"})

    def test_low_confidence_when_checked_but_not_detected(self):
        weather = {"condition": "clear sky", "wind_mph": 2, "temp_f": 70}
        clear = {"checked": True, "detected": False, "detail": "No verified outages reported"}

        result = assess_outage_sources(weather, clear, clear)

        self.assertEqual(result["network"]["confidence"], "Low")
        self.assertEqual(result["power"]["confidence"], "Low")

    def test_unknown_confidence_when_not_checked(self):
        weather = {"condition": "clear sky", "wind_mph": 2, "temp_f": 70}
        unconfigured = {"checked": False, "detected": False, "detail": "Cloudflare Radar not configured"}

        result = assess_outage_sources(weather, unconfigured, unconfigured)

        self.assertEqual(result["network"]["confidence"], "Unknown")
        self.assertEqual(result["power"]["confidence"], "Unknown")


if __name__ == "__main__":
    unittest.main()
