"""samsung_tv.py — Control Samsung Smart TV over WiFi (same network, no cable).

Uses samsungtvws (WebSocket API, port 8001/8002).
Config: ~/.config/jarvis/samsung_tv.json  →  {"ip": "192.168.1.X", "mac": "XX:XX:XX:XX:XX:XX"}
"""
import json
import subprocess
import time
from pathlib import Path

_CONFIG_PATH = Path.home() / ".config" / "jarvis" / "samsung_tv.json"

# Remote key codes (most common)
_KEYS = {
    # Power
    "off":        "KEY_POWEROFF",
    "on":         "KEY_POWERON",
    "power":      "KEY_POWER",
    # Volume
    "vol+":       "KEY_VOLUP",
    "vol-":       "KEY_VOLDOWN",
    "mute":       "KEY_MUTE",
    # Channels
    "ch+":        "KEY_CHUP",
    "ch-":        "KEY_CHDOWN",
    # Navigation
    "up":         "KEY_UP",
    "down":       "KEY_DOWN",
    "left":       "KEY_LEFT",
    "right":      "KEY_RIGHT",
    "ok":         "KEY_ENTER",
    "back":       "KEY_RETURN",
    "home":       "KEY_HOME",
    "menu":       "KEY_MENU",
    # Media
    "play":       "KEY_PLAY",
    "pause":      "KEY_PAUSE",
    "stop":       "KEY_STOP",
    "forward":    "KEY_FF",
    "rewind":     "KEY_RW",
    # Numbers
    "0": "KEY_0", "1": "KEY_1", "2": "KEY_2", "3": "KEY_3",
    "4": "KEY_4", "5": "KEY_5", "6": "KEY_6", "7": "KEY_7",
    "8": "KEY_8", "9": "KEY_9",
    # Sources / Smart
    "source":     "KEY_SOURCE",
    "hdmi1":      "KEY_HDMI1",
    "hdmi2":      "KEY_HDMI2",
    "smarthub":   "KEY_SMARTHUB",
    "netflix":    "KEY_NETFLIX",
    "youtube":    "KEY_YOUTUBE",
}

# App IDs for launching apps directly
_APPS = {
    "youtube":  "111299001912",
    "netflix":  "11101200001",
    "prime":    "3201910019365",
    "spotify":  "3201606009684",
    "plex":     "3201512006785",
    "browser":  "org.tizen.browser",
}


def _load_config() -> dict:
    if not _CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(_CONFIG_PATH.read_text())
    except Exception:
        return {}


def _save_config(cfg: dict):
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CONFIG_PATH.write_text(json.dumps(cfg, indent=2))


def _get_tv(ip: str, token_file: str | None = None):
    """Return an authenticated SamsungTVWS instance."""
    from samsungtvws import SamsungTVWS
    token_path = str(Path.home() / ".config" / "jarvis" / "samsung_tv_token.txt")
    tv = SamsungTVWS(
        host=ip,
        port=8002,
        token_file=token_path,
        timeout=5,
        name="JARVIS",
    )
    return tv


def _send_key(tv, key_code: str) -> bool:
    try:
        tv.send_key(key_code)
        return True
    except Exception as e:
        print(f"[SamsungTV] Key error: {e}")
        return False


def _wake_on_lan(mac: str):
    """Send WoL magic packet to power on TV."""
    try:
        import wakeonlan
        wakeonlan.send_magic_packet(mac)
        return True
    except Exception as e:
        print(f"[SamsungTV] WoL error: {e}")
        return False


