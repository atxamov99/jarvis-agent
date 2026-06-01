"""dictation.py — Voice dictation: record speech, transcribe, type/copy result.

Inspired by isair/jarvis dictation mode.
User says: "diktovka boshla 10 soniya" → Jarvis records 10s → transcribes → types in active window.
"""
import io
import json
import threading
import time
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd

_SAMPLE_RATE = 16000
_CHANNELS    = 1
_CFG_PATH    = Path(__file__).parent.parent / "config" / "api_keys.json"


def _load_cfg() -> dict:
    try:
        return json.loads(_CFG_PATH.read_text())
    except Exception:
        return {}


def _record(seconds: int, player=None) -> bytes:
    chunks = []

    def cb(indata, frames, time_info, status):
        chunks.append(indata.tobytes())

    with sd.InputStream(samplerate=_SAMPLE_RATE, channels=_CHANNELS,
                        dtype="int16", blocksize=1024, callback=cb):
        for i in range(seconds, 0, -1):
            if player:
                try:
                    player.write_log(f"🎙️ Diktovka: {i}s...")
                except Exception:
                    pass
            time.sleep(1)
    return b"".join(chunks)


def _transcribe(raw_pcm: bytes, language: str) -> str:
    cfg = _load_cfg()

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(_CHANNELS)
        wf.setsampwidth(2)
        wf.setframerate(_SAMPLE_RATE)
        wf.writeframes(raw_pcm)
    buf.seek(0)
    buf.name = "dictation.wav"

    # Try Groq Whisper (free)
    groq_key = cfg.get("groq_api_key", "")
    if groq_key:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=groq_key, base_url="https://api.groq.com/openai/v1")
            tx = client.audio.transcriptions.create(
                model="whisper-large-v3-turbo", file=buf, language=language
            )
            return tx.text.strip()
        except Exception as e:
            print(f"[Dictation] Groq Whisper xato: {e}")
            buf.seek(0)

    # Try OpenAI Whisper
    openai_key = cfg.get("openai_api_key", "")
    if openai_key:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=openai_key)
            tx = client.audio.transcriptions.create(
                model="whisper-1", file=buf, language=language
            )
            return tx.text.strip()
        except Exception as e:
            print(f"[Dictation] OpenAI Whisper xato: {e}")

    return "API kalit topilmadi."


def _type_text(text: str) -> str:
    import shutil, subprocess
    if shutil.which("xdotool"):
        try:
            time.sleep(0.3)  # small focus delay
            subprocess.run(
                ["xdotool", "type", "--clearmodifiers", "--delay=15", "--", text],
                timeout=30,
            )
            return f"✅ Yozildi: {text[:100]}"
        except Exception as e:
            pass

    # Clipboard fallback
    try:
        import pyperclip
        pyperclip.copy(text)
        return f"📋 Buferga saqlandi (Ctrl+V bilan joylashtiring): {text[:100]}"
    except Exception:
        return f"Matn: {text}"


def dictation(parameters=None, response=None, player=None, session_memory=None) -> str:
    params   = parameters or {}
    seconds  = min(max(int(params.get("seconds", 8)), 2), 60)
    language = (params.get("language") or "uz").strip()
    output   = (params.get("output") or "type").lower().strip()  # type | clipboard | text

    if player:
        try:
            player.write_log(f"🎙️ Diktovka boshlandi — {seconds} soniya gapiring...")
        except Exception:
            pass

    raw  = _record(seconds, player)
    text = _transcribe(raw, language)

    if not text or text.startswith("API kalit"):
        return text or "Ovoz aniqlanmadi."

    if output == "clipboard":
        try:
            import pyperclip
            pyperclip.copy(text)
            return f"📋 Buferga saqlandi: {text}"
        except Exception:
            return f"Matn: {text}"

    if output == "text":
        return text

    # Default: type into active window
    return _type_text(text)
