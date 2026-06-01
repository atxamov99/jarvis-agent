"""input_control.py — Wayland/X11-aware mouse & keyboard control.

GNOME Wayland blocks X11 input injection: `xdotool click/type` move the XWayland
cursor but the events never reach native Wayland windows (Telegram, Chrome,
GNOME apps) — so the agent can SEE the screen but can't ACT in the app.

This layer routes input through the backend that actually works:
  • Wayland → ydotool (mouse+keyboard via uinput) preferred; wtype for typing.
  • X11 / fallback → xdotool.

If on Wayland and neither ydotool nor wtype is available, click() returns a
hint so the caller can tell the user to install ydotool.
"""
import os
import shutil
import subprocess
import time

_IS_WAYLAND = (os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"
               or bool(os.environ.get("WAYLAND_DISPLAY")))

_HAS_YDOTOOL = shutil.which("ydotool") is not None
_HAS_WTYPE   = shutil.which("wtype") is not None
_HAS_XDOTOOL = shutil.which("xdotool") is not None

# ydotool needs a running daemon; detect a likely socket
_YDOTOOL_SOCK = os.environ.get("YDOTOOL_SOCKET", "/run/user/%d/.ydotool_socket" % os.getuid())


def backend() -> str:
    """Which input backend will be used: 'ydotool' | 'wtype+xdotool' | 'xdotool' | 'none'."""
    if _IS_WAYLAND:
        if _HAS_YDOTOOL:
            return "ydotool"
        if _HAS_WTYPE or _HAS_XDOTOOL:
            return "wtype+xdotool"
        return "none"
    return "xdotool" if _HAS_XDOTOOL else "none"


def needs_setup() -> str:
    """Return a user hint if input won't work in native Wayland apps, else ''."""
    if _IS_WAYLAND and not _HAS_YDOTOOL:
        return ("Wayland sessiyasida ilova ichida bosish uchun ydotool kerak. "
                "O'rnatish: sudo apt install ydotool && sudo systemctl enable --now ydotool")
    return ""


_ydotoold_checked = [False]

