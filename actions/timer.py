"""timer.py — Countdown timer with desktop notification.

Different from alarm (which fires at a clock time) — timer counts DOWN from now.
Multiple timers can run concurrently (each gets a unique ID).
"""
import threading
import time
from collections import OrderedDict

_timers: dict[int, threading.Timer] = {}
_lock = threading.Lock()
_next_id = 0


def _notify(label: str, player) -> None:
    msg = f"Taymer tugadi: {label}"
    if player:
        try:
            player.write_log(f"[Timer] {msg}")
        except Exception:
            pass
        try:
            import subprocess
            subprocess.Popen(["notify-send", "-u", "critical", "JARVIS Taymer", msg])
        except Exception:
            pass
        try:
            # Jarvis speaks the notification
            if hasattr(player, "speak"):
                player.speak(msg)
        except Exception:
            pass


def _seconds(value, unit: str) -> float:
    unit = unit.lower().strip()
    if unit in ("s", "sec", "second", "seconds", "soniya", "son"):
        return float(value)
    if unit in ("m", "min", "minute", "minutes", "daqiqa", "daq"):
        return float(value) * 60
    if unit in ("h", "hr", "hour", "hours", "soat"):
        return float(value) * 3600
    return float(value) * 60  # default: minutes


def timer(parameters=None, response=None, player=None, session_memory=None) -> str:
    global _next_id
    params = parameters or {}
    action = (params.get("action") or "set").lower().strip()

    # ── LIST ──────────────────────────────────────────────────────────────────
    if action in ("list", "show", "active"):
        with _lock:
            active = {tid: t for tid, t in _timers.items() if t.is_alive()}
        if not active:
            return "Hozirda faol taymer yo'q."
        return f"Faol taymerlar: {len(active)} ta (ID-lari: {', '.join(map(str, active.keys()))})"

    # ── CANCEL ────────────────────────────────────────────────────────────────
    if action in ("cancel", "stop", "bekor"):
        tid = params.get("id")
        with _lock:
            if tid is not None:
                t = _timers.pop(int(tid), None)
                if t:
                    t.cancel()
                    return f"Taymer #{tid} bekor qilindi."
                return f"Taymer #{tid} topilmadi."
            # cancel all
            for t in _timers.values():
                t.cancel()
            count = len(_timers)
            _timers.clear()
        return f"{count} ta taymer bekor qilindi."

    # ── SET ───────────────────────────────────────────────────────────────────
    duration = params.get("duration") or params.get("time") or params.get("vaqt")
    if duration is None:
        # try minutes / seconds / hours directly
        if params.get("minutes") or params.get("daqiqa"):
            val = float(params.get("minutes") or params.get("daqiqa") or 1)
            secs = val * 60
        elif params.get("seconds") or params.get("soniya"):
            secs = float(params.get("seconds") or params.get("soniya") or 30)
        elif params.get("hours") or params.get("soat"):
            secs = float(params.get("hours") or params.get("soat") or 1) * 3600
        else:
            return "Taymer vaqtini ko'rsating. Masalan: {duration: 5, unit: 'daqiqa'}"
    else:
        unit = params.get("unit") or "minutes"
        secs = _seconds(duration, unit)

    label = (params.get("label") or params.get("name") or f"{int(secs)}s taymer").strip()

    if secs <= 0 or secs > 86400:
        return "Taymer vaqti 1 soniya — 24 soat orasida bo'lishi kerak."

    with _lock:
        _next_id += 1
        tid = _next_id
        t = threading.Timer(secs, _notify, args=(label, player))
        t.daemon = True
        _timers[tid] = t
        t.start()

    if secs >= 3600:
        human = f"{secs/3600:.4g} soat"
    elif secs >= 60:
        human = f"{secs/60:.4g} daqiqa"
    else:
        human = f"{int(secs)} soniya"

    if player:
        player.write_log(f"[Timer #{tid}] {label} — {human}")

    return f"Taymer #{tid} o'rnatildi: {human} dan keyin '{label}' xabari beriladi."
