import os
from dotenv import load_dotenv

from app.paths import migrate_legacy_file, user_data_dir

ENV_PATH = user_data_dir() / ".env"
migrate_legacy_file(".env")
load_dotenv(dotenv_path=ENV_PATH)


def _positive_number(name, default, cast=float):
    """Read a numeric setting, falling back to *default* if it's missing,
    malformed, or not positive — a typo shouldn't stop the app starting."""
    try:
        value = cast(os.getenv(name, default))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")

SNMP_COMMUNITY = os.getenv("SNMP_COMMUNITY", "public")
SNMP_VERSION = os.getenv("SNMP_VERSION", "2c")
SNMP_TIMEOUT_SECONDS = float(os.getenv("SNMP_TIMEOUT_SECONDS", "2"))

# Device reachability sweeps (see app/services/device_monitor.py).
PING_TIMEOUT_SECONDS = _positive_number("PING_TIMEOUT_SECONDS", 1, int)
PING_CONCURRENCY = _positive_number("PING_CONCURRENCY", 64, int)
REACHABILITY_INTERVAL_SECONDS = _positive_number("REACHABILITY_INTERVAL_SECONDS", 15.0)

# Reachability/outage history behind the Trends page (see app/history.py).
HISTORY_RETENTION_DAYS = _positive_number("HISTORY_RETENTION_DAYS", 90, int)


SERVICENOW_INSTANCE_URL = os.getenv(
    "SERVICENOW_INSTANCE_URL",
    "https://dev374413.service-now.com",
)
SERVICENOW_CLIENT_ID = os.getenv("SERVICENOW_CLIENT_ID")
SERVICENOW_CLIENT_SECRET = os.getenv("SERVICENOW_CLIENT_SECRET")

CLOUDFLARE_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN")

ODIN_DATASET_URL = os.getenv(
    "ODIN_DATASET_URL",
    "https://ornl.opendatasoft.com/api/records/1.0/search/",
)
