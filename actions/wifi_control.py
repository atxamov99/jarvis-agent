"""wifi_control.py — List, connect, disconnect, and scan WiFi networks via nmcli."""
import shutil
import subprocess


def _nmcli(*args, timeout: int = 15) -> tuple[int, str, str]:
    r = subprocess.run(["nmcli"] + list(args), capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def wifi_control(parameters=None, response=None, player=None, session_memory=None) -> str:
    if not shutil.which("nmcli"):
        return "nmcli topilmadi. NetworkManager o'rnatilgan bo'lishi kerak."

    params = parameters or {}
    action = (params.get("action") or "list").lower().strip()
    ssid   = (params.get("ssid") or "").strip()
    password = (params.get("password") or "").strip()

    # ── STATUS ────────────────────────────────────────────────────────────────
    if action in ("status", "holat", "qaysi"):
        rc, out, _ = _nmcli("-t", "-f", "ACTIVE,SSID,SIGNAL,SECURITY", "dev", "wifi")
        active = [l for l in out.splitlines() if l.startswith("yes")]
        if not active:
            return "Hozir WiFi tarmog'iga ulangan emas."
        lines = []
        for l in active:
            parts = l.split(":")
            ssid_val = parts[1] if len(parts) > 1 else "?"
            signal   = parts[2] if len(parts) > 2 else "?"
            sec      = parts[3] if len(parts) > 3 else "?"
            lines.append(f"Ulangan: {ssid_val} | Signal: {signal}% | {sec}")
        return "\n".join(lines)

    # ── LIST / SCAN ───────────────────────────────────────────────────────────
    if action in ("list", "scan", "qidir", "tarmoqlar", "ko'rsat"):
        _nmcli("dev", "wifi", "rescan")  # trigger rescan (may take a moment)
        rc, out, _ = _nmcli("-t", "-f", "ACTIVE,SSID,SIGNAL,SECURITY,FREQ",
                             "dev", "wifi", "list")
        if rc != 0 or not out:
            return "WiFi tarmoqlari topilmadi."
        lines = []
        for l in out.splitlines():
            parts = l.split(":")
            if len(parts) < 4:
                continue
            active_flag = "✓ " if parts[0] == "yes" else "  "
            ssid_val    = parts[1] or "<hidden>"
            signal      = parts[2]
            sec         = parts[3]
            lines.append(f"{active_flag}{ssid_val:<30} {signal:>3}%  {sec}")
        if not lines:
            return "Tarmoqlar topilmadi."
        return f"WiFi tarmoqlari ({len(lines)}):\n" + "\n".join(lines[:20])

    # ── CONNECT ───────────────────────────────────────────────────────────────
    if action in ("connect", "ulash", "ul", "bog'lan"):
        if not ssid:
            return "SSID ko'rsatilmagan."
        if password:
            rc, out, err = _nmcli("dev", "wifi", "connect", ssid,
                                  "password", password, timeout=30)
        else:
            rc, out, err = _nmcli("dev", "wifi", "connect", ssid, timeout=30)
        if rc == 0:
            if player: player.write_log(f"[WiFi] Connected: {ssid}")
            return f"WiFi ulandi: {ssid}"
        return f"Ulanib bo'lmadi: {err or out}"

    # ── DISCONNECT ────────────────────────────────────────────────────────────
    if action in ("disconnect", "uzish", "uz", "chiqish"):
        rc, out, err = _nmcli("dev", "disconnect", "wlan0")
        if rc != 0:
            # Try by interface name from nmcli
            rc2, iface_out, _ = _nmcli("-t", "-f", "DEVICE,TYPE", "dev")
            for l in iface_out.splitlines():
                if "wifi" in l:
                    iface = l.split(":")[0]
                    rc, out, err = _nmcli("dev", "disconnect", iface)
                    break
        if player: player.write_log(f"[WiFi] Disconnected")
        return "WiFi uzildi." if rc == 0 else f"Uzib bo'lmadi: {err or out}"

    # ── ON / OFF ──────────────────────────────────────────────────────────────
    if action in ("on", "yoq", "enable"):
        rc, out, err = _nmcli("radio", "wifi", "on")
        return "WiFi yoqildi." if rc == 0 else f"Xato: {err}"

    if action in ("off", "o'chir", "disable"):
        rc, out, err = _nmcli("radio", "wifi", "off")
        return "WiFi o'chirildi." if rc == 0 else f"Xato: {err}"

    return "Amallar: status | list | connect | disconnect | on | off"
