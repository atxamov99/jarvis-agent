"""face_enroll_dialog.py — Step-by-step face enrollment UI (PyQt6).

Shows live camera feed. User clicks "Bosing" for each pose.
Must be created and shown from the main Qt thread.
"""

import os

import cv2
import numpy as np
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout,
)

import core.face_verifier as fv


_FRAMES_PER_STEP = 45   # frames captured per pose (~1.5s at 30fps)
_FEED_INTERVAL   = 33   # ms between camera frames (~30fps)

_STEPS = [
    ("Oldinga to'g'ri qarang",     "⬆️"),
    ("Biroz CHAPGA buriling",       "⬅️"),
    ("Biroz O'NGGA buriling",       "➡️"),
    ("Biroz YUQORIGA qarang",       "🔼"),
    ("Oldinga — tabassum qiling",   "😊"),
]


class FaceEnrollDialog(QDialog):
    enrollment_done = pyqtSignal(str)   # emitted when model saved

    def __init__(self, cam_index: int = 0, parent=None):
        super().__init__(parent)
        self.cam_index        = cam_index
        self.cap              = None
        self.current_step     = 0
        self.capturing        = False
        self.capture_count    = 0
        self.all_faces: list[np.ndarray] = []
        self._current_gray    = None
        self._current_faces   = ()
        self._warmup_frames   = 0      # skip first N frames while cam initialises
        self._cam_ready       = False  # True once we get a non-black frame

        self._build_ui()
        self._open_camera()    # sets up QTimer; camera opens asynchronously
        self._update_step_ui()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        self.setWindowTitle("JARVIS — Yuz ro'yxatdan o'tkazish")
        self.setFixedSize(700, 620)
        self.setStyleSheet("background:#0f0f0f; color:#e0e0e0;")

        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.setContentsMargins(16, 14, 16, 14)

        # ── Step indicator ────────────────────────────────────────────────────
        self.step_lbl = QLabel()
        self.step_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.step_lbl.setStyleSheet("font-size:13px; color:#666;")
        root.addWidget(self.step_lbl)

        # ── Instruction ───────────────────────────────────────────────────────
        self.instr_lbl = QLabel()
        self.instr_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.instr_lbl.setStyleSheet(
            "font-size:24px; font-weight:bold; color:#00e676; padding:4px;"
        )
        root.addWidget(self.instr_lbl)

        # ── Camera feed ───────────────────────────────────────────────────────
        self.cam_lbl = QLabel()
        self.cam_lbl.setFixedSize(660, 420)
        self.cam_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cam_lbl.setStyleSheet("background:#000; border-radius:6px;")
        root.addWidget(self.cam_lbl, alignment=Qt.AlignmentFlag.AlignCenter)

        # ── Progress bar ──────────────────────────────────────────────────────
        self.progress = QProgressBar()
        self.progress.setRange(0, _FRAMES_PER_STEP)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(8)
        self.progress.setStyleSheet("""
            QProgressBar { background:#222; border:none; border-radius:4px; }
            QProgressBar::chunk { background:#00e676; border-radius:4px; }
        """)
        root.addWidget(self.progress)

        # ── Bottom row ────────────────────────────────────────────────────────
        row = QHBoxLayout()
        row.setSpacing(12)

        self.status_lbl = QLabel("")
        self.status_lbl.setStyleSheet("font-size:14px; color:#aaa;")
        row.addWidget(self.status_lbl, stretch=1)

        self.btn = QPushButton("📸  Bosing")
        self.btn.setFixedSize(180, 52)
        self.btn.setStyleSheet("""
            QPushButton {
                background:#1b5e20; color:#fff; font-size:16px;
                border-radius:8px; border:none; font-weight:bold;
            }
            QPushButton:hover  { background:#2e7d32; }
            QPushButton:disabled { background:#222; color:#555; }
        """)
        self.btn.clicked.connect(self._on_capture_clicked)
        row.addWidget(self.btn)
        root.addLayout(row)

    # ── Camera ────────────────────────────────────────────────────────────────

    def _open_camera(self):
        import time

        if fv._watcher_started:
            fv._cam_released.clear()
            fv._cam_pause.set()
            ok = fv._cam_released.wait(timeout=3.0)
            if not ok:
                print("[FaceEnrollDialog] Warning: watcher release timeout.")
            # V4L2 needs extra time after cap.release() before device is free
            time.sleep(0.6)

        # Retry loop in case device isn't available yet
        self.cap = None
        for attempt in range(6):
            cap = cv2.VideoCapture(self.cam_index)
            if cap.isOpened():
                self.cap = cap
                break
            cap.release()
            time.sleep(0.3)
            print(f"[FaceEnrollDialog] Camera attempt {attempt + 1} failed, retrying...")

        if self.cap is None:
            self.cam_lbl.setText("❌  Kamera ochilmadi. Jarvisni qayta yoqing.")
            return

        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.cap.set(cv2.CAP_PROP_FPS, 30)

        self.cam_lbl.setText("⏳  Kamera ishga tushmoqda...")
        self.btn.setEnabled(False)   # disable until camera warms up

        self._feed_timer = QTimer(self)
        self._feed_timer.timeout.connect(self._tick)
        self._feed_timer.start(_FEED_INTERVAL)

    def _tick(self):
        if not self.cap or not self.cap.isOpened():
            return
        ret, frame = self.cap.read()
        if not ret or frame is None:
            return

        # Discard first 20 frames — camera needs time to adjust exposure
        if self._warmup_frames < 20:
            self._warmup_frames += 1
            return

        # First good frame: enable button and clear loading text
        if not self._cam_ready:
            self._cam_ready = True
            self.cam_lbl.setText("")
            self.btn.setEnabled(True)

        gray  = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray  = cv2.equalizeHist(gray)
        faces = fv._detect_face(gray)

        self._current_gray  = gray
        self._current_faces = faces

        display = frame.copy()

        # Collect frames while capturing
        if self.capturing:
            for (x, y, w, h) in faces:
                roi = fv._face_roi(gray, x, y, w, h)
                self.all_faces.append(roi)
                cv2.rectangle(display, (x, y), (x+w, y+h), (0, 230, 80), 3)

            self.capture_count += 1
            self.progress.setValue(self.capture_count)

            # Countdown overlay
            remaining_frames = _FRAMES_PER_STEP - self.capture_count
            secs = max(0, round(remaining_frames / 30, 1))
            cv2.putText(display, f"{secs}s", (16, 52),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.6, (0, 230, 80), 3)
            cv2.putText(display, f"{len(self.all_faces)} kadr", (16, 96),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 220, 0), 2)

            if self.capture_count >= _FRAMES_PER_STEP:
                self._step_done()
        else:
            # Idle — draw face box dimly
            for (x, y, w, h) in faces:
                cv2.rectangle(display, (x, y), (x+w, y+h), (80, 140, 255), 2)

        # BGR → RGB → QPixmap
        rgb = cv2.cvtColor(display, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qi = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
        self.cam_lbl.setPixmap(
            QPixmap.fromImage(qi).scaled(
                660, 420,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    # ── Capture flow ──────────────────────────────────────────────────────────

    def _update_step_ui(self):
        if self.current_step < len(_STEPS):
            instr, icon = _STEPS[self.current_step]
            self.instr_lbl.setText(f"{icon}  {instr}")
            self.step_lbl.setText(
                f"{self.current_step + 1} / {len(_STEPS)} qadam"
            )
            self.status_lbl.setText("")
            self.btn.setText("📸  Bosing")
            self.btn.setEnabled(True)
            self.progress.setValue(0)

    def _on_capture_clicked(self):
        if self.current_step >= len(_STEPS):
            return
        self.capturing     = True
        self.capture_count = 0
        self.btn.setEnabled(False)
        self.btn.setText("⏳  Yozilmoqda...")
        self.status_lbl.setText("")

    def _step_done(self):
        self.capturing = False
        self.current_step += 1

        if self.current_step < len(_STEPS):
            instr, icon = _STEPS[self.current_step]
            self.instr_lbl.setText(f"{icon}  {instr}")
            self.step_lbl.setText(
                f"{self.current_step + 1} / {len(_STEPS)} qadam"
            )
            self.status_lbl.setText("✅ Tayyor! Keyingi holatga o'ting.")
            self.btn.setText("📸  Bosing")
            self.btn.setEnabled(True)
            self.progress.setValue(0)
        else:
            self._save_model()

    def _save_model(self):
        self._feed_timer.stop()
        self.btn.setEnabled(False)
        self.instr_lbl.setText("⏳  Saqlanmoqda...")
        self.status_lbl.setText(f"Jami: {len(self.all_faces)} ta kadr")

        if len(self.all_faces) < 10:
            msg = "Yuz topilmadi yoki kadr kam. Qayta urining."
            self.instr_lbl.setText("❌  " + msg)
            self.enrollment_done.emit(msg)
            self.btn.setText("Yopish")
            self.btn.setEnabled(True)
            self.btn.clicked.disconnect()
            self.btn.clicked.connect(self.reject)
            return

        labels = np.zeros(len(self.all_faces), dtype=np.int32)
        rec    = cv2.face.LBPHFaceRecognizer_create(
            radius=1, neighbors=8, grid_x=10, grid_y=10,
            threshold=fv._LBPH_THRESHOLD,
        )
        rec.train(self.all_faces, labels)

        fv._PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        rec.save(str(fv._FACE_MODEL))
        os.chmod(fv._FACE_MODEL, 0o600)

        with fv._lock:
            fv._state["recognizer"] = rec
            fv._state["enabled"]    = True

        msg = f"✅ Yuz profili saqlandi! ({len(self.all_faces)} ta kadr)"
        self.instr_lbl.setText("✅  Tayyor!")
        self.status_lbl.setText(msg)
        self.progress.setValue(_FRAMES_PER_STEP)
        self.enrollment_done.emit(msg)

        self.btn.setText("Yopish")
        self.btn.setEnabled(True)
        self.btn.clicked.disconnect()
        self.btn.clicked.connect(self.accept)

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def closeEvent(self, event):
        if hasattr(self, "_feed_timer"):
            self._feed_timer.stop()
        if self.cap:
            self.cap.release()
            self.cap = None
        fv._cam_pause.clear()   # resume face watcher
        super().closeEvent(event)
