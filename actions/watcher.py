"""watcher.py — Proactive background monitors that alert when a condition is met.

The "anticipation" modality: JARVIS tells YOU when something happens, unprompted.
"Yuklab olish tugasa ayt", "CPU 90% dan oshsa xabar ber", "bu fayl paydo bo'lsa
bildiri", "batareya 20% ga tushsa ogohlantir", "bu sahifa yangilansa ayt".

Each watcher is a daemon thread polling its condition; on trigger it notifies
(notify-send + voice + log) once, then stops.
"""
import hashlib
import subprocess
import threading
import time
import urllib.request
from pathlib import Path

_watchers: dict = {}
_lock = threading.Lock()
_counter = [0]

_POLL = 12.0          # seconds between checks
_MAX_DURATION = 6 * 3600


def _notify(title: str, msg: str, speak=None, player=None):
    try:
        subprocess.Popen(["notify-send", "-u", "critical", title, msg])
    except Exception:
        pass
    if player:
        try: player.write_log(f"🔔 {msg}")
        except Exception: pass
    if speak:
        try: speak(msg)
        except Exception: pass


def _proc_running(name: str) -> bool:
    try:
        r = subprocess.run(["pgrep", "-i", name], capture_output=True, text=True, timeout=5)
        return r.returncode == 0 and bool(r.stdout.strip())
    except Exception:
        return False


def _cpu_pct() -> float:
    try:
        import psutil
        return psutil.cpu_percent(interval=0.5)
    except Exception:
        return -1.0


def _battery_pct() -> float:
    try:
        import psutil
        b = psutil.sensors_battery()
        return b.percent if b else -1.0
    except Exception:
        return -1.0


def _url_hash(url: str) -> str | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return hashlib.md5(r.read()).hexdigest()
    except Exception:
        return None


def _check(condition: str, value: str, state: dict) -> tuple:
    """Return (triggered: bool, message: str)."""
    c = condition
    if c == "process_done":
        if not _proc_running(value):
            return True, f"'{value}' tugadi."
        return False, ""
    if c == "process_start":
        if _proc_running(value):
            return True, f"'{value}' ishga tushdi."
        return False, ""
    if c == "file_exists":
        if Path(value).expanduser().exists():
            return True, f"Fayl paydo bo'ldi: {value}"
        return False, ""
    if c == "cpu_above":
        v = _cpu_pct()
        if v >= 0 and v >= float(value):
            return True, f"CPU {v:.0f}% — chegaradan ({value}%) oshdi."
        return False, ""
    if c == "cpu_below":
        v = _cpu_pct()
        if v >= 0 and v <= float(value):
            return True, f"CPU {v:.0f}% — chegaradan ({value}%) tushdi."
        return False, ""
    if c == "battery_below":
        v = _battery_pct()
        if v >= 0 and v <= float(value):
            return True, f"Batareya {v:.0f}% — {value}% dan past."
        return False, ""
    if c == "battery_full":
        v = _battery_pct()
        if v >= 0 and v >= float(value or 95):
            return True, f"Batareya to'ldi ({v:.0f}%)."
        return False, ""
    if c == "url_changed":
        h = _url_hash(value)
        if h is None:
            return False, ""
        if state.get("hash") is None:
            state["hash"] = h
            return False, ""
        if h != state["hash"]:
            return True, f"Sahifa yangilandi: {value}"
        return False, ""
    return False, ""


def _run_watcher(wid: int, condition: str, value: str, note: str, speak, player):
    state = {"hash": None}
    deadline = time.time() + _MAX_DURATION
    while time.time() < deadline:
        with _lock:
            if wid not in _watchers:
                return  # cancelled
        try:
            triggered, msg = _check(condition, value, state)
        except Exception:
            triggered, msg = False, ""
        if triggered:
            full = (note + " — " if note else "") + msg
            _notify("JARVIS Kuzatuvchi", full, speak=speak, player=player)
            with _lock:
                _watchers.pop(wid, None)
            return
        time.sleep(_POLL)
    with _lock:
        _watchers.pop(wid, None)


_CONDS = {"process_done", "process_start", "file_exists", "cpu_above", "cpu_below",
          "battery_below", "battery_full", "url_changed"}


def watcher(parameters=None, response=None, player=None, session_memory=None, speak=None) -> str:
    params = parameters or {}
    action = (params.get("action") or "add").lower().strip()

    if action in ("list", "royxat"):
        with _lock:
            if not _watchers:
                return "Faol kuzatuvchi yo'q."
            lines = ["Faol kuzatuvchilar:"]
            for wid, w in _watchers.items():
                lines.append(f"  • #{wid}: {w['condition']}={w['value']}" + (f" ({w['note']})" if w['note'] else ""))
            return "\n".join(lines)

    if action in ("cancel", "stop", "bekor"):
        target = str(params.get("id") or params.get("target") or "").strip().lstrip("#")
        with _lock:
            if target in ("all", "hammasi"):
                n = len(_watchers); _watchers.clear()
                return f"{n} ta kuzatuvchi bekor qilindi."
            if target.isdigit() and int(target) in _watchers:
                _watchers.pop(int(target))
                return f"#{target} bekor qilindi."
        return f"#{target} topilmadi."

    # ── ADD ──────────────────────────────────────────────────────────────────
    condition = (params.get("condition") or "").lower().strip()
    value     = str(params.get("value") or params.get("target") or "").strip()
    note      = (params.get("note") or "").strip()
    if condition not in _CONDS:
        return ("condition kerak: process_done | process_start | file_exists | "
                "cpu_above | cpu_below | battery_below | battery_full | url_changed")
    if condition not in ("battery_full",) and not value:
        return f"'{condition}' uchun value kerak (masalan, jarayon nomi, fayl yo'li, foiz yoki URL)."

    with _lock:
        _counter[0] += 1
        wid = _counter[0]
        _watchers[wid] = {"condition": condition, "value": value, "note": note}

    t = threading.Thread(target=_run_watcher, args=(wid, condition, value, note, speak, player),
                         daemon=True, name=f"Watcher-{wid}")
    t.start()
    desc = {
        "process_done":  f"'{value}' tugaganda",
        "process_start": f"'{value}' ishga tushganda",
        "file_exists":   f"'{value}' fayli paydo bo'lganda",
        "cpu_above":     f"CPU {value}% dan oshganda",
        "cpu_below":     f"CPU {value}% dan tushganda",
        "battery_below": f"batareya {value}% dan tushganda",
        "battery_full":  "batareya to'lganda",
        "url_changed":   f"{value} yangilanganda",
    }.get(condition, condition)
    return f"👁️ Kuzatuvchi #{wid} o'rnatildi — {desc} sizga xabar beraman."
