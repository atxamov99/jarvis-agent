"""screencast.py — venv-side controller for the silent screencast daemon.

The daemon (core/screencast_daemon.py) needs system python (gi + dbus), so we
launch it with /usr/bin/python3. It writes data/_live_frame.jpg continuously
with NO screen flash. This module starts/stops it and reads the latest frame.
"""
import subprocess
import time
from pathlib import Path

_BASE   = Path(__file__).resolve().parent.parent
_DAEMON = _BASE / "core" / "screencast_daemon.py"
_FRAME  = _BASE / "data" / "_live_frame.jpg"
_PIDF   = _BASE / "data" / "_screencast.pid"
_SYS_PY = "/usr/bin/python3"

_FRESH_S = 8.0   # a frame older than this means the daemon isn't streaming


def _pid_alive(pid: int) -> bool:
    try:
        import os
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def is_running() -> bool:
    try:
        if _PIDF.exists():
            pid = int(_PIDF.read_text().strip())
            return _pid_alive(pid)
    except Exception:
        pass
    return False


def ensure_started() -> bool:
    """Launch the silent screencast daemon if not already running.

    First launch shows ONE 'Share screen' dialog (persist_mode → never again).
    Returns True if the daemon is running/was started.
    """
    if is_running():
        return True
    if not Path(_SYS_PY).exists():
        print("[Screencast] system python not found.")
        return False
    try:
        _FRAME.parent.mkdir(parents=True, exist_ok=True)
        proc = subprocess.Popen(
            [_SYS_PY, str(_DAEMON)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        _PIDF.write_text(str(proc.pid))
        print(f"[Screencast] daemon launched (pid {proc.pid}).")
        return True
    except Exception as e:
        print(f"[Screencast] launch error: {e}")
        return False


def stop():
    try:
        if _PIDF.exists():
            pid = int(_PIDF.read_text().strip())
            import os, signal
            os.kill(pid, signal.SIGTERM)
            _PIDF.unlink()
    except Exception:
        pass


def live_frame_pil():
    """Return the latest silent-capture frame as a PIL Image, or None if the
    daemon isn't streaming a fresh frame yet."""
    try:
        if not _FRAME.exists():
            return None
        if time.time() - _FRAME.stat().st_mtime > _FRESH_S:
            return None
        from PIL import Image
        import numpy as np
        img = Image.open(str(_FRAME)).convert("RGB")
        img.load()
        if float(np.asarray(img).mean()) < 2.0:
            return None
        return img
    except Exception:
        return None
