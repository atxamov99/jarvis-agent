# JARVIS Windows Enhancement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add cinematic startup, 6 voice states with unique animations, RMS waveform, weather/tasks/notifications panels, auto-startup, and compact mode to the existing PyQt6 JARVIS app.

**Architecture:** All changes live in `ui.py` (UI components, animations, panels) and `main.py` (state wiring, auto-startup). `HudCanvas` gains 6 distinct animated states driven by `self.state`. Three new panel widgets are added to the right sidebar. No new Python dependencies except `pywin32` for auto-startup.

**Tech Stack:** PyQt6, Python 3.14, requests (already in requirements), pywin32 (new, Windows only)

---

## Task 1: HudCanvas — STARTUP boot sequence state

**Files:**
- Modify: `ui.py` — `HudCanvas.__init__`, `HudCanvas._step`, `HudCanvas.paintEvent`

### Boot lines and timing constants

- [ ] **Step 1: Add boot state fields to `HudCanvas.__init__`**

In `ui.py`, inside `HudCanvas.__init__` after `self._blink_tick = 0` (line ~342), add:

```python
        self._audio_rms: float = 0.0
        self._error_ticks: int = 0
        self._shake_x: float = 0.0

        # STARTUP boot sequence
        self._boot_lines: list[tuple[str, str]] = [
            ("INITIALISING CORE SYSTEMS...", "#00d4ff"),
            ("", ""),
            ("VOICE SYSTEM.......... OK",    "#00ff88"),
            ("MEMORY MODULE......... OK",    "#00ff88"),
            ("AUTOMATION ENGINE..... OK",    "#00ff88"),
            ("GEMINI API............ CONNECTING", "#ffcc00"),
            ("GEMINI API............ ONLINE", "#00ff88"),
            ("", ""),
            ("J.A.R.V.I.S SYSTEMS ONLINE.", "#00d4ff"),
        ]
        self._boot_idx:  int   = 0
        self._boot_t:    float = time.time()
        self._boot_done: bool  = False
```

- [ ] **Step 2: Advance boot sequence in `_step()`**

In `ui.py`, at the top of `HudCanvas._step()` (after `self._tick += 1`), add:

```python
        # advance STARTUP boot sequence
        if self.state == "STARTUP" and not self._boot_done:
            if time.time() - self._boot_t > 0.30:
                self._boot_t = time.time()
                self._boot_idx += 1
                if self._boot_idx >= len(self._boot_lines):
                    self._boot_done = True
            self.update()
            return
```

- [ ] **Step 3: Draw boot overlay in `paintEvent`**

In `ui.py`, in `HudCanvas.paintEvent`, just before the `# status text` section (around line 465), add:

```python
        # STARTUP overlay — drawn on top of everything
        if self.state == "STARTUP":
            self._paint_startup(p, W, H)
            p.end()
            return
```

- [ ] **Step 4: Add `_paint_startup` method to HudCanvas**

Add this method to `HudCanvas` after `_paint_drag_over`:

```python
    def _paint_startup(self, p: QPainter, W: int, H: int):
        # dark overlay
        p.fillRect(self.rect(), qcol(C.BG, 230))

        start_y = H * 0.25
        line_h  = 18
        visible = self._boot_lines[:self._boot_idx]

        p.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        for i, (text, color) in enumerate(visible):
            if not text:
                continue
            alpha = min(255, (self._boot_idx - i) * 40 + 180)
            p.setPen(QPen(qcol(color, alpha), 1))
            p.drawText(
                QRectF(0, start_y + i * line_h, W, line_h),
                Qt.AlignmentFlag.AlignCenter,
                text,
            )

        # blinking cursor on last visible line
        if not self._boot_done and self._blink and visible:
            last_idx = len(visible) - 1
            p.setPen(QPen(qcol(C.PRI), 1))
            p.drawText(
                QRectF(0, start_y + (last_idx + 1) * line_h, W, line_h),
                Qt.AlignmentFlag.AlignCenter,
                "▋",
            )
```

- [ ] **Step 5: Set initial state to STARTUP in MainWindow**

In `ui.py`, `MainWindow.__init__`, find where `hud` is assigned and after its creation set state:

```python
        self.hud = HudCanvas(face_path, central)
        self.hud.state = "STARTUP"
```

- [ ] **Step 6: Smoke test**

