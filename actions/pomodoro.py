"""pomodoro.py — Pomodoro timer with desktop notifications."""
import threading
import time
import shutil
import subprocess

_state: dict = {"running": False, "thread": None, "label": "", "end_time": 0.0}

def _notify(title: str, body: str):
    if shutil.which("notify-send"):
        subprocess.Popen(["notify-send", "-t", "8000", "-u", "critical", title, body])
    if shutil.which("paplay"):
        subprocess.Popen(["paplay", "/usr/share/sounds/freedesktop/stereo/complete.oga"],
                         stderr=subprocess.DEVNULL)

def _run_timer(label: str, seconds: int, callback_msg: str, speak_fn=None):
    _state.update({"running": True, "label": label, "end_time": time.time() + seconds})
    time.sleep(seconds)
    if _state["running"]:
        _notify("Jarvis Pomodoro", callback_msg)
        if speak_fn:
            try: speak_fn(callback_msg)
            except Exception: pass
    _state["running"] = False

def pomodoro(parameters=None, response=None, player=None, session_memory=None,
             speak=None) -> str:
    params = parameters or {}
    action = (params.get("action") or "start").lower().strip()

    if action in ("start", "boshlash", "ishla", "run"):
        if _state["running"]:
            left = max(0, int(_state["end_time"] - time.time()))
            return f"Already running: {_state['label']} — {left//60}m {left%60}s left."

        work_min  = int(params.get("work_minutes", 25))
        break_min = int(params.get("break_minutes", 5))
        label     = f"Pomodoro {work_min}m"

        def _cycle():
            _run_timer(label, work_min * 60,
                       f"Pomodoro tugadi! {break_min} daqiqa dam oling.", speak)
            time.sleep(2)
            if not _state["running"]:
                _run_timer(f"Break {break_min}m", break_min * 60,
                           "Dam olish tugadi! Yana ishlashga tayyor.", speak)

        t = threading.Thread(target=_cycle, daemon=True)
        t.start()
        _state["thread"] = t
        _notify("Jarvis Pomodoro", f"{work_min} daqiqalik Pomodoro boshlandi!")
        if player: player.write_log(f"[Pomodoro] Started {work_min}m work + {break_min}m break")
        return f"Pomodoro boshlandi: {work_min} daqiqa ish, keyin {break_min} daqiqa dam."

    if action in ("stop", "cancel", "to'xtat"):
        if not _state["running"]:
            return "No active Pomodoro."
        _state["running"] = False
        return "Pomodoro stopped."

    if action in ("status", "holat", "qancha"):
        if not _state["running"]:
            return "No active Pomodoro."
        left = max(0, int(_state["end_time"] - time.time()))
        return f"{_state['label']}: {left//60}m {left%60}s remaining."

    return "Actions: start | stop | status"
