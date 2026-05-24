"""screen_recorder.py — Record the screen to MP4 via ffmpeg."""
import os
import shutil
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

_REC_DIR = Path.home() / "Videos" / "Recordings"
_state: dict = {"proc": None, "path": None, "start": 0.0}


def _rec_dir() -> Path:
    _REC_DIR.mkdir(parents=True, exist_ok=True)
    return _REC_DIR


def _display() -> str:
    return os.environ.get("DISPLAY", ":0")


def _resolution() -> str:
    try:
        r = subprocess.run(
            ["xdpyinfo", "-display", _display()],
            capture_output=True, text=True, timeout=3,
        )
        for line in r.stdout.splitlines():
            if "dimensions:" in line:
                return line.split()[1]
    except Exception:
        pass
    return "1920x1080"


def screen_recorder(parameters=None, response=None, player=None, session_memory=None) -> str:
    if not shutil.which("ffmpeg"):
        return "ffmpeg topilmadi. `sudo apt install ffmpeg` qiling."

    params = parameters or {}
    action = (params.get("action") or "start").lower().strip()
    fps    = int(params.get("fps", 30))
    audio  = bool(params.get("audio", False))

    # ── START ─────────────────────────────────────────────────────────────────
    if action in ("start", "boshlash", "yoz"):
        if _state["proc"] and _state["proc"].poll() is None:
            dur = int(time.time() - _state["start"])
            return f"Allaqachon yozilmoqda ({dur}s). To'xtatish uchun 'stop' dang."

        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = _rec_dir() / f"screen_{ts}.mp4"
        res  = _resolution()

        cmd = [
            "ffmpeg", "-y",
            "-f", "x11grab",
            "-framerate", str(fps),
            "-video_size", res,
            "-i", f"{_display()}.0",
        ]
        if audio and shutil.which("pactl"):
            cmd += ["-f", "pulse", "-i", "default"]
        cmd += [
            "-c:v", "libx264", "-preset", "ultrafast",
            "-crf", "28",
            str(path),
        ]

        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        _state.update({"proc": proc, "path": path, "start": time.time()})
        if player: player.write_log(f"[ScreenRec] Started: {path.name} ({res}@{fps}fps)")
        return f"🔴 Ekran yozish boshlandi ({res} @ {fps}fps).\nFayl: {path}\nTo'xtatish: 'to'xtat'"

    # ── STOP ──────────────────────────────────────────────────────────────────
    if action in ("stop", "to'xtat", "tugatish", "save"):
        if not _state["proc"] or _state["proc"].poll() is not None:
            return "Faol yozuv yo'q."
        try:
            _state["proc"].stdin.write(b"q")
            _state["proc"].stdin.flush()
        except Exception:
            _state["proc"].terminate()

        _state["proc"].wait(timeout=10)
        path = _state["path"]
        dur  = int(time.time() - _state["start"])
        _state.update({"proc": None, "path": None, "start": 0.0})

        if path and path.exists():
            size_mb = path.stat().st_size / 1_000_000
            if player: player.write_log(f"[ScreenRec] Saved: {path.name} ({dur}s {size_mb:.1f}MB)")
            return f"✅ Saqlandi: {path}\n({dur} soniya, {size_mb:.1f} MB)"
        return "Yozuv saqlashda xato."

    # ── STATUS ────────────────────────────────────────────────────────────────
    if action in ("status", "holat"):
        if not _state["proc"] or _state["proc"].poll() is not None:
            return "Ekran yozilmayapti."
        dur = int(time.time() - _state["start"])
        return f"🔴 Yozilmoqda: {dur}s | {_state['path'].name}"

    # ── LIST ──────────────────────────────────────────────────────────────────
    if action in ("list", "ro'yxat"):
        files = sorted(_rec_dir().glob("*.mp4"), reverse=True)
        if not files:
            return "Yozuvlar yo'q."
        lines = []
        for f in files[:10]:
            lines.append(f"• {f.name}  ({f.stat().st_size//1_000_000} MB)")
        return f"Ekran yozuvlari ({len(files)}):\n" + "\n".join(lines)

    return "Amallar: start | stop | status | list"