Run `python _test_ui.py` — window should open, show boot text scrolling in, then close. Check `C:\Temp\jarvis_test.txt` for "WINDOW CREATED OK".

- [ ] **Step 7: Commit**

```
git add ui.py
git commit -m "feat: HudCanvas STARTUP boot sequence state"
```

---

## Task 2: Fade-in on open, fade-out on quit

**Files:**
- Modify: `ui.py` — `MainWindow.__init__`, `MainWindow._real_quit`

- [ ] **Step 1: Add QPropertyAnimation import**

In `ui.py`, add to the `from PyQt6.QtCore import` block:

```python
from PyQt6.QtCore import (
    QEasingCurve, QMimeData, QObject, QPointF, QPropertyAnimation, QRectF,
    QSize, Qt, QTimer, QUrl, pyqtSignal,
)
```

- [ ] **Step 2: Start fade-in after window show in `MainWindow.__init__`**

Find the `self._win.show()` equivalent — in `MainWindow.__init__` the window is shown from `JarvisUI.__init__`. Add fade-in at the end of `MainWindow.__init__` (before the closing of the method):

```python
        # Fade-in on open
        self.setWindowOpacity(0.0)
        self._fade_in = QPropertyAnimation(self, b"windowOpacity")
        self._fade_in.setDuration(1200)
        self._fade_in.setStartValue(0.0)
        self._fade_in.setEndValue(1.0)
        self._fade_in.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade_in.start()
```

- [ ] **Step 3: Fade-out in `_real_quit`**

Replace the body of `_real_quit()` in `ui.py`:

```python
    def _real_quit(self):
        self._real_quit_requested = True
        self._save_geometry()
        if self._tray is not None:
            self._tray.hide()

        self._fade_out = QPropertyAnimation(self, b"windowOpacity")
        self._fade_out.setDuration(800)
        self._fade_out.setStartValue(self.windowOpacity())
        self._fade_out.setEndValue(0.0)
        self._fade_out.setEasingCurve(QEasingCurve.Type.InCubic)
        self._fade_out.finished.connect(QApplication.instance().quit)
        self._fade_out.start()
```

- [ ] **Step 4: Smoke test**

Run `python _test_ui.py` — window should fade in smoothly over 1.2s. If it opens at full opacity, check that `setWindowOpacity(0.0)` is called before `_fade_in.start()`.

- [ ] **Step 5: Commit**

```
git add ui.py
git commit -m "feat: fade-in on open, fade-out on quit"
```

---

## Task 3: Enhanced EXECUTING and ERROR states

**Files:**
- Modify: `ui.py` — `HudCanvas._step`, `HudCanvas.paintEvent`

- [ ] **Step 1: Wire EXECUTING state into `_step()`**

In `HudCanvas._step()`, replace the existing `speeds` and ring rotation lines:

```python
        state = self.state

        # ring and scan speeds per state
        if state == "EXECUTING":
            speeds = [2.5, -1.8, 3.5]
            scan_spd, scan2_spd = 5.0, -3.5
        elif state == "THINKING":
            speeds = [1.8, -1.2, 2.8]
            scan_spd, scan2_spd = 4.0, -2.5
        elif self.speaking or state == "SPEAKING":
            speeds = [1.3, -0.9, 2.0]
            scan_spd, scan2_spd = 3.0, -2.0
        elif state == "ERROR":
            speeds = [3.5, -2.5, 4.0]
            scan_spd, scan2_spd = 6.0, -4.0
        else:  # IDLE / LISTENING / MUTED
            speeds = [0.55, -0.35, 0.9]
            scan_spd, scan2_spd = 1.3, -0.75

        for i, spd in enumerate(speeds):
            self._rings[i] = (self._rings[i] + spd) % 360
        self._scan  = (self._scan  + scan_spd)  % 360
        self._scan2 = (self._scan2 + scan2_spd) % 360
```

- [ ] **Step 2: Add ERROR shake counter in `_step()`**

In `_step()`, after the ring/scan block, add:

```python
        # ERROR shake — decays over ~40 frames
        if state == "ERROR":
            if self._error_ticks > 0:
                self._error_ticks -= 1
                amp = self._error_ticks / 40.0 * 4.0
                self._shake_x = random.uniform(-amp, amp)
            else:
                self._shake_x = 0.0
        else:
            self._error_ticks = 0
            self._shake_x = 0.0
```

