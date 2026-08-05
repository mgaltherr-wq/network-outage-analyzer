import requests

from app.config import ODIN_DATASET_URL


def lookup_us_county(lat, lon):
    """Reverse-geocode coordinates to a US county/state via the free FCC Census API.

    Returns (county_name, state_name) or (None, None) if it can't be resolved
    (e.g. the coordinates are outside the US).
    """
    response = requests.get(
        "https://geo.fcc.gov/api/census/block/find",
        params={"latitude": lat, "longitude": lon, "format": "json"},
        timeout=10,
    )
    response.raise_for_status()
    data = response.json()

    county = (data.get("County") or {}).get("name")
    state = (data.get("State") or {}).get("name")
    if not county or not state:
        return None, None

    return county.removesuffix(" County"), state


def check_power_outage(lat, lon):
    """Check the DOE/ORNL ODIN dataset for county-level power outages.

    Returns a status dict rather than raising, so an unresolvable location or
    a flaky upstream never breaks the caller.
    """
    county, state = lookup_us_county(lat, lon)
    if not county:
        return {
            "checked": False,
            "detected": False,
            "detail": "Could not resolve a US county for these coordinates",
        }

    response = requests.get(
        ODIN_DATASET_URL,
        params={
            "dataset": "odin-real-time-outages-county",
            "rows": 1,
            "refine.county": county,
            "refine.state": state,
        },
        timeout=10,
    )
    response.raise_for_status()

    records = response.json().get("records", [])
    meters_affected = records[0]["fields"].get("metersaffected", 0) if records else 0

    if not meters_affected:
        return {
            "checked": True,
            "detected": False,
            "detail": f"No significant power outages reported in {county} County",
        }

    return {
        "checked": True,
        "detected": True,
        "detail": f"{meters_affected} meters without power in {county} County",
    }
