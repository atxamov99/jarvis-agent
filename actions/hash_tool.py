"""hash_tool.py — Compute and verify cryptographic hashes (stdlib only)."""
import hashlib
from pathlib import Path

_ALGOS = {"md5", "sha1", "sha256", "sha512", "sha224", "sha384"}


def _compute(data: bytes, algo: str) -> str:
    h = hashlib.new(algo)
    h.update(data)
    return h.hexdigest()


def _compute_file(path: Path, algo: str, chunk: int = 1 << 20) -> str:
    h = hashlib.new(algo)
    with path.open("rb") as f:
        while buf := f.read(chunk):
            h.update(buf)
    return h.hexdigest()


def hash_tool(parameters=None, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    action = (params.get("action") or "hash").lower().strip()
    algo   = (params.get("algo") or "sha256").lower().strip()

    if algo not in _ALGOS:
        return f"Noma'lum algoritm: {algo}. Mavjudlar: {', '.join(sorted(_ALGOS))}"

    # ── HASH TEXT ─────────────────────────────────────────────────────────────
    if action in ("hash", "hisob", "text"):
        text = params.get("text") or ""
        if not text:
            return "Hesh uchun 'text' parametrini bering."
        digest = _compute(text.encode(), algo)
        if player: player.write_log(f"[Hash] {algo}({text[:30]}…) = {digest[:16]}…")
        return f"{algo.upper()}: {digest}"

    # ── HASH FILE ─────────────────────────────────────────────────────────────
    if action in ("file", "fayl"):
        file_path = params.get("file") or params.get("path") or ""
        if not file_path:
            return "Fayl yo'lini ko'rsating."
        p = Path(file_path).expanduser()
        if not p.exists():
            return f"Fayl topilmadi: {p}"
        if not p.is_file():
            return f"Bu fayl emas: {p}"
        digest = _compute_file(p, algo)
        size_mb = p.stat().st_size / 1_000_000
        if player: player.write_log(f"[Hash] {algo}({p.name}) = {digest[:16]}…")
        return f"{algo.upper()} [{p.name}  {size_mb:.2f} MB]:\n{digest}"

    # ── VERIFY ────────────────────────────────────────────────────────────────
    if action in ("verify", "tekshir"):
        file_path = params.get("file") or params.get("path") or ""
        expected  = (params.get("expected") or params.get("hash") or "").strip().lower()
        if not file_path or not expected:
            return "Tekshirish uchun 'file' va 'expected' (kutilgan hesh) kerak."
        p = Path(file_path).expanduser()
        if not p.exists():
            return f"Fayl topilmadi: {p}"
        digest = _compute_file(p, algo)
        match = digest == expected
        symbol = "✅" if match else "❌"
        return (
            f"{symbol} {'Mos keldi' if match else 'Mos kelmadi'}!\n"
            f"Fayl:     {digest}\n"
            f"Kutilgan: {expected}"
        )

    # ── ALL ALGOS ─────────────────────────────────────────────────────────────
    if action in ("all", "barchasi"):
        text = params.get("text") or ""
        file_path = params.get("file") or params.get("path") or ""
        if text:
            data = text.encode()
            lines = [f"{a.upper()}: {_compute(data, a)}" for a in sorted(_ALGOS)]
        elif file_path:
            p = Path(file_path).expanduser()
            if not p.exists():
                return f"Fayl topilmadi: {p}"
            lines = [f"{a.upper()}: {_compute_file(p, a)}" for a in sorted(_ALGOS)]
        else:
            return "Matn yoki fayl yo'li ko'rsating."
        return "\n".join(lines)

    return "Amallar: hash | file | verify | all"
