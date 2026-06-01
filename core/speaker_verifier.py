"""speaker_verifier.py — Lightweight MFCC + GMM speaker verification.

No heavy ML deps — uses only scipy + sklearn (already in venv).
Enrollment: record 10-20s of voice → fit GMM → save model params as .npz.
Verification: compute MFCC → GMM log-likelihood vs threshold.
"""
import io
import os
import threading
import wave
from pathlib import Path

import numpy as np
from scipy.fft import dct
from scipy.signal import get_window

_PROFILE_DIR  = Path.home() / ".config" / "jarvis"
_PROFILE_PATH = _PROFILE_DIR / "voice_profile.npz"
_VOICE_ID_CFG = _PROFILE_DIR / "voice_id.cfg"   # master ON/OFF toggle (owner-only mode)

_N_MFCC       = 20
_N_MELS       = 40
_WIN_LEN      = 0.025   # 25 ms window
_HOP_LEN      = 0.010   # 10 ms hop
_N_COMPONENTS = 8
_THRESHOLD    = -25.0   # log-likelihood per frame

_state = {
    "gmm":       None,
    "enabled":   False,
    "active":    True,    # owner-only mode ON when a profile exists (toggleable)
    "threshold": _THRESHOLD,
}
_lock = threading.Lock()


# ── MFCC extraction (pure scipy) ─────────────────────────────────────────────

def _mel_filterbank(sr: int, n_fft: int, n_mels: int) -> np.ndarray:
    def hz_to_mel(hz):  return 2595 * np.log10(1 + hz / 700)
    def mel_to_hz(mel): return 700 * (10 ** (mel / 2595) - 1)

    low_mel  = hz_to_mel(0)
    high_mel = hz_to_mel(sr / 2)
    mel_pts  = np.linspace(low_mel, high_mel, n_mels + 2)
    hz_pts   = mel_to_hz(mel_pts)
    bins     = np.floor((n_fft + 1) * hz_pts / sr).astype(int)

    fb = np.zeros((n_mels, n_fft // 2 + 1))
    for m in range(1, n_mels + 1):
        f_left, f_center, f_right = bins[m - 1], bins[m], bins[m + 1]
        for k in range(f_left, f_center):
            if f_center > f_left:
                fb[m - 1, k] = (k - f_left) / (f_center - f_left)
        for k in range(f_center, f_right):
            if f_right > f_center:
                fb[m - 1, k] = (f_right - k) / (f_right - f_center)
    return fb


def _extract_mfcc(raw_bytes: bytes, sr: int = 16000) -> np.ndarray | None:
    """Extract MFCC matrix (T, N_MFCC) from raw PCM int16 bytes."""
    try:
        samples = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32)
        if len(samples) < sr * 0.3:
            return None

        mx = np.abs(samples).max()
        if mx > 0:
            samples /= mx

        win_samples = int(_WIN_LEN * sr)
        hop_samples = int(_HOP_LEN * sr)
        n_fft       = 1 << (win_samples - 1).bit_length()
        window      = get_window("hamming", win_samples)
        fb          = _mel_filterbank(sr, n_fft, _N_MELS)

        frames = []
        for start in range(0, len(samples) - win_samples, hop_samples):
            frame   = samples[start:start + win_samples] * window
            spec    = np.abs(np.fft.rfft(frame, n=n_fft)) ** 2
            mel_e   = fb @ spec
            mel_e   = np.where(mel_e > 1e-10, mel_e, 1e-10)
            mfcc    = dct(np.log(mel_e), type=2, n=_N_MFCC, norm="ortho")
            frames.append(mfcc)

        return np.vstack(frames) if frames else None
    except Exception as e:
        print(f"[SpeakerVerifier] MFCC error: {e}")
        return None


# ── GMM score (manual, without re-loading sklearn object) ────────────────────

def _gmm_score(X: np.ndarray, weights, means, covariances) -> float:
    """Compute mean log-likelihood of X under a diagonal-cov GMM."""
    n_samples, n_features = X.shape
    n_comp = len(weights)
    log_probs = np.zeros((n_samples, n_comp))

    for k in range(n_comp):
        diff = X - means[k]
        cov  = np.maximum(covariances[k], 1e-6)
        log_det  = np.sum(np.log(cov))
        maha     = np.sum(diff ** 2 / cov, axis=1)
        log_probs[:, k] = (
            np.log(weights[k])
            - 0.5 * (n_features * np.log(2 * np.pi) + log_det + maha)
        )

    # log-sum-exp per frame
    log_max   = log_probs.max(axis=1, keepdims=True)
    log_like  = log_max.squeeze() + np.log(
        np.exp(log_probs - log_max).sum(axis=1)
    )
    return float(log_like.mean())


# ── Persistence (.npz — safe numpy binary) ───────────────────────────────────

def _save_profile(weights, means, covariances, threshold):
    _PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        str(_PROFILE_PATH),
        weights=weights,
        means=means,
        covariances=covariances,
        threshold=np.array([threshold]),
    )
    os.chmod(_PROFILE_PATH, 0o600)


def _load_profile():
    if not _PROFILE_PATH.exists():
        return
    try:
        data = np.load(str(_PROFILE_PATH))
        with _lock:
            _state["gmm"] = {
                "weights":     data["weights"],
                "means":       data["means"],
                "covariances": data["covariances"],
            }
            _state["threshold"] = float(data["threshold"][0])
            _state["enabled"]   = True
        print("[SpeakerVerifier] Profile loaded.")
    except Exception as e:
        print(f"[SpeakerVerifier] Load error: {e}")


# ── Public API ────────────────────────────────────────────────────────────────

def load_profile():
    _load_profile()


def is_enabled() -> bool:
    return _state["enabled"] and _state["gmm"] is not None