- [ ] **Step 3: Add `trigger_error()` method to HudCanvas**

```python
    def trigger_error(self):
        self.state = "ERROR"
        self._error_ticks = 40
        QTimer.singleShot(2000, lambda: self._clear_error())

    def _clear_error(self):
        if self.state == "ERROR":
            self.state = "LISTENING" if not self.muted else "MUTED"
```

- [ ] **Step 4: Apply shake and accent colors in `paintEvent`**

In `HudCanvas.paintEvent`, after `W, H = self.width(), self.height()` add:

```python
        cx = W / 2 + self._shake_x
        cy = H / 2
```

And remove the existing `cx, cy = W / 2, H / 2` line.

In the halo glow section, change the color selection:

```python
        state = self.state
        if self.muted:
            halo_col = C.MUTED_C
        elif state == "ERROR":
            halo_col = C.RED
        elif state == "EXECUTING":
            halo_col = C.ACC        # orange
        elif state == "THINKING":
            halo_col = C.ACC2       # yellow
        elif state == "LISTENING":
            halo_col = C.GREEN
        else:
            halo_col = C.PRI        # cyan

        for i in range(10):
            r   = r_face * (1.8 - i * 0.08)
            frc = 1.0 - i / 10
            a   = max(0, min(255, int(self._halo * 0.085 * frc)))
            col = qcol(halo_col, a)
            p.setPen(QPen(col, 1.5)); p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))
```

- [ ] **Step 5: Draw corner brackets for EXECUTING state**

In `HudCanvas.paintEvent`, just before the `# status text` section, add:

```python
        # EXECUTING — corner bracket indicators
        if state == "EXECUTING":
            bracket_sz = 18
            alpha = 160 + int(40 * math.sin(self._tick * 0.15))
            p.setPen(QPen(qcol(C.ACC, alpha), 2))
            for bx, by, dx, dy in [
                (4, 4, 1, 1), (W-4, 4, -1, 1),
                (4, H-4, 1, -1), (W-4, H-4, -1, -1),
            ]:
                p.drawLine(int(bx), int(by), int(bx + dx*bracket_sz), int(by))
                p.drawLine(int(bx), int(by), int(bx), int(by + dy*bracket_sz))
```

- [ ] **Step 6: Update status text section for all 6 states**

Replace the existing status text section (lines ~467–482) with:

```python
        sy = cy + fw * 0.40
        state = self.state
        if self.muted:
            txt, col = "⊘  MUTED",          qcol(C.MUTED_C)
        elif state == "SPEAKING":
            txt, col = "●  SPEAKING",        qcol(C.PRI)
        elif state == "THINKING":
            sym = "◈" if self._blink else "◇"
            txt, col = f"{sym}  THINKING",   qcol(C.ACC2)
        elif state == "EXECUTING":
            sym = "▷" if self._blink else "▶"
            txt, col = f"{sym}  EXECUTING",  qcol(C.ACC)
        elif state == "ERROR":
            sym = "✕" if self._blink else "!"
            txt, col = f"{sym}  ERROR",      qcol(C.RED)
        elif state == "LISTENING":
            sym = "●" if self._blink else "○"
            txt, col = f"{sym}  LISTENING",  qcol(C.GREEN)
        else:
            sym = "●" if self._blink else "○"
            txt, col = f"{sym}  {state}",    qcol(C.PRI)

        p.setPen(QPen(col, 1))
        p.setFont(QFont("Courier New", 11, QFont.Weight.Bold))
        p.drawText(QRectF(0, sy, W, 26), Qt.AlignmentFlag.AlignCenter, txt)
```

- [ ] **Step 7: Smoke test**

Run `python _test_ui.py` — window opens, boot sequence runs, transitions to normal mode.

- [ ] **Step 8: Commit**

```
git add ui.py
git commit -m "feat: EXECUTING/ERROR states with shake and corner brackets"
```

---

## Task 4: RMS-driven waveform for LISTENING state

**Files:**
- Modify: `ui.py` — `HudCanvas.paintEvent` waveform section, add `set_audio_level`
- Modify: `main.py` — call `set_audio_level` from audio callback

- [ ] **Step 1: Add `set_audio_level` to HudCanvas**

Add this method to `HudCanvas`:

