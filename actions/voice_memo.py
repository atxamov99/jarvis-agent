"""voice_memo.py — Record, list, play, and delete voice memos."""
import os
import shutil
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

_MEMO_DIR  = Path.home() / "VoiceMemos"
_SAMPLERATE = 44100
_CHANNELS   = 1

_rec_state: dict = {"recording": False, "frames": [], "thread": None}


def _memo_dir() -> Path:
    _MEMO_DIR.mkdir(exist_ok=True)
    return _MEMO_DIR


def _record_thread(seconds: int):
    frames = []
    chunk  = 1024

    def callback(indata, frame_count, time_info, status):
        frames.append(indata.copy())

    with sd.InputStream(samplerate=_SAMPLERATE, channels=_CHANNELS,
                        dtype="float32", blocksize=chunk, callback=callback):
        deadline = time.time() + seconds
        while _rec_state["recording"] and time.time() < deadline:
            time.sleep(0.05)

    _rec_state["frames"] = frames
    _rec_state["recording"] = False


def voice_memo(parameters=None, response=None, player=None, session_memory=None) -> str:
    params  = parameters or {}
    action  = (params.get("action") or "record").lower().strip()
    seconds = int(params.get("seconds", 30))
    name    = (params.get("name") or "").strip()

    # ── RECORD ────────────────────────────────────────────────────────────────
    if action in ("record", "yoz", "start", "boshlash"):
        if _rec_state["recording"]:
            return "Allaqachon yozilmoqda. Avval 'stop' dang."
        _rec_state.update({"recording": True, "frames": []})
        t = threading.Thread(target=_record_thread, args=(seconds,), daemon=True)
        t.start()
        _rec_state["thread"] = t
        if player: player.write_log(f"[VoiceMemo] Recording {seconds}s")
        return f"Yozish boshlandi ({seconds} soniya). Tugatish uchun 'to'xtat' dang."

    # ── STOP / SAVE ───────────────────────────────────────────────────────────
    if action in ("stop", "to'xtat", "saqlash", "save"):
        if not _rec_state["recording"] and not _rec_state["frames"]:
            return "Yozuv yo'q."
        _rec_state["recording"] = False
        if _rec_state["thread"]:
            _rec_state["thread"].join(timeout=2)

        frames = _rec_state["frames"]
        if not frames:
            return "Yozuv bo'sh (mikrofon ishlamadimi?)."

        ts    = datetime.now().strftime("%Y%m%d_%H%M%S")
        slug  = name.replace(" ", "_") if name else ts
        path  = _memo_dir() / f"{slug}.wav"
        audio = np.concatenate(frames, axis=0)
        sf.write(path, audio, _SAMPLERATE)
        dur   = len(audio) / _SAMPLERATE
        _rec_state["frames"] = []
        if player: player.write_log(f"[VoiceMemo] Saved: {path.name} ({dur:.1f}s)")
        return f"Saqlandi: {path.name} ({dur:.1f} soniya, {path.stat().st_size//1024} KB)"

    # ── LIST ──────────────────────────────────────────────────────────────────
    if action in ("list", "ro'yxat", "hammasi", "ko'rsat"):
        files = sorted(_memo_dir().glob("*.wav"), reverse=True)
        if not files:
            return "Ovoz yozuvlari yo'q."
        lines = []
        for i, f in enumerate(files[:15], 1):
            info  = sf.info(f)
            lines.append(f"{i}. {f.stem} ({info.duration:.0f}s, {f.stat().st_size//1024}KB)")
        return f"Ovoz yozuvlari ({len(files)}):\n" + "\n".join(lines)

    # ── PLAY ──────────────────────────────────────────────────────────────────
    if action in ("play", "ijro", "o'yna", "eshit"):
        query = name.lower() if name else ""
        files = sorted(_memo_dir().glob("*.wav"), reverse=True)
        target = None
        if not query and files:
            target = files[0]
        else:
            for f in files:
                if query in f.stem.lower():
                    target = f
                    break
        if not target:
            return f"Topilmadi: '{name}'"
        if shutil.which("paplay"):
            subprocess.Popen(["paplay", str(target)])
        elif shutil.which("aplay"):
            subprocess.Popen(["aplay", str(target)])
        else:
            data, sr = sf.read(target)
            sd.play(data, sr)
        if player: player.write_log(f"[VoiceMemo] Play: {target.name}")
        return f"Ijro etilmoqda: {target.name}"

    # ── DELETE ────────────────────────────────────────────────────────────────
    if action in ("delete", "o'chir", "remove"):
        if not name:
            return "O'chirish uchun nom ko'rsating."
        files = sorted(_memo_dir().glob("*.wav"), reverse=True)
        target = next((f for f in files if name.lower() in f.stem.lower()), None)
        if not target:
            return f"Topilmadi: '{name}'"
        target.unlink()
        if player: player.write_log(f"[VoiceMemo] Deleted: {target.name}")
        return f"O'chirildi: {target.name}"

    return "Amallar: record | stop | list | play | delete"
