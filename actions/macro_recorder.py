"""macro_recorder.py — Record and replay keyboard/mouse macros."""
import json
import threading
import time
from pathlib import Path

_MACRO_DIR = Path.home() / ".config" / "jarvis" / "macros"
_state: dict = {"recording": False, "events": [], "thread": None, "listeners": []}


def _macro_dir() -> Path:
    _MACRO_DIR.mkdir(parents=True, exist_ok=True)
    return _MACRO_DIR


def _stop_listeners():
    for lst in _state["listeners"]:
        try: lst.stop()
        except Exception: pass
    _state["listeners"].clear()


def _start_recording():
    from pynput import keyboard, mouse

    events = []
    start  = time.time()

    def on_key_press(key):
        if not _state["recording"]: return False
        try:   k = key.char
        except AttributeError: k = str(key)
        events.append({"t": round(time.time() - start, 3), "type": "key_press", "key": k})

    def on_key_release(key):
        if not _state["recording"]: return False
        try:   k = key.char
        except AttributeError: k = str(key)
        events.append({"t": round(time.time() - start, 3), "type": "key_release", "key": k})

    def on_click(x, y, button, pressed):
        if not _state["recording"]: return False
        events.append({
            "t": round(time.time() - start, 3),
            "type": "click", "x": x, "y": y,
            "button": str(button), "pressed": pressed,
        })

    def on_move(x, y):
        if not _state["recording"]: return False
        events.append({"t": round(time.time() - start, 3), "type": "move", "x": x, "y": y})

    kb_lst = keyboard.Listener(on_press=on_key_press, on_release=on_key_release)
    ms_lst = mouse.Listener(on_click=on_click, on_move=on_move)
    kb_lst.start()
    ms_lst.start()
    _state["listeners"] = [kb_lst, ms_lst]
    _state["events"]    = events


def _replay_events(events: list, speed: float = 1.0):
    from pynput import keyboard, mouse
    kb = keyboard.Controller()
    ms = mouse.Controller()

    prev_t = 0.0
    for ev in events:
        delay = (ev["t"] - prev_t) / speed
        if delay > 0:
            time.sleep(delay)
        prev_t = ev["t"]

        etype = ev["type"]
        if etype == "key_press":
            try:
                from pynput.keyboard import Key
                key = getattr(Key, ev["key"].replace("Key.", ""), None) or ev["key"]
                kb.press(key)
            except Exception: pass
        elif etype == "key_release":
            try:
                from pynput.keyboard import Key
                key = getattr(Key, ev["key"].replace("Key.", ""), None) or ev["key"]
                kb.release(key)
            except Exception: pass
        elif etype == "click":
            from pynput.mouse import Button
            ms.position = (ev["x"], ev["y"])
            btn = Button.left if "left" in ev["button"] else Button.right
            if ev["pressed"]: ms.press(btn)
            else:             ms.release(btn)
        elif etype == "move":
            ms.position = (ev["x"], ev["y"])


def macro_recorder(parameters=None, response=None, player=None, session_memory=None) -> str:
    params  = parameters or {}
    action  = (params.get("action") or "list").lower().strip()
    name    = (params.get("name") or "").strip()
    speed   = float(params.get("speed", 1.0))
    seconds = float(params.get("seconds", 0))

    # ── RECORD START ──────────────────────────────────────────────────────────
    if action in ("record", "boshlash", "yozish"):
        if _state["recording"]:
            return "Allaqachon yozilmoqda."
        _state["recording"] = True
        _start_recording()
        if player: player.write_log(f"[Macro] Recording started")
        msg = "Makro yozish boshlandi."
        if seconds > 0:
            def _auto_stop():
                time.sleep(seconds)
                _state["recording"] = False
                _stop_listeners()
            threading.Thread(target=_auto_stop, daemon=True).start()
            msg += f" {seconds:.0f} soniyadan keyin avtomatik to'xtaydi."
        return msg

    # ── RECORD STOP ───────────────────────────────────────────────────────────
    if action in ("stop", "to'xtat", "tugatish"):
        if not _state["recording"] and not _state["events"]:
            return "Yozuv yo'q."
        _state["recording"] = False
        _stop_listeners()
        events = _state["events"]
        if not events:
            return "Makroda voqealar topilmadi."

        save_name = name or f"macro_{int(time.time())}"
        path = _macro_dir() / f"{save_name}.json"
        path.write_text(json.dumps(events, indent=2))
        _state["events"] = []
        if player: player.write_log(f"[Macro] Saved: {path.name} ({len(events)} events)")
        return f"Makro saqlandi: {path.name} ({len(events)} ta voqea)"

    # ── PLAY ──────────────────────────────────────────────────────────────────
    if action in ("play", "ijro", "run", "ishlat"):
        if not name:
            files = sorted(_macro_dir().glob("*.json"), reverse=True)
            if not files:
                return "Makrolar yo'q."
            path = files[0]
        else:
            path = next(
                (f for f in _macro_dir().glob("*.json") if name.lower() in f.stem.lower()),
                None
            )
            if not path:
                return f"Makro topilmadi: '{name}'"

        events = json.loads(path.read_text())
        if player: player.write_log(f"[Macro] Playing: {path.name} x{speed}")
        t = threading.Thread(target=_replay_events, args=(events, speed), daemon=True)
        t.start()
        return f"Makro ijro etilmoqda: {path.name} ({len(events)} voqea, {speed}x tezlik)"

    # ── LIST ──────────────────────────────────────────────────────────────────
    if action in ("list", "ro'yxat", "hammasi"):
        files = sorted(_macro_dir().glob("*.json"), reverse=True)
        if not files:
            return "Saqlangan makrolar yo'q."
        lines = []
        for f in files[:10]:
            try:
                events = json.loads(f.read_text())
                dur    = events[-1]["t"] if events else 0
                lines.append(f"• {f.stem} ({len(events)} voqea, {dur:.1f}s)")
            except Exception:
                lines.append(f"• {f.stem}")
        return f"Makrolar ({len(files)}):\n" + "\n".join(lines)

    # ── DELETE ────────────────────────────────────────────────────────────────
    if action in ("delete", "o'chir"):
        if not name:
            return "O'chirish uchun nom ko'rsating."
        path = next(
            (f for f in _macro_dir().glob("*.json") if name.lower() in f.stem.lower()),
            None
        )
        if not path:
            return f"Makro topilmadi: '{name}'"
        path.unlink()
        return f"O'chirildi: {path.name}"

    return "Amallar: record | stop | play | list | delete"
