import requests

from app.config import CLOUDFLARE_API_TOKEN


def check_network_outage(country_code):
    """Check Cloudflare Radar for verified internet outages in a country.

    Returns a status dict rather than raising, so a missing token or a flaky
    upstream never breaks the caller.
    """
    if not CLOUDFLARE_API_TOKEN or not country_code:
        return {
            "checked": False,
            "detected": False,
            "detail": "Cloudflare Radar not configured",
        }

    response = requests.get(
        "https://api.cloudflare.com/client/v4/radar/annotations/outages",
        headers={"Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}"},
        params={"location": country_code, "limit": 5},
        timeout=10,
    )
    response.raise_for_status()

    annotations = response.json().get("result", {}).get("annotations", [])
    if not annotations:
        return {
            "checked": True,
            "detected": False,
            "detail": "No verified outages reported",
        }

    return {
        "checked": True,
        "detected": True,
        "detail": annotations[0].get("description") or "Verified outage reported",
    }
