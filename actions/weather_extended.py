"""weather_extended.py — Real weather data via Open-Meteo (no API key needed)."""
import json
import urllib.request
from urllib.parse import urlencode


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "JarvisWeather/1.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def _geocode(city: str) -> tuple[float, float, str] | None:
    params = urlencode({"name": city, "count": 1, "language": "en", "format": "json"})
    data = _get(f"https://geocoding-api.open-meteo.com/v1/search?{params}")
    results = data.get("results")
    if not results:
        return None
    r = results[0]
    return r["latitude"], r["longitude"], r.get("name", city)


_WMO_CODES = {
    0: "Ochiq", 1: "Ko'proq ochiq", 2: "Qisman bulutli", 3: "Bulutli",
    45: "Tuman", 48: "Muzli tuman",
    51: "Yengil chisalash", 53: "Chisalash", 55: "Kuchli chisalash",
    61: "Engil yomg'ir", 63: "Yomg'ir", 65: "Kuchli yomg'ir",
    71: "Yengil qor", 73: "Qor", 75: "Kuchli qor", 77: "Qor donalari",
    80: "Yomg'ir jarchilari", 81: "Yomg'ir", 82: "Kuchli yomg'ir",
    85: "Qor jarchilari", 86: "Kuchli qor jarchilari",
    95: "Momaqaldiroqli bo'ron", 96: "Do'l bilan bo'ron", 99: "Kuchli do'l bilan bo'ron",
}


def _fmt_weather(desc: str, temp: float, feels: float, wind: float,
                 humidity: float, precip: float) -> str:
    return (
        f"🌡 {temp:.0f}°C (seziladi {feels:.0f}°C)\n"
        f"☁️  {desc}\n"
        f"💧 Namlik: {humidity:.0f}%  |  💨 Shamol: {wind:.1f} km/s\n"
        f"🌧 Yog'in: {precip:.1f} mm"
    )


def weather_extended(parameters=None, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    city   = (params.get("city") or "Tashkent").strip()
    mode   = (params.get("mode") or "current").lower().strip()
    days   = min(int(params.get("days", 3)), 7)

    coords = _geocode(city)
    if not coords:
        return f"'{city}' shahri topilmadi."
    lat, lon, city_name = coords

    base_params = {
        "latitude": lat, "longitude": lon,
        "timezone": "auto", "wind_speed_unit": "kmh",
    }

    if mode in ("current", "hozir", "bugun"):
        p = dict(base_params)
        p.update({
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,"
                       "precipitation,wind_speed_10m,weather_code",
        })
        data = _get(f"https://api.open-meteo.com/v1/forecast?{urlencode(p)}")
        c    = data["current"]
        desc = _WMO_CODES.get(c["weather_code"], "Noma'lum")
        body = _fmt_weather(
            desc, c["temperature_2m"], c["apparent_temperature"],
            c["wind_speed_10m"], c["relative_humidity_2m"], c["precipitation"],
        )
        if player: player.write_log(f"[Weather] {city_name}: {c['temperature_2m']}°C")
        return f"🌍 {city_name} — hozirgi ob-havo:\n{body}"

    if mode in ("forecast", "prognoz", "hafta"):
        p = dict(base_params)
        p.update({
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,"
                     "precipitation_sum,wind_speed_10m_max",
            "forecast_days": days,
        })
        data  = _get(f"https://api.open-meteo.com/v1/forecast?{urlencode(p)}")
        daily = data["daily"]
        lines = []
        for i in range(days):
            date  = daily["time"][i]
            desc  = _WMO_CODES.get(daily["weather_code"][i], "?")
            tmax  = daily["temperature_2m_max"][i]
            tmin  = daily["temperature_2m_min"][i]
            rain  = daily["precipitation_sum"][i]
            wind  = daily["wind_speed_10m_max"][i]
            lines.append(
                f"{date}: {desc}  {tmin:.0f}–{tmax:.0f}°C  "
                f"🌧{rain:.1f}mm  💨{wind:.0f}km/s"
            )
        if player: player.write_log(f"[Weather] {city_name} {days}-day forecast")
        return f"🌍 {city_name} — {days} kunlik prognoz:\n" + "\n".join(lines)

    if mode in ("hourly", "soatlik"):
        p = dict(base_params)
        p.update({
            "hourly": "temperature_2m,precipitation_probability,weather_code",
            "forecast_days": 1,
        })
        data   = _get(f"https://api.open-meteo.com/v1/forecast?{urlencode(p)}")
        hourly = data["hourly"]
        lines  = []
        for i in range(0, 24, 3):
            t    = hourly["time"][i][-5:]
            desc = _WMO_CODES.get(hourly["weather_code"][i], "?")
            temp = hourly["temperature_2m"][i]
            prob = hourly["precipitation_probability"][i]
            lines.append(f"{t}  {temp:.0f}°C  {desc}  🌧{prob}%")
        return f"🌍 {city_name} — bugungi soatlik:\n" + "\n".join(lines)

    return "mode: current | forecast | hourly"
