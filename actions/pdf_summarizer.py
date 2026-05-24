"""pdf_summarizer.py — Extract text from PDF and summarize via Gemini."""
import json
import os
from pathlib import Path


def _load_gemini_key() -> str | None:
    cfg = Path(__file__).parent.parent / "config" / "api_keys.json"
    try:
        return json.loads(cfg.read_text())["gemini_api_key"]
    except Exception:
        return None


def _extract_text_pypdf(pdf_path: Path, max_pages: int = 20) -> str:
    try:
        import pypdf
        reader = pypdf.PdfReader(str(pdf_path))
        pages  = reader.pages[:max_pages]
        return "\n".join(p.extract_text() or "" for p in pages)
    except ImportError:
        pass
    try:
        import pdfplumber
        with pdfplumber.open(str(pdf_path)) as pdf:
            return "\n".join(
                (p.extract_text() or "") for p in pdf.pages[:max_pages]
            )
    except ImportError:
        return ""


def _gemini_pdf_summarize(text: str, lang: str = "uz") -> str:
    from google import genai

    key = _load_gemini_key()
    if not key:
        return "Gemini API kaliti topilmadi."

    lang_map = {"uz": "O'zbek", "ru": "Ruscha", "en": "English"}
    lang_label = lang_map.get(lang, "O'zbek")

    client = genai.Client(api_key=key)
    prompt = (
        f"{lang_label} tilida javob bering.\n\n"
        "Quyidagi PDF matnini qisqacha xulosa qiling (5-7 ta asosiy fikr, "
        "har biri alohida qatorda):\n\n"
        f"{text[:12000]}"
    )
    resp = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
    return (resp.text or "").strip() or "Xulosa tayyorlab bo'lmadi."


def pdf_summarizer(parameters=None, response=None, player=None, session_memory=None) -> str:
    params    = parameters or {}
    path_str  = (params.get("path") or "").strip()
    lang      = (params.get("language") or "uz").strip().lower()
    max_pages = int(params.get("max_pages", 20))

    if not path_str:
        return "PDF fayl yo'li ko'rsatilmagan (path parametri)."

    pdf_path = Path(os.path.expanduser(path_str))
    if not pdf_path.exists():
        return f"Fayl topilmadi: {pdf_path}"
    if pdf_path.suffix.lower() != ".pdf":
        return f"Faqat PDF fayllar qo'llab-quvvatlanadi: {pdf_path.name}"

    if player: player.write_log(f"[PDF] Extracting: {pdf_path.name}")

    text = _extract_text_pypdf(pdf_path, max_pages)
    if not text or len(text.strip()) < 50:
        return (
            "PDFdan matn ajratib bo'lmadi (skanerlangan yoki rasmlidan iborat bo'lishi mumkin). "
            "pypdf yoki pdfplumber o'rnatilganini tekshiring."
        )

    size_kb = pdf_path.stat().st_size // 1024
    if player: player.write_log(f"[PDF] {len(text)} chars, summarizing…")

    summary = _gemini_pdf_summarize(text, lang)
    return f"PDF: {pdf_path.name} ({size_kb} KB, {max_pages} sahifagacha)\n\n{summary}"
