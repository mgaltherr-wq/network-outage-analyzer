import requests

from app import config


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


def find_incident_sys_id(incident_number):
    response = requests.get(
        f"{_base_url()}/api/now/table/incident",
        auth=_auth(),
        headers=_headers(),
        params={
            "sysparm_query": f"number={incident_number}",
            "sysparm_fields": "sys_id,number",
            "sysparm_limit": "1",
        },
        timeout=15,
    )
    response.raise_for_status()

    results = response.json().get("result", [])
    if not results:
        raise ServiceNowConfigError(
            f"No ServiceNow incident found for {incident_number}."
        )

    return results[0]["sys_id"]


def configured_incident_sys_id():
    if config.SERVICENOW_INCIDENT_SYS_ID:
        return config.SERVICENOW_INCIDENT_SYS_ID

    if config.SERVICENOW_INCIDENT_NUMBER:
        return find_incident_sys_id(config.SERVICENOW_INCIDENT_NUMBER)

    raise ServiceNowConfigError(
        "Set SERVICENOW_INCIDENT_SYS_ID or SERVICENOW_INCIDENT_NUMBER in .env."
    )


def build_weather_note(weather, analysis, percent_down):
    return (
        "Automated outage weather analysis\n"
        f"Devices down: {percent_down:.0%}\n"
        f"Weather condition: {weather['condition']}\n"
        f"Wind speed: {weather['wind_mph']} mph\n"
        f"Temperature: {weather['temp_f']} F\n"
        f"Potential cause: {analysis['potential_cause']}\n"
        f"Confidence: {analysis['confidence']}"
    )


def update_incident_with_weather(weather, analysis, percent_down):
    incident_sys_id = configured_incident_sys_id()
    note = build_weather_note(weather, analysis, percent_down)

    response = requests.patch(
        f"{_base_url()}/api/now/table/incident/{incident_sys_id}",
        auth=_auth(),
        headers=_headers(),
        json={config.SERVICENOW_NOTE_FIELD: note},
        timeout=15,
    )
    response.raise_for_status()

    return response.json()["result"]
