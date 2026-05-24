"""google_calendar.py — List, create, and delete Google Calendar events via OAuth2."""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

_CFG_DIR   = Path.home() / ".config" / "jarvis"
_TOKEN     = _CFG_DIR / "gcal_token.json"
_CREDS     = _CFG_DIR / "gcal_credentials.json"
_SCOPES    = ["https://www.googleapis.com/auth/calendar"]


def _get_service():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    if _TOKEN.exists():
        creds = Credentials.from_authorized_user_file(str(_TOKEN), _SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        elif _CREDS.exists():
            flow  = InstalledAppFlow.from_client_secrets_file(str(_CREDS), _SCOPES)
            creds = flow.run_local_server(port=0)
        else:
            raise FileNotFoundError(
                f"Google Calendar credentials topilmadi: {_CREDS}\n"
                "Google Cloud Console → OAuth2 credentials → Desktop app → "
                f"JSON ni {_CREDS} ga saqlang."
            )
        _CFG_DIR.mkdir(parents=True, exist_ok=True)
        _TOKEN.write_text(creds.to_json())

    return build("calendar", "v3", credentials=creds)


def _parse_dt(text: str) -> str:
    """Return ISO 8601 datetime string from natural text."""
    text = text.strip().lower()
    now  = datetime.now()

    if text in ("bugun", "today"):
        dt = now.replace(hour=9, minute=0, second=0, microsecond=0)
    elif text in ("ertaga", "tomorrow"):
        dt = (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
    else:
        for fmt in ("%Y-%m-%d %H:%M", "%d.%m.%Y %H:%M", "%Y-%m-%d", "%d.%m.%Y",
                    "%H:%M", "%d/%m/%Y"):
            try:
                dt = datetime.strptime(text, fmt)
                if fmt == "%H:%M":
                    dt = now.replace(hour=dt.hour, minute=dt.minute, second=0, microsecond=0)
                break
            except ValueError:
                continue
        else:
            raise ValueError(f"Sana formatini tushunolmadim: '{text}'")

    return dt.isoformat()


def google_calendar(parameters=None, response=None, player=None, session_memory=None) -> str:
    params  = parameters or {}
    action  = (params.get("action") or "list").lower().strip()

    try:
        svc = _get_service()
    except FileNotFoundError as e:
        return str(e)
    except Exception as e:
        return f"Google Calendar ulanishda xato: {e}"

    # ── LIST ──────────────────────────────────────────────────────────────────
    if action in ("list", "ko'rsat", "voqealar", "jadval"):
        days  = int(params.get("days", 7))
        now   = datetime.utcnow().isoformat() + "Z"
        end   = (datetime.utcnow() + timedelta(days=days)).isoformat() + "Z"
        res   = svc.events().list(
            calendarId="primary", timeMin=now, timeMax=end,
            maxResults=15, singleEvents=True, orderBy="startTime",
        ).execute()
        items = res.get("items", [])
        if not items:
            return f"Kelgusi {days} kun uchun voqealar yo'q."
        lines = []
        for ev in items:
            start = ev["start"].get("dateTime", ev["start"].get("date", "?"))
            try:
                dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
                label = dt.strftime("%d.%m %H:%M")
            except Exception:
                label = start[:10]
            lines.append(f"• {label} — {ev.get('summary', 'Nomsiz')}")
        if player: player.write_log(f"[GCal] Listed {len(items)} events")
        return f"Voqealar ({days} kun):\n" + "\n".join(lines)

    # ── CREATE ────────────────────────────────────────────────────────────────
    if action in ("create", "qo'sh", "yarat", "add"):
        title    = (params.get("title") or "Voqea").strip()
        start_s  = (params.get("start") or "bugun").strip()
        dur_min  = int(params.get("duration_minutes", 60))
        location = (params.get("location") or "").strip()
        desc     = (params.get("description") or "").strip()

        try:
            start_dt = datetime.fromisoformat(_parse_dt(start_s))
        except Exception as e:
            return f"Sana xato: {e}"

        end_dt = start_dt + timedelta(minutes=dur_min)
        body   = {
            "summary":  title,
            "start":    {"dateTime": start_dt.isoformat(), "timeZone": "Asia/Tashkent"},
            "end":      {"dateTime": end_dt.isoformat(),   "timeZone": "Asia/Tashkent"},
        }
        if location: body["location"]    = location
        if desc:     body["description"] = desc

        ev = svc.events().insert(calendarId="primary", body=body).execute()
        if player: player.write_log(f"[GCal] Created: {title}")
        return f"Voqea qo'shildi: {title} — {start_dt.strftime('%d.%m.%Y %H:%M')}"

    # ── DELETE ────────────────────────────────────────────────────────────────
    if action in ("delete", "o'chir", "bekor"):
        title = (params.get("title") or "").strip().lower()
        if not title:
            return "O'chirish uchun voqea nomini ko'rsating."
        now = datetime.utcnow().isoformat() + "Z"
        res = svc.events().list(
            calendarId="primary", timeMin=now, maxResults=20,
            singleEvents=True, orderBy="startTime",
        ).execute()
        items = res.get("items", [])
        target = next(
            (ev for ev in items if title in ev.get("summary", "").lower()), None
        )
        if not target:
            return f"Voqea topilmadi: '{title}'"
        svc.events().delete(calendarId="primary", eventId=target["id"]).execute()
        if player: player.write_log(f"[GCal] Deleted: {target.get('summary')}")
        return f"O'chirildi: {target.get('summary')}"

    return "Amallar: list | create | delete"
