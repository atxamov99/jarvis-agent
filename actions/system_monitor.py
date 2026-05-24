"""system_monitor.py — Real-time CPU, RAM, disk, network, battery stats."""
import time
import threading
from pathlib import Path


def _fmt_bytes(b: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} PB"


def _battery() -> str | None:
    bat_dirs = list(Path("/sys/class/power_supply").glob("BAT*"))
    if not bat_dirs:
        return None
    b = bat_dirs[0]
    try:
        cap    = int((b / "capacity").read_text().strip())
        status = (b / "status").read_text().strip()
        icons  = {"Charging": "⚡", "Full": "🔋", "Discharging": "🔌"}
        icon   = icons.get(status, "🔋")
        return f"{icon} Batareya: {cap}% ({status})"
    except Exception:
        return None


_alert_state: dict = {"thread": None, "running": False}


def _run_alert(cpu_thresh: int, ram_thresh: int, interval: int, speak_fn=None):
    import psutil
    while _alert_state["running"]:
        cpu = psutil.cpu_percent(interval=1)
        ram = psutil.virtual_memory().percent
        msgs = []
        if cpu > cpu_thresh:
            msgs.append(f"CPU {cpu:.0f}% ga yetdi!")
        if ram > ram_thresh:
            msgs.append(f"RAM {ram:.0f}% ga yetdi!")
        if msgs and speak_fn:
            try: speak_fn(" ".join(msgs))
            except Exception: pass
        time.sleep(interval)


def system_monitor(parameters=None, response=None, player=None, session_memory=None,
                   speak=None) -> str:
    try:
        import psutil
    except ImportError:
        return "psutil o'rnatilmagan. `pip install psutil` qiling."

    params = parameters or {}
    action = (params.get("action") or "status").lower().strip()

    # ── STATUS ────────────────────────────────────────────────────────────────
    if action in ("status", "holat", "ko'rsat", "all"):
        cpu   = psutil.cpu_percent(interval=0.5)
        cpu_f = psutil.cpu_freq()
        ram   = psutil.virtual_memory()
        disk  = psutil.disk_usage("/")
        net   = psutil.net_io_counters()

        lines = [
            f"🖥  CPU:   {cpu:.1f}%  ({cpu_f.current:.0f} MHz)" if cpu_f else
            f"🖥  CPU:   {cpu:.1f}%",
            f"💾 RAM:   {ram.percent:.1f}%  ({_fmt_bytes(ram.used)} / {_fmt_bytes(ram.total)})",
            f"💿 Disk:  {disk.percent:.1f}%  ({_fmt_bytes(disk.used)} / {_fmt_bytes(disk.total)})",
            f"🌐 Net ↓: {_fmt_bytes(net.bytes_recv)}  ↑: {_fmt_bytes(net.bytes_sent)}",
        ]
        bat = _battery()
        if bat:
            lines.append(bat)
        if player: player.write_log(f"[Monitor] CPU {cpu:.0f}% RAM {ram.percent:.0f}%")
        return "\n".join(lines)

    # ── CPU ───────────────────────────────────────────────────────────────────
    if action in ("cpu",):
        cpu   = psutil.cpu_percent(interval=1, percpu=True)
        avg   = sum(cpu) / len(cpu)
        cores = "  ".join(f"C{i}:{c:.0f}%" for i, c in enumerate(cpu))
        return f"CPU o'rtacha: {avg:.1f}%\n{cores}"

    # ── RAM ───────────────────────────────────────────────────────────────────
    if action in ("ram", "memory", "xotira"):
        ram = psutil.virtual_memory()
        swap = psutil.swap_memory()
        return (
            f"RAM:  {ram.percent:.1f}%  "
            f"({_fmt_bytes(ram.used)} band / {_fmt_bytes(ram.available)} bo'sh / {_fmt_bytes(ram.total)} jami)\n"
            f"Swap: {swap.percent:.1f}%  ({_fmt_bytes(swap.used)} / {_fmt_bytes(swap.total)})"
        )

    # ── DISK ──────────────────────────────────────────────────────────────────
    if action in ("disk", "storage", "xotira_disk"):
        lines = []
        for part in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(part.mountpoint)
                lines.append(
                    f"• {part.mountpoint}  {usage.percent:.0f}%  "
                    f"({_fmt_bytes(usage.free)} bo'sh / {_fmt_bytes(usage.total)})"
                )
            except PermissionError:
                pass
        return "Disklar:\n" + "\n".join(lines) if lines else "Disk ma'lumoti yo'q."

    # ── TOP PROCESSES ─────────────────────────────────────────────────────────
    if action in ("top", "processes", "jarayonlar"):
        n = int(params.get("count", 10))
        procs = sorted(
            (p.info for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"])
             if p.info["cpu_percent"] is not None),
            key=lambda x: x["cpu_percent"], reverse=True
        )[:n]
        lines = [f"{'PID':>6}  {'CPU%':>5}  {'RAM%':>5}  Jarayon"]
        for p in procs:
            lines.append(f"{p['pid']:>6}  {p['cpu_percent']:>5.1f}  {p['memory_percent']:>5.1f}  {p['name']}")
        return "\n".join(lines)

    # ── BATTERY ───────────────────────────────────────────────────────────────
    if action in ("battery", "batareya", "zaryad"):
        bat = _battery()
        return bat if bat else "Batareya topilmadi (desktop kompyuter?)."

    # ── ALERT ─────────────────────────────────────────────────────────────────
    if action in ("alert", "ogohlantir", "watch"):
        cpu_t = int(params.get("cpu_threshold", 85))
        ram_t = int(params.get("ram_threshold", 85))
        ivl   = int(params.get("interval", 30))
        if _alert_state["running"]:
            _alert_state["running"] = False
            return "Monitoring to'xtatildi."
        _alert_state["running"] = True
        t = threading.Thread(
            target=_run_alert, args=(cpu_t, ram_t, ivl, speak), daemon=True
        )
        t.start()
        _alert_state["thread"] = t
        return (
            f"Monitoring boshlandi: CPU>{cpu_t}% yoki RAM>{ram_t}% bo'lsa ogohlantiradi "
            f"(har {ivl}s)."
        )

    return "Amallar: status | cpu | ram | disk | top | battery | alert"
