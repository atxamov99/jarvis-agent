"""timezone.py — Current time in any city or timezone worldwide.

Inspired by: swapagarwal/JARVIS-on-Messenger ("time in seattle")

Uses pytz (standard, no API key) + worldtimeapi.org as fallback.
"""
import json
import urllib.parse
import urllib.request
from datetime import datetime

try:
    import pytz
    _HAS_PYTZ = True
except ImportError:
    _HAS_PYTZ = False

# City → timezone mapping (most requested cities)
_CITY_TZ = {
    "toshkent": "Asia/Tashkent", "tashkent": "Asia/Tashkent",
    "samarqand": "Asia/Samarkand", "samarkand": "Asia/Samarkand",
    "moskva": "Europe/Moscow", "moscow": "Europe/Moscow",
    "london": "Europe/London",
    "new york": "America/New_York", "newyork": "America/New_York", "ny": "America/New_York",
    "los angeles": "America/Los_Angeles", "la": "America/Los_Angeles",
    "dubai": "Asia/Dubai",
    "istanbul": "Europe/Istanbul",
    "berlin": "Europe/Berlin", "germany": "Europe/Berlin",
    "paris": "Europe/Paris",
    "tokyo": "Asia/Tokyo",
    "beijing": "Asia/Shanghai", "pekin": "Asia/Shanghai",
    "seoul": "Asia/Seoul",
    "delhi": "Asia/Kolkata", "mumbai": "Asia/Kolkata", "india": "Asia/Kolkata",
    "sydney": "Australia/Sydney",
    "singapore": "Asia/Singapore",
    "toronto": "America/Toronto",
    "chicago": "America/Chicago",
    "houston": "America/Chicago",
    "seattle": "America/Los_Angeles",
    "miami": "America/New_York",
    "riyadh": "Asia/Riyadh", "saudiya": "Asia/Riyadh",
    "cairo": "Africa/Cairo", "qohira": "Africa/Cairo",
    "almaty": "Asia/Almaty", "olmaota": "Asia/Almaty",
    "baku": "Asia/Baku", "boku": "Asia/Baku",
    "tehran": "Asia/Tehran",
    "islamabad": "Asia/Karachi", "karachi": "Asia/Karachi",
    "bangkok": "Asia/Bangkok",
    "jakarta": "Asia/Jakarta",
    "amsterdam": "Europe/Amsterdam",
    "rome": "Europe/Rome", "rim": "Europe/Rome",
    "madrid": "Europe/Madrid",
    "kyiv": "Europe/Kyiv", "kiev": "Europe/Kyiv",
    "beijing": "Asia/Shanghai",
    "hong kong": "Asia/Hong_Kong",
    "utc": "UTC", "gmt": "UTC",
}


def _time_pytz(tz_name: str) -> str:
    tz  = pytz.timezone(tz_name)
    now = datetime.now(tz)
    return now.strftime("%H:%M:%S, %A — %d %B %Y (%Z)")


def _time_api(city: str) -> str:
    url = f"https://worldtimeapi.org/api/timezone/{urllib.parse.quote(city)}"
    req = urllib.request.Request(url, headers={"User-Agent": "JarvisAI/1.0"})
    with urllib.request.urlopen(req, timeout=8) as r:
        d = json.loads(r.read())
    dt = d.get("datetime", "")[:19]
    tz = d.get("timezone", "")
    abbr = d.get("abbreviation", "")
    return f"{dt.replace('T', ' ')} ({abbr} — {tz})"


def timezone(parameters=None, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    city   = (params.get("city") or params.get("timezone") or "").strip().lower()

    if not city:
        # Return local time
        now = datetime.now()
        return f"🕐 Mahalliy vaqt: {now.strftime('%H:%M:%S, %A — %d %B %Y')}"

    # Resolve city name
    tz_name = _CITY_TZ.get(city)
    if not tz_name:
        # Try partial match
        for key, val in _CITY_TZ.items():
            if city in key or key in city:
                tz_name = val
                break

    if tz_name and _HAS_PYTZ:
        try:
            t = _time_pytz(tz_name)
            return f"🕐 {city.title()}da vaqt: {t}"
        except Exception:
            pass

    # Fallback: worldtimeapi
    if tz_name:
        try:
            t = _time_api(tz_name)
            return f"🕐 {city.title()}da vaqt: {t}"
        except Exception:
            pass

    return f"'{city}' shahri uchun vaqt topilmadi. Mashhur shaharlar: Toshkent, London, New York, Tokyo, Dubai..."
