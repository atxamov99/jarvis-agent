"""face_auth.py — Face enrollment and verification management. NOT pushed to GitHub."""
from core import face_verifier


def face_auth(parameters=None, response=None, player=None, session_memory=None) -> str:
    params    = parameters or {}
    action    = (params.get("action") or "status").lower().strip()
    seconds   = int(params.get("seconds", 5))
    cam_index = int(params.get("cam", 0))
    threshold = params.get("threshold")

    # ── PREVIEW (jonli kamera oynasi — ko'zgu) ────────────────────────────────
    if action in ("preview", "ko'rsat", "korsat", "kamera", "yuz_kor"):
        if player and hasattr(player, "open_preview_window"):
            player.open_preview_window(cam_index)
            return "📷 Kamera oynasi ochildi."
        return "📷 UI mavjud emas."

    if action in ("preview_stop", "kamera_yop", "oyna_yop"):
        # Preview window closes itself; just a confirmation message
        return "📷 Kamera oynasini o'z X tugmasidan yoping."

    # ── STATUS ────────────────────────────────────────────────────────────────
    if action in ("status", "holat"):
        return face_verifier.get_info()

    # ── ENROLL ────────────────────────────────────────────────────────────────
    if action in ("enroll", "o'rgat", "esla", "yodla"):
        if player and hasattr(player, "open_enroll_dialog"):
            player.open_enroll_dialog(cam_index)
            return "📷 Yuz ro'yxatdan o'tkazish oynasi ochildi."
        # Fallback: silent enrollment if no UI
        return face_verifier.enroll(seconds=max(3, min(seconds, 30)),
                                    cam_index=cam_index, player=player,
                                    show_preview=False)

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
