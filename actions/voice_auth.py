"""voice_auth.py — Speaker enrollment and verification management."""
import threading
import time

import numpy as np
import sounddevice as sd

from core.speaker_verifier import (
    enroll as _sv_enroll,
    reset as _sv_reset,
    set_threshold as _sv_set_threshold,
    get_info as _sv_info,
    is_enabled as _sv_enabled,
    verify as _sv_verify,
)

SAMPLE_RATE = 16000
_enroll_state = {"recording": False, "buf": [], "done": threading.Event()}


def _record_enrollment(seconds: int, player) -> bytes:
    """Record `seconds` seconds from mic and return raw PCM bytes."""
    buf = []
    done = threading.Event()

    def _cb(indata, frames, time_info, status):
        buf.append(indata.tobytes())

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                        blocksize=1024, callback=_cb):
        if player:
            player.write_log(f"[VoiceAuth] Recording {seconds}s enrollment...")
        for remaining in range(seconds, 0, -1):
            if player:
                player.write_log(f"[VoiceAuth] {remaining}s qoldi...")
            time.sleep(1)

    return b"".join(buf)


def voice_auth(parameters=None, response=None, player=None, session_memory=None) -> str:
    params   = parameters or {}
    action   = (params.get("action") or "status").lower().strip()
    seconds  = int(params.get("seconds", 15))
    threshold = params.get("threshold")

    # ── STATUS ────────────────────────────────────────────────────────────────
    if action in ("status", "holat"):
        return _sv_info()

    # ── ENROLL ────────────────────────────────────────────────────────────────
    if action in ("enroll", "o'rgat", "esla", "yodla"):
        if seconds < 5:
            seconds = 5
        if seconds > 60:
            seconds = 60

        if player:
            player.write_log(f"[VoiceAuth] Starting {seconds}s enrollment")

        result_holder = [None]

        def _do_enroll():
            try:
                raw_pcm = _record_enrollment(seconds, player)
                result_holder[0] = _sv_enroll(raw_pcm, SAMPLE_RATE)
            except Exception as e:
                result_holder[0] = f"Xato: {e}"

        t = threading.Thread(target=_do_enroll, daemon=True)
        t.start()
        t.join(timeout=seconds + 10)

        return result_holder[0] or "Enrollment tugamadi."

    # ── TEST ──────────────────────────────────────────────────────────────────
    if action in ("test", "tekshir"):
        if not _sv_enabled():
            return "Avval ovozingizni o'rgating ('voice_auth enroll')."

        dur = min(int(params.get("seconds", 5)), 10)
        if player: player.write_log(f"[VoiceAuth] Test recording {dur}s...")
        raw = _record_enrollment(dur, player)
        match = _sv_verify(raw, SAMPLE_RATE)
        return (
            "✅ Ovoz mos keldi — bu siz!" if match
            else "❌ Ovoz mos kelmadi — bu boshqa kishi."
        )

    # ── RESET ─────────────────────────────────────────────────────────────────
    if action in ("reset", "o'chir", "delete"):
        _sv_reset()
        return "✅ Ovoz profili o'chirildi. Endi barcha ovozni qabul qiladi."

    # ── THRESHOLD ─────────────────────────────────────────────────────────────
    if action in ("threshold", "sezgirlik") and threshold is not None:
        _sv_set_threshold(float(threshold))
        return f"✅ Threshold {float(threshold):.1f} ga o'rnatildi."

    return "Amallar: enroll | test | reset | status | threshold"
