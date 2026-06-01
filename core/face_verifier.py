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
_FACE_ID_CFG    = _PROFILE_DIR / "face_id.cfg"     # master ON/OFF toggle (like phone Face ID)
_CASCADE_FACE   = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
_CASCADE_SMILE  = cv2.data.haarcascades + "haarcascade_smile.xml"

_LBPH_THRESHOLD  = 130.0  # LBPH confidence < this → owner (lower = stricter)
_LIP_THRESHOLD   = 8.0    # mean pixel diff in mouth ROI → speaking
_FACE_SIZE       = (100, 100)  # resize face ROI before training/predict
_ENROLL_FRAMES   = 60     # frames to capture during enrollment (~3-4 seconds)
_WATCH_INTERVAL  = 0.04   # seconds between watcher frames (~25fps)
_NO_FACE_GRACE   = 70     # consecutive no-face frames before muting (~2.8s at 25fps)
_STRANGER_GRACE  = 50     # consecutive stranger frames before muting (~2.0s at 25fps)
_OWNER_CONFIRM   = 4      # consecutive owner frames needed to unmute (~0.16s)
_CONF_EMA_ALPHA  = 0.30   # EMA smoothing factor for LBPH confidence (0=frozen, 1=raw)
_BURST_INTERVAL = 0     # 0 = continuous operation (camera always open, LED always on)
_BURST_DURATION = 3.0   # seconds camera is active per burst (only used when _BURST_INTERVAL > 0)
_OWNER_STALE_S  = 150.0 # seconds without owner confirmation before auto-mute in burst mode
_LED_BLINK_INTERVAL = 30.0  # seconds between LED blink pulses (30s = 2 blinks per minute)
_LED_BLINK_DURATION  = 0.3    # seconds camera closes during each blink (LED off)
_WATCH_INTERVAL_SLOW = 0.10   # 10fps when owner confirmed (saves ~60% CPU vs 25fps)
_CAM_FAIL_MAX        = 10     # reopen camera after N consecutive cap.read() failures
_AUTO_ENROLL_CONF_FRAC = 0.55  # auto-enroll when conf < threshold × this fraction
_AUTO_ENROLL_INTERVAL  = 300.0 # min seconds between auto-update saves (5 min)
_AUTO_ENROLL_FRAMES    = 25    # frames to accumulate before model reinforcement update

_CASCADE_PROFILE = cv2.data.haarcascades + "haarcascade_profileface.xml"

_face_cascade    = cv2.CascadeClassifier(_CASCADE_FACE)
_smile_cascade   = cv2.CascadeClassifier(_CASCADE_SMILE)
_profile_cascade = cv2.CascadeClassifier(_CASCADE_PROFILE)

# CLAHE for local contrast normalization — handles dim/uneven lighting better than equalizeHist
_clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))

_state = {
    "recognizer":     None,
    "enabled":        False,
    "active":         False,   # master switch — toggled via UI (persisted)
    "speaking":       False,   # True when lips are moving
    "owner_seen":     False,   # True when owner's face is in frame
    "stranger_active":False,   # True when an UNKNOWN face is positively detected
    "threshold":      _LBPH_THRESHOLD,
}
_lock = threading.Lock()
_watcher_started = False       # guard: only one watcher thread ever
_watcher_stop    = threading.Event()   # set → watcher loop exits & releases camera
_blinker_started = False       # guard: only one LED blinker thread ever
_preview_active  = False       # show live camera window (legacy imshow flag)
_cam_pause       = threading.Event()   # set → watcher must release camera
_cam_released    = threading.Event()   # set by watcher after cap.release() confirmed
_cam_held        = threading.Event()   # set while watcher currently holds the camera open

# Shared frame buffer — watcher writes, preview window reads (no extra camera open)
_frame_lock   = threading.Lock()
_latest_frame = None   # BGR ndarray or None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _detect_face(gray: np.ndarray):
    """Return list of (x,y,w,h). Frontal first, profile cascade as fallback."""
    faces = list(_face_cascade.detectMultiScale(
        gray, scaleFactor=1.1, minNeighbors=4, minSize=(55, 55)
    ))
    if not faces:
        faces = list(_profile_cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=4, minSize=(55, 55)
        ))
    return faces


