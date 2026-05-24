"""focus_mode.py — Block/unblock distracting websites via /etc/hosts (pkexec)."""
import subprocess
import time
from pathlib import Path

_HOSTS = Path("/etc/hosts")
_MARKER_START = "# JARVIS-FOCUS-START"
_MARKER_END   = "# JARVIS-FOCUS-END"

_DEFAULT_SITES = [
    "youtube.com", "www.youtube.com",
    "twitter.com", "www.twitter.com", "x.com", "www.x.com",
    "facebook.com", "www.facebook.com",
    "instagram.com", "www.instagram.com",
    "tiktok.com", "www.tiktok.com",
    "reddit.com", "www.reddit.com",
    "vk.com", "www.vk.com",
    "twitch.tv", "www.twitch.tv",
]

_state: dict = {"active": False, "until": 0.0, "blocked": []}


def _hosts_content() -> str:
    return _HOSTS.read_text(errors="replace")


def _is_focus_active() -> bool:
    return _MARKER_START in _hosts_content()


def _write_hosts(content: str) -> tuple[bool, str]:
    """Write /etc/hosts via pkexec (graphical sudo) or sudo."""
    import tempfile, os
    with tempfile.NamedTemporaryFile("w", suffix=".hosts", delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        # try pkexec first (GUI), fall back to sudo
        for cmd in (["pkexec", "cp", tmp_path, str(_HOSTS)],
                    ["sudo", "-n", "cp", tmp_path, str(_HOSTS)]):
            r = subprocess.run(cmd, capture_output=True, timeout=15)
            if r.returncode == 0:
                return True, ""
        return False, "Hosts faylni yozish uchun ruxsat yo'q (pkexec/sudo kerak)."
    except subprocess.TimeoutExpired:
        return False, "Ruxsat so'rovi vaqti tugadi."
    except FileNotFoundError:
        return False, "pkexec/sudo topilmadi."
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def _add_blocks(sites: list[str]) -> tuple[bool, str]:
    content = _hosts_content()
    if _MARKER_START in content:
        return False, "Fokus rejimi allaqachon faol."
    block_lines = "\n".join(f"127.0.0.1 {s}" for s in sites)
    addition = f"\n{_MARKER_START}\n{block_lines}\n{_MARKER_END}\n"
    return _write_hosts(content + addition)


def _remove_blocks() -> tuple[bool, str]:
    content = _hosts_content()
    if _MARKER_START not in content:
        return False, "Fokus rejimi faol emas."
    lines = content.splitlines(keepends=True)
    inside = False
    filtered = []
    for line in lines:
        if _MARKER_START in line:
            inside = True
            continue
        if _MARKER_END in line:
            inside = False
            continue
        if not inside:
            filtered.append(line)
    return _write_hosts("".join(filtered))


def focus_mode(parameters=None, response=None, player=None, session_memory=None) -> str:
    params   = parameters or {}
    action   = (params.get("action") or "status").lower().strip()
    duration = int(params.get("duration", 0))  # minutes

    # ── STATUS ────────────────────────────────────────────────────────────────
    if action in ("status", "holat"):
        if _is_focus_active():
            remaining = ""
            if _state["until"] > time.time():
                mins = int((_state["until"] - time.time()) / 60)
                remaining = f" ({mins} daqiqa qoldi)"
            sites = _state.get("blocked", _DEFAULT_SITES)
            return (
                f"🎯 Fokus rejimi FAOL{remaining}.\n"
                f"Bloklangan: {len(sites)} ta sayt."
            )
        return "Fokus rejimi o'chirilgan."

    # ── START ─────────────────────────────────────────────────────────────────
    if action in ("start", "boshlash", "yoq", "on", "enable"):
        raw_sites = params.get("sites")
        if raw_sites:
            if isinstance(raw_sites, list):
                sites = raw_sites
            else:
                sites = [s.strip() for s in str(raw_sites).split(",")]
        else:
            sites = _DEFAULT_SITES

        ok, err = _add_blocks(sites)
        if not ok:
            return f"Xato: {err}"

        _state["active"] = True
        _state["blocked"] = sites
        if duration > 0:
            _state["until"] = time.time() + duration * 60
            import threading
            def _auto_stop():
                time.sleep(duration * 60)
                _remove_blocks()
                _state.update({"active": False, "until": 0.0, "blocked": []})
                if player: player.write_log("[Focus] Auto-stopped.")
            threading.Thread(target=_auto_stop, daemon=True).start()
            dur_text = f"{duration} daqiqaga "
        else:
            _state["until"] = 0.0
            dur_text = ""

        if player: player.write_log(f"[Focus] Started {dur_text}({len(sites)} sites)")
        return (
            f"🎯 Fokus rejimi {dur_text}yoqildi!\n"
            f"Bloklangan {len(sites)} ta sayt:\n"
            + "\n".join(f"  • {s}" for s in sites[:8])
            + ("\n  ..." if len(sites) > 8 else "")
        )

    # ── STOP ──────────────────────────────────────────────────────────────────
    if action in ("stop", "o'chir", "off", "disable", "tugatish"):
        ok, err = _remove_blocks()
        if not ok:
            return f"Xato: {err}"
        _state.update({"active": False, "until": 0.0, "blocked": []})
        if player: player.write_log("[Focus] Stopped.")
        return "✅ Fokus rejimi o'chirildi. Saytlar blokdan chiqarildi."

    # ── LIST ──────────────────────────────────────────────────────────────────
    if action in ("list", "saytlar"):
        lines = [f"  • {s}" for s in _DEFAULT_SITES]
        return "Standart bloklangan saytlar:\n" + "\n".join(lines)

    return "Amallar: start | stop | status | list"
