"""screen_vision.py — Give JARVIS eyes on the DESKTOP screen.

Captures the screen (mss) and answers questions about it via Gemini vision.
"What's on my screen?", "read this error", "summarize this page", "is there
anything important?". This is the headline 2026 assistant feature: the model
can see and reason about whatever the user is looking at.
"""
import base64
import io
import json
import urllib.request
from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent
_API  = _BASE / "config" / "api_keys.json"


def _api_key() -> str:
    try:
        return json.loads(_API.read_text(encoding="utf-8")).get("gemini_api_key", "").strip()
    except Exception:
        return ""


def _grab_screen_b64(monitor: int = 0, max_w: int = 1280) -> str | None:
    """Capture the screen (Wayland/X11 aware) and return a base64 JPEG."""
    try:
        from actions.screen_capture import capture_pil
        from PIL import Image
        img = capture_pil()
        if img is None:
            return None
        if img.width > max_w:
            h = int(img.height * max_w / img.width)
            img = img.resize((max_w, h), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=80)
        return base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception as e:
        print(f"[ScreenVision] capture error: {e}")
        return None


def _gemini_vision(image_b64: str, prompt: str, api_key: str, max_tokens: int = 600) -> str:
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"gemini-2.5-flash-lite:generateContent?key={api_key}")
    body = json.dumps({
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": "image/jpeg", "data": image_b64}},
            ]
        }],
        "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.2},
    }).encode()
    req = urllib.request.Request(url, data=body,
                                headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    return data["candidates"][0]["content"]["parts"][0]["text"].strip()


_PROMPTS = {
    "describe":  "Ekranda nima ko'rinayapti? Asosiy oyna, ilova va kontentni o'zbek tilida qisqacha tasvirla.",
    "read":      "Ekrandagi barcha muhim matnni o'qib ber (xato xabarlari, tugmalar, sarlavhalar). O'zbekcha.",
    "summarize": "Ekrandagi kontentni (maqola/sahifa/hujjat) o'zbek tilida qisqacha xulosa qil.",
    "error":     "Ekranda biron xato yoki ogohlantirish bormi? Bo'lsa, nima va qanday tuzatishni o'zbekcha tushuntir.",
    "important": "Ekranda foydalanuvchi e'tibor berishi kerak bo'lgan muhim narsa bormi? O'zbekcha ayt.",
}


def screen_vision(parameters=None, response=None, player=None, session_memory=None) -> str:
    params  = parameters or {}
    action  = (params.get("action") or "describe").lower().strip()
    monitor = int(params.get("monitor", 0))

    api_key = _api_key()
    if not api_key:
        return "Gemini API kaliti topilmadi (config/api_keys.json)."

    if player:
        player.write_log("[ScreenVision] Ekran tahlil qilinmoqda...")

    img = _grab_screen_b64(monitor)
    if img is None:
        return "Ekranni suratga olib bo'lmadi. Wayland sessiyasi — 'sudo apt install gnome-screenshot' kerak bo'lishi mumkin."

    # Free-form question takes priority over preset action
    question = (params.get("question") or params.get("prompt") or params.get("ask") or "").strip()
    prompt = question or _PROMPTS.get(action, _PROMPTS["describe"])

    try:
        answer = _gemini_vision(img, prompt, api_key)
        if player:
            player.write_log(f"[ScreenVision] {answer[:60]}")
        return answer or "Javob bo'sh qaytdi."
    except Exception as e:
        return f"Ekran tahlilida xato: {e}"
