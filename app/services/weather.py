import requests
from app.config import WEATHER_API_KEY


def geocode_location(location):
    """Return coordinates for a place name using OpenWeather, or None."""
    if not WEATHER_API_KEY or not location or not location.strip():
        return None

    response = requests.get(
        "https://api.openweathermap.org/geo/1.0/direct",
        params={"q": location.strip(), "limit": 1, "appid": WEATHER_API_KEY},
        timeout=5,
    )
    response.raise_for_status()
    matches = response.json()
    if not matches:
        return None

    match = matches[0]
    return {
        "latitude": match["lat"],
        "longitude": match["lon"],
        "name": match.get("name") or location.strip(),
        "state": match.get("state"),
        "country": match.get("country"),
    }


def get_weather(lat, lon):
    url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={WEATHER_API_KEY}&units=imperial"

    response = requests.get(url)
    data = response.json()

    return {
        "condition": data["weather"][0]["description"],
        "wind_mph": data["wind"]["speed"],
        "temp_f": data["main"]["temp"]
    }
