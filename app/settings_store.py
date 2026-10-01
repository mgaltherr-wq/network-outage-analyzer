"""Read and update the app's .env-backed settings (API keys, SNMP, ServiceNow).

Both the dashboard settings API and the CLI settings menu go through this
module so there is one place that knows how to persist a change and make it
take effect in the running process.
"""

import importlib
import os

from dotenv import set_key, unset_key

from app import config
from app.paths import user_data_dir

ENV_PATH = user_data_dir() / ".env"

SECRET = "secret"
TEXT = "text"


class SettingField:
    __slots__ = ("key", "label", "kind", "group")

    def __init__(self, key, label, kind, group):
        self.key = key
        self.label = label
        self.kind = kind
        self.group = group


SETTINGS_FIELDS = [
    SettingField("WEATHER_API_KEY", "OpenWeather API key", SECRET, "Weather"),
    SettingField("CLOUDFLARE_API_TOKEN", "Cloudflare API token", SECRET, "Network outage detection"),
    SettingField("SNMP_COMMUNITY", "SNMP community string", SECRET, "SNMP"),
    SettingField("SNMP_VERSION", "SNMP version", TEXT, "SNMP"),
    SettingField("SNMP_TIMEOUT_SECONDS", "SNMP timeout (seconds)", TEXT, "SNMP"),
    SettingField("SERVICENOW_INSTANCE_URL", "ServiceNow instance URL", TEXT, "ServiceNow"),
    SettingField("SERVICENOW_CLIENT_ID", "ServiceNow OAuth client ID", TEXT, "ServiceNow"),
    SettingField("SERVICENOW_CLIENT_SECRET", "ServiceNow OAuth client secret", SECRET, "ServiceNow"),
    SettingField("REACHABILITY_INTERVAL_SECONDS", "Reachability check interval (seconds)", TEXT, "Device monitoring"),
    SettingField("PING_TIMEOUT_SECONDS", "Ping timeout (seconds)", TEXT, "Device monitoring"),
    SettingField("PING_CONCURRENCY", "Max concurrent pings", TEXT, "Device monitoring"),
]

FIELDS_BY_KEY = {field.key: field for field in SETTINGS_FIELDS}


def _mask(value):
    if len(value) <= 4:
        return "*" * len(value)
    return f"{'*' * (len(value) - 4)}{value[-4:]}"


def get_settings():
    """Return every setting's current state, with secret values masked."""
    settings = []
    for field in SETTINGS_FIELDS:
        raw = os.getenv(field.key, "") or ""
        settings.append({
            "key": field.key,
            "label": field.label,
            "group": field.group,
            "secret": field.kind == SECRET,
            "is_set": bool(raw),
            "value": _mask(raw) if field.kind == SECRET else raw,
        })
    return settings


def update_settings(updates: dict):
    """Persist *updates* (key -> new value) to .env and apply them live.

    An empty/blank value clears the setting (falls back to app.config's
    built-in default, if any). Returns the refreshed settings list.
    """
    unknown = set(updates) - set(FIELDS_BY_KEY)
    if unknown:
        raise ValueError(f"Unknown setting(s): {', '.join(sorted(unknown))}")

    ENV_PATH.touch(exist_ok=True)
    for key, value in updates.items():
        value = "" if value is None else str(value).strip()
        if value:
            set_key(str(ENV_PATH), key, value, quote_mode="never")
            os.environ[key] = value
        else:
            unset_key(str(ENV_PATH), key)
            os.environ.pop(key, None)

    # app.config computes its values from os.environ at import time; reloading
    # it re-runs that logic so every module holding `config` (not a copied
    # constant) sees the new values immediately, no restart required.
    importlib.reload(config)

    return get_settings()
