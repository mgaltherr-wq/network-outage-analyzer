
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

On startup, the app shows a menu where you can view, add, or remove IP
addresses before continuing to the outage analysis. The list is stored in
`ip_addresses.json`, which is created automatically the first time you add an
address.

## Dashboard

Launch the browser dashboard with:

```sh
uvicorn app.dashboard:app --reload
```

Then open `http://127.0.0.1:8000`. The dashboard shows the same persisted
device list used by the analyzer, lets you add or remove IP addresses, and
includes a U.S.-focused weather map with an optional weather overlay.


# Network Outage Analyzer

A Python-based network monitoring tool that analyzes network outages by correlating device availability with external conditions such as weather. The goal is to help determine whether an outage is likely caused by a network/device issue or an external event.

## Features

* Polls network devices and analyzes outage conditions
* Integrates with weather APIs to correlate outages with storms and environmental conditions
* Uses Python automation to assist with network troubleshooting
* Designed to integrate with monitoring and IT service management platforms

---

# Installation

## Prerequisites

* Ubuntu Linux (tested on Ubuntu 24.04)
* Python 3.12+
* Git

## Clone the Repository

```bash
git clone <repository-url>
cd network-outage-analyzer
```

## Create a Virtual Environment

Create a Python virtual environment:

```bash
python3 -m venv venv
```

Activate the environment:

```bash
source venv/bin/activate
```

## Install Dependencies

Install required Python packages:

```bash
pip install -r requirements.txt
```

---

# Configuration

## Environment Variables

This project uses environment variables to store API keys and other sensitive information.

Create a `.env` file in the project root:

```bash
nano .env
```

Add your OpenWeather API key:

```text
WEATHER_API_KEY=your_openweather_api_key_here
```

The `.env` file should not be committed to GitHub. It is included in `.gitignore` to keep credentials secure.

---

# Running the Application

Activate the virtual environment:

```bash
source venv/bin/activate
```

Run the analyzer:

```bash
python3 run.py
```

---

# Updating Dependencies

After installing new Python packages, update the requirements file:

```bash
pip freeze > requirements.txt
```

Commit the updated dependency list:

```bash
git add requirements.txt
git commit -m "Update Python dependencies"
git push
```

---

# Project Structure

```
network-outage-analyzer/
│
├── app/
│   ├── main.py
│   ├── config.py
│   └── services/
│       └── weather.py
│
├── tests/
│
├── run.py
├── requirements.txt
├── .env              # Not committed
├── README.md
└── venv/             # Local virtual environment
```

---

# Troubleshooting

## Missing Python Modules

If you see:

```
ModuleNotFoundError: No module named '<package>'
```

activate the virtual environment and install dependencies:

```bash
source venv/bin/activate
pip install -r requirements.txt
```

## Weather API Errors

If weather data is unavailable, verify:

* `.env` exists in the project root
* `WEATHER_API_KEY` is set correctly
* The API key is valid
* Internet connectivity is available

Test the environment variable:

```bash
python3 -c "from app.config import WEATHER_API_KEY; print(WEATHER_API_KEY)"
```

---

# Development Environment

This project was developed and tested in an Ubuntu virtual machine running inside a GNS3 network lab environment.
