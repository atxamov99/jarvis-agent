"""gesture_control.py — Hand gesture control via MediaPipe.

Gestures:
  - Pinch (thumb + index) distance → volume control
  - Fist → mute/unmute
  - Open palm → stop gesture listening
  - V-sign (peace) → screenshot
  - Thumbs up → confirm / OK
  - Thumbs down → cancel
"""
import os
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")

import math
import subprocess
import threading
import time

_gesture_thread: threading.Thread | None = None
_stop_event = threading.Event()
_lock = threading.Lock()
_current_gesture = "none"


def _distance(p1, p2) -> float:
    return math.hypot(p1.x - p2.x, p1.y - p2.y)


def _fingers_up(hand_landmarks) -> list[bool]:
    lm = hand_landmarks.landmark
    tips   = [4, 8, 12, 16, 20]
    joints = [3, 6, 10, 14, 18]
    up = []
    # Thumb: compare x (horizontal)
    up.append(lm[tips[0]].x < lm[joints[0]].x)
    # Other fingers: compare y (vertical)
    for i in range(1, 5):
        up.append(lm[tips[i]].y < lm[joints[i]].y)
    return up


def _classify_gesture(hand_landmarks, image_width: int) -> str:
    lm = hand_landmarks.landmark
    up = _fingers_up(hand_landmarks)

    # Pinch (thumb + index close together)
    pinch_dist = _distance(lm[4], lm[8])
    if pinch_dist < 0.05:
        return "pinch"

    thumb, index, middle, ring, pinky = up

    if all(up):
        return "open_palm"
    if not any(up):
        return "fist"
    if thumb and not index and not middle and not ring and not pinky:
        return "thumbs_up"
    if not thumb and not index and not middle and not ring and not pinky:
        return "thumbs_down"
    if not thumb and index and middle and not ring and not pinky:
        return "v_sign"
    if not thumb and index and not middle and not ring and not pinky:
        return "point"

    return "unknown"


def _set_volume(level: int):
    try:
        subprocess.run(
            ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{max(0, min(100, level))}%"],
            capture_output=True, timeout=2
        )
    except Exception:
        pass


def _get_volume() -> int:
    try:
        r = subprocess.run(
            ["pactl", "get-sink-volume", "@DEFAULT_SINK@"],
            capture_output=True, text=True, timeout=2
        )
        import re
        m = re.search(r'(\d+)%', r.stdout)
        return int(m.group(1)) if m else 50
    except Exception:
        return 50


def _gesture_loop(duration: float, player, sensitivity: float):
    global _current_gesture
    try:
        import cv2
        import mediapipe as mp
    except ImportError:
        if player:
            player.write_log("[Gesture] mediapipe yoki cv2 yo'q")
        return

    mp_hands = mp.solutions.hands
    hands = mp_hands.Hands(
        max_num_hands=1,
        min_detection_confidence=0.7,
        min_tracking_confidence=0.5,
        model_complexity=0,
    )

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        if player:
            player.write_log("[Gesture] Kamera ochilmadi")
        return

    start     = time.time()
    last_vol  = _get_volume()
    last_lm4y = None  # for volume pinch tracking

    try:
        while not _stop_event.is_set() and (time.time() - start) < duration:
            ret, frame = cap.read()
            if not ret:
                break

            h, w = frame.shape[:2]
            rgb  = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            res  = hands.process(rgb)

            if res.multi_hand_landmarks:
                hl = res.multi_hand_landmarks[0]
                gesture = _classify_gesture(hl, w)

                with _lock:
                    _current_gesture = gesture

                lm = hl.landmark

                # Volume control via pinch + vertical movement
                if gesture == "pinch":
                    y4 = lm[4].y
                    if last_lm4y is not None:
                        delta = (last_lm4y - y4) * 200 * sensitivity
                        last_vol = max(0, min(100, last_vol + int(delta)))
                        _set_volume(last_vol)
                    last_lm4y = y4
                else:
                    last_lm4y = None

                # Fist → mute
                if gesture == "fist":
                    _set_volume(0)
                    if player:
                        player.write_log("[Gesture] Fist — muted")
                    time.sleep(1.5)

                # V-sign → screenshot
                if gesture == "v_sign":
                    try:
                        import subprocess as sp
                        sp.run(["scrot", "-d", "1"], check=False, timeout=5)
                        if player:
                            player.write_log("[Gesture] V-sign — screenshot olindi")
                    except Exception:
                        pass
                    time.sleep(2.0)

                # Open palm → stop
                if gesture == "open_palm":
                    if player:
                        player.write_log("[Gesture] Open palm — gestlar to'xtatildi")
                    break

            time.sleep(0.05)

    finally:
        cap.release()
        hands.close()
        with _lock:
            _current_gesture = "none"
        if player:
            player.write_log("[Gesture] Gest boshqaruvi tugatildi")


def gesture_control(parameters=None, response=None, player=None, session_memory=None) -> str:
    global _gesture_thread
    params   = parameters or {}
    action   = (params.get("action") or "start").lower().strip()
    duration = float(params.get("duration") or params.get("seconds") or 30)
    sensitivity = float(params.get("sensitivity") or 1.0)

    # ── STATUS ─────────────────────────────────────────────────────────────────
    if action in ("status", "holat"):
        with _lock:
            g = _current_gesture
        active = _gesture_thread and _gesture_thread.is_alive()
        if active:
            return f"Gest boshqaruvi faol. Joriy gest: {g}"
        return "Gest boshqaruvi faol emas."

    # ── STOP ───────────────────────────────────────────────────────────────────
    if action in ("stop", "off", "toqtat"):
        _stop_event.set()
        if _gesture_thread and _gesture_thread.is_alive():
            _gesture_thread.join(timeout=3)
        _stop_event.clear()
        return "Gest boshqaruvi to'xtatildi."

    # ── START ──────────────────────────────────────────────────────────────────
    if _gesture_thread and _gesture_thread.is_alive():
        return "Gest boshqaruvi allaqachon faol. Avval 'stop' buyrug'ini bering."

    _stop_event.clear()
    _gesture_thread = threading.Thread(
        target=_gesture_loop,
        args=(duration, player, sensitivity),
        daemon=True
    )
    _gesture_thread.start()

    if player:
        player.write_log(f"[Gesture] {duration:.0f}s davomida gest boshqaruvi yoqildi")

    return (
        f"Gest boshqaruvi yoqildi ({duration:.0f}s).\n"
        "Gestlar:\n"
        "  Qo'l yumgan (Fist) → Tovush o'chadi (mute)\n"
        "  Qo'l ochiq (Open palm) → To'xtash\n"
        "  Qisish (Pinch) + yuqori/pastga → Tovush balandligi\n"
        "  V-belgi → Screenshot\n"
        "  Ko'rsatgich barmog'i → Ko'rsatish"
    )
