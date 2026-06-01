import re
from pathlib import Path


def _get_client():
    from actions.openai_client import get_client
    return get_client()


def _extract_pdf_text(path: str, max_chars: int = 15000) -> str:
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            pages = [p.extract_text() or "" for p in pdf.pages]
        return "\n\n".join(pages)[:max_chars]
    except ImportError:
        pass
    try:
        import PyPDF2
        with open(path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            pages = [p.extract_text() or "" for p in reader.pages]
        return "\n\n".join(pages)[:max_chars]
    except Exception as e:
        raise RuntimeError(f"PDF o'qib bo'lmadi: {e}")


def _openai_pdf_summarize(text: str, lang: str = "uz") -> str:
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
                "Quyidagi PDF matnini 5-7 ta qisqa gapda xulosa qiling. "
                "Asosiy fikr va xulosalarni ajratib ko'rsating.\n\n"
                f"{text[:12000]}"
            ),
        }],
    )
    return (resp.choices[0].message.content or "").strip() or "PDF xulosa tayyorlab bo'lmadi."


def pdf_summarizer(parameters=None, player=None, **kwargs) -> str:
    params = parameters or {}
    path   = (params.get("path") or params.get("file") or "").strip()
    lang   = (params.get("language") or "uz").strip().lower()

    if not path:
        return "PDF fayl yo'li ko'rsatilmagan."

    if player: player.write_log(f"[PDF] Reading: {path[:60]}")
    try:
        text = _extract_pdf_text(path)
        if len(text) < 50:
            return "PDF dan matn olib bo'lmadi."
    except Exception as e:
        return str(e)

    if player: player.write_log(f"[PDF] Summarizing {len(text)} chars")
    summary = _openai_pdf_summarize(text, lang)
    return summary