def _largest_face(faces):
    """Pick the biggest bounding box — most reliable for recognition."""
    return max(faces, key=lambda r: r[2] * r[3])


def _roi_quality(roi: np.ndarray) -> bool:
    """True if ROI has enough contrast for meaningful LBPH prediction."""
    return float(roi.std()) >= 12.0


def _verify_with_conf(gray: np.ndarray, faces) -> tuple:
    """Return (is_owner: bool, confidence: float). 999.0 = unreadable frame."""
    if not is_enabled() or not faces:
        return False, 999.0
    with _lock:
        rec = _state["recognizer"]
        thr = _state["threshold"]
    best_conf   = 999.0
    owner_found = False
    for (x, y, w, h) in faces:
        roi = _face_roi(gray, x, y, w, h)
        if not _roi_quality(roi):
            continue
        try:
            label, confidence = rec.predict(roi)
            if confidence < best_conf:
                best_conf = float(confidence)
            if label == 0 and confidence < thr:
                owner_found = True
        except Exception:
            continue
    return owner_found, best_conf

def _face_roi(gray: np.ndarray, x, y, w, h) -> np.ndarray:
    """Crop face ROI, apply elliptical mask (removes background corners), resize."""
    # Shrink bounding box ~8% inward to cut out edge background
    pad_x = int(w * 0.08)
    pad_y = int(h * 0.08)
    x1 = max(x + pad_x, 0)
    y1 = max(y + pad_y, 0)
    x2 = min(x + w - pad_x, gray.shape[1])
    y2 = min(y + h - pad_y, gray.shape[0])

    roi     = gray[y1:y2, x1:x2]
    resized = cv2.resize(roi, _FACE_SIZE)
    resized = cv2.GaussianBlur(resized, (3, 3), 0)  # slight denoise

    # Elliptical mask: corners (background) → mean pixel value of face
    mask   = np.zeros(_FACE_SIZE, dtype=np.uint8)
    cx, cy = _FACE_SIZE[0] // 2, _FACE_SIZE[1] // 2
    cv2.ellipse(mask, (cx, cy), (cx - 2, cy - 2), 0, 0, 360, 255, -1)
    mean_val          = int(resized[mask > 0].mean()) if mask.any() else 128
    result            = np.full(_FACE_SIZE, mean_val, dtype=np.uint8)
    result[mask > 0]  = resized[mask > 0]

    return result

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

def is_stranger_active() -> bool:
    """True only when an unknown face is positively in frame (not just 'no face')."""
    return _state["stranger_active"]

def is_access_blocked() -> bool:
    """True when Face ID is ACTIVE + enrolled AND owner is NOT seen (no face OR stranger)."""
    if not _state["active"]:
        return False
    if not is_enabled():
        return False
    return not _state["owner_seen"]


# ── Master ON/OFF switch (phone-style Face ID toggle, persisted) ───────────────

def _load_active():
    """Read persisted ON/OFF state. Default OFF when no config exists."""
    try:
        if _FACE_ID_CFG.exists():
            val = _FACE_ID_CFG.read_text(encoding="utf-8").strip().lower()
            _state["active"] = (val == "on")
    except Exception:
        _state["active"] = False

def _save_active(active: bool):
    try:
        _PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        _FACE_ID_CFG.write_text("on" if active else "off", encoding="utf-8")
    except Exception as e:
        print(f"[FaceVerifier] Cannot save Face ID state: {e}")

def is_active() -> bool:
    """True when the user has turned Face ID ON via the toggle."""
    return _state["active"]