def samsung_tv(parameters=None, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    action = (params.get("action") or "status").lower().strip()

    cfg = _load_config()

    # ── SETUP ─────────────────────────────────────────────────────────────────
    if action in ("setup", "sozla", "connect"):
        ip  = (params.get("ip") or "").strip()
        mac = (params.get("mac") or "").strip()
        if not ip:
            return (
                "Samsung TV IP manzilini ko'rsating.\n"
                "Router admin panelidan yoki TV: Settings → General → Network → "
                "Network Status da IP ni toping.\n"
                "Masalan: action='setup', ip='192.168.1.50', mac='AA:BB:CC:DD:EE:FF'"
            )
        cfg["ip"]  = ip
        if mac:
            cfg["mac"] = mac
        _save_config(cfg)
        if player: player.write_log(f"[SamsungTV] Config saved: {ip}")
        return f"✅ Samsung TV sozlandi: {ip}\nEndi 'samsung_tv yoq' deb urinib ko'ring."

    ip = cfg.get("ip", "")
    if not ip:
        return "Avval sozlang: action='setup', ip='192.168.1.X' (TV IP manzili)."

    # ── POWER ON (Wake on LAN) ────────────────────────────────────────────────
    if action in ("on", "yoq", "yoqish", "wake"):
        mac = cfg.get("mac", "")
        if not mac:
            return (
                "TV ni yoqish uchun MAC manzil kerak.\n"
                "TV: Settings → General → Network → Network Status → MAC Address\n"
                "action='setup', ip='...', mac='AA:BB:CC:DD:EE:FF'"
            )
        ok = _wake_on_lan(mac)
        if ok:
            if player: player.write_log("[SamsungTV] WoL sent")
            return f"📺 Wake-on-LAN yuborildi → {mac}\nTV bir necha soniyada yonadi."
        return "WoL xatosi."

    # ── All other actions need TV connection ──────────────────────────────────
    try:
        tv = _get_tv(ip)
    except Exception as e:
        return f"TV ga ulanib bo'lmadi ({ip}): {e}\nTV yoniq va bir WiFi da ekanini tekshiring."

    # ── POWER OFF ─────────────────────────────────────────────────────────────
    if action in ("off", "o'chir", "o'chirish"):
        ok = _send_key(tv, "KEY_POWEROFF")
        return "📺 TV o'chirildi." if ok else "Xato: TV javob bermadi."

    # ── VOLUME ────────────────────────────────────────────────────────────────
    if action in ("vol+", "volume_up", "ovoz+", "balandroq"):
        steps = int(params.get("steps", 3))
        for _ in range(steps):
            _send_key(tv, "KEY_VOLUP")
            time.sleep(0.15)
        return f"🔊 Ovoz +{steps}"

    if action in ("vol-", "volume_down", "ovoz-", "pastroq"):
        steps = int(params.get("steps", 3))
        for _ in range(steps):
            _send_key(tv, "KEY_VOLDOWN")
            time.sleep(0.15)
        return f"🔉 Ovoz -{steps}"

    if action in ("mute", "soket", "jim"):
        _send_key(tv, "KEY_MUTE")
        return "🔇 Ovoz o'chirildi/yoqildi."

    if action in ("volume", "vol", "ovoz"):
        level = int(params.get("level", 20))
        level = max(0, min(100, level))
        try:
            tv.send_command(
                "ms.remote.control",
                {"method": "ms.remote.control",
                 "params": {"Cmd": "SET_VOLUME", "DataOfCmd": str(level),
                            "TypeOfRemote": "SendRemoteKey"}}
            )
            return f"🔊 Ovoz {level}% ga o'rnatildi."
        except Exception:
            return "Ovoz darajasini to'g'ridan o'rnatib bo'lmadi (TV modeli cheklovlari)."

    # ── CHANNEL ───────────────────────────────────────────────────────────────
    if action in ("ch+", "channel_up", "kanal+"):
        _send_key(tv, "KEY_CHUP")
        return "📺 Keyingi kanal."

    if action in ("ch-", "channel_down", "kanal-"):
        _send_key(tv, "KEY_CHDOWN")
        return "📺 Oldingi kanal."

    if action in ("channel", "ch", "kanal"):
        ch = str(params.get("channel") or params.get("number") or "")
        if not ch.isdigit():
            return "Kanal raqamini ko'rsating. Masalan: channel=5"
        for digit in ch:
            _send_key(tv, f"KEY_{digit}")
            time.sleep(0.2)
        _send_key(tv, "KEY_ENTER")
        return f"📺 {ch}-kanal."

    # ── APP LAUNCH ────────────────────────────────────────────────────────────
    if action in ("app", "ilova", "open"):
        app_name = (params.get("app") or "").lower().strip()
        app_id   = _APPS.get(app_name, app_name)
        try:
            tv.run_app(app_id)
            if player: player.write_log(f"[SamsungTV] App: {app_name}")
            return f"▶️ {app_name.capitalize()} ishga tushirildi."
        except Exception as e:
            return f"Ilova ochmadi: {e}"

    # ── KEY ───────────────────────────────────────────────────────────────────
    if action in ("key", "tugma"):
        key_name = (params.get("key") or "").lower().strip()
        key_code = _KEYS.get(key_name, key_name.upper())
        ok = _send_key(tv, key_code)
        return f"✅ {key_code} yuborildi." if ok else f"❌ {key_code} xatosi."

    # ── INFO ──────────────────────────────────────────────────────────────────
    if action in ("status", "info", "holat"):
        try:
            info = tv.rest_device_info()
            name  = info.get("device", {}).get("name", "?")
            model = info.get("device", {}).get("modelName", "?")
            return f"📺 Samsung TV\nNom: {name}\nModel: {model}\nIP: {ip}"
        except Exception:
            return f"📺 TV IP: {ip} (ulanib bo'lmadi — yoniq emasmi?)"

    # ── NAVIGATION shortcuts ──────────────────────────────────────────────────
    nav_map = {
        "up": "KEY_UP", "down": "KEY_DOWN",
        "left": "KEY_LEFT", "right": "KEY_RIGHT",
        "ok": "KEY_ENTER", "enter": "KEY_ENTER",
        "back": "KEY_RETURN", "home": "KEY_HOME",
        "play": "KEY_PLAY", "pause": "KEY_PAUSE",
        "netflix": "KEY_NETFLIX", "youtube": "KEY_YOUTUBE",
        "source": "KEY_SOURCE", "menu": "KEY_MENU",
    }
    if action in nav_map:
        ok = _send_key(tv, nav_map[action])
        return f"✅ {action}" if ok else "❌ Xato"

    return (
        "Amallar: setup | on | off | vol+ | vol- | mute | volume | "
        "ch+ | ch- | channel | app | key | status | "
        "up | down | left | right | ok | back | home | play | pause | netflix | youtube"
    )
