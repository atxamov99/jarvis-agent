"""archiver.py — zip/unzip/list archive files."""
import os
import zipfile
import tarfile
from pathlib import Path


def _expand(path: str) -> Path:
    return Path(os.path.expanduser(os.path.expandvars(path))).resolve()


def archiver(parameters=None, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    action = (params.get("action") or "list").lower().strip()
    src    = params.get("source", "").strip()
    dst    = params.get("destination", "").strip()

    if not src:
        return "Manba fayl/papka ko'rsatilmagan (source parametri)."

    src_path = _expand(src)

    # ── ZIP ──────────────────────────────────────────────────────────────────
    if action in ("zip", "arxivla", "siqish"):
        if not src_path.exists():
            return f"Topilmadi: {src_path}"
        out = _expand(dst) if dst else src_path.with_suffix(".zip")
        if out.is_dir():
            out = out / (src_path.name + ".zip")
        with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            if src_path.is_dir():
                for f in src_path.rglob("*"):
                    if f.is_file():
                        zf.write(f, f.relative_to(src_path.parent))
            else:
                zf.write(src_path, src_path.name)
        size_kb = out.stat().st_size // 1024
        if player: player.write_log(f"[Archiver] zip → {out.name} ({size_kb}KB)")
        return f"Arxivlandi: {out} ({size_kb} KB)"

    # ── UNZIP ────────────────────────────────────────────────────────────────
    if action in ("unzip", "ochish", "extract", "chiqarish"):
        if not src_path.exists():
            return f"Topilmadi: {src_path}"
        out_dir = _expand(dst) if dst else src_path.parent / src_path.stem
        out_dir.mkdir(parents=True, exist_ok=True)

        suffix = src_path.suffix.lower()
        if suffix == ".zip":
            with zipfile.ZipFile(src_path, "r") as zf:
                zf.extractall(out_dir)
                count = len(zf.namelist())
        elif suffix in (".tar", ".gz", ".bz2", ".xz") or src_path.name.endswith(
            (".tar.gz", ".tar.bz2", ".tar.xz")):
            with tarfile.open(src_path, "r:*") as tf:
                tf.extractall(out_dir)
                count = len(tf.getnames())
        else:
            return f"Qo'llab-quvvatlanmagan format: {suffix}. Faqat .zip, .tar.gz, .tar.bz2"

        if player: player.write_log(f"[Archiver] extract → {out_dir.name} ({count} fayl)")
        return f"Chiqarildi: {count} fayl → {out_dir}"

    # ── LIST ─────────────────────────────────────────────────────────────────
    if action in ("list", "ko'rsat", "tarkib"):
        if not src_path.exists():
            return f"Topilmadi: {src_path}"
        suffix = src_path.suffix.lower()
        if suffix == ".zip":
            with zipfile.ZipFile(src_path, "r") as zf:
                names = zf.namelist()
        elif suffix in (".tar", ".gz", ".bz2", ".xz") or src_path.name.endswith(
            (".tar.gz", ".tar.bz2", ".tar.xz")):
            with tarfile.open(src_path, "r:*") as tf:
                names = tf.getnames()
        else:
            return f"Qo'llab-quvvatlanmagan format: {suffix}"

        preview = names[:20]
        more    = len(names) - len(preview)
        lines   = "\n".join(f"  {n}" for n in preview)
        suffix_str = f"\n  … va {more} ta boshqa" if more > 0 else ""
        return f"{src_path.name} tarkibi ({len(names)} element):\n{lines}{suffix_str}"

    return "Noma'lum amal. Ishlatish: zip | unzip | list"
