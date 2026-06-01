"""Shared AI client — Groq (free) primary, OpenAI fallback if available."""
import json
from pathlib import Path

_CONFIG = Path(__file__).resolve().parent.parent / "config" / "api_keys.json"

_GROQ_BASE_URL = "https://api.groq.com/openai/v1"
_GROQ_MODEL    = "llama-3.3-70b-versatile"
_OPENAI_MODEL  = "llama-3.3-70b-versatile"


def _load_config() -> dict:
    try:
        with open(_CONFIG, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def get_client():
    """Return an OpenAI-compatible client. Groq preferred (free), OpenAI fallback."""
    from openai import OpenAI
    cfg = _load_config()

    groq_key = cfg.get("groq_api_key") or ""
    if groq_key:
        return OpenAI(api_key=groq_key, base_url=_GROQ_BASE_URL)

    openai_key = cfg.get("openai_api_key") or ""
    if openai_key:
        return OpenAI(api_key=openai_key)

    raise RuntimeError("Hech qanday API kalit topilmadi (groq_api_key yoki openai_api_key).")


def get_model(fast: bool = False) -> str:
    """Return the best available model name."""
    cfg = _load_config()
    if cfg.get("groq_api_key"):
        return _GROQ_MODEL
    return _GROQ_MODEL if fast else _OPENAI_MODEL


def available() -> bool:
    cfg = _load_config()
    return bool(cfg.get("groq_api_key") or cfg.get("openai_api_key"))