def set_active(active: bool, ui=None) -> str:
    """Turn Face ID protection ON or OFF at runtime (persisted).

    Returns one of: 'on', 'off', 'no_profile'.
    - ON  : loads profile if needed, starts the face watcher.
    - OFF : stops the watcher, releases the camera, unmutes the mic.
    """
    active = bool(active)
    _save_active(active)
    with _lock:
        _state["active"] = active

    if active:
        if not is_enabled():
            load_profile()
        if not is_enabled():
            # No enrolled face — caller should trigger enrollment.
            print("[FaceVerifier] Face ID ON requested but no profile enrolled.")
            return "no_profile"
        with _lock:
            _state["owner_seen"] = False   # start blocked until owner confirmed
        start_face_watcher(ui, cam_index=0)
        print("[FaceVerifier] 🔒 Face ID ON.")
        return "on"
    else:
        stop_face_watcher()
        with _lock:
            _state["owner_seen"]      = True   # not blocked while OFF
            _state["speaking"]        = False
            _state["stranger_active"] = False
        if ui is not None:
            try:
                ui.muted = False
            except Exception:
                pass
        print("[FaceVerifier] 🔓 Face ID OFF.")
        return "off"


def stop_face_watcher():
    """Signal the watcher thread to exit and release the camera."""
    global _watcher_started
    if not _watcher_started:
        return
    _watcher_stop.set()
    # Wait briefly for the loop to release the camera (loop ticks ~25fps).
    for _ in range(20):
        if not _cam_held.is_set():
            break
        time.sleep(0.05)
    _watcher_started = False


