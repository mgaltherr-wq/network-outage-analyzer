# Test Plan — Network Outage Analyzer

## 1. Objective

Verify that the Network Outage Analyzer correctly determines device
reachability, discovers device locations via SNMP, and correlates
unreachable devices with external signals (weather, verified network
outages, power outages) to produce an accurate, actionable outage
assessment — without producing false positives from partial or
transient device loss.

## 2. Scope

**In scope**
- ICMP reachability checks (`app/services/reachability.py`)
- IP address inventory management and validation (`app/ip_inventory.py`)
- SNMP-based device location discovery and persistence (`app/dashboard.py`)
- Outage correlation and confidence scoring (`app/analysis/correlator.py`)
- External data source integrations: weather (`app/services/weather.py`),
  network outages (`app/services/network_outages.py`), power outages
  (`app/services/power_outages.py`)
- ServiceNow incident note formatting (`app/services/servicenow.py`)
- Dashboard HTTP API (`app/dashboard.py`)
- Startup menu / CLI workflow (`app/menu.py`)

**Out of scope**
- Load/performance testing of the dashboard under concurrent users
- Live third-party API behavior (OpenWeather, Cloudflare Radar, ODIN,
  FCC Census Block, SNMP agents) — these are mocked, not tested live
- ServiceNow incident submission over the network (currently disabled
  in `app/main.py`)
- Security testing (auth, input sanitization beyond IP validation)

## 3. Test Environment

| Item | Value |
|---|---|
| OS | Ubuntu Linux (developed/tested on Ubuntu 24.04) |
| Language | Python 3.12+ (verified on 3.14) |
| Test framework | `unittest` (standard library) |
| HTTP integration testing | `fastapi.testclient.TestClient` |
| Key dependencies | `fastapi`, `pysnmp`, `requests`, `python-dotenv` |
| Execution | `python -m unittest discover -s tests` |
| CI | None currently — tests are run manually before pushing |

## 4. Assumptions and Constraints

- Tests must not depend on live network access, real devices, or real
  third-party API credentials. All I/O boundaries (`subprocess.run`,
  `requests`/HTTP calls, SNMP queries, filesystem) are mocked or
  redirected to temporary paths.
- `ip_addresses.json` is treated as external state; tests use
  `tempfile.TemporaryDirectory` rather than the developer's real
  inventory file.
- SNMP discovery is best-effort: if `pysnmp` is unavailable or a
  device doesn't respond, the system must degrade to "no location"
  rather than error.
- Outage correlation assumes device unreachability alone is not proof
  of an outage — confidence must be corroborated by an independent
  external signal.

## 5. Test Categories

| # | Category | Representative module(s) | Test file(s) |
|---|---|---|---|
| 1 | Reachability / protocol | `reachability.py` | `test_reachability.py` |
| 2 | Data validation | `ip_inventory.py` | `test_ip_inventory.py` |
| 3 | Device discovery (SNMP) | `dashboard.py` | `test_snmp_sync.py`, `test_device_locations.py` |
| 4 | Outage correlation / decision logic | `correlator.py` | `test_correlator.py` |
| 5 | External signal integration (fault injection) | `network_outages.py`, `power_outages.py`, `weather.py` | `test_network_outages.py`, `test_power_outages.py`, `test_weather.py` |
| 6 | Notification formatting | `servicenow.py` | `test_servicenow.py` |
| 7 | API / integration | `dashboard.py` | `test_dashboard.py` |
| 8 | CLI / user workflow | `menu.py` | `test_menu.py` |

## 6. Pass / Fail Criteria

- **Pass:** Test asserts the expected return value, persisted state,
  or HTTP response for a given input, and the assertion holds with no
  unhandled exception.
- **Fail:** Actual output diverges from expected (wrong reachability
  result, wrong confidence level, malformed API response, unhandled
  exception, or a network/filesystem side effect that escapes the
  mocked boundary).
- **Suite-level exit criteria:** All tests pass (`OK` from
  `unittest`) with zero failures and zero errors before a change is
  pushed. A skipped or `xfail` test must have a linked explanation in
  the test docstring or commit message.

## 7. Representative Test Cases

| ID | Category | Case | Input | Expected Result |
|---|---|---|---|---|
| TC-01 | Reachability | Device responds to ping | Mocked `subprocess.run` returns code 0 | `is_reachable()` returns `True`; ping invoked with `-c 1 -W <timeout>` |
| TC-02 | Reachability | Device does not respond | Mocked `subprocess.run` returns code 1 | `is_reachable()` returns `False` |
| TC-03 | Reachability | Batch check splits results | Mixed reachable/unreachable IP list | `check_devices()` returns `(reachable, unreachable)` partitioned correctly |
| TC-04 | Data validation | Duplicate IP add rejected | Add an IP already in inventory | `add_ip_address()` returns `added=False`, list unchanged |
| TC-05 | Data validation | Save normalizes and dedupes | Unsorted list with a duplicate | Persisted JSON is sorted, deduplicated, normalized |
| TC-06 | SNMP discovery | Location refresh persists SNMP result | Mocked `lookup_location_snmp()` returns a new location for a known device | Stored device record is updated with the discovered location |
| TC-07 | SNMP discovery | Devices grouped by site | Multiple devices share one location | Dashboard groups them under a single site entry |
| TC-08 | Correlation | Partial outage is not actionable | 20% of devices at a site down | `analyze_outage()` does not flag for notification |
| TC-09 | Correlation | Severe weather at full outage | 100% down + high wind/severe condition | Result flags `NOTIFY_KEY=True` with weather as cause |
| TC-10 | Correlation | Multi-source confidence scoring | Weather, network, and power signals mixed (detected/not-configured/checked) | Each source reports independent `High`/`Low`/`Unknown` confidence |
| TC-11 | Fault injection | External API unconfigured | No `CLOUDFLARE_API_TOKEN` set | `check_network_outage()` returns "unconfigured" rather than raising |
| TC-12 | Fault injection | Geocoding lookup fails | County lookup service errors | Power outage check returns "unresolvable" gracefully |
| TC-13 | API integration | Dashboard page renders | GET `/` via `TestClient` | Response includes location input control, HTTP 200 |
| TC-14 | CLI workflow | Invalid menu input reprompts | User enters `9` then a valid option | Menu reprints choices and does not exit or crash |
| TC-15 | CLI workflow | Add IP from menu persists | User adds a valid new IP, then quits | `save_ip_addresses()` called once with updated list |

## 8. Known Limitations

- No automated CI — tests are run manually; a future improvement is a
  GitHub Actions workflow running `unittest discover` on push/PR.
- No live-integration or contract tests against the real third-party
  APIs (would require credentials and network access, and risks flaky
  runs).
- No load testing of the dashboard's concurrent request handling.

## 9. How to Run

```sh
source venv/bin/activate
python -m unittest discover -s tests
```
