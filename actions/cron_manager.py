"""cron_manager.py — View, add, and remove cron jobs via crontab CLI."""
import subprocess
import re


def _read_crontab() -> list[str]:
    r = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    if r.returncode != 0 and "no crontab" in r.stderr.lower():
        return []
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip())
    return r.stdout.splitlines()


def _write_crontab(lines: list[str]) -> None:
    content = "\n".join(lines)
    if content and not content.endswith("\n"):
        content += "\n"
    r = subprocess.run(
        ["crontab", "-"],
        input=content, capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip())


def _parse_entry(line: str) -> dict | None:
    """Parse a cron line into parts, skipping comments and blanks."""
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    parts = stripped.split(None, 5)
    if len(parts) < 6:
        return None
    return {
        "schedule": " ".join(parts[:5]),
        "command":  parts[5],
        "raw":      stripped,
    }


_SCHEDULE_ALIASES = {
    "har_daqiqa":    "* * * * *",
    "har_soat":      "0 * * * *",
    "har_kun":       "0 8 * * *",
    "har_kuni":      "0 8 * * *",
    "har_haftada":   "0 8 * * 1",
    "har_oyda":      "0 8 1 * *",
    "every_minute":  "* * * * *",
    "every_hour":    "0 * * * *",
    "daily":         "0 8 * * *",
    "weekly":        "0 8 * * 1",
    "monthly":       "0 8 1 * *",
}


def cron_manager(parameters=None, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    action = (params.get("action") or "list").lower().strip()

    # ── LIST ──────────────────────────────────────────────────────────────────
    if action in ("list", "ro'yxat", "ko'rsat"):
        try:
            lines = _read_crontab()
        except RuntimeError as e:
            return f"Crontab xatosi: {e}"

        entries = [_parse_entry(l) for l in lines]
        valid   = [e for e in entries if e]

        if not valid:
            return "Cron jadval bo'sh."

        result = [f"Cron jadval ({len(valid)} ta):"]
        for i, e in enumerate(valid, 1):
            result.append(f"{i}. [{e['schedule']}] {e['command'][:60]}")
        return "\n".join(result)

    # ── ADD ───────────────────────────────────────────────────────────────────
    if action in ("add", "qo'sh", "yangi"):
        schedule = (params.get("schedule") or "").strip()
        command  = (params.get("command") or "").strip()

        if not command:
            return "Cron qo'shish uchun 'command' parametri kerak."
        if not schedule:
            return "Cron qo'shish uchun 'schedule' kerak (masalan: '0 8 * * *' yoki 'har_kun')."

        # resolve aliases
        schedule = _SCHEDULE_ALIASES.get(schedule.lower(), schedule)

        # basic validation: 5 fields
        if len(schedule.split()) != 5:
            return (
                f"Noto'g'ri schedule: '{schedule}'.\n"
                "Format: 'daqiqa soat kun_oy oy kun_hafta' (5 qism) yoki alias:\n"
                "har_daqiqa | har_soat | har_kun | har_haftada | har_oyda"
            )

        new_line = f"{schedule} {command}"
        try:
            lines = _read_crontab()
            if new_line in lines:
                return "Bu cron allaqachon mavjud."
            lines.append(new_line)
            _write_crontab(lines)
        except RuntimeError as e:
            return f"Crontab xatosi: {e}"

        if player: player.write_log(f"[Cron] Added: {new_line[:60]}")
        return f"✅ Cron qo'shildi:\n  [{schedule}] {command}"

    # ── DELETE ────────────────────────────────────────────────────────────────
    if action in ("delete", "o'chir", "remove"):
        index   = params.get("index")   # 1-based
        command = (params.get("command") or "").strip()

        try:
            lines = _read_crontab()
        except RuntimeError as e:
            return f"Crontab xatosi: {e}"

        entries = [(i, l) for i, l in enumerate(lines) if _parse_entry(l)]

        if index is not None:
            idx = int(index) - 1
            if idx < 0 or idx >= len(entries):
                return f"Noto'g'ri raqam: {index}. Ro'yxatda {len(entries)} ta cron bor."
            real_idx, target = entries[idx]
            new_lines = [l for i, l in enumerate(lines) if i != real_idx]
            removed = target
        elif command:
            matched = [(ri, l) for ri, l in entries if command.lower() in l.lower()]
            if not matched:
                return f"'{command}' bo'yicha cron topilmadi."
            real_idx, target = matched[0]
            new_lines = [l for i, l in enumerate(lines) if i != real_idx]
            removed = target
        else:
            return "O'chirish uchun 'index' (raqam) yoki 'command' (qidiruv) kerak."

        try:
            _write_crontab(new_lines)
        except RuntimeError as e:
            return f"Crontab xatosi: {e}"

        if player: player.write_log(f"[Cron] Deleted: {removed[:60]}")
        return f"✅ Cron o'chirildi:\n  {removed}"

    # ── CLEAR ─────────────────────────────────────────────────────────────────
    if action in ("clear", "tozalash"):
        try:
            subprocess.run(["crontab", "-r"], capture_output=True)
        except Exception as e:
            return str(e)
        if player: player.write_log("[Cron] All cleared.")
        return "✅ Barcha cron yozuvlar o'chirildi."

    return "Amallar: list | add | delete | clear"
