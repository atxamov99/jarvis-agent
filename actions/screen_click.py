"""screen_click.py — Vision-guided computer use: click anything by describing it.

"Click the Login button", "press the red X", "click the search box".
Captures the screen, asks Gemini vision for the element's center coordinates,
then moves and clicks there with xdotool. Works on ANY app, not just browsers.
"""
import base64
import io
import json
import re
import subprocess
import urllib.request
from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent
_API  = _BASE / "config" / "api_keys.json"


def _api_key() -> str:
    try:
        return json.loads(_API.read_text(encoding="utf-8")).get("gemini_api_key", "").strip()
    except Exception:
        return ""


def _grab_monitor(monitor: int = 1):
    """Return (jpeg_b64, geom). Wayland/X11-aware capture; geom in screen pixels."""
    from actions.screen_capture import capture_pil
    img = capture_pil()
    if img is None:
        raise RuntimeError("Ekran surati olinmadi (Wayland — gnome-screenshot kerak).")
    W, H = img.size
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return b64, {"left": 0, "top": 0, "width": W, "height": H}


def _gemini_locate(image_b64: str, target: str, api_key: str) -> dict:
    """Ask Gemini for the element's center as normalized 0-1000 coords. Returns dict."""
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"gemini-2.5-flash-lite:generateContent?key={api_key}")
    prompt = (
        f"You are a screen-grounding model. Find this UI element: \"{target}\".\n"
        "Respond with ONLY a compact JSON object, no markdown. "
        "If found, give the CENTER point normalized to 0-1000 relative to the image "
        "(x = left→right, y = top→bottom): {\"found\":true,\"x\":<int>,\"y\":<int>,\"label\":\"<what you clicked>\"}. "
        "If not visible: {\"found\":false}."
    )
    body = json.dumps({
        "contents": [{"parts": [
            {"text": prompt},
            {"inline_data": {"mime_type": "image/jpeg", "data": image_b64}},
        ]}],
        "generationConfig": {"maxOutputTokens": 120, "temperature": 0.0},
    }).encode()
    req = urllib.request.Request(url, data=body,
                                headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
    m = re.search(r"\{.*\}", text, re.DOTALL)
    return json.loads(m.group(0)) if m else {"found": False}


def screen_click(parameters=None, response=None, player=None, session_memory=None) -> str:
    params  = parameters or {}
    target  = (params.get("target") or params.get("element") or params.get("description") or "").strip()
    button  = (params.get("button") or "left").lower().strip()
    monitor = int(params.get("monitor", 1))
    if not target:
        return "Nimani bosishni ayting (masalan: 'Login tugmasi')."

    api_key = _api_key()
    if not api_key:
        return "Gemini API kaliti topilmadi."

    if player:
        player.write_log(f"[ScreenClick] '{target}' qidirilmoqda...")

    try:
        b64, geom = _grab_monitor(monitor)
    except Exception as e:
        return f"Ekranni olishda xato: {e}"

    try:
        loc = _gemini_locate(b64, target, api_key)
    except Exception as e:
        return f"Element qidirishda xato: {e}"

    if not loc.get("found"):
        return f"'{target}' ekranda topilmadi."

    try:
        nx, ny = float(loc["x"]), float(loc["y"])
    except Exception:
        return f"Koordinata noto'g'ri qaytdi: {loc}"

    abs_x = int(geom["left"] + nx / 1000.0 * geom["width"])
    abs_y = int(geom["top"]  + ny / 1000.0 * geom["height"])

    try:
        import core.input_control as ic
        is_double = button in ("double", "double_left")
        btn = "right" if button == "right" else ("middle" if button == "middle" else "left")
        ic.click(abs_x, abs_y, button=btn, double=is_double)
    except Exception as e:
        return f"Bosishda xato: {e}"

    label = loc.get("label", target)
    hint = ""
    try:
        import core.input_control as ic
        if ic.needs_setup():
            hint = "\n⚠️ " + ic.needs_setup()
    except Exception:
        pass
    return f"✅ Bosildi: '{label}' → ({abs_x}, {abs_y})" + hint
