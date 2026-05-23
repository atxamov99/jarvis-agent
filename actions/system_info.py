"""system_info.py — report CPU, RAM, disk, battery, network, uptime.

Use this when the user asks: "akkumulyator qancha qoldi", "RAM qancha bo'sh",
"disk to'lganmi", "kompyuter ish ko'rsatkichlari", etc.
"""

import platform
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path

try:
    import psutil
    _PSUTIL = True
except ImportError:
    _PSUTIL = False

_OS = platform.system()


def _human_bytes(b: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} PB"


def _cpu_info() -> str:
    if _PSUTIL:
        percent = psutil.cpu_percent(interval=0.4)
        cores   = psutil.cpu_count(logical=True)
        return f"CPU: {percent:.0f}% (across {cores} cores)"
    return "CPU: (psutil not installed)"


def _ram_info() -> str:
    if _PSUTIL:
        m = psutil.virtual_memory()
        return f"RAM: {_human_bytes(m.used)} / {_human_bytes(m.total)} ({m.percent:.0f}% used, {_human_bytes(m.available)} free)"
    return "RAM: (psutil not installed)"


def _disk_info(path: str = "/") -> str:
    if _PSUTIL:
        d = psutil.disk_usage(path)
        return f"Disk ({path}): {_human_bytes(d.used)} / {_human_bytes(d.total)} ({d.percent:.0f}% used, {_human_bytes(d.free)} free)"
    total, used, free = shutil.disk_usage(path)
    pct = used * 100 / total if total else 0
    return f"Disk ({path}): {_human_bytes(used)} / {_human_bytes(total)} ({pct:.0f}% used, {_human_bytes(free)} free)"


def _battery_info() -> str:
    if _PSUTIL:
        b = psutil.sensors_battery()
        if b is None:
            return "Battery: not present (desktop or unsupported)"
        plugged = "plugged in" if b.power_plugged else "on battery"
        if b.secsleft in (psutil.POWER_TIME_UNLIMITED, psutil.POWER_TIME_UNKNOWN):
            remain = ""
        else:
            mins = max(0, int(b.secsleft / 60))
            hrs, mins = divmod(mins, 60)
            remain = f", ~{hrs}h {mins}m remaining"
        return f"Battery: {b.percent:.0f}% ({plugged}{remain})"
    # Linux fallback via /sys
    try:
        for bat in Path("/sys/class/power_supply").glob("BAT*"):
            cap = (bat / "capacity").read_text().strip()
            stat = (bat / "status").read_text().strip()
            return f"Battery: {cap}% ({stat})"
    except Exception:
        pass
    return "Battery: information unavailable"


def _uptime_info() -> str:
    if _PSUTIL:
        secs = time.time() - psutil.boot_time()
    else:
        try:
            with open("/proc/uptime") as f:
                secs = float(f.read().split()[0])
        except Exception:
            return "Uptime: unknown"
    mins = int(secs // 60)
    hrs, mins = divmod(mins, 60)
    days, hrs = divmod(hrs, 24)
    parts = []
    if days: parts.append(f"{days}d")
    if hrs:  parts.append(f"{hrs}h")
    parts.append(f"{mins}m")
    return f"Uptime: {' '.join(parts)}"


def _network_info() -> str:
    if not _PSUTIL:
        return "Network: (psutil not installed)"
    try:
        nics = psutil.net_if_stats()
        active = [name for name, s in nics.items() if s.isup and name != "lo"]
        return f"Network: {len(active)} active interface(s) — {', '.join(active) if active else 'none'}"
    except Exception as e:
        return f"Network: error — {e}"


def _os_info() -> str:
    sys_str = f"{platform.system()} {platform.release()}"
    machine = platform.machine()
    py      = platform.python_version()
    return f"OS: {sys_str} ({machine}) — Python {py}"


def system_info(parameters=None, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    metric = (params.get("metric") or "all").lower().strip()

    handlers = {
        "cpu":     _cpu_info,
        "ram":     _ram_info,
        "memory":  _ram_info,
        "disk":    lambda: _disk_info(params.get("path") or "/"),
        "battery": _battery_info,
        "network": _network_info,
        "uptime":  _uptime_info,
        "os":      _os_info,
    }

    if metric in handlers:
        result = handlers[metric]()
    else:
        # all / summary
        result = "\n".join([
            _os_info(),
            _cpu_info(),
            _ram_info(),
            _disk_info("/"),
            _battery_info(),
            _network_info(),
            _uptime_info(),
            f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        ])

    if player:
        player.write_log(f"[system_info] {metric}")
    return result
