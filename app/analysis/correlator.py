CAUSE_KEY = "potential_cause"
NOTIFY_KEY = "should_notify"

def analyze_outage(weather_data, percent_down):
    condition = weather_data["condition"].lower()
    wind = weather_data["wind_mph"]

    # 🔴 Full site outage
    if percent_down >= 0.9:
        if "thunder" in condition or "storm" in condition:
            return {
                CAUSE_KEY: "Severe Weather (Thunderstorm)",
                "confidence": "High",
                NOTIFY_KEY: True
            }

        if "rain" in condition and wind > 15:
            return {
                CAUSE_KEY: "Weather (Rain + Wind)",
                "confidence": "Medium",
                NOTIFY_KEY: True
            }

        if "rain" in condition:
            return {
                CAUSE_KEY: "Weather (Light Rain)",
                "confidence": "Low",
                NOTIFY_KEY: True
            }

        return {
            CAUSE_KEY: "Unknown",
            "confidence": "Low",
            NOTIFY_KEY: True
        }

    # 🟡 Partial outage
    return {
        CAUSE_KEY: "Likely Device/Network Issue",
        "confidence": "Low",
        NOTIFY_KEY: False
    }