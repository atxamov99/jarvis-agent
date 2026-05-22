import json
import sys
from pathlib import Path


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


_API_KEY_PATH = _base_dir() / "config" / "api_keys.json"


def _api_key() -> str:
    with open(_API_KEY_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]


def _gemini_translate(text: str, target: str, source: str | None = None) -> str:
    from google import genai
    client = genai.Client(api_key=_api_key())

    src_part = f" from {source}" if source else ""
    prompt = (
        f"You are a professional translator. Translate the text below"
        f"{src_part} into {target}.\n"
        f"Rules:\n"
        f"- Translate EVERYTHING — no untranslated fragments.\n"
        f"- Preserve numbers, names, formatting and meaning.\n"
        f"- Output ONLY the translation, no commentary, no quotes, no labels.\n\n"
        f"Text:\n{text}"
    )

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )
    out = ""
    for part in response.candidates[0].content.parts:
        if hasattr(part, "text") and part.text:
            out += part.text
    out = out.strip().strip('"').strip("'")
    if not out:
        raise ValueError("Empty translation response")
    return out


def translate(
    parameters: dict | None = None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params = parameters or {}
    text   = (params.get("text") or "").strip()
    target = (params.get("target_language") or "uzbek").strip()
    source = (params.get("source_language") or "").strip() or None

    if not text:
        return "Tarjima qilish uchun matn berilmagan."

    if player:
        snippet = text[:60] + ("…" if len(text) > 60 else "")
        player.write_log(f"[Translate→{target}] {snippet}")

    print(f"[Translate] 🌐 → {target} (from {source or 'auto'}): {text[:80]!r}")

    try:
        return _gemini_translate(text, target, source)
    except Exception as e:
        print(f"[Translate] ❌ {e}")
        return f"Tarjima qilishda xato: {e}"
