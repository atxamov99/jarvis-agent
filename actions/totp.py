"""totp.py — Generate TOTP 2FA codes and manage secrets securely."""
import json
import time
from pathlib import Path

_STORE = Path.home() / ".config" / "jarvis" / "totp_secrets.json"


def _load() -> dict:
    try:
        return json.loads(_STORE.read_text())
    except Exception:
        return {}


def _save(data: dict):
    _STORE.parent.mkdir(parents=True, exist_ok=True)
    _STORE.write_text(json.dumps(data, indent=2))
    _STORE.chmod(0o600)


def _get_code(secret: str) -> tuple[str, int]:
    import pyotp
    totp      = pyotp.TOTP(secret)
    code      = totp.now()
    remaining = 30 - int(time.time()) % 30
    return code, remaining


def totp(parameters=None, response=None, player=None, session_memory=None) -> str:
    params  = parameters or {}
    action  = (params.get("action") or "get").lower().strip()
    name    = (params.get("name") or "").strip()
    secret  = (params.get("secret") or "").strip().upper().replace(" ", "")

    # ── GET CODE ──────────────────────────────────────────────────────────────
    if action in ("get", "kod", "generate", "oq"):
        store = _load()
        if not store:
            return "Saqlangan TOTP sirlar yo'q. Avval 'add' orqali qo'shing."
        if name:
            key = name.lower()
            entry = next((v for k, v in store.items() if key in k.lower()), None)
            if not entry:
                available = ", ".join(store.keys())
                return f"'{name}' topilmadi. Mavjud: {available}"
            sec = entry if isinstance(entry, str) else entry.get("secret", "")
            label = name
        else:
            label, entry = next(iter(store.items()))
            sec = entry if isinstance(entry, str) else entry.get("secret", "")

        try:
            code, remaining = _get_code(sec)
        except Exception as e:
            return f"TOTP xatosi: {e}"

        if player: player.write_log(f"[TOTP] {label}: {code} ({remaining}s)")
        return f"{label} TOTP kodi: {code}  ({remaining} soniya qoldi)"

    # ── ADD ───────────────────────────────────────────────────────────────────
    if action in ("add", "qo'sh", "saqlash"):
        if not name or not secret:
            return "Nom va secret kerak: name='Github', secret='JBSWY3DPEHPK3PXP'"
        store = _load()
        store[name.lower()] = secret
        _save(store)
        if player: player.write_log(f"[TOTP] Added: {name}")
        return f"TOTP qo'shildi: {name}"

    # ── LIST ──────────────────────────────────────────────────────────────────
    if action in ("list", "ro'yxat", "hammasi"):
        store = _load()
        if not store:
            return "TOTP sirlar yo'q."
        lines = []
        for label, entry in store.items():
            sec = entry if isinstance(entry, str) else entry.get("secret", "")
            try:
                code, remaining = _get_code(sec)
                lines.append(f"• {label}: {code}  ({remaining}s)")
            except Exception:
                lines.append(f"• {label}: [xato]")
        return f"Barcha TOTP kodlar:\n" + "\n".join(lines)

    # ── DELETE ────────────────────────────────────────────────────────────────
    if action in ("delete", "o'chir", "remove"):
        if not name:
            return "O'chirish uchun nom ko'rsating."
        store = _load()
        key   = next((k for k in store if name.lower() in k.lower()), None)
        if not key:
            return f"'{name}' topilmadi."
        del store[key]
        _save(store)
        if player: player.write_log(f"[TOTP] Deleted: {key}")
        return f"O'chirildi: {key}"

    return "Amallar: get | add | list | delete"
