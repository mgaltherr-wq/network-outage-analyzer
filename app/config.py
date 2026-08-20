import os
from dotenv import load_dotenv

from app.paths import migrate_legacy_file, user_data_dir

ENV_PATH = user_data_dir() / ".env"
migrate_legacy_file(".env")
load_dotenv(dotenv_path=ENV_PATH)

WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")

SNMP_COMMUNITY = os.getenv("SNMP_COMMUNITY", "public")
SNMP_VERSION = os.getenv("SNMP_VERSION", "2c")
SNMP_TIMEOUT_SECONDS = float(os.getenv("SNMP_TIMEOUT_SECONDS", "2"))


SERVICENOW_INSTANCE_URL = os.getenv(
    "SERVICENOW_INSTANCE_URL",
    "https://dev374413.service-now.com",
)
SERVICENOW_USERNAME = os.getenv("SERVICENOW_USERNAME")
SERVICENOW_PASSWORD = os.getenv("SERVICENOW_PASSWORD")
SERVICENOW_NOTE_FIELD = os.getenv("SERVICENOW_NOTE_FIELD", "work_notes")

CLOUDFLARE_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN")

ODIN_DATASET_URL = os.getenv(
    "ODIN_DATASET_URL",
    "https://ornl.opendatasoft.com/api/records/1.0/search/",
)
