"""webcam_vision.py — Capture webcam frame and describe with Gemini Vision.

Reads from FaceWatcher buffer or opens camera directly.
Sends frame to Gemini for description/analysis.
"""
import base64
import json
import os
import sys
import urllib.request
from pathlib import Path


def _cfg() -> dict:
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
    try:
        return json.loads((base / "config" / "api_keys.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def _get_frame():
    """Get frame from FaceWatcher shared buffer first, else open camera."""
    try:
        import core.face_verifier as fv
        with fv._frame_lock:
            frame = fv._latest_frame
            if frame is not None:
                return frame.copy()
    except Exception:
        pass

    try:
        import cv2
        cap = cv2.VideoCapture(0)
        # Warm up camera (first few frames may be dark)
        for _ in range(5):
            cap.read()
        ret, frame = cap.read()
        cap.release()
        if ret and frame is not None:
            return frame
    except Exception:
        pass
    return None


def _frame_to_b64(frame) -> str:
    import cv2
    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return base64.b64encode(buf.tobytes()).decode("utf-8")


def _gemini_vision(image_b64: str, prompt: str, api_key: str) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent?key={api_key}"
    body = json.dumps({
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": "image/jpeg", "data": image_b64}},
            ]
        }],
        "generationConfig": {"maxOutputTokens": 512},
    }).encode()

    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.loads(r.read())

    return data["candidates"][0]["content"]["parts"][0]["text"].strip()


def webcam_vision(parameters=None, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    prompt = (
        params.get("prompt") or
        params.get("question") or
        params.get("ask") or
        "Kamerada nima ko'rinayapti? Qisqacha va aniq tasvirla."
    ).strip()

    action = (params.get("action") or "describe").lower().strip()

    cfg     = _cfg()
    api_key = cfg.get("gemini_api_key", "").strip()
    if not api_key:
        return "Gemini API key sozlanmagan."

    if player:
        player.write_log("[Vision] Kamera tasviri olinmoqda...")

    frame = _get_frame()
    if frame is None:
        return "Kamera tasviri olinmadi. Kamera ulangan va FaceWatcher ishlamoqdami?"

    # For "save" action — save the frame
    if action == "save":
        try:
            import cv2
            from datetime import datetime
            name = datetime.now().strftime("webcam_%Y%m%d_%H%M%S.jpg")
            path = str(Path.home() / "Pictures" / name)
            cv2.imwrite(path, frame)
            return f"Surat saqlandi: {path}"
        except Exception as e:
            return f"Saqlashda xato: {e}"

    image_b64 = _frame_to_b64(frame)

    # Preset prompts
    if action in ("describe", "tasvirla"):
        prompt = "Bu tasvirda nima ko'rinayapti? Muhim narsalarni sanab o't."
    elif action in ("people", "kishilar"):
        prompt = "Bu tasvirda nechta odam bor? Ularning hissiyotlari va faoliyatini tasvirla."
    elif action in ("read", "o'qi"):
        prompt = "Bu tasvirda yozilgan barcha matnni o'qi va qaytarib ber."
    elif action in ("count", "san"):
        obj = params.get("object") or params.get("nima") or "odam"
        prompt = f"Bu tasvirda nechta '{obj}' bor? Faqat raqamni ayt."
    elif action in ("emotion", "hissiyot"):
        prompt = "Bu tasvirda odamning yuz ifodasi qanday? Hissiyotini aniqla."

    if player:
        player.write_log(f"[Vision] Gemini ga yuborilmoqda: {prompt[:60]}")

    try:
        result = _gemini_vision(image_b64, prompt, api_key)
        if player:
            player.write_log("[Vision] Natija olindi")
        return result
    except Exception as e:
        return f"Gemini vision xatosi: {e}"
