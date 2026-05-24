# JARVIS Windows Enhancement — Design Spec
**Date:** 2026-05-23  
**Stack:** PyQt6, Python, Gemini API  
**Scope:** Windows only (Mac/Linux in a follow-up session)

---

## 1. Cinematic Startup Sequence

### Behavior
Window opens at 0% opacity and fades in over 1.2 seconds using `QPropertyAnimation` on `windowOpacity`.

During fade-in, `HudCanvas` shows a boot sequence overlay:
```
INITIALISING CORE SYSTEMS...

VOICE SYSTEM.......... OK
MEMORY MODULE......... OK
AUTOMATION ENGINE..... OK
GEMINI API............ CONNECTING
GEMINI API............ ONLINE

J.A.R.V.I.S SYSTEMS ONLINE.
```
Each line appears with a 300ms stagger. Lines are drawn via `QPainter` in a new `STARTUP` state of `HudCanvas`.

### Implementation
- New `HudCanvas` state: `"STARTUP"` — renders boot text overlay on top of the normal HUD
- `JarvisUI.__init__` sets `windowOpacity(0)`, starts fade animation, triggers boot sequence
- After sequence completes (~3.5s total), state transitions to `"IDLE"`
- `main.py` calls `ui.announce_online()` after Gemini connects — this triggers the final "SYSTEMS ONLINE" line and state change

### Shutdown
- `_real_quit()` triggers a fade-out animation (0.8s) before calling `app.quit()`
- Uses `QPropertyAnimation` on `windowOpacity` with `finished` signal

---

## 2. Auto-Startup (Windows)

### Behavior
On first launch, Jarvis registers itself in the Windows Startup folder silently:
`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\JARVIS.lnk`

The shortcut points to `start.bat` (already in the repo).

### Single-instance guard
Already implemented (commit `eb14a91`). No changes needed — duplicate launches focus the existing window.

### Implementation
- New function `_register_startup_windows()` in `main.py`
- Uses `winshell` or `win32com.shell` to create `.lnk` shortcut
- Falls back to copying `start.bat` to Startup folder if COM unavailable
- Called once on startup, skipped if shortcut already exists
- Can be toggled via a checkbox in SetupOverlay or settings

---

## 3. Six Voice States

### State Definitions

| State | Trigger | Visual |
|-------|---------|--------|
| `IDLE` | Default, no activity | Slow pulse, dim cyan, rings rotate at 0.3x speed |
| `LISTENING` | Mic active, waiting for speech | Green accent, waveform bars react to mic RMS, rings at 1x |
| `THINKING` | Sent to Gemini, waiting response | Fast-spinning scan arcs, blue accent, orbital dots |
| `SPEAKING` | TTS playing audio | Core pulses with amplitude, bright cyan, waveform simulates voice |
| `EXECUTING` | Tool call in progress | Corner progress indicators, orange accent, scan lines |
| `ERROR` | Exception / failed tool | Red flicker, core shake (translate offset ±3px), "ERROR" text overlay |

### Waveform Visualizer
- Strip of 32 vertical bars at bottom of `HudCanvas`
- `LISTENING`: driven by real mic RMS sampled every 50ms, passed via `set_audio_level(rms: float)`
- `SPEAKING`: driven by a sine-wave simulation that varies with `_tick`
- Other states: bars flatten with easing

### State transitions
`HudCanvas.set_state(state: str)` — replaces current `self.state` and `self.speaking` boolean.  
`main.py` calls this at the right moments:
- Before sending to Gemini → `"THINKING"`
- When TTS starts → `"SPEAKING"`
- When tool executes → `"EXECUTING"`
- On exception → `"ERROR"` (auto-clears after 2s)
- Default → `"IDLE"`

---

## 4. New Dashboard Panels

### Weather Panel (right sidebar, below system metrics)
- Source: `wttr.in/{city}?format=j1` (JSON, free, no API key)
- Shows: temperature, condition text, weather emoji icon
- City: read from `config/api_keys.json` as `"city"` key, default `"Tashkent"`
- Refresh: every 10 minutes via `QTimer`
- Failure: shows last cached value or "WEATHER UNAVAILABLE"

### Active Tasks Panel (right sidebar)
- Reads from `agent/task_queue.py` task list
- Shows last 3 active/completed tasks with status icons:
  - `⟳` running, `✓` done, `✕` error
- Updates every 500ms via `QTimer`

### Notifications Panel (right sidebar, bottom)
- Ring buffer of last 3 events (voice commands received, tool results)
- `JarvisUI.push_notification(text: str)` — called from `main.py` after each exchange
- Each card shows timestamp + truncated text (max 48 chars)
- Cards fade in with `QPropertyAnimation` on opacity

---

## 5. UI Polish

### Animated panel borders
- Panels in left/right sidebars get a slow glow pulse on their border color
- Implemented via a shared `_border_alpha` float on `JarvisUI` updated by `QTimer` every 50ms
- Border color interpolates between `C.BORDER` and `C.BORDER_B` using sine wave

### Compact mode
- Keyboard shortcut `Ctrl+Shift+C` or button in header
- Window resizes to 320×120px: only HUD core + waveform strip visible
- All panels hidden, header hidden
- Toggle back restores previous size

### Hover effects on buttons
- Left panel nav buttons get `QSS :hover` state with `background: #0a2535; border-left: 2px solid #00d4ff`

---

## 6. Files Changed

| File | Change |
|------|--------|
| `ui.py` | Startup fade, 6 states, waveform, weather/tasks/notifications panels, compact mode, border glow, hover styles |
| `main.py` | Call `set_state()` at right moments, `push_notification()`, `_register_startup_windows()` |
| `config/api_keys.json` | Add `"city"` field (default "Tashkent") |
| `requirements.txt` | Add `pywin32` (for startup shortcut, Windows only) |

---

## Out of Scope (v2)
- Draggable widgets (needs QGraphicsScene)
- Music controls (no stable cross-platform media API)
- Google Calendar integration
- Electron/React rewrite
- Mac/Linux support (separate session)