def enroll(seconds: int = 8, cam_index: int = 0, player=None,
           show_preview: bool = True) -> str:
    """
    Record face from webcam, train LBPH model, and save permanently.
    Pauses the face watcher thread while camera is in use.
    show_preview=False → silent mode (no imshow), use when called from a background thread.
    """
    if player: player.write_log(f"[FaceVerifier] Enrolling {seconds}s...")

    # Pause watcher, wait for it to confirm camera release
    if _watcher_started:
        _cam_released.clear()
        _cam_pause.set()
        ok = _cam_released.wait(timeout=3.0)
        if not ok:
            print("[FaceVerifier] Watcher did not release camera in time.")
        time.sleep(0.15)
    else:
        _cam_pause.set()

    try:
        cap = _open_cam(cam_index)
    except RuntimeError as e:
        _cam_pause.clear()
        return str(e)

    face_images = []
    end_time    = time.time() + seconds
    phase_hints = [
        "Oldinga qarang",
        "Biroz chapga buriling",
        "Biroz o'ngga buriling",
        "Biroz yuqoriga qarang",
        "Oldinga qarang (tabassum)",
    ]
    last_log_second = -1

    while time.time() < end_time:
        ret, frame = cap.read()
        if not ret:
            break
        gray  = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray  = _clahe.apply(gray)
        faces = _detect_face(gray)

        for (x, y, w, h) in faces:
            roi = _face_roi(gray, x, y, w, h)
            face_images.append(roi)

        remaining = max(0, int(end_time - time.time()))

        if show_preview:
            for (x, y, w, h) in faces:
                cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
            phase_idx = min(int((seconds - remaining) / max(seconds / len(phase_hints), 1)),
                            len(phase_hints) - 1)
            hint = phase_hints[phase_idx]
            cv2.putText(frame, f"{hint}: {remaining}s", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            cv2.putText(frame, f"Saqlangan kadrlar: {len(face_images)}", (10, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 220, 0), 2)
            cv2.imshow("JARVIS — Yuz ro'yxatga olish", frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
        else:
            # Silent mode — log progress every second instead of imshow
            if remaining != last_log_second:
                last_log_second = remaining
                phase_idx = min(int((seconds - remaining) / max(seconds / len(phase_hints), 1)),
                                len(phase_hints) - 1)
                hint = phase_hints[phase_idx]
                if player:
                    player.write_log(
                        f"📷 {hint} — {remaining}s qoldi | {len(face_images)} kadr"
                    )
                else:
                    print(f"[Enroll] {hint} — {remaining}s | {len(face_images)} frames")

    cap.release()
    if show_preview:
        cv2.destroyAllWindows()
    _cam_pause.clear()  # resume watcher

    if len(face_images) < 10:
        return (f"Yuz topilmadi yoki kam ({len(face_images)} kadr). "
                "Yaxshi yorug'likda qayta urining.")

    labels = np.zeros(len(face_images), dtype=np.int32)  # owner = label 0
    rec    = cv2.face.LBPHFaceRecognizer_create(
        radius=1, neighbors=8, grid_x=10, grid_y=10, threshold=_LBPH_THRESHOLD
    )
    rec.train(face_images, labels)

    _PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    rec.save(str(_FACE_MODEL))
    os.chmod(_FACE_MODEL, 0o600)

    with _lock:
        _state["recognizer"] = rec
        _state["enabled"]    = True

    if player: player.write_log(f"[FaceVerifier] Enrolled {len(face_images)} frames → saved.")
    return (f"✅ Yuz profili doimiy saqlandi! ({len(face_images)} ta kadr)\n"
            f"Fayl: {_FACE_MODEL}\n"
            "Jarvis qayta ishga tushganda ham eslab qoladi.")


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


def verify_once(cam_index: int = 0) -> bool:
    """One-shot face check. Uses watcher state if watcher is already running."""
    if _watcher_started:
        # Watcher already owns the camera — read its cached state
        with _lock:
            return _state["owner_seen"]
    # Watcher not started — open camera ourselves
    try:
        cap = _open_cam(cam_index)
        for _ in range(10):
            ret, frame = cap.read()
            if not ret:
                continue
            gray  = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray  = _clahe.apply(gray)
            faces = _detect_face(gray)
            if len(faces) > 0:
                result = verify_frame(gray, faces)
                cap.release()
                return result
        cap.release()
    except Exception as e:
        print(f"[FaceVerifier] verify_once error: {e}")
    return False


def start_preview():
    global _preview_active
    _preview_active = True

def stop_preview():
    global _preview_active
    _preview_active = False


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

def start_led_blinker(cam_index: int = 0,
                     interval: float = 60.0,
                     duration: float = 2.0):
    """Blink the camera LED on a fixed interval — no frame capture, no recognition.

    Camera opens for `duration` seconds (LED on), then closes for
    `interval - duration` seconds (LED off).  Pure visual heartbeat.
    Skips a cycle automatically when enrollment dialog has the camera.
    """
    global _blinker_started
    if _blinker_started or _watcher_started:
        return
    _blinker_started = True

    def _blink():
        while True:
            # Skip if enrollment dialog currently holds the camera
            if _cam_pause.is_set():
                time.sleep(0.5)
                continue
            try:
                cap = cv2.VideoCapture(cam_index)
                if cap.isOpened():
                    print(f"[LEDBlinker] LED yondi ({duration:.0f}s)")
                    time.sleep(duration)
                cap.release()
            except Exception as e:
                print(f"[LEDBlinker] Xato: {e}")
            time.sleep(max(0.0, interval - duration))

    t = threading.Thread(target=_blink, daemon=True, name="LEDBlinker")
    t.start()
    print(f"[LEDBlinker] Ishga tushdi — har {interval:.0f}s da {duration:.0f}s yonadi.")


def start_face_watcher(ui, cam_index: int = 0):
    """
    Daemon thread that reads webcam frames continuously.

    Logic:
    - Detects face each frame (Haar cascade, fast).
    - If face found: runs LBPH verification (owner or not).
    - Tracks lip motion via frame difference on mouth ROI.
    - Owner present → UNMUTE (ui.muted = False, GIL-safe bool only).
    - No face / unknown face → MUTE after grace period (ui.muted = True).
    - Never calls ui.set_state() or ui.write_log() — PyQt6 is not thread-safe.
    """
    global _watcher_started
    if _watcher_started:
        return  # already running, don't spawn another thread
    _watcher_stop.clear()
    _watcher_started = True

    def _loop():
        try:
            cap = _open_cam(cam_index)
            _cam_held.set()
        except RuntimeError as e:
            print(f"[FaceWatcher] Cannot open camera: {e}")
            return

        # ── Streak-based state machine ─────────────────────────────────────────
        # Three mutually exclusive streaks; whichever hits its threshold wins.
        # Asymmetric: unmute needs only _OWNER_CONFIRM frames (fast),
        # mute needs _STRANGER_GRACE / _NO_FACE_GRACE frames (slow = tolerant).
        owner_streak    = 0     # consecutive confirmed-owner frames
        stranger_streak = 0     # consecutive confirmed-stranger frames
        no_face_streak  = 0     # consecutive no-face frames
        conf_ema        = None  # exponential moving avg of raw LBPH confidence
        prev_mouth_roi  = None
        lip_motion_buf  = []
        LIP_BUF_SIZE    = 6
        prev_preview    = False
        _dbg_tick       = 0     # periodic confidence log counter
        last_led_blink_t    = time.time()  # for LED blink pulse
        owner_confirmed_flag = False       # for adaptive FPS
        _cam_fail_count      = 0           # consecutive cap.read() failures
        auto_enroll_buf      = []          # positive reinforcement frame buffer
        last_auto_enroll_t   = 0.0         # timestamp of last auto-model-update
        # ── Burst (intermittent) mode ─────────────────────────────────────────
        cam_held               = True       # local: watcher currently owns camera
        burst_start            = time.time()
        last_owner_confirmed_t = 0.0        # time of most recent owner confirmation

        print("[FaceWatcher] Started.")

        while True:
            # Toggle OFF: exit cleanly and release the camera
            if _watcher_stop.is_set():
                print("[FaceWatcher] Stop requested — exiting & releasing camera.")
                break

            # Pause when enrollment/dialog needs the camera
            if _cam_pause.is_set():
                if cam_held:
                    cap.release()
                    _cam_held.clear()
                    cam_held = False
                _cam_released.set()    # confirm camera is free
                print("[FaceWatcher] Camera released — waiting for resume...")
                _cam_pause.wait()      # block until caller clears the pause flag
                _cam_released.clear()
                time.sleep(0.15)
                try:
                    cap = _open_cam(cam_index)
                    cam_held = True
                    _cam_held.set()
                    burst_start = time.time()
                    print("[FaceWatcher] Camera resumed.")
                except RuntimeError:
                    time.sleep(1.0)
                    continue

            # Burst mode: if camera released during sleep, just tick
            if not cam_held:
                time.sleep(0.5)
                continue

            ret, frame = cap.read()
            if not ret:
                _cam_fail_count += 1
                time.sleep(0.2)
                if _cam_fail_count >= _CAM_FAIL_MAX:
                    print("[FaceWatcher] Kamera xatosi — qayta ochilmoqda...")
                    try: cap.release()
                    except Exception: pass
                    cam_held = False
                    _cam_held.clear()
                    time.sleep(1.0)
                    try:
                        cap = _open_cam(cam_index)
                        cam_held = True
                        _cam_held.set()
                        _cam_fail_count = 0
                        print("[FaceWatcher] Kamera qayta ochildi.")
                    except RuntimeError:
                        pass
                continue
            _cam_fail_count = 0

            # Share frame with preview window (no extra camera open needed)
            with _frame_lock:
                global _latest_frame
                _latest_frame = frame.copy()

            gray  = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray  = _clahe.apply(gray)
            faces = _detect_face(gray)

            if len(faces) == 0:
                # ── No face detected ──────────────────────────────────────────
                no_face_streak += 1
                owner_streak    = 0
                stranger_streak = 0
                owner_confirmed_flag = False
                conf_ema        = None   # reset EMA — stale when face reappears
                prev_mouth_roi  = None
                if no_face_streak >= _NO_FACE_GRACE:
                    ui.muted = True
                with _lock:
                    _state["owner_seen"]      = False
                    _state["speaking"]        = False
                    _state["stranger_active"] = False
            else:
                # ── Face detected ─────────────────────────────────────────────
                no_face_streak = 0

                if not is_enabled():
                    # No profile enrolled → always treat any face as owner
                    owner_streak   += 1
                    stranger_streak = 0
                    if owner_streak >= _OWNER_CONFIRM:
                        ui.muted = False
                    with _lock:
                        _state["owner_seen"]      = (owner_streak >= _OWNER_CONFIRM)
                        _state["stranger_active"] = False
                else:
                    raw_owner, raw_conf = _verify_with_conf(gray, faces)

                    # EMA smoothing of raw confidence (skip unreadable frames)
                    if raw_conf < 990.0:
                        if conf_ema is None:
                            conf_ema = raw_conf
                        else:
                            conf_ema = _CONF_EMA_ALPHA * raw_conf + (1.0 - _CONF_EMA_ALPHA) * conf_ema

                        with _lock:
                            thr = _state["threshold"]
                        ema_owner = conf_ema < thr

                        # Periodic debug log (~every 2s)
                        _dbg_tick += 1
                        if _dbg_tick % 50 == 0:
                            print(f"[FaceWatcher] conf_ema={conf_ema:.1f} thr={thr:.0f} "
                                  f"owner_s={owner_streak} stranger_s={stranger_streak}")

                        if ema_owner:
                            owner_streak   += 1
                            stranger_streak = 0
                        else:
                            stranger_streak += 1
                            owner_streak    = 0
                    # else: bad ROI quality → keep streaks unchanged (don't penalise)

                    owner_confirmed    = owner_streak    >= _OWNER_CONFIRM
                    stranger_confirmed = stranger_streak >= _STRANGER_GRACE
                    owner_confirmed_flag = owner_confirmed

                    with _lock:
                        _state["owner_seen"]      = owner_confirmed
                        _state["stranger_active"] = stranger_confirmed

                    if owner_confirmed:
                        ui.muted = False
                        last_owner_confirmed_t = time.time()
                        # Positive reinforcement: capture very-confident frames
                        if raw_conf < 990.0:
                            with _lock:
                                _thr_now = _state["threshold"]
                            if raw_conf < _thr_now * _AUTO_ENROLL_CONF_FRAC:
                                _xe, _ye, _we, _he = _largest_face(faces)
                                _roi_e = _face_roi(gray, _xe, _ye, _we, _he)
                                if _roi_quality(_roi_e):
                                    auto_enroll_buf.append(_roi_e)
                        if (len(auto_enroll_buf) >= _AUTO_ENROLL_FRAMES
                                and time.time() - last_auto_enroll_t >= _AUTO_ENROLL_INTERVAL):
                            _lbls = np.zeros(len(auto_enroll_buf), dtype=np.int32)
                            try:
                                with _lock:
                                    _state["recognizer"].update(auto_enroll_buf, _lbls)
                                    _state["recognizer"].save(str(_FACE_MODEL))
                                print(f"[FaceWatcher] ✅ Auto-o'rganildi: {len(auto_enroll_buf)} kadr")
                            except Exception as _ae:
                                print(f"[FaceWatcher] Auto-enroll xato: {_ae}")
                            auto_enroll_buf.clear()
                            last_auto_enroll_t = time.time()
                        # Track lip motion for speaking detection
                        x, y, w, h = _largest_face(faces)
                        mouth_now  = _mouth_roi(gray, x, y, w, h)
                        lip_motion = 0.0
                        if prev_mouth_roi is not None and mouth_now.shape == prev_mouth_roi.shape:
                            lip_motion = float(np.mean(cv2.absdiff(mouth_now, prev_mouth_roi)))
                        prev_mouth_roi = mouth_now.copy()
                        lip_motion_buf.append(lip_motion)
                        if len(lip_motion_buf) > LIP_BUF_SIZE:
                            lip_motion_buf.pop(0)
                        with _lock:
                            _state["speaking"] = (
                                sum(lip_motion_buf) / len(lip_motion_buf)
                            ) >= _LIP_THRESHOLD
                    elif stranger_confirmed:
                        ui.muted = True
                        prev_mouth_roi = None
                    # else: uncertain (streaks building) → hold current muted state

            # ── Live preview (enabled via start_preview / stop_preview) ──────
            if _preview_active:
                display = frame.copy()
                for (fx, fy, fw, fh) in faces:
                    with _lock:
                        own = _state["owner_seen"]
                        spk = _state["speaking"]
                    color = (0, 220, 0) if own else (0, 0, 220)
                    label = ("Egasi" + (" [gapiryapti]" if spk else "")) if own else "Begona"
                    cv2.rectangle(display, (fx, fy), (fx+fw, fy+fh), color, 2)
                    cv2.putText(display, label, (fx, fy - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2)
                status = "FAOL" if not ui.muted else "JIM"
                cv2.putText(display, f"JARVIS [{status}]", (8, 28),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 200, 0), 2)
                cv2.imshow("JARVIS — Yuz kuzatuvi", display)
                cv2.waitKey(1)
                prev_preview = True
            elif prev_preview:
                cv2.destroyAllWindows()
                prev_preview = False

            time.sleep(_WATCH_INTERVAL_SLOW if owner_confirmed_flag else _WATCH_INTERVAL)

            # ── LED blink indicator (privacy pulse, 2x per minute) ────────────
            if cam_held and not _cam_pause.is_set():
                now = time.time()
                if now - last_led_blink_t >= _LED_BLINK_INTERVAL:
                    cap.release()
                    cam_held = False
                    _cam_held.clear()
                    time.sleep(_LED_BLINK_DURATION)  # LED off briefly
                    for _r in range(5):
                        try:
                            cap = _open_cam(cam_index)
                            cam_held = True
                            _cam_held.set()
                            break
                        except RuntimeError:
                            time.sleep(0.3)
                    last_led_blink_t = now

            # ── Burst mode: release camera (LED off) between bursts ───────────
            if _BURST_INTERVAL > 0 and cam_held:
                now = time.time()
                # Staleness: if owner unseen for too long, auto-mute during sleep
                if (last_owner_confirmed_t == 0.0
                        and now - burst_start >= _BURST_DURATION):
                    ui.muted = True
                elif (last_owner_confirmed_t > 0.0
                        and now - last_owner_confirmed_t > _OWNER_STALE_S):
                    ui.muted = True
                    with _lock:
                        _state["owner_seen"] = False

                if now - burst_start >= _BURST_DURATION:
                    # Release camera → LED off
                    cap.release()
                    cam_held = False
                    _cam_held.clear()
                    with _frame_lock:
                        _latest_frame = None
                    print("[FaceWatcher] Burst done — camera released (LED off).")

                    # Sleep until next burst
                    sleep_end = burst_start + _BURST_INTERVAL
                    while time.time() < sleep_end:
                        if _cam_pause.is_set():
                            _cam_released.set()
                            _cam_pause.wait()
                            _cam_released.clear()
                            break
                        time.sleep(0.5)

                    # Reopen for next burst
                    try:
                        cap = _open_cam(cam_index)
                        cam_held = True
                        _cam_held.set()
                        burst_start = time.time()
                        # Reset streaks for fresh read each burst
                        owner_streak = 0
                        stranger_streak = 0
                        no_face_streak  = 0
                        conf_ema = None
                        print("[FaceWatcher] Burst starting — camera open (LED on).")
                    except RuntimeError:
                        time.sleep(1.0)

        # ── Loop exited (toggle OFF) — release camera & reset guards ──────────
        global _watcher_started
        try:
            if cam_held:
                cap.release()
        except Exception:
            pass
        _cam_held.clear()
        with _frame_lock:
            _latest_frame = None
        _watcher_started = False
        print("[FaceWatcher] Stopped.")

    t = threading.Thread(target=_loop, daemon=True, name="FaceWatcher")
    t.start()
    print("[FaceWatcher] Thread launched.")
