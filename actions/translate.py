import sys
from pathlib import Path


def _openai_translate(text: str, target: str, source: str | None = None) -> str:
    from actions.openai_client import get_client
    client = get_client()

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

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
    )
    out = (response.choices[0].message.content or "").strip().strip('"').strip("'")
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
        return _openai_translate(text, target, source)
    except Exception as e:
        print(f"[Translate] ❌ {e}")
        return f"Tarjima qilishda xato: {e}"