```python
    def set_audio_level(self, rms: float):
        self._audio_rms = min(1.0, rms / 3000.0)
```

- [ ] **Step 2: Replace waveform section in `paintEvent`**

Find the `# waveform` section (lines ~488–505) and replace with:

```python
        # waveform
        wy = sy + 30
        N, bw = 36, 8
        wx0 = (W - N * bw) / 2
        state = self.state
        for i in range(N):
            if self.muted:
                hgt, cl = 2, qcol(C.MUTED_C)
            elif state == "SPEAKING":
                # sine wave simulation for TTS output
                phase = self._tick * 0.11 + i * 0.55
                hgt = int(4 + 14 * abs(math.sin(phase)) * (0.6 + 0.4 * math.sin(phase * 1.7)))
                cl  = qcol(C.PRI) if hgt > 10 else qcol(C.PRI_DIM)
            elif state == "LISTENING":
                # RMS-driven bars with per-bar noise
                base = self._audio_rms * 20
                hgt  = max(2, int(base * (0.7 + 0.6 * abs(math.sin(i * 1.1 + self._tick * 0.05)))))
                hgt  = min(hgt, 22)
                cl   = qcol(C.GREEN) if hgt > 8 else qcol(C.GREEN_D)
            elif state == "THINKING":
                hgt = int(4 + 8 * abs(math.sin(self._tick * 0.18 + i * 0.4)))
                cl  = qcol(C.ACC2)
            elif state == "EXECUTING":
                hgt = int(3 + 6 * abs(math.sin(self._tick * 0.22 + i * 0.3)))
                cl  = qcol(C.ACC)
            elif state == "ERROR":
                hgt = int(3 + 12 * abs(math.sin(self._tick * 0.35 + i * 0.8)))
                cl  = qcol(C.RED)
            else:
                hgt = int(2 + 2 * math.sin(self._tick * 0.09 + i * 0.6))
                cl  = qcol(C.PRI_DIM)

            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(cl))
            p.drawRect(
                QRectF(wx0 + i * bw + 1, wy + (22 - hgt), bw - 2, hgt)
            )
```

- [ ] **Step 3: Wire RMS in main.py audio callback**

In `main.py`, find the `sounddevice` audio input callback. Search for `sd.InputStream` or `def _audio_callback`. Add RMS computation and call to `set_audio_level`:

Find where audio frames are processed (around `_audio_callback` or the sounddevice stream). In the callback that receives audio frames, add after receiving the audio data:

```python
            # feed RMS to UI waveform
            rms = float(np.sqrt(np.mean(indata.astype(np.float32) ** 2)))
            if hasattr(self, 'ui') and self.ui is not None:
                try:
                    self.ui._win.hud.set_audio_level(rms)
                except Exception:
                    pass
```

- [ ] **Step 4: Smoke test**

Run the full app. In LISTENING state, speak into the mic — waveform bars should react.

- [ ] **Step 5: Commit**

```
git add ui.py main.py
git commit -m "feat: RMS-driven waveform for LISTENING, per-state waveform colors"
```

---

## Task 5: Weather panel in right sidebar

**Files:**
- Modify: `ui.py` — add `WeatherPanel` class, modify `MainWindow._build_right_panel`

- [ ] **Step 1: Add `WeatherPanel` class in `ui.py`**

Add this class before `MainWindow`:

```python
class WeatherPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            f"background: {C.PANEL2}; border: 1px solid {C.BORDER_A}; border-radius: 4px;"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(2)

        hdr = QLabel("▸ WEATHER")
        hdr.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent; border: none;")
        lay.addWidget(hdr)

        self._main_lbl = QLabel("--°C  —")
        self._main_lbl.setFont(QFont("Courier New", 11, QFont.Weight.Bold))
        self._main_lbl.setStyleSheet(f"color: {C.PRI}; background: transparent; border: none;")
        lay.addWidget(self._main_lbl)

        self._sub_lbl = QLabel("Loading...")
        self._sub_lbl.setFont(QFont("Courier New", 7))
        self._sub_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; border: none;")
        lay.addWidget(self._sub_lbl)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(600_000)  # every 10 min
        QTimer.singleShot(800, self._refresh)

    def _refresh(self):
        threading.Thread(target=self._fetch, daemon=True).start()

    def _fetch(self):
        import requests as _req
        try:
            cfg = {}
            if API_FILE.exists():
                cfg = json.loads(API_FILE.read_text(encoding="utf-8"))
            city = cfg.get("city", "Tashkent")
            r = _req.get(
                f"https://wttr.in/{city}?format=j1",
                timeout=8,
                headers={"User-Agent": "JARVIS/1.0"},
            )
            if r.status_code == 200:
                d    = r.json()
                curr = d["current_condition"][0]
                temp = curr["temp_C"]
                desc = curr["weatherDesc"][0]["value"]
                self._main_lbl.setText(f"{temp}°C")
                self._sub_lbl.setText(f"{desc}  ·  {city}")
            else:
                self._sub_lbl.setText("UNAVAILABLE")
        except Exception:
            self._sub_lbl.setText("OFFLINE")
```

