"""stt_context.py — Personalized STT vocabulary + correction.

Speech-to-text mishears NAMES the most (apps, contacts, projects) and Uzbek
command words. This module builds a vocabulary from what the user actually has
on their machine and uses it two ways:

  • Whisper bias  — feed the vocabulary as the Whisper `prompt` (free, no latency)
  • System hint   — tell the LLM the user's apps/contacts so it resolves a
                    near-miss transcript to the intended item (helps Gemini Live too)
  • correct()     — optional fast LLM pass that fixes an obvious mishearing

Everything is fail-open: on any error the original text is used unchanged.
"""
import json
import sqlite3
import urllib.request
from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent
_API  = _BASE / "config" / "api_keys.json"
_MODEL = "gemini-2.5-flash-lite"

_STATIC_CMDS = (
    "Jarvis, yoq, o'chir, och, yop, boshlash, to'xtat, ko'rsat, qidir, yukla, "
    "saqla, holat, tekshir, qo'sh, o'zgartir, vazifa, signal, eslatma, taymer, "
    "ob-havo, tarjima, hisob, parol, ovoz oshir, ovoz kamaytir, yorqinlik, "
    "screenshot, ekran, fayl, papka, ish stoli, yuklamalar, hujjatlar, "
    "dollar, so'm, rubl, evro, YouTube, GitHub, Google, brifing, tadqiqot"
)


def _api_key() -> str:
    try:
        return json.loads(_API.read_text(encoding="utf-8")).get("gemini_api_key", "").strip()
    except Exception:
        return ""


def _app_names(limit: int = 45) -> list:
    try:
        from actions.open_app import _APP_ALIASES
        names = [k for k in _APP_ALIASES.keys() if " " not in k or len(k) < 16]
        return names[:limit]
    except Exception:
        return []


def _contacts(limit: int = 30) -> list:
    try:
        db = _BASE / "data" / "contacts.db"
        if not db.exists():
            return []
        c = sqlite3.connect(str(db))
        rows = c.execute("SELECT name FROM contacts").fetchall()
        c.close()
        return [r[0] for r in rows][:limit]
    except Exception:
        return []


def _projects(limit: int = 20) -> list:
    """Top-level folders on the desktop = likely project names the user says."""
    try:
        import os
        xdg = os.environ.get("XDG_DESKTOP_DIR", "").strip()
        desk = Path(xdg) if xdg else (Path.home() / "Рабочий стол")
        if not desk.exists():
            desk = Path.home() / "Desktop"
        if not desk.exists():
            return []
        skip = {"__pycache__", "venv", "node_modules"}
        out = [p.name for p in desk.iterdir()
               if p.is_dir() and not p.name.startswith(".") and p.name not in skip]
        return out[:limit]
    except Exception:
        return []


def _memory_terms(limit: int = 25) -> list:
    try:
        from memory.memory_manager import load_memory
        mem = load_memory()
        terms = []
        for cat, items in (mem or {}).items():
            if isinstance(items, dict):
                terms.extend(list(items.keys()))
        return terms[:limit]
    except Exception:
        return []


import time as _time
_vocab_cache = {"data": None, "ts": 0.0}
_VOCAB_TTL = 60.0  # rebuild at most once a minute (apps/contacts rarely change)

def build_vocab() -> dict:
    now = _time.time()
    if _vocab_cache["data"] is not None and now - _vocab_cache["ts"] < _VOCAB_TTL:
        return _vocab_cache["data"]
    data = {
        "apps":     _app_names(),
        "contacts": _contacts(),
        "projects": _projects(),
        "memory":   _memory_terms(),
    }
    _vocab_cache["data"] = data
    _vocab_cache["ts"] = now
    return data


def whisper_prompt() -> str:
    """Vocabulary string for Whisper's `prompt` bias param."""
    v = build_vocab()
    words = []
    words += v["apps"]
    words += v["contacts"]
    words += v["projects"]
    extra = ", ".join(words)
    return (_STATIC_CMDS + (", " + extra if extra else ""))[:880]


def system_vocab_block() -> str:
    """Instructive block injected into the LLM system prompt (all backends)."""
    v = build_vocab()
    lines = []
    if v["apps"]:
        lines.append("Apps: " + ", ".join(v["apps"][:30]))
    if v["contacts"]:
        lines.append("Contacts: " + ", ".join(v["contacts"]))
    if v["projects"]:
        lines.append("Projects/folders: " + ", ".join(v["projects"]))
    if v["memory"]:
        lines.append("Known terms: " + ", ".join(v["memory"][:20]))
    if not lines:
        return ""
    return (
        "\n[USER VOCABULARY — speech recognition aid]\n"
        "These are the names the user actually uses. If a voice transcript is a "
        "near-miss of one of these (a misheard app/contact/project name), interpret "
        "it as the closest matching item below — do NOT act on the garbled word.\n"
        + "\n".join(lines) + "\n"
    )


def correct(raw_text: str) -> str:
    """Fast LLM pass that fixes an obvious STT mishearing. Fail-open: returns the
    original text on any error, empty input, or missing key."""
    text = (raw_text or "").strip()
    if len(text) < 3:
        return text
    # Speed: skip the LLM pass for short commands that are already clean
    # (1-2 words and every word is short/known) — most quick commands.
    words = text.split()
    if len(words) <= 2 and all(len(w) <= 12 for w in words):
        v0 = build_vocab()
        known = {w.lower() for grp in v0.values() for item in grp for w in str(item).split()}
        known |= {w.lower().strip(",.") for w in _STATIC_CMDS.replace(",", " ").split()}
        if all(w.lower().strip(",.?!") in known for w in words):
            return text
    api_key = _api_key()
    if not api_key:
        return text
    v = build_vocab()
    vocab = ", ".join(v["apps"][:30] + v["contacts"] + v["projects"])
    try:
        prompt = (
            "Sen o'zbekcha ovozli buyruq uchun STT (nutqdan-matn) xatolarini "
            "tuzatuvchisan. Quyidagi xom transkriptni FAQAT tuzatib qaytar "
            "(izohsiz, qo'shimchasiz). Noto'g'ri eshitilgan ilova/kontakt/loyiha "
            "nomini eng yaqin tanish nomga moslab to'g'rila. Agar matn allaqachon "
            "to'g'ri bo'lsa, o'zgartirmasdan qaytar.\n"
            f"Tanish nomlar: {vocab}\n\n"
            f"Xom transkript: {text}\n\nTuzatilgan:"
        )
        import core.gemini_rest as _gr
        fixed = _gr.generate_text(prompt, max_tokens=60, temperature=0.0, timeout=8).strip().strip('"')
        # Sanity: keep correction only if it's a plausible same-length-ish command
        if fixed and len(fixed) <= len(text) * 2 + 20:
            return fixed
        return text
    except Exception as e:
        print(f"[STTCorrect] skip: {e}")
        return text