# ── Owner-only master switch (Voice ID toggle, persisted) ─────────────────────

def _load_active():
    """Read persisted ON/OFF. Default ON (owner-only) when config absent."""
    try:
        if _VOICE_ID_CFG.exists():
            _state["active"] = (_VOICE_ID_CFG.read_text(encoding="utf-8").strip().lower() == "on")
    except Exception:
        _state["active"] = True

def _save_active(active: bool):
    try:
        _PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        _VOICE_ID_CFG.write_text("on" if active else "off", encoding="utf-8")
    except Exception as e:
        print(f"[SpeakerVerifier] Cannot save Voice ID state: {e}")

def is_active() -> bool:
    """True when owner-only voice mode is enabled by the user."""
    return _state["active"]

def set_active(active: bool) -> str:
    """Turn owner-only mode ON/OFF without deleting the enrolled profile."""
    active = bool(active)
    _save_active(active)
    with _lock:
        _state["active"] = active
    print(f"[SpeakerVerifier] Owner-only mode {'ON' if active else 'OFF'}.")
    return "on" if active else "off"


def _calibrate_threshold(mfcc, weights, means, covariances) -> tuple:
    """Derive an owner-relative threshold from enrollment audio alone.

    Scores overlapping windows of the owner's own speech, then sets the
    threshold just below the owner's weakest windows. This adapts to the
    speaker's voice + microphone instead of a brittle fixed value, so the
    owner passes reliably while clearly different voices fall below.
    Returns (threshold, owner_mean, owner_min).
    """
    win, step = 150, 75   # 1.5s windows, 0.75s overlap (hop=10ms)
    scores = []
    for start in range(0, max(1, len(mfcc) - win + 1), step):
        w = mfcc[start:start + win]
        if len(w) >= 30:
            scores.append(_gmm_score(w, weights, means, covariances))
    if len(scores) >= 4:
        import numpy as _np
        arr = _np.array(scores)
        # Generous margin: live speech varies more than enrollment, so the owner
        # must stay comfortably above threshold. Rejecting the owner is the worst
        # failure; a clearly different voice/TV still scores far lower than this.
        thr = float(_np.percentile(arr, 8)) - 6.0
        owner_mean, owner_min = float(arr.mean()), float(arr.min())
    else:
        base = _gmm_score(mfcc, weights, means, covariances)
        thr, owner_mean, owner_min = base - 8.0, base, base
    thr = max(min(thr, -8.0), -45.0)   # clamp to a sane range
    return thr, owner_mean, owner_min


def enroll(raw_pcm: bytes, sr: int = 16000) -> str:
    """Fit GMM on enrollment audio (need ≥10s of speech) + auto-calibrate threshold."""
    from sklearn.mixture import GaussianMixture

    mfcc = _extract_mfcc(raw_pcm, sr)
    if mfcc is None or len(mfcc) < 50:
        return "Ovoz namunasi juda qisqa (kamida 5 soniya tinmay gapiring)."

    n_comp = min(_N_COMPONENTS, len(mfcc) // 5)
    gmm    = GaussianMixture(
        n_components=n_comp,
        covariance_type="diag",
        max_iter=200,
        random_state=42,
    )
    try:
        gmm.fit(mfcc)
    except Exception as e:
        return f"GMM o'rgatishda xato: {e}"

    weights     = gmm.weights_
    means       = gmm.means_
    covariances = gmm.covariances_

    threshold, owner_mean, owner_min = _calibrate_threshold(mfcc, weights, means, covariances)

    with _lock:
        _state["gmm"]       = {"weights": weights, "means": means, "covariances": covariances}
        _state["enabled"]   = True
        _state["active"]    = True   # enrolling turns owner-only mode ON
        _state["threshold"] = threshold

    _save_profile(weights, means, covariances, threshold)
    _save_active(True)

    print(f"[SpeakerVerifier] Enrolled. Frames={len(mfcc)}, "
          f"owner_mean={owner_mean:.1f}, owner_min={owner_min:.1f}, thr={threshold:.1f}")
    return (f"✅ Ovoz profili saqlandi! Endi Jarvis faqat sizning ovozingizga javob beradi.\n"
            f"({len(mfcc)} frame | egasi LL≈{owner_mean:.1f} | chegara={threshold:.1f})")


def verify(raw_pcm: bytes, sr: int = 16000) -> bool:
    if not is_enabled() or not _state["active"]:
        return True

    mfcc = _extract_mfcc(raw_pcm, sr)
    if mfcc is None or len(mfcc) < 10:
        return True

    with _lock:
        gmm       = _state["gmm"]
        threshold = _state["threshold"]

    try:
        ll = _gmm_score(mfcc, gmm["weights"], gmm["means"], gmm["covariances"])
        print(f"[SpeakerVerifier] LL={ll:.2f} threshold={threshold:.2f} → {'✅' if ll >= threshold else '❌'}")
        return ll >= threshold
    except Exception as e:
        print(f"[SpeakerVerifier] Verify error: {e}")
        return True


def reset():
    with _lock:
        _state["gmm"]     = None
        _state["enabled"] = False
    if _PROFILE_PATH.exists():
        _PROFILE_PATH.unlink()
    print("[SpeakerVerifier] Profile reset.")


def set_threshold(t: float):
    with _lock:
        _state["threshold"] = float(t)
    if _state["gmm"] is not None:
        g = _state["gmm"]
        _save_profile(g["weights"], g["means"], g["covariances"], float(t))


def get_info() -> str:
    if not is_enabled():
        return "Ovoz profili yo'q. 'ovozimni esla' yoki 'voice_auth enroll' deng."
    with _lock:
        thr = _state["threshold"]
    return f"Ovoz profili faol (threshold={thr:.1f})."