- [ ] **Step 2: Add WeatherPanel to `_build_right_panel`**

In `MainWindow._build_right_panel`, after `lay.addWidget(_sec("ACTIVITY LOG"))` and the log widget (before the first `sep`), insert:

```python
        self._weather = WeatherPanel()
        lay.addWidget(self._weather)

        sep0 = QFrame(); sep0.setFrameShape(QFrame.Shape.HLine)
        sep0.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
        lay.addWidget(sep0)
```

- [ ] **Step 3: Smoke test**

Run the app — right panel should show "Loading..." then weather data for Tashkent within ~1 second.

- [ ] **Step 4: Commit**

```
git add ui.py
git commit -m "feat: weather panel in right sidebar (wttr.in, 10min refresh)"
```

---

## Task 6: Active Tasks and Notifications panels

**Files:**
- Modify: `ui.py` — add `TasksPanel`, `NotificationsPanel`, modify `_build_right_panel`, `MainWindow`

- [ ] **Step 1: Add `TasksPanel` class in `ui.py`**

Add before `MainWindow`:

```python
class TasksPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(80)
        self.setStyleSheet(
            f"background: {C.PANEL2}; border: 1px solid {C.BORDER_A}; border-radius: 4px;"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 5, 8, 5)
        lay.setSpacing(2)

        hdr = QLabel("▸ ACTIVE TASKS")
        hdr.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent; border: none;")
        lay.addWidget(hdr)

        self._labels: list[QLabel] = []
        for _ in range(3):
            lbl = QLabel("")
            lbl.setFont(QFont("Courier New", 7))
            lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; border: none;")
            lbl.setWordWrap(False)
            lay.addWidget(lbl)
            self._labels.append(lbl)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(1000)

    def _refresh(self):
        from agent.task_queue import get_queue
        try:
            tasks = get_queue().get_all_statuses()[-3:]
        except Exception:
            tasks = []

        _icons = {"running": "⟳", "completed": "✓", "failed": "✕",
                  "pending": "…", "cancelled": "–"}
        _cols  = {"running": C.PRI, "completed": C.GREEN, "failed": C.RED,
                  "pending": C.ACC2, "cancelled": C.TEXT_DIM}

        for i, lbl in enumerate(self._labels):
            if i < len(tasks):
                t    = tasks[i]
                ico  = _icons.get(t["status"], "?")
                col  = _cols.get(t["status"], C.TEXT_DIM)
                goal = t["goal"][:34]
                lbl.setText(f"{ico} {goal}")
                lbl.setStyleSheet(f"color: {col}; background: transparent; border: none;")
            else:
                lbl.setText("")
```

- [ ] **Step 2: Add `NotificationsPanel` class in `ui.py`**

Add before `MainWindow`:

```python
class NotificationsPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(82)
        self.setStyleSheet(
            f"background: {C.PANEL2}; border: 1px solid {C.BORDER_A}; border-radius: 4px;"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 5, 8, 5)
        lay.setSpacing(2)

        hdr = QLabel("▸ NOTIFICATIONS")
        hdr.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent; border: none;")
        lay.addWidget(hdr)

        self._labels: list[QLabel] = []
        for _ in range(3):
            lbl = QLabel("")
            lbl.setFont(QFont("Courier New", 7))
            lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; border: none;")
            lbl.setWordWrap(False)
            lay.addWidget(lbl)
            self._labels.append(lbl)

        self._items: list[str] = []

    def push(self, text: str):
        ts   = time.strftime("%H:%M")
        line = f"[{ts}] {text[:42]}"
        self._items.append(line)
        if len(self._items) > 3:
            self._items.pop(0)
        for i, lbl in enumerate(self._labels):
            if i < len(self._items):
                lbl.setText(self._items[i])
                lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent; border: none;")
            else:
                lbl.setText("")
```

