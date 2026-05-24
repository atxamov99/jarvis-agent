"""notifier.py — Schedule a desktop notification after N minutes/seconds."""
import threading
import time
import shutil
import subprocess


def _send(title: str, body: str, urgency: str = "normal"):
    if shutil.which("notify-send"):
        subprocess.Popen(["notify-send", "-t", "10000", "-u", urgency, title, body])
    if shutil.which("paplay"):
        subprocess.Popen(
            ["paplay", "/usr/share/sounds/freedesktop/stereo/bell.oga"],
            stderr=subprocess.DEVNULL,
        )


def notifier(parameters=None, response=None, player=None, session_memory=None,
             speak=None) -> str:
    params  = parameters or {}
    message = (params.get("message") or "Vaqt tugadi!").strip()
    minutes = float(params.get("minutes", 0))
    seconds = float(params.get("seconds", 0))
    delay   = minutes * 60 + seconds

    if delay <= 0:
        # Immediate notification
        _send("Jarvis", message)
        return f"Bildirishnoma yuborildi: {message}"

    total_sec = int(delay)
    label = f"{int(minutes)}d {int(seconds)}s" if minutes and seconds else \
            (f"{int(minutes)} daqiqa" if minutes else f"{int(seconds)} soniya")

    def _fire():
        time.sleep(delay)
        _send("Jarvis Eslatma", message, urgency="critical")
        if speak:
            try: speak(message)
            except Exception: pass

    t = threading.Thread(target=_fire, daemon=True)
    t.start()
    if player:
        player.write_log(f"[Notifier] Scheduled in {total_sec}s: {message}")
    return f"{label} dan keyin eslataman: \"{message}\""