def _ensure_ydotoold():
    """Make sure ydotoold (the uinput daemon ydotool talks to) is running."""
    if _ydotoold_checked[0] or not _HAS_YDOTOOL:
        return
    _ydotoold_checked[0] = True
    if os.path.exists(_YDOTOOL_SOCK):
        return
    # Try the user systemd service first, then a background daemon.
    try:
        subprocess.run(["systemctl", "--user", "start", "ydotool"],
                       timeout=4, capture_output=True)
    except Exception:
        pass
    if os.path.exists(_YDOTOOL_SOCK):
        return
    if shutil.which("ydotoold"):
        try:
            subprocess.Popen(["ydotoold"], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
            time.sleep(0.6)
        except Exception:
            pass


def _run(cmd, timeout=6) -> bool:
    try:
        env = dict(os.environ)
        env.setdefault("YDOTOOL_SOCKET", _YDOTOOL_SOCK)
        r = subprocess.run(cmd, timeout=timeout, capture_output=True, env=env)
        return r.returncode == 0
    except Exception as e:
        print(f"[InputControl] {cmd[0]} error: {e}")
        return False


# ── Mouse ─────────────────────────────────────────────────────────────────────

def move(x: int, y: int) -> bool:
    if _IS_WAYLAND and _HAS_YDOTOOL:
        _ensure_ydotoold()
        return _run(["ydotool", "mousemove", str(x), str(y)])
    if _HAS_XDOTOOL:
        return _run(["xdotool", "mousemove", str(x), str(y)])
    return False


def click(x: int, y: int, button: str = "left", double: bool = False) -> bool:
    move(x, y)
    time.sleep(0.12)
    if _IS_WAYLAND and _HAS_YDOTOOL:
        code = {"left": "1", "right": "2", "middle": "3"}.get(button, "1")
        if double:
            return _run(["ydotool", "click", "--repeat", "2", code])
        return _run(["ydotool", "click", code])
    if _HAS_XDOTOOL:
        btn = {"left": "1", "middle": "2", "right": "3"}.get(button, "1")
        if double:
            return _run(["xdotool", "click", "--repeat", "2", btn])
        return _run(["xdotool", "click", btn])
    return False


def scroll(direction: str = "down", amount: int = 3) -> bool:
    if _HAS_XDOTOOL:
        btn = "5" if direction == "down" else "4"
        return _run(["xdotool", "click", "--repeat", str(amount), btn])
    return False


# ── Keyboard ──────────────────────────────────────────────────────────────────

def type_text(text: str) -> bool:
    if not text:
        return True
    if _IS_WAYLAND:
        if _HAS_YDOTOOL:
            _ensure_ydotoold()
            return _run(["ydotool", "type", "--key-delay", "20", text], timeout=25)
        if _HAS_WTYPE:
            return _run(["wtype", text], timeout=20)
    if _HAS_XDOTOOL:
        return _run(["xdotool", "type", "--clearmodifiers", "--delay", "25", "--", text], timeout=20)
    return False


# Map common key names to wtype / ydotool conventions
_WTYPE_KEYS = {
    "Return": "Return", "Enter": "Return", "Tab": "Tab", "Escape": "Escape",
    "BackSpace": "BackSpace", "Delete": "Delete", "space": "space",
    "Up": "Up", "Down": "Down", "Left": "Left", "Right": "Right",
    "Home": "Home", "End": "End", "Page_Up": "Prior", "Page_Down": "Next",
}


def key(combo: str) -> bool:
    """Press a key or chord like 'Return', 'ctrl+a', 'ctrl+f'."""
    combo = (combo or "Return").strip()
    if _IS_WAYLAND and _HAS_YDOTOOL:
        _ensure_ydotoold()
        return _run(["ydotool", "key", combo])  # 0.1.8 accepts xdotool-style names
    if _IS_WAYLAND and _HAS_WTYPE:
        return _wtype_key(combo)
    if _HAS_XDOTOOL:
        return _run(["xdotool", "key", "--clearmodifiers", combo])
    return False


def _wtype_key(combo: str) -> bool:
    parts = combo.split("+")
    if len(parts) == 1:
        k = _WTYPE_KEYS.get(parts[0], parts[0])
        return _run(["wtype", "-k", k])
    # modifiers + key: wtype -M ctrl -k a -m ctrl
    mods = parts[:-1]
    base = parts[-1]
    cmd = ["wtype"]
    for mod in mods:
        cmd += ["-M", mod]
    cmd += ["-k", _WTYPE_KEYS.get(base, base)]
    for mod in mods:
        cmd += ["-m", mod]
    return _run(cmd)


# Minimal keycode table for ydotool (Linux input-event codes)
_YDO_CODES = {
    "Return": 28, "Enter": 28, "Tab": 15, "Escape": 1, "BackSpace": 14,
    "Delete": 111, "space": 57, "Up": 103, "Down": 108, "Left": 105, "Right": 106,
    "ctrl": 29, "alt": 56, "shift": 42, "super": 125,
    "a": 30, "c": 46, "v": 47, "x": 45, "f": 33, "z": 44, "s": 31, "l": 38,
}


def _ydotool_key(combo: str) -> bool:
    parts = combo.split("+")
    seq = []
    codes = [_YDO_CODES.get(p) for p in parts]
    if any(c is None for c in codes):
        # Unknown key — fall back to xdotool if present
        if _HAS_XDOTOOL:
            return _run(["xdotool", "key", "--clearmodifiers", combo])
        return False
    for c in codes:           # press all
        seq.append(f"{c}:1")
    for c in reversed(codes):  # release all
        seq.append(f"{c}:0")
    return _run(["ydotool", "key"] + seq)
