"""clap_detector — listens for double-clap pattern to toggle JARVIS on/off."""
import threading
import time
import numpy as np


class ClapDetector:
    """
    Runs a background thread listening to the microphone.
    Double clap (2 loud spikes within 0.8s) triggers on_double_clap callback.
    """

    THRESHOLD   = 0.45   # RMS amplitude threshold (0.0–1.0 float32)
    MIN_GAP     = 0.08   # min seconds between two claps (avoids echo)
    MAX_GAP     = 0.80   # max seconds between two claps for a "double"
    COOLDOWN    = 1.20   # seconds to ignore after triggering (avoid re-trigger)
    CHUNK       = 1024

    def __init__(self, on_double_clap):
        self._cb         = on_double_clap
        self._thread     = None
        self._running    = False
        self._clap_times: list[float] = []
        self._last_fired = 0.0
        self._lock       = threading.Lock()

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread  = threading.Thread(target=self._run, daemon=True, name="ClapDetector")
        self._thread.start()

    def stop(self):
        self._running = False

    def _run(self):
        try:
            import sounddevice as sd
        except ImportError:
            print("[ClapDetector] sounddevice not available")
            return

        def _callback(indata, frames, time_info, status):
            if not self._running:
                return
            rms = float(np.sqrt(np.mean(indata.astype(np.float32) ** 2)) / 32768)
            if rms < self.THRESHOLD:
                return

            now = time.time()

            # Cooldown after firing
            if now - self._last_fired < self.COOLDOWN:
                return

            with self._lock:
                # Remove old entries outside window
                self._clap_times = [t for t in self._clap_times if now - t < self.MAX_GAP]

                # Ignore if too close to last clap (echo/reverb)
                if self._clap_times and now - self._clap_times[-1] < self.MIN_GAP:
                    return

                self._clap_times.append(now)

                if len(self._clap_times) >= 2:
                    self._clap_times.clear()
                    self._last_fired = now
                    # Fire in separate thread to avoid blocking audio
                    threading.Thread(target=self._cb, daemon=True).start()

        try:
            with sd.InputStream(
                samplerate=16000,
                channels=1,
                dtype="int16",
                blocksize=self.CHUNK,
                callback=_callback,
            ):
                print("[ClapDetector] 👏 Listening for double clap...")
                while self._running:
                    time.sleep(0.1)
        except Exception as e:
            print(f"[ClapDetector] Error: {e}")
