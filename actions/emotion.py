"""emotion.py — Real-time emotion detection from webcam using DeepFace.

Reads from FaceWatcher's shared frame buffer (no camera conflict).
Detects: happy, sad, angry, surprise, fear, disgust, neutral.
"""
import os
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")

import threading
import time

_lock = threading.Lock()
_last_result: dict | None = None
_last_ts: float = 0.0
_TTL = 4.0  # seconds before result is considered stale

_UZ_EMOTIONS = {
    "happy":    "Xursand",
    "sad":      "Xafa",
    "angry":    "G'azablangan",
    "surprise": "Hayron",
    "fear":     "Qo'rqqan",
    "disgust":  "Jirkanch",
    "neutral":  "Neytral",
}


def _analyze_frame(frame):
    """Run DeepFace analysis on a single BGR frame. Returns dict or None."""
    try:
        from deepface import DeepFace
        results = DeepFace.analyze(
            frame,
            actions=["emotion"],
            enforce_detection=False,
            silent=True,
            detector_backend="opencv",
        )
        if isinstance(results, list):
            results = results[0]
        return results
    except Exception:
        return None


def _get_frame():
    """Get latest frame from FaceWatcher shared buffer."""
    try:
        import core.face_verifier as fv
        with fv._frame_lock:
            frame = fv._latest_frame
            if frame is not None:
                return frame.copy()
    except Exception:
        pass
    return None


def emotion(parameters=None, response=None, player=None, session_memory=None) -> str:
    global _last_result, _last_ts
    params = parameters or {}
    action = (params.get("action") or "detect").lower().strip()

    # ── LAST RESULT ────────────────────────────────────────────────────────────
    if action in ("last", "current", "oxirgi"):
        with _lock:
            if _last_result and (time.time() - _last_ts) < _TTL * 2:
                dom = _last_result.get("dominant_emotion", "")
                scores = _last_result.get("emotion", {})
                return _format_result(dom, scores)
        return "Hali hech qanday tahlil bajarilmagan."

    # ── DETECT (fresh) ─────────────────────────────────────────────────────────
    frame = _get_frame()
    if frame is None:
        # Try opening camera directly
        try:
            import cv2
            cap = cv2.VideoCapture(0)
            ret, frame = cap.read()
            cap.release()
            if not ret or frame is None:
                return "Kamera mavjud emas yoki FaceWatcher ishlamayapti."
        except Exception as e:
            return f"Kamera xatosi: {e}"

    if player:
        player.write_log("[Emotion] Tahlil boshlanmoqda...")

    result = _analyze_frame(frame)
    if result is None:
        return "Yuz aniqlanmadi yoki tahlil xatosi yuz berdi."

    with _lock:
        _last_result = result
        _last_ts = time.time()

    dom = result.get("dominant_emotion", "")
    scores = result.get("emotion", {})

    if player:
        player.write_log(f"[Emotion] {dom}")

    return _format_result(dom, scores)


def _format_result(dominant: str, scores: dict) -> str:
    uz_name = _UZ_EMOTIONS.get(dominant.lower(), dominant)
    lines = [f"Hissiyot: **{uz_name}** ({dominant})"]

    if scores:
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:4]
        bars = []
        for em, score in sorted_scores:
            uz = _UZ_EMOTIONS.get(em.lower(), em)
            bar = "█" * int(score / 10) + "░" * (10 - int(score / 10))
            bars.append(f"  {uz:<14} {bar} {score:.1f}%")
        lines.append("\nBatafsil:")
        lines.extend(bars)

    return "\n".join(lines)
