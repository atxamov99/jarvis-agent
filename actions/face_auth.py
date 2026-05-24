"""face_auth.py — Face enrollment and verification management. NOT pushed to GitHub."""
from core import face_verifier


def face_auth(parameters=None, response=None, player=None, session_memory=None) -> str:
    params    = parameters or {}
    action    = (params.get("action") or "status").lower().strip()
    seconds   = int(params.get("seconds", 5))
    cam_index = int(params.get("cam", 0))
    threshold = params.get("threshold")

    if not face_verifier.is_available():
        return (
            "face_recognition kutubxonasi o'rnatilmagan.\n"
            "`pip install face-recognition` qiling (dlib kerak)."
        )

    # ── STATUS ────────────────────────────────────────────────────────────────
    if action in ("status", "holat"):
        return face_verifier.get_info()

    # ── ENROLL ────────────────────────────────────────────────────────────────
    if action in ("enroll", "o'rgat", "esla", "yodla"):
        if seconds < 3:
            seconds = 3
        if seconds > 30:
            seconds = 30
        if player: player.write_log(f"[FaceAuth] Starting {seconds}s enrollment...")
        return face_verifier.enroll(seconds=seconds, cam_index=cam_index, player=player)

    # ── VERIFY (manual one-shot check) ────────────────────────────────────────
    if action in ("verify", "tekshir", "kim"):
        if not face_verifier.is_enabled():
            return "Avval yuzingizni o'rgating ('face_auth enroll')."
        ok = face_verifier.verify_once(cam_index=cam_index)
        return "✅ Bu siz — egasi!" if ok else "❌ Noto'g'ri yuz — begona!"

    # ── RESET ─────────────────────────────────────────────────────────────────
    if action in ("reset", "o'chir"):
        face_verifier.reset()
        return "✅ Yuz profili o'chirildi."

    # ── THRESHOLD ─────────────────────────────────────────────────────────────
    if action in ("threshold", "sezgirlik") and threshold is not None:
        face_verifier.set_threshold(float(threshold))
        return f"✅ Yuz threshold {float(threshold):.2f} ga o'rnatildi."

    return "Amallar: enroll | verify | reset | status | threshold"
