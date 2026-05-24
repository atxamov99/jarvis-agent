"""qr_code.py — Generate QR codes and decode QR images."""
import subprocess
from pathlib import Path

_QR_DIR = Path.home() / "Pictures" / "QRCodes"

try:
    import qrcode as _qr_lib
    from PIL import Image as _PIL_Image
    _HAS_QR = True
except ImportError:
    _HAS_QR = False

try:
    from pyzbar import pyzbar as _pyzbar
    from PIL import Image as _PIL_Image
    _HAS_PYZBAR = True
except Exception:
    _HAS_PYZBAR = False


def _qr_dir() -> Path:
    _QR_DIR.mkdir(parents=True, exist_ok=True)
    return _QR_DIR


def qr_code(parameters=None, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    action = (params.get("action") or "generate").lower().strip()

    # ── GENERATE ──────────────────────────────────────────────────────────────
    if action in ("generate", "yaratish", "qr", "create"):
        if not _HAS_QR:
            return "qrcode[pil] kutubxonasi o'rnatilmagan. `pip install qrcode[pil]` qiling."

        data = params.get("data") or params.get("text") or params.get("url") or ""
        if not data:
            return "QR kod uchun 'data' parametrini bering (matn, URL, va boshqa)."

        size = int(params.get("size", 10))
        name = params.get("name") or "qr"
        fname = f"{name}.png"
        path = _qr_dir() / fname

        qr = _qr_lib.QRCode(
            version=None,
            error_correction=_qr_lib.constants.ERROR_CORRECT_M,
            box_size=size,
            border=4,
        )
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        img.save(str(path))

        if player: player.write_log(f"[QR] Generated: {fname}")
        subprocess.Popen(["xdg-open", str(path)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return f"✅ QR kod yaratildi:\n{path}\nMazmun: {data[:80]}"

    # ── DECODE ────────────────────────────────────────────────────────────────
    if action in ("decode", "o'qish", "read", "scan"):
        if not _HAS_PYZBAR:
            return (
                "QR o'qish uchun pyzbar + libzbar0 kerak.\n"
                "`sudo apt install libzbar0 && pip install pyzbar` qiling."
            )
        file_path = params.get("file") or params.get("path") or ""
        if not file_path:
            return "O'qish uchun 'file' (rasm yo'li) parametrini bering."
        p = Path(file_path).expanduser()
        if not p.exists():
            return f"Fayl topilmadi: {p}"

        img = _PIL_Image.open(str(p))
        decoded = _pyzbar.decode(img)
        if not decoded:
            return "QR kod topilmadi."
        results = []
        for obj in decoded:
            results.append(f"Tur: {obj.type}\nMazmun: {obj.data.decode('utf-8', errors='replace')}")
        return "\n---\n".join(results)

    # ── LIST ──────────────────────────────────────────────────────────────────
    if action in ("list", "ro'yxat"):
        files = sorted(_qr_dir().glob("*.png"), reverse=True)
        if not files:
            return "QR kodlar yo'q."
        lines = [f"• {f.name}" for f in files[:15]]
        return f"QR kodlar ({len(files)}):\n" + "\n".join(lines)

    return "Amallar: generate | decode | list"
