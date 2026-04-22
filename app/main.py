#Current code status: the code does not work in the condition when percent_down is less than 0.9.

from app.services.weather import get_weather
from app.analysis.correlator import analyze_outage
from app.analysis.correlator import CAUSE_KEY
from app.analysis.correlator import NOTIFY_KEY

def run_analysis():
    lat, lon = 29.7604, -95.3698
    percent_down = .9  # simulate 90% outage

    weather = get_weather(lat, lon)
    result = analyze_outage(weather, percent_down)

    print("\n=== Automated Outage Analysis ===")
    print(f"Weather Condition: {weather['condition']}")
    print(f"Wind Speed: {weather['wind_mph']} mph")
    print(f"Temperature: {weather['temp_f']} F")

    print("\n--- Assessment ---")
    #print(f"Potential Cause: {result[CAUSE_KEY]}")
    if result.get(NOTIFY_KEY):
        print(f"Potential Cause: {result[CAUSE_KEY]}")
        print(f"Confidence: {result['confidence']}")
    else:
        print("No actionable outage detected.")
   

    


