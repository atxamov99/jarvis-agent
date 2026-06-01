"""ocr.py — Extract text from screen/image via OpenAI Vision."""
import base64
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def _take_screenshot() -> Path | None:
    tmp = Path(tempfile.mktemp(suffix=".png"))
    for tool, args in [
        ("gnome-screenshot", ["-f", str(tmp)]),
        ("scrot",            [str(tmp)]),
        ("import",           ["-window", "root", str(tmp)]),
        ("grim",             [str(tmp)]),
    ]:
        if shutil.which(tool):
            r = subprocess.run([tool] + args, capture_output=True, timeout=10)
            if r.returncode == 0 and tmp.exists():
                return tmp
    return None


def _openai_ocr(image_path: Path, prompt: str) -> str:
    from actions.openai_client import _load_config
    cfg = _load_config()

    with open(image_path, "rb") as f:
        img_bytes = f.read()
    img_b64 = base64.b64encode(img_bytes).decode()

    # OpenAI birlamchi
    openai_key = cfg.get("openai_api_key", "")
    if openai_key:
        from openai import OpenAI
        client = OpenAI(api_key=openai_key)
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
                {"type": "text", "text": prompt},
            ]}],
        )
        text = response.choices[0].message.content or ""
        return text.strip() if text.strip() else "Matn topilmadi."

    # Gemini zaxira
    gemini_key = cfg.get("gemini_api_key", "")
    if gemini_key:
        from google import genai
        from google.genai import types as gtypes
        client = genai.Client(api_key=gemini_key)
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[gtypes.Part.from_bytes(data=img_bytes, mime_type="image/png"), prompt],
        )
        text = response.text or ""
        return text.strip() if text.strip() else "Matn topilmadi."

    return "OCR uchun OpenAI yoki Gemini API kaliti kerak."


def ocr(parameters=None, response=None, player=None, session_memory=None) -> str:
    params         = parameters or {}
    image_path_str = (params.get("image_path") or "").strip()
    mode           = (params.get("mode") or "extract").lower().strip()

    prompts = {
        "extract":   "Extract and return ALL text visible in this image exactly as it appears.",
        "translate": "Extract all text from this image and translate it to Uzbek.",
        "summarize": "Extract the text from this image and provide a brief summary in Uzbek.",
        "describe":  "Describe what you see in this image in Uzbek.",
    }
    prompt = prompts.get(mode, prompts["extract"])

    if image_path_str:
        image_path = Path(os.path.expanduser(image_path_str))
        if not image_path.exists():
            return f"Fayl topilmadi: {image_path}"
    else:
        if player: player.write_log("[OCR] Taking screenshot…")
        image_path = _take_screenshot()
        if not image_path:
            return "Skrinshot olishda xato. gnome-screenshot, scrot, yoki grim o'rnatilgan bo'lsin."

    try:
        result = _openai_ocr(image_path, prompt)
    finally:
        if not image_path_str and image_path and image_path.exists():
            image_path.unlink(missing_ok=True)

    if player: player.write_log(f"[OCR] Done: {len(result)} chars")
    return result
