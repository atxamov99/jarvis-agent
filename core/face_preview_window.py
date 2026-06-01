"""face_preview_window.py — Live camera mirror (reads from watcher's shared buffer).

Does NOT open the camera itself — reads frames written by FaceWatcher.
No camera conflicts, no release/pause needed.
"""

import cv2
import numpy as np
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QHBoxLayout, QWidget, QPushButton

import core.face_verifier as fv

_FEED_MS = 40   # ~25fps (matches watcher speed)


class FacePreviewWindow(QWidget):
    def __init__(self, cam_index: int = 0, parent=None):
        super().__init__(parent)
        self.setWindowTitle("JARVIS — Yuz ko'rinishi")
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.WindowCloseButtonHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setStyleSheet("background:#0a0a0a;")
        self.setFixedSize(680, 560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        self.status_lbl = QLabel("⏳  Kamera tayyorlanmoqda...")
        self.status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_lbl.setStyleSheet("color:#666; font-size:13px;")
        layout.addWidget(self.status_lbl)

        self.cam_lbl = QLabel()
        self.cam_lbl.setFixedSize(660, 500)
        self.cam_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cam_lbl.setStyleSheet("background:#000; border-radius:6px;")
        layout.addWidget(self.cam_lbl)

        # Yopish tugmasi
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._close_btn = QPushButton("✕  Yopish")
        self._close_btn.setFixedHeight(32)
        self._close_btn.setStyleSheet(
            "QPushButton {"
            "  background:#1e1e1e; color:#ccc; border:1px solid #333;"
            "  border-radius:6px; padding:0 16px; font-size:13px;"
            "}"
            "QPushButton:hover { background:#c0392b; color:#fff; border-color:#c0392b; }"
        )
        self._close_btn.clicked.connect(self.close)
        btn_row.addWidget(self._close_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(_FEED_MS)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Escape, Qt.Key.Key_Q):
            self.close()
        else:
            super().keyPressEvent(event)

    def _tick(self):
        with fv._frame_lock:
            frame = fv._latest_frame
            if frame is None:
                return
            frame = frame.copy()

        self.status_lbl.setText("")

        gray  = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray  = cv2.equalizeHist(gray)
        faces = fv._detect_face(gray)

        display = frame.copy()
        for (x, y, w, h) in faces:
            with fv._lock:
                own = fv._state["owner_seen"]
                spk = fv._state["speaking"]
            color = (0, 220, 60) if own else (60, 60, 220)
            label = ("Siz" + (" 🗣" if spk else "")) if own else "Begona"
            cv2.rectangle(display, (x, y), (x+w, y+h), color, 2)
            cv2.putText(display, label, (x, y - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2)

        rgb = cv2.cvtColor(display, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qi = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
        self.cam_lbl.setPixmap(
            QPixmap.fromImage(qi).scaled(
                660, 500,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def closeEvent(self, event):
        self._timer.stop()
        super().closeEvent(event)
