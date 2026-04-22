import requests
from app.config import WEATHER_API_KEY

def get_weather(lat, lon):
    url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={WEATHER_API_KEY}&units=imperial"

    response = requests.get(url)
    data = response.json()

    return {
        "condition": data["weather"][0]["description"],
        "wind_mph": data["wind"]["speed"],
        "temp_f": data["main"]["temp"]
    }