- [ ] **Step 3: Add panels to `_build_right_panel` and expose `push_notification`**

In `MainWindow._build_right_panel`, before the return statement, add:

```python
        sep3 = QFrame(); sep3.setFrameShape(QFrame.Shape.HLine)
        sep3.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
        lay.addWidget(sep3)

        self._tasks_panel = TasksPanel()
        lay.addWidget(self._tasks_panel)

        self._notif_panel = NotificationsPanel()
        lay.addWidget(self._notif_panel)
```

- [ ] **Step 4: Add `push_notification` to MainWindow and JarvisUI**

In `MainWindow`, add:

```python
    def push_notification(self, text: str):
        self._notif_panel.push(text)
```

In `JarvisUI`, add:

```python
    def push_notification(self, text: str):
        self._win.push_notification(text)
```

- [ ] **Step 5: Call push_notification from main.py**

In `main.py`, find the section after each complete AI exchange (when response text is received). Locate where `self.ui.write_log` is called with the assistant's response and add after it:

```python
                self.ui.push_notification(text[:60] if text else "Response received")
```

- [ ] **Step 6: Smoke test**

Run the app — right panel should show "ACTIVE TASKS" and "NOTIFICATIONS" panels. Send a text command — notifications panel should update.

- [ ] **Step 7: Commit**

```
git add ui.py main.py
git commit -m "feat: active tasks and notifications panels in right sidebar"
```

---

## Task 7: Wire EXECUTING state in main.py

**Files:**
- Modify: `main.py` — `_execute_tool` method

- [ ] **Step 1: Set EXECUTING before running tools**

In `main.py`, in `_execute_tool()` (around line 904), replace the line:

```python
        self.ui.set_state("THINKING")
```

with:

```python
        self.ui.set_state("EXECUTING")
```

*(THINKING is set earlier when the message is being sent; EXECUTING is the right state during actual tool invocation.)*

- [ ] **Step 2: Wire ERROR state on tool failure**

In `_execute_tool()`, find the outer `try/except` that catches tool failures (around line 905+). Add error state trigger:

```python
        except Exception as exc:
            self.ui._win.hud.trigger_error()
            raise
```

If no outer try/except exists around the tool dispatch block, wrap the `if name == ...` dispatch with:

```python
        try:
            if name == "open_app":
                ...
            # ... all other elif name == ... blocks ...
        except Exception as exc:
            self.ui._win.hud.trigger_error()
            result = f"Error: {exc}"
```

- [ ] **Step 3: Restore LISTENING after tool completes**

After the giant if/elif chain returns a `result`, ensure state returns to LISTENING:

```python
        if not self.ui.muted:
            self.ui.set_state("LISTENING")
        return types.FunctionResponse(id=fc.id, name=name, response={"result": result})
```

Check that the existing `return` at the end of `_execute_tool` does this already — if so, skip.

- [ ] **Step 4: Commit**

```
git add main.py
git commit -m "feat: EXECUTING state during tool calls, ERROR state on failure"
```

---

## Task 8: Auto-startup on Windows boot

**Files:**
- Modify: `main.py` — add `_register_startup_windows()`, call on init

- [ ] **Step 1: Add `_register_startup_windows` function in main.py**

Add near the top of `main.py` after imports:

```python
def _register_startup_windows() -> None:
    """Copy start.bat to Windows Startup folder if not already there."""
    import sys
    if sys.platform != "win32":
        return
    try:
        startup_dir = Path(os.environ.get("APPDATA", "")) / \
            "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        if not startup_dir.exists():
            return
        dst = startup_dir / "JARVIS.bat"
        src = Path(__file__).parent / "start.bat"
        if dst.exists():
            return  # already registered
        if not src.exists():
            return
        import shutil
        shutil.copy2(src, dst)
        print(f"[JARVIS] ✅ Auto-startup registered: {dst}")
    except Exception as e:
        print(f"[JARVIS] ⚠️ Could not register startup: {e}")
```

- [ ] **Step 2: Call `_register_startup_windows()` on first init**

