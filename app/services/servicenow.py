import requests

from app import config

OUTAGE_SEARCH_WINDOW_HOURS = 4
HIGH_PRIORITY = "2"


class ServiceNowConfigError(ValueError):
    pass


def _base_url():
    return config.SERVICENOW_INSTANCE_URL.rstrip("/")


def _auth():
    if not config.SERVICENOW_USERNAME or not config.SERVICENOW_PASSWORD:
        raise ServiceNowConfigError(
            "Set SERVICENOW_USERNAME and SERVICENOW_PASSWORD in .env."
        )

    return (config.SERVICENOW_USERNAME, config.SERVICENOW_PASSWORD)


def _headers():
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def _parse_json(response):
    try:
        return response.json()
    except ValueError as exc:
        raise ServiceNowConfigError(
            "ServiceNow returned a non-JSON response "
            f"(HTTP {response.status_code}). If this is a Personal Developer "
            "Instance, it may be hibernating — wake it up at "
            "https://developer.servicenow.com and try again."
        ) from exc


def find_recent_incident_for_ips(ip_addresses, hours=OUTAGE_SEARCH_WINDOW_HOURS):
    """Return the most recent incident created in the last *hours* whose
    short description or description mentions any of *ip_addresses*, or None.

    Fetches a time-windowed batch and matches in Python rather than building
    an encoded ^OR query per IP/field: `work_notes`/`comments` are journal
    fields ServiceNow doesn't reliably let you LIKE-filter via the Table API,
    and OR-ing many IPs across two fields needs `^NQ` grouping that gets
    unwieldy fast. This assumes recent ticket volume is small enough for one
    page (true for a dev/small instance); a busier instance would need
    pagination.
    """
    response = requests.get(
        f"{_base_url()}/api/now/table/incident",
        auth=_auth(),
        headers=_headers(),
        params={
            "sysparm_query": (
                f"sys_created_on>=javascript:gs.hoursAgoStart({hours})"
                "^ORDERBYDESCsys_created_on"
            ),
            "sysparm_fields": "sys_id,number,short_description,description",
            "sysparm_limit": "50",
        },
        timeout=15,
    )
    response.raise_for_status()

    for incident in _parse_json(response).get("result", []):
        text = f"{incident.get('short_description', '')} {incident.get('description', '')}"
        if any(ip in text for ip in ip_addresses):
            return incident

    return None


def create_incident(short_description, description):
    response = requests.post(
        f"{_base_url()}/api/now/table/incident",
        auth=_auth(),
        headers=_headers(),
        json={
            "short_description": short_description,
            "description": description,
            "priority": HIGH_PRIORITY,
        },
        timeout=15,
    )
    response.raise_for_status()

    return _parse_json(response)["result"]


def add_comment(incident_sys_id, note):
    response = requests.patch(
        f"{_base_url()}/api/now/table/incident/{incident_sys_id}",
        auth=_auth(),
        headers=_headers(),
        json={config.SERVICENOW_NOTE_FIELD: note},
        timeout=15,
    )
    response.raise_for_status()

    return _parse_json(response)["result"]


def build_outage_note(location, ip_addresses, percent_down, confidence):
    lines = [
        "Automated outage analysis (Network Outage Analyzer)",
        f"Location: {location}",
        f"Devices down: {percent_down:.0%} ({', '.join(ip_addresses)})",
    ]

    if confidence:
        lines.append(
            f"Weather: {confidence['weather']['confidence']} — {confidence['weather']['detail']}"
        )
        lines.append(
            f"Network outage: {confidence['network']['confidence']} — {confidence['network']['detail']}"
        )
        lines.append(
            f"Power outage: {confidence['power']['confidence']} — {confidence['power']['detail']}"
        )

    return "\n".join(lines)


def search_or_create_outage_incident(location, ip_addresses, percent_down, confidence):
    """Find a recent incident referencing any of *ip_addresses*, or create one.

    Either way, the outage analysis is posted as a comment. Returns the
    incident dict (at least "number" and "sys_id") plus an "action" key
    ("updated" or "created").
    """
    existing = find_recent_incident_for_ips(ip_addresses)
    note = build_outage_note(location, ip_addresses, percent_down, confidence)

    if existing:
        add_comment(existing["sys_id"], note)
        return {**existing, "action": "updated"}

    short_description = f"Possible outage at {location} ({percent_down:.0%} devices down)"
    incident = create_incident(short_description, note)
    return {**incident, "action": "created"}
