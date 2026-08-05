CAUSE_KEY = "potential_cause"
NOTIFY_KEY = "should_notify"

OUTAGE_THRESHOLD = 0.9


def _assess_weather_cause(weather_data):
    condition = weather_data["condition"].lower()
    wind = weather_data["wind_mph"]

    if "thunder" in condition or "storm" in condition:
        return "Severe Weather (Thunderstorm)", "High"

    if "rain" in condition and wind > 15:
        return "Weather (Rain + Wind)", "Medium"

    if "rain" in condition:
        return "Weather (Light Rain)", "Low"

    return "Unknown", "Low"


def analyze_outage(weather_data, percent_down):
    # 🔴 Full site outage
    if percent_down >= OUTAGE_THRESHOLD:
        cause, confidence = _assess_weather_cause(weather_data)
        return {
            CAUSE_KEY: cause,
            "confidence": confidence,
            NOTIFY_KEY: True
        }

    # 🟡 Partial outage
    return {
        CAUSE_KEY: "Likely Device/Network Issue",
        "confidence": "Low",
        NOTIFY_KEY: False
    }


def _assess_external_source(source_result):
    if not source_result.get("checked"):
        return {"confidence": "Unknown", "detail": source_result.get("detail", "")}

    if source_result.get("detected"):
        return {"confidence": "High", "detail": source_result.get("detail", "")}

    return {"confidence": "Low", "detail": source_result.get("detail", "")}


def assess_outage_sources(weather_data, network_result, power_result):
    """Assess how likely a location's outage is due to weather, a broader
    network outage, or a broader power outage, as three parallel signals.

    Callers should only invoke this once a location's percent_down has
    crossed OUTAGE_THRESHOLD.
    """
    cause, confidence = _assess_weather_cause(weather_data)

    return {
        "weather": {"confidence": confidence, "detail": cause},
        "network": _assess_external_source(network_result),
        "power": _assess_external_source(power_result),
    }