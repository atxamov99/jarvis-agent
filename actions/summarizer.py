"""summarizer.py — Summarize web pages or plain text via OpenAI."""
import json
import re
import urllib.request
from pathlib import Path


def _get_client():
    from actions.openai_client import get_client
    return get_client()


def _fetch_text(url: str, max_chars: int = 12000) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read().decode("utf-8", errors="replace")

    text = re.sub(r"<style[^>]*>.*?</style>", " ", raw, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]


def _openai_summarize(content: str, lang: str = "uz") -> str:
    lang_instruction = {
        "uz": "O'zbek tilida xulosa yozing.",
        "ru": "Напишите резюме на русском языке.",
        "en": "Write the summary in English.",
    }.get(lang, "O'zbek tilida xulosa yozing.")

    client = _get_client()
    resp = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{
            "role": "user",
            "content": (
                f"{lang_instruction}\n\n"
                "Quyidagi matnni 3-5 ta qisqa gapda xulosa qiling. "
                "Asosiy fikrlarni ajratib ko'rsating.\n\n"
                f"{content[:10000]}"
            ),
        }],
    )
    return (resp.choices[0].message.content or "").strip() or "Xulosa tayyorlab bo'lmadi."


def summarizer(parameters=None, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    url    = (params.get("url") or "").strip()
    text   = (params.get("text") or "").strip()
    lang   = (params.get("language") or "uz").strip().lower()

    if not url and not text:
        return "URL yoki matn ko'rsatilmagan."

    if url:
        if player: player.write_log(f"[Summarizer] Fetching: {url[:60]}")
        try:
            content = _fetch_text(url)
            if len(content) < 100:
                return "Sahifadan matn olib bo'lmadi (JavaScript-only yoki kirish taqiqlangan)."
        except Exception as e:
            return f"URL yuklab bo'lmadi: {e}"
    else:
        content = text

    if player: player.write_log(f"[Summarizer] Summarizing {len(content)} chars")
    return _openai_summarize(content, lang)
