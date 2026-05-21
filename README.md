# Network Outage Analyzer

Checks weather conditions when a remote location has enough devices down to
suggest a site-impacting outage. When the analysis is actionable, the app can
append the weather assessment to a ServiceNow incident.

## Configuration

Create a `.env` file with:

```sh
WEATHER_API_KEY=your_openweather_api_key

SERVICENOW_INSTANCE_URL=https://dev374413.service-now.com
SERVICENOW_USERNAME=your_servicenow_username
SERVICENOW_PASSWORD=your_servicenow_password

# Use either the sys_id directly, or an incident number to look up the sys_id.
SERVICENOW_INCIDENT_SYS_ID=
SERVICENOW_INCIDENT_NUMBER=INC0010001

# Optional. Use comments if you want a customer-visible comment.
SERVICENOW_NOTE_FIELD=work_notes
```

## Run

```sh
python run.py
```
