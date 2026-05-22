"""Wake-word detector using openwakeword's pretrained 'hey_jarvis' model.

Feeds raw 16 kHz mono int16 audio chunks; triggers a callback when the
phrase 'hey jarvis' (or close variants) is detected.
"""
import numpy as np
import threading
import time


class WakeWordDetector:
    SAMPLE_RATE   = 16000
    FRAME_SAMPLES = 1280   # ~80 ms — openwakeword's expected frame size
    MODEL_KEY     = "hey_jarvis_v0.1"

    def __init__(self, on_wake, threshold: float = 0.5, cooldown_s: float = 2.0):
        import openwakeword
        from openwakeword.model import Model

        paths = openwakeword.get_pretrained_model_paths()
        jarvis_paths = [p for p in paths if "hey_jarvis" in p]
        if not jarvis_paths:
            raise RuntimeError("hey_jarvis model not bundled with openwakeword install")

        self.model      = Model(wakeword_model_paths=[jarvis_paths[0]])
        self.on_wake    = on_wake
        self.threshold  = threshold
        self.cooldown_s = cooldown_s
        self._enabled   = True
        self._lock      = threading.Lock()
        self._buf       = np.array([], dtype=np.int16)
        self._last_fire = 0.0
        print(f"[WakeWord] 🎯 hey_jarvis model ready (threshold={threshold})")

    def feed(self, indata):
        """Feed int16 mono samples. Safe to call from audio callback thread."""
        with self._lock:
            if not self._enabled:
                return
            flat = np.asarray(indata, dtype=np.int16).reshape(-1)
            self._buf = np.concatenate([self._buf, flat]) if self._buf.size else flat

            while self._buf.size >= self.FRAME_SAMPLES:
                chunk     = self._buf[:self.FRAME_SAMPLES]
                self._buf = self._buf[self.FRAME_SAMPLES:]
                try:
                    scores = self.model.predict(chunk)
                except Exception as e:
                    print(f"[WakeWord] ⚠️ predict error: {e}")
                    continue

                score = scores.get(self.MODEL_KEY, 0.0)
                now   = time.time()
                if score >= self.threshold and (now - self._last_fire) > self.cooldown_s:
                    self._last_fire = now
                    print(f"[WakeWord] 🟢 hey_jarvis detected (score={score:.3f})")
                    try:
                        self.on_wake()
                    except Exception as e:
                        print(f"[WakeWord] callback error: {e}")
                    self._buf = np.array([], dtype=np.int16)
                    return

    def pause(self):
        with self._lock:
            self._enabled = False

    def resume(self):
        with self._lock:
            self._enabled = True
            self._buf = np.array([], dtype=np.int16)
