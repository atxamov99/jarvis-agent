"""face_verifier.py — Face recognition + lip-movement speaking detection.

Uses ONLY OpenCV (already installed) — no dlib, no face_recognition, no mediapipe.

Features:
  1. Face recognition via LBPH (cv2.face.LBPHFaceRecognizer) — built into OpenCV.
  2. Lip movement VAD — detects speaking by measuring frame diff in the mouth ROI.
  3. Face watcher thread:
       • Owner visible + lips moving  → UNMUTE Jarvis (start listening)
       • Owner visible, lips still    → keep current state (stay listening)
       • Face disappears / unknown    → MUTE Jarvis (ignore commands)
"""

import os
import threading
import time
from pathlib import Path

import cv2
import numpy as np

_PROFILE_DIR    = Path.home() / ".config" / "jarvis"
_FACE_MODEL     = _PROFILE_DIR / "face_lbph.yml"   # OpenCV LBPH model
_CASCADE_FACE   = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
_CASCADE_SMILE  = cv2.data.haarcascades + "haarcascade_smile.xml"

_LBPH_THRESHOLD  = 80.0   # LBPH confidence < this → owner (lower = stricter)
_LIP_THRESHOLD   = 8.0    # mean pixel diff in mouth ROI → speaking
_FACE_SIZE       = (100, 100)  # resize face ROI before training/predict
_ENROLL_FRAMES   = 60     # frames to capture during enrollment (~3-4 seconds)
_WATCH_INTERVAL  = 0.08   # seconds between watcher frames (~12fps)
_NO_FACE_GRACE   = 25     # consecutive no-face frames before muting (~2s)

_face_cascade  = cv2.CascadeClassifier(_CASCADE_FACE)
_smile_cascade = cv2.CascadeClassifier(_CASCADE_SMILE)

_state = {
    "recognizer": None,
    "enabled":    False,
    "speaking":   False,   # True when lips are moving
    "owner_seen": False,   # True when owner's face is in frame
    "threshold":  _LBPH_THRESHOLD,
}
_lock = threading.Lock()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _detect_face(gray: np.ndarray):
    """Return list of (x,y,w,h) face bounding boxes."""
    return _face_cascade.detectMultiScale(
        gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60)
    )

def _face_roi(gray: np.ndarray, x, y, w, h) -> np.ndarray:
    """Crop and resize face ROI for LBPH."""
    roi = gray[y:y+h, x:x+w]
    return cv2.resize(roi, _FACE_SIZE)

def _mouth_roi(gray: np.ndarray, x, y, w, h) -> np.ndarray:
    """Crop the lower 40% of face = mouth/lip region."""
    y_start = y + int(h * 0.60)
    return gray[y_start:y+h, x:x+w]

def _open_cam(index: int = 0):
    cap = cv2.VideoCapture(index)
    if not cap.isOpened():
        raise RuntimeError(f"Kamera ochilmadi (index={index}).")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 30)
    return cap


# ── Persistence ───────────────────────────────────────────────────────────────

def load_profile():
    if not _FACE_MODEL.exists():
        return
    try:
        rec = cv2.face.LBPHFaceRecognizer_create()
        rec.read(str(_FACE_MODEL))
        with _lock:
            _state["recognizer"] = rec
            _state["enabled"]    = True
        print("[FaceVerifier] LBPH profile loaded.")
    except Exception as e:
        print(f"[FaceVerifier] Load error: {e}")


# ── Public API ────────────────────────────────────────────────────────────────

def is_enabled() -> bool:
    return _state["enabled"] and _state["recognizer"] is not None

def is_speaking() -> bool:
    return _state["speaking"]

def is_owner_seen() -> bool:
    return _state["owner_seen"]


