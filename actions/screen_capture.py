"""screen_capture.py — Robust cross-stack screenshot (Wayland + X11).

GNOME Wayland blocks X11 capture (mss/ImageMagick return a BLACK frame). This
helper tries the working backends in order and returns the first NON-BLACK image,
so the vision features (screen_vision, screen_click, auto_agent, time_machine)
work regardless of display server — as long as a capable tool is installed.

Preferred on GNOME Wayland: `gnome-screenshot` (apt install gnome-screenshot).
"""
import shutil
import subprocess
import tempfile
from pathlib import Path

_MIN_MEAN = 2.0   # below this the frame is "black" (X11 capture under Wayland)


def _load_nonblack(path: str):
    try:
        from PIL import Image
        import numpy as np
        img = Image.open(path).convert("RGB")
        if float(np.asarray(img).mean()) >= _MIN_MEAN:
            return img
    except Exception:
        pass
    return None


def _via_tool(cmd_builder) -> "object | None":
    tmp = Path(tempfile.gettempdir()) / f"_jv_shot_{tempfile.gettempprefix()}.png"
    try:
        if tmp.exists():
            tmp.unlink()
    except Exception:
        pass
    try:
        cmd = cmd_builder(str(tmp))
        subprocess.run(cmd, capture_output=True, timeout=15)
        if tmp.exists():
            img = _load_nonblack(str(tmp))
            try: tmp.unlink()
            except Exception: pass
            return img
    except Exception:
        pass
    return None


def _via_mss():
    try:
        import mss, numpy as np
        from PIL import Image
        with mss.mss() as sct:
            shot = sct.grab(sct.monitors[0])
            img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        if float(np.asarray(img).mean()) >= _MIN_MEAN:
            return img
    except Exception:
        pass
    return None


def capture_pil():
    """Return a full-screen PIL.Image (RGB) using the first backend that yields
    a non-black frame, or None if screen capture is unavailable.

    Order: the SILENT PipeWire screencast (no flash) if its daemon is streaming,
    then gnome-screenshot (flashes), then X11 tools.
    """
    # Silent path — flash-free PipeWire frame from the screencast daemon
    try:
        import core.screencast as _sc
        img = _sc.live_frame_pil()
        if img is not None:
            return img
    except Exception:
        pass
    # GNOME (Wayland + X11) — reliable but flashes
    if shutil.which("gnome-screenshot"):
        img = _via_tool(lambda p: ["gnome-screenshot", "-f", p])
        if img is not None:
            return img
    # wlroots Wayland
    if shutil.which("grim"):
        img = _via_tool(lambda p: ["grim", p])
        if img is not None:
            return img
    # KDE
    if shutil.which("spectacle"):
        img = _via_tool(lambda p: ["spectacle", "-b", "-n", "-o", p])
        if img is not None:
            return img
    # X11 fast path
    img = _via_mss()
    if img is not None:
        return img
    # X11 ImageMagick
    if shutil.which("import"):
        img = _via_tool(lambda p: ["import", "-window", "root", p])
        if img is not None:
            return img
    return None


def capture_available() -> bool:
    return capture_pil() is not None
