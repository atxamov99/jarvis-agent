"""chat_history.py — View, search, save, and clear the current session history."""
import json
from datetime import datetime
from pathlib import Path

_LOG_DIR = Path.home() / "Notes" / "ChatHistory"


def _log_dir() -> Path:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    return _LOG_DIR


def chat_history(parameters=None, response=None, player=None, session_memory=None) -> str:
    """
    history_ref is injected by the dispatcher — it's a reference to the
    JarvisOpenAI._history list (or a snapshot of it).
    """
    params  = parameters or {}
    action  = (params.get("action") or "show").lower().strip()
    query   = (params.get("query") or "").strip().lower()
    n       = int(params.get("count", 10))

    # history_ref injected at call time by the handler
    history: list[dict] = params.get("_history", [])

    # ── SHOW / LIST ───────────────────────────────────────────────────────────
    if action in ("show", "ko'rsat", "list", "tarixi"):
        if not history:
            return "Suhbat tarixi bo'sh (yangi session)."
        turns = [m for m in history if m.get("role") in ("user", "assistant")][-n*2:]
        lines = []
        for m in turns:
            role = "Siz" if m["role"] == "user" else "Jarvis"
            text = str(m.get("content") or "")
            if isinstance(m.get("content"), list):
                text = " ".join(
                    p.get("text", "") for p in m["content"] if isinstance(p, dict)
                )
            lines.append(f"[{role}] {text[:200]}" + ("…" if len(text) > 200 else ""))
        return f"Oxirgi {len(turns)//2} ta almashiш:\n" + "\n".join(lines)

    # ── SEARCH ────────────────────────────────────────────────────────────────
    if action in ("search", "qidir"):
        if not query:
            return "Qidiruv so'zi ko'rsatilmagan."
        results = []
        for m in history:
            text = str(m.get("content") or "")
            if query in text.lower():
                role = "Siz" if m["role"] == "user" else "Jarvis"
                snip = text[max(0, text.lower().index(query)-30):text.lower().index(query)+100]
                results.append(f"[{role}] …{snip}…")
        if not results:
            return f"'{query}' topilmadi."
        return f"'{query}' bo'yicha natijalar ({len(results)}):\n" + "\n".join(results[:10])

    # ── SAVE ──────────────────────────────────────────────────────────────────
    if action in ("save", "saqlash"):
        if not history:
            return "Saqlanadigan tarix yo'q."
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = _log_dir() / f"chat_{ts}.json"
        path.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
        if player: player.write_log(f"[History] Saved: {path.name}")
        return f"Tarix saqlandi: {path} ({len(history)} xabar)"

    # ── COUNT ─────────────────────────────────────────────────────────────────
    if action in ("count", "nechta", "size"):
        turns = len([m for m in history if m.get("role") == "user"])
        return f"Joriy sessiyada {turns} ta savol, jami {len(history)} xabar."

    return "Amallar: show | search | save | count"
