from datetime import datetime, timedelta

import requests

from app.config import CLOUDFLARE_API_TOKEN


def check_network_outage(country_code, days=12):
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

    date_end = datetime.utcnow()
    date_start = date_end - timedelta(days=days)

    response = requests.get(
        "https://api.cloudflare.com/client/v4/radar/annotations/outages",
        headers={"Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}"},
        params={
            "dateStart": date_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "dateEnd": date_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "limit": 20,
        },
        timeout=10,
    )
    response.raise_for_status()

    annotations = response.json().get("result", {}).get("annotations", [])
    matches = [a for a in annotations if country_code in a.get("locations", [])]

    if not matches:
        return {
            "checked": True,
            "detected": False,
            "detail": "No verified outages reported",
        }

    return {
        "checked": True,
        "detected": True,
        "detail": matches[0].get("description") or "Verified outage reported",
    }
