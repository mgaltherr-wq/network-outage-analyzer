
# Network Outage Analyzer

Checks weather conditions when a remote location has enough devices down to
suggest a site-impacting outage. When a location crosses that threshold, the
dashboard searches ServiceNow for a recent incident already covering the
affected IPs and comments on it, or opens a new high-priority incident if
none exists.

## Download

The easiest way to try this out — no Python required:

* **Windows** — download `NetworkOutageAnalyzer-Setup.exe` from the
  [latest release](https://github.com/mgaltherr-wq/network-outage-analyzer/releases/latest)
  and run it. It installs for your user account only, so no admin rights
  needed. It launches the dashboard and opens it in your browser automatically.
* **Linux** — download `NetworkOutageAnalyzer-x86_64.AppImage` from the same
  page, then:
  ```sh
  chmod +x NetworkOutageAnalyzer-x86_64.AppImage
  ./NetworkOutageAnalyzer-x86_64.AppImage
  ```
  (The `chmod +x` is needed because most browsers don't preserve the
  executable bit on download.) No installation step — it's a single file.

Either way, the dashboard opens at `http://127.0.0.1:8000`, bound to your
machine only (not exposed to your network). Everything below this point
describes running from source instead, for development.

## Configuration

`.env`/`ip_addresses.json` live in a per-user config directory —
`%APPDATA%\NetworkOutageAnalyzer` on Windows, `~/.config/network-outage-analyzer`
on Linux — not the project folder. The easiest way to set values is the
[Settings page](#settings) (gear icon in the dashboard, or option 5 in the
CLI menu) rather than editing the file directly. If you do want to hand-edit
it, create/edit `.env` in that directory with:

```sh
WEATHER_API_KEY=your_openweather_api_key

# SNMP location discovery (SNMPv2c by default)
SNMP_COMMUNITY=your_read_only_community
SNMP_VERSION=2c
SNMP_TIMEOUT_SECONDS=2

# ServiceNow ticketing authenticates with OAuth (client_credentials grant).
SERVICENOW_INSTANCE_URL=https://dev374413.service-now.com
SERVICENOW_CLIENT_ID=your_oauth_client_id
SERVICENOW_CLIENT_SECRET=your_oauth_client_secret

# Optional. Enables the Cloudflare Radar network-outage check on the dashboard.
# Without it, the network signal reports "Unknown" confidence instead of
# checking for a verified internet outage in the area.
CLOUDFLARE_API_TOKEN=your_cloudflare_api_token
```

## Outage confidence breakdown

When a location on the dashboard map crosses 90% of its devices unreachable,
the dashboard checks three independent sources and reports a confidence level
for each as a possible cause:

* **Weather** — via the existing OpenWeather integration.
* **Network outage** — via [Cloudflare Radar](https://radar.cloudflare.com/outage-center),
  a free API that reports verified internet outages by country. Requires
  `CLOUDFLARE_API_TOKEN`.
* **Power outage** — via [ODIN](https://ornl.opendatasoft.com/explore/dataset/odin-real-time-outages-county/)
  (DOE / Oak Ridge National Lab), a free, no-key-required, county-level power
  outage dataset. Coordinates are reverse-geocoded to a US county using the
  free FCC Census Block API.

Each source reports "High" (detected), "Low" (checked, nothing detected), or
"Unknown" (source unavailable/unconfigured) independently — they aren't
blended into a single score.

## ServiceNow ticketing

When a location crosses the same 90% threshold, the dashboard also opens (or
updates) a ServiceNow incident. This requires the OAuth client ID/secret to
be configured (see below):

1. Searches incidents created in the last 4 hours for the affected IP
   addresses appearing in their short description or description.
2. If a match is found, adds the outage analysis (location, affected IPs,
   percent down, and the weather/network/power confidence breakdown above)
   as an additional comment (the customer-visible `comments` field) on that
   incident.
3. If no match is found, creates a new **High** priority incident with the
   same analysis.

To avoid commenting every 30 seconds while an outage is ongoing, each
location is only ticketed once per "episode" — once its devices recover
below 90% down, the next time it crosses the threshold is treated as a new
episode and tickets again. This state resets when the dashboard restarts.

### OAuth

Set `SERVICENOW_CLIENT_ID` and `SERVICENOW_CLIENT_SECRET` (from an "OAuth API
endpoint for external clients" entry in the instance's System OAuth >
Application Registry). The app requests a bearer token from
`<instance>/oauth_token.do` using the `client_credentials` grant, so the
instance must have that grant enabled
(`glide.oauth.inbound.client.credential.grant_type.enabled` system property)
and an OAuth Application User assigned on the registry entry; incidents are
created as that user. Tokens are cached and refreshed shortly before they
expire.

This runs from the dashboard only (`app/dashboard.py`), since it needs the
per-location device grouping the CLI's single aggregate analysis doesn't
have. A failure here (bad credentials, ServiceNow unreachable) never breaks
the dashboard — the location still renders, just without a `ticket` entry.

## Run (from source)

```sh
python run.py
```

On startup, the app shows a menu where you can view, add, or remove IP
addresses before continuing to the outage analysis. The list is stored in
`ip_addresses.json` in the per-user config directory described above, which
is created automatically the first time you add an address.

## Dashboard (from source)

Launch the browser dashboard with:

```sh
uvicorn app.dashboard:app --reload --host 0.0.0.0 --port 8000
```

Then open `http://127.0.0.1:8000` for local access, or from another machine
open `http://<server-ip>:8000` (for example `http://192.168.42.234:8000`).
The dashboard shows the same persisted device list used by the analyzer,
lets you add or remove IP addresses, and includes a U.S.-focused weather
map with an optional weather overlay.

Note this differs from the packaged installer, which binds to
`127.0.0.1` only by default (see [Download](#download)) since the dashboard
has no authentication — `--host 0.0.0.0` here is an explicit opt-in for
intentionally monitoring devices from another machine on your network.

## Settings

API keys, ServiceNow credentials, and SNMP settings can be changed without
editing `.env` by hand:

* **Dashboard** — click the gear icon in the top bar (or open
  `http://127.0.0.1:8000/settings`) to view and update every setting. Secret
  values (API keys, passwords, the SNMP community string) are always masked
  on screen; type a new value to replace one, or check "Clear" to remove it.
* **CLI** — choose "5. Settings" from the startup menu, pick a field by
  number, and enter the new value (secret fields prompt without echoing
  input). Leave the prompt blank to cancel, or enter `-` to clear a field.

Both paths write to the same `.env` file and apply immediately to the
running process — no restart required.

> Note: the dashboard has no authentication, so anyone who can reach the
> port can view masked settings and change them. Keep it on a trusted
> network, and don't expose port 8000 to the public internet.

## Building the installers yourself

`.github/workflows/build-installers.yml` builds both installers on GitHub's
own runners — a `windows-latest` job (PyInstaller + Inno Setup) and an
`ubuntu-latest` job (PyInstaller + AppImage) — and, on a `v*` tag push,
publishes both to a GitHub Release. Trigger it manually via the Actions
tab ("Run workflow") to test the pipeline without cutting a release, or
push a tag:

```sh
git tag v1.0.0
git push origin v1.0.0
```

To build locally instead:

```sh
pip install -r requirements.txt pyinstaller

# Linux
pyinstaller --distpath dist/linux packaging/linux.spec
./dist/linux/NetworkOutageAnalyzer/NetworkOutageAnalyzer --selftest
# then assemble an AppDir and run appimagetool — see the workflow's
# "Assemble AppDir" / "Build AppImage" steps for the exact commands.

# Windows
pyinstaller --distpath dist\windows packaging\windows.spec
dist\windows\NetworkOutageAnalyzer.exe --selftest
iscc packaging\windows.iss
```


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
The simplest way to set them is the Settings page/menu described above; see
that section for the actual per-OS file location if you'd rather edit `.env`
by hand.

The `.env` file should not be committed to GitHub — it's covered by `.gitignore`.

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
│   ├── paths.py       # per-user data directory (.env, ip_addresses.json)
│   ├── launcher.py     # packaged-app entry point (dashboard + open browser)
│   └── services/
│       └── weather.py
│
├── packaging/           # PyInstaller specs, Inno Setup script, icons
├── tests/
│
├── run.py
├── requirements.txt
├── README.md
└── venv/             # Local virtual environment
```

`.env` and `ip_addresses.json` are no longer stored in the project folder —
see [Configuration](#configuration) above.

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

* `.env` exists in the per-user config directory (see [Configuration](#configuration))
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
