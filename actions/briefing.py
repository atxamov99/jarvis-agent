"""briefing.py — Daily morning briefing: weather + news + todos + greeting.

Aggregates data from existing actions to produce a single summary.
"""
import datetime
import json
import sys
import urllib.request
from pathlib import Path


def _cfg() -> dict:
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
    try:
        return json.loads((base / "config" / "api_keys.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def _greeting() -> str:
    h = datetime.datetime.now().hour
    if h < 5:
        return "Kechasi xayrli bo'lsin"
    if h < 12:
        return "Xayrli tong"
    if h < 17:
        return "Xayrli kun"
    if h < 21:
        return "Xayrli kech"
    return "Xayrli oqshom"


def _weather_snippet(city: str) -> str:
    try:
        from actions.weather_report import weather_report
        result = weather_report(parameters={"city": city, "units": "metric"})
        if result:
            lines = result.strip().splitlines()
            return "\n".join(lines[:4])
    except Exception:
        pass
    return "Ob-havo ma'lumoti mavjud emas."


def _news_snippet(count: int = 4) -> str:
    try:
        from actions.news import news
        result = news(parameters={"category": "world", "count": count})
        if result:
            return result.strip()
    except Exception:
        pass
    return "Yangiliklar mavjud emas."


def _todos_snippet() -> str:
    try:
        from actions.todo import todo
        result = todo(parameters={"action": "list"})
        if result and "bo'sh" not in result.lower() and "empty" not in result.lower():
            lines = result.strip().splitlines()
            return "\n".join(lines[:6])
    except Exception:
        pass
    return None


def _reminders_snippet() -> str:
    try:
        from actions.reminder import reminder
        result = reminder(parameters={"action": "list"})
        if result and "bo'sh" not in result.lower() and "empty" not in result.lower():
            lines = result.strip().splitlines()
            return "\n".join(lines[:5])
    except Exception:
        pass
    return None


def briefing(parameters=None, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    cfg    = _cfg()
    city   = (params.get("city") or cfg.get("weather_city") or cfg.get("city") or "Tashkent").strip()
    now    = datetime.datetime.now()

    sections = []

    # Header
    greeting = _greeting()
    sections.append(
        f"{greeting}! Bugun {now.strftime('%A, %d %B %Y')}, soat {now.strftime('%H:%M')}."
    )

    # Weather
    sections.append("\nOB-HAVO:")
    sections.append(_weather_snippet(city))

    # News
    sections.append("\nSOʻNGGI YANGILIKLAR:")
    sections.append(_news_snippet(4))

    # Todos
    todos = _todos_snippet()
    if todos:
        sections.append("\nBUGUNGI VAZIFALAR:")
        sections.append(todos)

    # Reminders
    rems = _reminders_snippet()
    if rems:
        sections.append("\nESLATMALAR:")
        sections.append(rems)

    sections.append("\nYaxshi kun tilayman!")

    return "\n".join(sections)