In `main.py`, find where `JarvisAgent` or the main class is initialized (the `if __name__ == "__main__":` block). Call the function before the main loop:

```python
if __name__ == "__main__":
    _register_startup_windows()
    # ... rest of startup ...
```

- [ ] **Step 3: Test**

Run the app once. Check that `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\JARVIS.bat` was created. Run the app again — it should print "already registered" (i.e., not copy again).

```
dir "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\"
```

Expected: `JARVIS.bat` present.

- [ ] **Step 4: Commit**

```
git add main.py
git commit -m "feat: auto-startup via Windows Startup folder, single-copy guard"
```

---

## Task 9: Compact mode (Ctrl+Shift+C)

**Files:**
- Modify: `ui.py` — `MainWindow.__init__`, add `_toggle_compact`

- [ ] **Step 1: Add compact mode fields and shortcut in `MainWindow.__init__`**

At the end of `MainWindow.__init__` (before closing), add:

```python
        self._compact = False
        self._normal_size = None
        compact_sc = QShortcut(QKeySequence("Ctrl+Shift+C"), self)
        compact_sc.activated.connect(self._toggle_compact)
```

- [ ] **Step 2: Add `_toggle_compact` method to MainWindow**

```python
    def _toggle_compact(self):
        if self._compact:
            # restore
            self._compact = False
            self._left_panel.show()
            self._right_panel.show()
            self._header.show()
            self._footer.show()
            if self._normal_size:
                self.resize(self._normal_size)
        else:
            # go compact
            self._compact = True
            self._normal_size = self.size()
            self._left_panel.hide()
            self._right_panel.hide()
            self._header.hide()
            self._footer.hide()
            self.resize(320, 200)
```

- [ ] **Step 3: Store panel references in `MainWindow.__init__`**

In `MainWindow.__init__`, where the central layout is built, store references to panels. Find where `_build_left_panel`, `_build_right_panel`, `_build_header`, `_build_footer` are called and assign to `self._left_panel`, `self._right_panel`, `self._header`, `self._footer`:

```python
        self._header = self._build_header()
        self._left_panel = self._build_left_panel()
        self._right_panel = self._build_right_panel()
        self._footer = self._build_footer()
```

*(Check the existing `__init__` code — it may already assign these or build them inline. Adjust variable names to match.)*

- [ ] **Step 4: Smoke test**

Run app. Press `Ctrl+Shift+C` — window shrinks to 320×200 with only the HUD visible. Press again — restores.

- [ ] **Step 5: Commit**

```
git add ui.py
git commit -m "feat: compact mode toggle Ctrl+Shift+C"
```

---

## Task 10: STARTUP → LISTENING transition after Gemini connects

**Files:**
- Modify: `main.py` — `announce_online` or session connect handler

- [ ] **Step 1: Find where Gemini session connects in main.py**

Search for where `write_log` says "online" or where the session is established. Find the `announce_online` call or similar.

Run: `grep -n "online\|connected\|ONLINE\|announce" main.py`

- [ ] **Step 2: Add state transition after connect**

Where the session connects and Jarvis announces "online", add:

```python
            self.ui.set_state("LISTENING")
            self.ui.push_notification("JARVIS systems online")
```

This transitions the HUD out of STARTUP into the first real state.

- [ ] **Step 3: Full integration test**

Run `python main.py` — full startup should:
1. Window fades in
2. Boot sequence plays in HUD
3. Gemini connects
4. State switches to LISTENING
5. Weather panel loads
6. "JARVIS systems online" appears in Notifications

- [ ] **Step 4: Final commit and push**

```
git add ui.py main.py
git commit -m "feat: wire STARTUP→LISTENING transition on Gemini connect"
git push origin yahyo
```

---

---

## Task 11: Always-sleep mode — Jarvis only responds when called

**Files:**
- Modify: `main.py` — init block, `_on_wake_word`

**Problem:** Jarvis only starts muted when openwakeword loads successfully (line ~761). If the model fails to init, Jarvis listens constantly. User wants Jarvis to ONLY respond when called.

- [ ] **Step 1: Always start muted regardless of wake word availability**

In `main.py`, find the wake-word init block (around line 756):

