"""home_assistant.py — Control Home Assistant entities via REST API."""
import json
import urllib.request
import urllib.error
from pathlib import Path

_CFG = Path.home() / ".config" / "jarvis" / "home_assistant.json"


def _load_config() -> dict | None:
    try:
        return json.loads(_CFG.read_text())
    except Exception:
        return None


def _save_config(url: str, token: str):
    _CFG.parent.mkdir(parents=True, exist_ok=True)
    _CFG.write_text(json.dumps({"url": url.rstrip("/"), "token": token}, indent=2))
    _CFG.chmod(0o600)


def _request(method: str, path: str, data: dict | None = None) -> dict | str:
    cfg = _load_config()
    if not cfg:
        return {"error": "Home Assistant sozlanmagan. Avval 'setup' qiling."}
    url   = f"{cfg['url']}/api{path}"
    token = cfg["token"]
    body  = json.dumps(data).encode() if data else None
    req   = urllib.request.Request(
        url, data=body, method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type":  "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            resp = r.read()
            return json.loads(resp) if resp else {}
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.reason}"}
    except Exception as e:
        return {"error": str(e)}


def home_assistant(parameters=None, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    action = (params.get("action") or "status").lower().strip()

    # ── SETUP ─────────────────────────────────────────────────────────────────
    if action in ("setup", "sozlash", "config"):
        url   = (params.get("url") or "").strip()
        token = (params.get("token") or "").strip()
        if not url or not token:
            return (
                "Home Assistant URL va token kerak.\n"
                "URL: http://homeassistant.local:8123\n"
                "Token: HA → Profil → Long-lived access tokens"
            )
        _save_config(url, token)
        # Test connection
        result = _request("GET", "/")
        if isinstance(result, dict) and result.get("error"):
            return f"Ulanib bo'lmadi: {result['error']}"
        return f"Home Assistant ulandi: {url}"

    # ── LIST ENTITIES ─────────────────────────────────────────────────────────
    if action in ("list", "entities", "qurilmalar", "ko'rsat"):
        domain = (params.get("domain") or "").strip().lower()
        result = _request("GET", "/states")
        if isinstance(result, dict) and result.get("error"):
            return f"Xato: {result['error']}"
        if not isinstance(result, list):
            return "Natija noto'g'ri formatda."
        entities = result
        if domain:
            entities = [e for e in entities if e["entity_id"].startswith(domain + ".")]
        lines = []
        for e in entities[:20]:
            eid   = e["entity_id"]
            state = e.get("state", "?")
            name  = e.get("attributes", {}).get("friendly_name", eid)
            lines.append(f"• {name} [{eid}]: {state}")
        total = len(result)
        shown = len(lines)
        return f"Qurilmalar ({shown}/{total}):\n" + "\n".join(lines)

    # ── TURN ON/OFF ───────────────────────────────────────────────────────────
    if action in ("on", "yoq", "turn_on"):
        entity = (params.get("entity") or "").strip()
        if not entity:
            return "entity_id ko'rsatilmagan."
        result = _request("POST", f"/services/homeassistant/turn_on",
                          {"entity_id": entity})
        if player: player.write_log(f"[HA] turn_on: {entity}")
        return f"Yoqildi: {entity}" if not isinstance(result, dict) or not result.get("error") \
               else f"Xato: {result['error']}"

    if action in ("off", "o'chir", "turn_off"):
        entity = (params.get("entity") or "").strip()
        if not entity:
            return "entity_id ko'rsatilmagan."
        result = _request("POST", f"/services/homeassistant/turn_off",
                          {"entity_id": entity})
        if player: player.write_log(f"[HA] turn_off: {entity}")
        return f"O'chirildi: {entity}" if not isinstance(result, dict) or not result.get("error") \
               else f"Xato: {result['error']}"

    # ── TOGGLE ────────────────────────────────────────────────────────────────
    if action in ("toggle", "almashtiruv"):
        entity = (params.get("entity") or "").strip()
        if not entity:
            return "entity_id ko'rsatilmagan."
        result = _request("POST", "/services/homeassistant/toggle",
                          {"entity_id": entity})
        if player: player.write_log(f"[HA] toggle: {entity}")
        return f"Almashtirildi: {entity}"

    # ── STATUS ────────────────────────────────────────────────────────────────
    if action in ("status", "holat", "get"):
        entity = (params.get("entity") or "").strip()
        if not entity:
            result = _request("GET", "/")
            if isinstance(result, dict):
                return f"Home Assistant: {result.get('message', 'ulangan')}"
            return "Home Assistant ulangan."
        result = _request("GET", f"/states/{entity}")
        if isinstance(result, dict) and result.get("error"):
            return f"Xato: {result['error']}"
        state = result.get("state", "?") if isinstance(result, dict) else "?"
        name  = result.get("attributes", {}).get("friendly_name", entity) if isinstance(result, dict) else entity
        attrs = result.get("attributes", {}) if isinstance(result, dict) else {}
        info  = f"{name}: {state}"
        if "temperature" in attrs:
            info += f"  🌡{attrs['temperature']}°C"
        if "brightness" in attrs:
            info += f"  💡{attrs['brightness']}/255"
        return info

    return "Amallar: setup | list | on | off | toggle | status"
