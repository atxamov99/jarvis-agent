"""disk_manager.py — Disk usage analysis via psutil + du/df."""
import os
import subprocess
from pathlib import Path

try:
    import psutil as _psutil
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False


def _fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def _partitions() -> list[dict]:
    results = []
    if _HAS_PSUTIL:
        for p in _psutil.disk_partitions(all=False):
            try:
                usage = _psutil.disk_usage(p.mountpoint)
                results.append({
                    "device":      p.device,
                    "mountpoint":  p.mountpoint,
                    "fstype":      p.fstype,
                    "total":       usage.total,
                    "used":        usage.used,
                    "free":        usage.free,
                    "percent":     usage.percent,
                })
            except (PermissionError, OSError):
                pass
    return results


def _du_top(path: str, n: int = 10) -> list[tuple[int, str]]:
    try:
        r = subprocess.run(
            ["du", "-x", "--max-depth=1", path],
            capture_output=True, text=True, timeout=30,
        )
        entries = []
        for line in r.stdout.splitlines():
            parts = line.split("\t", 1)
            if len(parts) == 2 and parts[1] != path:
                try:
                    entries.append((int(parts[0]) * 1024, parts[1]))
                except ValueError:
                    pass
        return sorted(entries, reverse=True)[:n]
    except Exception:
        return []


def disk_manager(parameters=None, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    action = (params.get("action") or "overview").lower().strip()

    # ── OVERVIEW / ALL PARTITIONS ─────────────────────────────────────────────
    if action in ("overview", "umumiy", "df", "partitions", "disk"):
        if not _HAS_PSUTIL:
            r = subprocess.run(["df", "-h", "--output=source,size,used,avail,pcent,target"],
                               capture_output=True, text=True, timeout=5)
            return r.stdout.strip() or "df natijasi yo'q."
        parts = _partitions()
        if not parts:
            return "Disk ma'lumotlari topilmadi."
        lines = []
        for p in parts:
            bar_filled = int(p["percent"] / 5)
            bar = "█" * bar_filled + "░" * (20 - bar_filled)
            lines.append(
                f"{p['device']} → {p['mountpoint']}\n"
                f"  [{bar}] {p['percent']:.1f}%\n"
                f"  Jami: {_fmt_size(p['total'])} | "
                f"Foydalanilgan: {_fmt_size(p['used'])} | "
                f"Bo'sh: {_fmt_size(p['free'])}"
            )
        return "\n\n".join(lines)

    # ── USAGE of specific path ────────────────────────────────────────────────
    if action in ("usage", "hajm", "size", "du"):
        path = params.get("path") or str(Path.home())
        p = Path(path).expanduser()
        if not p.exists():
            return f"Yo'l topilmadi: {p}"
        if _HAS_PSUTIL and p.is_absolute():
            try:
                usage = _psutil.disk_usage(str(p))
                return (
                    f"Disk: {p}\n"
                    f"Jami:            {_fmt_size(usage.total)}\n"
                    f"Foydalanilgan:   {_fmt_size(usage.used)} ({usage.percent:.1f}%)\n"
                    f"Bo'sh:           {_fmt_size(usage.free)}"
                )
            except Exception:
                pass
        try:
            r = subprocess.run(["du", "-sh", str(p)], capture_output=True, text=True, timeout=30)
            return f"{p}: {r.stdout.split()[0]}" if r.returncode == 0 else str(r.stderr[:200])
        except Exception as e:
            return str(e)

    # ── TOP DIRECTORIES ───────────────────────────────────────────────────────
    if action in ("top", "katta", "largest"):
        path = params.get("path") or str(Path.home())
        n    = int(params.get("count", 10))
        p    = Path(path).expanduser()
        if not p.exists():
            return f"Yo'l topilmadi: {p}"
        if player: player.write_log(f"[Disk] Top {n} in {p}")
        entries = _du_top(str(p), n)
        if not entries:
            return "Ma'lumot olib bo'lmadi (du buyrug'i kerak)."
        lines = [f"  {_fmt_size(size):>10}  {Path(name).name}" for size, name in entries]
        return f"Eng katta papkalar ({p}):\n" + "\n".join(lines)

    # ── FIND LARGE FILES ──────────────────────────────────────────────────────
    if action in ("large", "katta_fayllar", "bigfiles"):
        path    = params.get("path") or str(Path.home())
        min_mb  = int(params.get("min_mb", 100))
        n       = int(params.get("count", 20))
        p       = Path(path).expanduser()
        if player: player.write_log(f"[Disk] Large files >{min_mb}MB in {p}")
        try:
            r = subprocess.run(
                ["find", str(p), "-xdev", "-type", "f",
                 "-size", f"+{min_mb}M", "-printf", "%s %p\n"],
                capture_output=True, text=True, timeout=60,
            )
            entries = []
            for line in r.stdout.splitlines():
                parts = line.split(" ", 1)
                if len(parts) == 2:
                    try:
                        entries.append((int(parts[0]), parts[1]))
                    except ValueError:
                        pass
            entries.sort(reverse=True)
            if not entries:
                return f"{min_mb} MB dan katta fayl topilmadi."
            lines = [f"  {_fmt_size(s):>10}  {name}" for s, name in entries[:n]]
            return f"Katta fayllar (>{min_mb} MB):\n" + "\n".join(lines)
        except subprocess.TimeoutExpired:
            return "Qidiruv vaqti tugadi (60s)."
        except Exception as e:
            return str(e)

    return "Amallar: overview | usage | top | large"