def enroll(seconds: int = 5, cam_index: int = 0, player=None) -> str:
    """
    Record `seconds` seconds from webcam, collect face ROIs, train LBPH.
    Shows live preview window during enrollment.
    """
    if player: player.write_log(f"[FaceVerifier] Enrolling {seconds}s...")

    try:
        cap = _open_cam(cam_index)
    except RuntimeError as e:
        return str(e)

    face_images = []
    end_time    = time.time() + seconds

    while time.time() < end_time:
        ret, frame = cap.read()
        if not ret:
            break
        gray   = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray   = cv2.equalizeHist(gray)
        faces  = _detect_face(gray)

        for (x, y, w, h) in faces:
            roi = _face_roi(gray, x, y, w, h)
            face_images.append(roi)

            # Live preview
            cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
            remaining = max(0, int(end_time - time.time()))
            cv2.putText(frame, f"Yuzingizni ko'rsating: {remaining}s",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            cv2.putText(frame, f"Kadrlar: {len(face_images)}",
                        (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)

        cv2.imshow("JARVIS — Yuz ro'yxatga olish", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

    if len(face_images) < 10:
        return f"Yuz topilmadi yoki kam ({len(face_images)} kadr). Yaxshi yorug'likda qayta urining."

    labels = np.zeros(len(face_images), dtype=np.int32)  # owner = label 0
    rec    = cv2.face.LBPHFaceRecognizer_create(
        radius=1, neighbors=8, grid_x=8, grid_y=8, threshold=_LBPH_THRESHOLD
    )
    rec.train(face_images, labels)

    _PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    rec.save(str(_FACE_MODEL))
    os.chmod(_FACE_MODEL, 0o600)

    with _lock:
        _state["recognizer"] = rec
        _state["enabled"]    = True

    if player: player.write_log(f"[FaceVerifier] Enrolled {len(face_images)} frames.")
    return f"✅ Yuz profili saqlandi! ({len(face_images)} ta kadr)"


def verify_frame(gray: np.ndarray, faces) -> bool:
    """Check if any detected face matches enrolled profile."""
    if not is_enabled() or len(faces) == 0:
        return False
    with _lock:
        rec = _state["recognizer"]
        thr = _state["threshold"]
    for (x, y, w, h) in faces:
        roi = _face_roi(gray, x, y, w, h)
        try:
            label, confidence = rec.predict(roi)
            if label == 0 and confidence < thr:
                return True
        except Exception:
            pass
    return False


def reset():
    with _lock:
        _state["recognizer"] = None
        _state["enabled"]    = False
        _state["speaking"]   = False
        _state["owner_seen"] = False
    if _FACE_MODEL.exists():
        _FACE_MODEL.unlink()
    print("[FaceVerifier] Profile reset.")


def set_threshold(t: float):
    with _lock:
        _state["threshold"] = float(t)


def get_info() -> str:
    if not is_enabled():
        return "Yuz profili yo'q. 'yuzimni esla' deng."
    with _lock:
        thr   = _state["threshold"]
        own   = _state["owner_seen"]
        spk   = _state["speaking"]
    return (
        f"Yuz profili: ✅ Faol | threshold={thr:.0f}\n"
        f"Holatda: {'Ko\'rinyapti' if own else 'Ko\'rinmaydi'} | "
        f"{'Gapiryapti' if spk else 'Jim'}"
    )


# ── Face Watcher (main real-time loop) ───────────────────────────────────────

def start_face_watcher(ui, cam_index: int = 0):
    """
    Daemon thread that reads webcam frames continuously.

    Logic:
    - Detects face each frame (Haar cascade, fast).
    - If face found: runs LBPH verification (owner or not).
    - Tracks lip motion via frame difference on mouth ROI.
    - Owner present + lips moving  → UNMUTE (JARVIS listens).
    - Owner present, lips still    → keep listening (mic stays open).
    - No face / unknown face       → MUTE after grace period.
    """

    def _loop():
        try:
            cap = _open_cam(cam_index)
        except RuntimeError as e:
            print(f"[FaceWatcher] Cannot open camera: {e}")
            return

        no_face_count  = 0
        prev_mouth_roi = None
        lip_motion_buf = []   # rolling buffer of recent motion values
        LIP_BUF_SIZE   = 6   # smooth over N frames

        print("[FaceWatcher] Started.")

        while True:
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.2)
                continue

            gray  = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray  = cv2.equalizeHist(gray)
            faces = _detect_face(gray)

            if len(faces) == 0:
                no_face_count += 1
                prev_mouth_roi = None

                # Grace period before muting
                if no_face_count >= _NO_FACE_GRACE and not ui.muted:
                    ui.muted = True
                    try:
                        ui.set_state("MUTED")
                        ui.write_log("[FaceWatcher] Yuz ko'rinmadi → mute.")
                    except Exception:
                        pass
                with _lock:
                    _state["owner_seen"] = False
                    _state["speaking"]   = False

                time.sleep(_WATCH_INTERVAL)
                continue

            # At least one face detected
            no_face_count = 0

            if not is_enabled():
                # No profile — always stay listening
                if ui.muted:
                    ui.muted = False
                    try:
                        ui.set_state("LISTENING")
                    except Exception:
                        pass
                with _lock:
                    _state["owner_seen"] = True
                time.sleep(_WATCH_INTERVAL)
                continue

            # Run LBPH verification on the first (largest) face
            owner_here = verify_frame(gray, faces)

            with _lock:
                _state["owner_seen"] = owner_here

            if not owner_here:
                # Unknown face → mute
                if not ui.muted:
                    ui.muted = True
                    try:
                        ui.set_state("MUTED")
                        ui.write_log("[FaceWatcher] Begona yuz → mute.")
                    except Exception:
                        pass
                prev_mouth_roi = None
                time.sleep(_WATCH_INTERVAL)
                continue

            # ── Owner is here: track lip movement ────────────────────────────
            x, y, w, h = faces[0]  # use primary face
            mouth_now = _mouth_roi(gray, x, y, w, h)

            lip_motion = 0.0
            if prev_mouth_roi is not None and mouth_now.shape == prev_mouth_roi.shape:
                diff       = cv2.absdiff(mouth_now, prev_mouth_roi)
                lip_motion = float(np.mean(diff))

            prev_mouth_roi = mouth_now.copy()

            # Smooth motion signal
            lip_motion_buf.append(lip_motion)
            if len(lip_motion_buf) > LIP_BUF_SIZE:
                lip_motion_buf.pop(0)
            avg_motion = sum(lip_motion_buf) / len(lip_motion_buf)

            speaking_now = avg_motion >= _LIP_THRESHOLD

            with _lock:
                _state["speaking"] = speaking_now

            # Unmute as soon as owner is detected (whether speaking or not)
            if ui.muted:
                ui.muted = False
                try:
                    ui.set_state("LISTENING")
                    ui.write_log("[FaceWatcher] Egasi ko'rindi → faol.")
                except Exception:
                    pass

            time.sleep(_WATCH_INTERVAL)

        cap.release()

    t = threading.Thread(target=_loop, daemon=True, name="FaceWatcher")
    t.start()
    print("[FaceWatcher] Thread launched.")
