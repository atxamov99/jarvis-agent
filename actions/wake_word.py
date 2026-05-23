"""Wake-word detector using openwakeword's pretrained 'hey_jarvis' model.

Architecture (designed to avoid segfaults under PipeWire/PortAudio):
- `feed()` is called from the real-time audio callback. It ONLY pushes
  audio into a bounded queue and returns immediately.
- A dedicated worker thread pulls from the queue, accumulates 1280-sample
  frames, runs ONNX inference, and fires `on_wake` when the score crosses
  the threshold.
- Speex noise suppression is enabled to reject external/background noise.
- A simple VAD energy gate skips clearly-silent frames to save CPU.
"""
import numpy as np
import threading
import queue
import time


class WakeWordDetector:
    SAMPLE_RATE   = 16000
    FRAME_SAMPLES = 1280     # ~80 ms at 16 kHz
    MODEL_KEY     = "hey_jarvis_v0.1"
    MAX_QUEUE     = 50       # ~4 s of audio backlog — drop older if behind

    def __init__(
        self,
        on_wake,
        threshold: float    = 0.42,  # was 0.5 — more sensitive to quiet "hey jarvis"
        cooldown_s: float   = 2.0,
        energy_floor: int   = 80,    # was 250 — matches noise gate, catches softer speech
    ):
        import openwakeword
        from openwakeword.model import Model

        paths = openwakeword.get_pretrained_model_paths()
        jarvis_paths = [p for p in paths if "hey_jarvis" in p]
        if not jarvis_paths:
            raise RuntimeError("hey_jarvis model not bundled with openwakeword install")

        # Try with Speex noise suppression — fall back gracefully if missing.
        try:
            self.model = Model(
                wakeword_model_paths=[jarvis_paths[0]],
                enable_speex_noise_suppression=True,
            )
            print("[WakeWord] 🛡️  Speex noise suppression: ON")
        except Exception as e:
            print(f"[WakeWord] ⚠️ Noise suppression unavailable ({e}) — using raw audio")
            self.model = Model(wakeword_model_paths=[jarvis_paths[0]])

        self.on_wake     = on_wake
        self.threshold   = threshold
        self.cooldown_s  = cooldown_s
        self.energy_floor = energy_floor

        self._queue      = queue.Queue(maxsize=self.MAX_QUEUE)
        self._enabled    = threading.Event()
        self._enabled.set()
        self._stop       = threading.Event()
        self._last_fire  = 0.0
        self._buf        = np.array([], dtype=np.int16)

        self._worker = threading.Thread(
            target=self._run_worker, name="WakeWord", daemon=True
        )
        self._worker.start()
        print(f"[WakeWord] 🎯 hey_jarvis ready (threshold={threshold}, "
              f"energy_floor={energy_floor})")

    def feed(self, indata):
        """Audio-callback safe: push samples and return immediately."""
        if not self._enabled.is_set():
            return
        try:
            arr = np.asarray(indata, dtype=np.int16).reshape(-1).copy()
            self._queue.put_nowait(arr)
        except queue.Full:
            # Behind on processing — drop the chunk silently.
            pass

    def pause(self):
        self._enabled.clear()
        # Drain pending audio so we don't process stale frames on resume.
        try:
            while True:
                self._queue.get_nowait()
        except queue.Empty:
            pass
        self._buf = np.array([], dtype=np.int16)

    def resume(self):
        self._buf = np.array([], dtype=np.int16)
        self._enabled.set()

    def stop(self):
        self._stop.set()
        self._enabled.clear()

    def _run_worker(self):
        while not self._stop.is_set():
            try:
                chunk = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue
            if not self._enabled.is_set():
                continue

            self._buf = (
                np.concatenate([self._buf, chunk]) if self._buf.size else chunk
            )

            while self._buf.size >= self.FRAME_SAMPLES and self._enabled.is_set():
                frame     = self._buf[:self.FRAME_SAMPLES]
                self._buf = self._buf[self.FRAME_SAMPLES:]

                # Cheap VAD: skip near-silent frames (saves ~80% CPU when quiet).
                rms = float(np.sqrt(np.mean(frame.astype(np.float32) ** 2)))
                if rms < self.energy_floor:
                    continue

                try:
                    scores = self.model.predict(frame)
                except Exception as e:
                    print(f"[WakeWord] ⚠️ predict error: {e}")
                    continue

                score = scores.get(self.MODEL_KEY, 0.0)
                now   = time.time()
                if score >= self.threshold and (now - self._last_fire) > self.cooldown_s:
                    self._last_fire = now
                    print(f"[WakeWord] 🟢 hey_jarvis detected (score={score:.3f}, rms={rms:.0f})")
                    try:
                        self.on_wake()
                    except Exception as e:
                        print(f"[WakeWord] callback error: {e}")
                    self._buf = np.array([], dtype=np.int16)
                    break