```python
        # Wake-word detector ("hey jarvis"). Starts muted; unmutes on wake.
        self._wake_detector = None
        if _WAKE_WORD_AVAILABLE:
            try:
                self._wake_detector = WakeWordDetector(on_wake=self._on_wake_word)
                self.ui.muted = True
                print("[JARVIS] 💤 Started in sleep mode — say 'hey jarvis' to wake")
            except Exception as e:
                print(f"[JARVIS] ⚠️ Wake-word init failed: {e}")
                self._wake_detector = None
```

Replace with:

```python
        # Always start muted — user must say "hey jarvis" or press F4 to activate
        self.ui.muted = True
        self._wake_detector = None
        if _WAKE_WORD_AVAILABLE:
            try:
                self._wake_detector = WakeWordDetector(on_wake=self._on_wake_word)
                print("[JARVIS] 💤 Wake-word active — say 'hey jarvis' to wake")
            except Exception as e:
                print(f"[JARVIS] ⚠️ Wake-word init failed: {e}")
                print("[JARVIS] 💤 Sleeping — press F4 to manually activate")
                self._wake_detector = None
        else:
            print("[JARVIS] 💤 Sleeping — press F4 to activate (wake-word unavailable)")
```

- [ ] **Step 2: Log that wake-word fallback is F4**

In `ui.py`, update the footer label to mention sleep mode:

Find in `_build_footer`:
```python
        lay.addWidget(_fl("[F4] Mute  ·  [F11] Fullscreen"))
```

Replace with:
```python
        lay.addWidget(_fl("[F4] Wake/Sleep  ·  [F11] Fullscreen  ·  [Ctrl+Shift+C] Compact"))
```

- [ ] **Step 3: Verify openwakeword model is downloaded**

Run in terminal:
```
python -c "import openwakeword; paths = openwakeword.get_pretrained_model_paths(); print([p for p in paths if 'hey_jarvis' in p])"
```

Expected: a list with at least one path containing `hey_jarvis`.

If empty, download model:
```
python -c "import openwakeword; openwakeword.utils.download_models()"
```

- [ ] **Step 4: Integration test**

Run `python main.py`:
1. Jarvis starts — microphone icon shows MUTED / sleeping
2. Say "hey jarvis" → mic unmutes, state → LISTENING
3. Ask something → Jarvis responds
4. Wait 8 seconds → auto-mutes back to sleep
5. OR press F4 → manually wake/sleep

- [ ] **Step 5: Commit and push**

```
git add main.py ui.py
git commit -m "fix: always start in sleep mode, wake via hey-jarvis or F4"
git push origin yahyo
```

---

## Self-Review

**Spec coverage check:**
- ✅ Cinematic startup sequence — Task 1 (boot text) + Task 2 (fade-in)
- ✅ Fade-out on quit — Task 2
- ✅ Auto-startup Windows — Task 8
- ✅ IDLE state — falls through to default in `_step`/`paintEvent`
- ✅ LISTENING state — Task 3 status text + Task 4 waveform
- ✅ THINKING state — Task 3
- ✅ SPEAKING state — Task 3 + existing particles
- ✅ EXECUTING state — Task 3 (corners) + Task 7 (wiring)
- ✅ ERROR state — Task 3 (shake/red) + Task 7 (trigger)
- ✅ RMS waveform — Task 4
- ✅ Weather panel — Task 5
- ✅ Active Tasks panel — Task 6
- ✅ Notifications panel — Task 6
- ✅ push_notification API — Task 6
- ✅ Compact mode — Task 9
- ✅ STARTUP→LISTENING transition — Task 10
- ✅ Always-sleep / wake-word-only mode — Task 11

**Type/name consistency:**
- `HudCanvas.set_audio_level(rms: float)` — defined Task 4 Step 1, used Task 4 Step 3 ✅
- `HudCanvas.trigger_error()` — defined Task 3 Step 3, used Task 7 Step 2 ✅
- `NotificationsPanel.push(text)` — defined Task 6 Step 2, called via `MainWindow.push_notification` Task 6 Step 4 ✅
- `JarvisUI.push_notification(text)` — defined Task 6 Step 4, called in Task 6 Step 5 and Task 10 Step 2 ✅
- `self._left_panel`, `self._right_panel`, `self._header`, `self._footer` — stored Task 9 Step 3, used Task 9 Step 2 ✅
- `self._compact`, `self._normal_size` — stored Task 9 Step 1, used Task 9 Step 2 ✅
