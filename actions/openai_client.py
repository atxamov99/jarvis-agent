"""Shared OpenAI client — lazy-loaded, cached per process."""
import json
from pathlib import Path
from functools import lru_cache

_CONFIG = Path(__file__).resolve().parent.parent / "config" / "api_keys.json"


@lru_cache(maxsize=1)
def _load_key() -> str | None:
    try:
        with open(_CONFIG, "r", encoding="utf-8") as f:
            return json.load(f).get("openai_api_key") or None
    except Exception:
        return None


def get_client():
    """Return an openai.OpenAI instance or raise if key missing."""
    from openai import OpenAI
    key = _load_key()
    if not key:
        raise RuntimeError("openai_api_key not set in config/api_keys.json")
    return OpenAI(api_key=key)


def available() -> bool:
    return bool(_load_key())
