"""alarm.py — Set alarms at specific times (once or recurring)."""
import json
import shutil
import subprocess
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

_ALARM_FILE = Path.home() / ".config" / "jarvis" / "alarms.json"
_active: dict[str, threading.Timer] = {}


def _load() -> list:
    try: return json.loads(_ALARM_FILE.read_text())
    except Exception: return []


def _save(data: list):
    _ALARM_FILE.parent.mkdir(parents=True, exist_ok=True)
    _ALARM_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def _notify(title: str, body: str):
    if shutil.which("notify-send"):
        subprocess.Popen(["notify-send", "-u", "critical", "-t", "0", title, body])
    if shutil.which("paplay"):
        subprocess.Popen(
            ["paplay", "/usr/share/sounds/freedesktop/stereo/bell.oga"],
            stderr=subprocess.DEVNULL,
        )


def _parse_time(text: str) -> datetime | None:
    text = text.strip().lower()
    now  = datetime.now()

    prefixes = {
        "bugun": 0, "today": 0,
        "ertaga": 1, "tomorrow": 1,
        "indinga": 2,
    }
    offset = 0
    for word, days in prefixes.items():
        if text.startswith(word):
            offset = days
            text   = text[len(word):].strip()
            break

    for fmt in ("%H:%M", "%H:%M:%S", "%I:%M %p", "%H"):
        try:
            t  = datetime.strptime(text, fmt)
            dt = now.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
            dt += timedelta(days=offset)
            if dt <= now and offset == 0:
                dt += timedelta(days=1)
            return dt
        except ValueError:
            continue

    for fmt in ("%Y-%m-%d %H:%M", "%d.%m.%Y %H:%M", "%d/%m/%Y %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue

    return None


def _fire_alarm(alarm_id: str, label: str, speak_fn=None):
    msg = f"Signal: {label}!"
    _notify("⏰ Jarvis Signal", msg)
    if speak_fn:
        try: speak_fn(msg)
        except Exception: pass
    # Remove from active
    _active.pop(alarm_id, None)
    # Remove non-recurring from storage
    alarms = [a for a in _load() if not (a["id"] == alarm_id and not a.get("repeat"))]
    _save(alarms)


def _schedule(alarm: dict, speak_fn=None):
    alarm_id = alarm["id"]
    dt       = datetime.fromisoformat(alarm["time"])
    delay    = (dt - datetime.now()).total_seconds()
    if delay <= 0:
        if alarm.get("repeat"):
            # Schedule for next occurrence
            dt += timedelta(days=1)
            alarm["time"] = dt.isoformat()
            delay = (dt - datetime.now()).total_seconds()
        else:
            return
    t = threading.Timer(delay, _fire_alarm, args=(alarm_id, alarm["label"], speak_fn))
    t.daemon = True
    t.start()
    _active[alarm_id] = t


def _restore_alarms(speak_fn=None):
    for alarm in _load():
        if alarm["id"] not in _active:
            _schedule(alarm, speak_fn)


def alarm(parameters=None, response=None, player=None, session_memory=None,
          speak=None) -> str:
    params = parameters or {}
    action = (params.get("action") or "set").lower().strip()

    # Restore persisted alarms on first call
    if not _active:
        _restore_alarms(speak)

    # ── SET ───────────────────────────────────────────────────────────────────
    if action in ("set", "qo'y", "boshlash", "yaratish", "add"):
        time_str = (params.get("time") or "").strip()
        label    = (params.get("label") or "Signal").strip()
        repeat   = bool(params.get("repeat", False))

        if not time_str:
            return "Vaqt ko'rsatilmagan. Masalan: '07:30' yoki 'ertaga 08:00'."

        dt = _parse_time(time_str)
        if not dt:
            return f"Vaqt formatini tushunolmadim: '{time_str}'. Format: '07:30', 'ertaga 08:00', '2025-06-01 09:00'"

        alarm_id = f"alarm_{int(dt.timestamp())}"
        entry    = {
            "id":     alarm_id,
            "time":   dt.isoformat(),
            "label":  label,
            "repeat": repeat,
        }
        alarms = _load()
        alarms.append(entry)
        _save(alarms)
        _schedule(entry, speak)

        diff = dt - datetime.now()
        h, m = divmod(int(diff.total_seconds() / 60), 60)
        when  = f"{h} soat {m} daqiqadan keyin" if h else f"{m} daqiqadan keyin"
        rpt   = " (har kuni)" if repeat else ""
        if player: player.write_log(f"[Alarm] Set: {label} at {dt.strftime('%H:%M')}")
        return f"⏰ Signal o'rnatildi: {label} — {dt.strftime('%d.%m.%Y %H:%M')} ({when}){rpt}"

    # ── LIST ──────────────────────────────────────────────────────────────────
    if action in ("list", "ro'yxat", "hammasi", "ko'rsat"):
        alarms = _load()
        if not alarms:
            return "Faol signallar yo'q."
        lines = []
        now   = datetime.now()
        for a in alarms:
            dt   = datetime.fromisoformat(a["time"])
            diff = dt - now
            h, m = divmod(max(0, int(diff.total_seconds() / 60)), 60)
            left = f"{h}s {m}d" if h else f"{m}d"
            rpt  = " 🔁" if a.get("repeat") else ""
            lines.append(f"• {a['label']} — {dt.strftime('%H:%M')} ({left} qoldi){rpt}")
        return f"Signallar ({len(alarms)}):\n" + "\n".join(lines)

    # ── DELETE ────────────────────────────────────────────────────────────────
    if action in ("delete", "o'chir", "bekor", "cancel"):
        label = (params.get("label") or "").strip().lower()
        alarms = _load()
        if not alarms:
            return "Signallar yo'q."
        if not label:
            # Cancel the soonest alarm
            target = min(alarms, key=lambda a: a["time"])
        else:
            target = next((a for a in alarms if label in a["label"].lower()), None)
            if not target:
                return f"'{label}' nomi bilan signal topilmadi."
        alarms.remove(target)
        _save(alarms)
        t = _active.pop(target["id"], None)
        if t: t.cancel()
        if player: player.write_log(f"[Alarm] Cancelled: {target['label']}")
        return f"Signal bekor qilindi: {target['label']}"

    return "Amallar: set | list | delete"
