"""summarizer.py — Summarize web pages or plain text via Gemini."""
import json
import re
import urllib.request
from pathlib import Path


def _load_gemini_key() -> str | None:
    cfg = Path(__file__).parent.parent / "config" / "api_keys.json"
    try:
        return json.loads(cfg.read_text())["gemini_api_key"]
    except Exception:
        return None


def _fetch_text(url: str, max_chars: int = 12000) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read().decode("utf-8", errors="replace")

    # Strip HTML tags
    text = re.sub(r"<style[^>]*>.*?</style>", " ", raw, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]


def _gemini_summarize(content: str, lang: str = "uz") -> str:
    from google import genai
    key = _load_gemini_key()
    if not key:
        return "Gemini API kaliti topilmadi."

    lang_instruction = {
        "uz": "O'zbek tilida xulosa yozing.",
        "ru": "Напишите резюме на русском языке.",
        "en": "Write the summary in English.",
    }.get(lang, "O'zbek tilida xulosa yozing.")

    client = genai.Client(api_key=key)
    prompt = (
        f"{lang_instruction}\n\n"
        "Quyidagi matnni 3-5 ta qisqa gapda xulosa qiling. "
        "Asosiy fikrlarni ajratib ko'rsating.\n\n"
        f"{content[:10000]}"
    )
    resp = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt,
    )
    return (resp.text or "").strip() or "Xulosa tayyorlab bo'lmadi."


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
    return _gemini_summarize(content, lang)
