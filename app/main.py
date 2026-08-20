from app.services.weather import get_weather
from app.analysis.correlator import analyze_outage
from app.analysis.correlator import CAUSE_KEY
from app.analysis.correlator import NOTIFY_KEY
from app.ip_inventory import load_ip_addresses
from app.menu import CONTINUE, show_startup_menu
from app.services.reachability import check_devices


def run_analysis():
    if show_startup_menu() != CONTINUE:
        print("Exiting Network Outage Analyzer.")
        return

    ip_addresses = load_ip_addresses()
    if not ip_addresses:
        print("No IP addresses configured; no outage analysis was run.")
        return

    reachable, unreachable = check_devices(ip_addresses)
    percent_down = len(unreachable) / len(ip_addresses)

    print("\n=== Device Reachability ===")
    print(f"Reachable: {len(reachable)}/{len(ip_addresses)}")
    if unreachable:
        print(f"Unreachable: {', '.join(unreachable)}")

    lat, lon = 29.7604, -95.3698

    weather = get_weather(lat, lon)
    result = analyze_outage(weather, percent_down)

    print("\n=== Automated Outage Analysis ===")
    print(f"Weather Condition: {weather['condition']}")
    print(f"Wind Speed: {weather['wind_mph']} mph")
    print(f"Temperature: {weather['temp_f']} F")

    print("\n--- Assessment ---")
    if result.get(NOTIFY_KEY):
        print(f"Potential Cause: {result[CAUSE_KEY]}")
        print(f"Confidence: {result['confidence']}")

        # ServiceNow ticketing runs per-location from the dashboard
        # (app/dashboard.py's list_device_locations), where devices are
        # grouped by location — this CLI flow only has a single aggregate
        # percent_down across all configured IPs, with no location grouping
        # to search/create a ticket against.
    else:
        print("No actionable outage detected.")
