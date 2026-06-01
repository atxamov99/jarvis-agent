"""time_machine.py — Perfect Recall: a searchable memory of everything you saw.

Microsoft-Recall-style "time machine" that almost no personal JARVIS has.
A background thread periodically captures the screen (only when it CHANGES),
records the active window title + visible text + a thumbnail + a semantic
embedding into a local timeline. You can then ask:

  "kecha soat 3 da nima qilayotgan edim?"   → timeline around that time
  "o'sha byudjet jadvalini qachon ko'rgandim?" / "find when I saw X"  → semantic search

100% local storage. OFF by default (privacy); start it explicitly.
"""
import base64
import io
import json
import sqlite3
import subprocess
import threading
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from actions.smart_memory import _embed

_BASE      = Path(__file__).resolve().parent.parent
_API       = _BASE / "config" / "api_keys.json"
_DB        = _BASE / "data" / "timemachine.db"
_THUMBS    = _BASE / "data" / "timemachine_thumbs"
_CFG       = Path.home() / ".config" / "jarvis" / "timemachine.cfg"
_MODEL     = "gemini-2.5-flash-lite"

_INTERVAL      = 45.0    # seconds between capture attempts
_CHANGE_HAMMING = 6      # min avg-hash difference (of 64) to count as "changed"

_state = {"recording": False}
_thread = None
_lock = threading.Lock()
_stop = threading.Event()


def _api_key() -> str:
    try:
        return json.loads(_API.read_text(encoding="utf-8")).get("gemini_api_key", "").strip()
    except Exception:
        return ""


# ── Persistence of the ON/OFF flag ───────────────────────────────────────────

def load_flag():
    try:
        if _CFG.exists():
            _state["recording"] = _CFG.read_text(encoding="utf-8").strip().lower() == "on"
    except Exception:
        _state["recording"] = False

def _save_flag(on: bool):
    try:
        _CFG.parent.mkdir(parents=True, exist_ok=True)
        _CFG.write_text("on" if on else "off", encoding="utf-8")
    except Exception:
        pass


# ── DB ────────────────────────────────────────────────────────────────────────

def _connect():
    _DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS moments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL, window TEXT, text TEXT, thumb TEXT,
            dim INTEGER, embedding BLOB, phash TEXT
        )
    """)
    return conn


# ── Capture helpers ───────────────────────────────────────────────────────────

def _grab():
    from actions.screen_capture import capture_pil
    img = capture_pil()
    if img is None:
        raise RuntimeError("capture unavailable")
    return img


def _avg_hash(img) -> str:
    g = img.convert("L").resize((8, 8))
    px = list(g.getdata())
    avg = sum(px) / len(px)
    return "".join("1" if p > avg else "0" for p in px)


def _hamming(a: str, b: str) -> int:
    if not a or not b or len(a) != len(b):
        return 64
    return sum(c1 != c2 for c1, c2 in zip(a, b))


def _active_window() -> str:
    try:
        wid = subprocess.run(["xdotool", "getactivewindow"], capture_output=True, text=True, timeout=4)
        name = subprocess.run(["xdotool", "getwindowname", wid.stdout.strip()],
                              capture_output=True, text=True, timeout=4)
        return name.stdout.strip()[:200]
    except Exception:
        return ""


def _gemini_text(img, api_key: str) -> str:
    """Best-effort: extract the gist + key visible text. Tolerates quota errors."""
    try:
        small = img.copy()
        if small.width > 1100:
            small = small.resize((1100, int(small.height * 1100 / small.width)))
        buf = io.BytesIO(); small.save(buf, format="JPEG", quality=70)
        b64 = base64.b64encode(buf.getvalue()).decode()
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{_MODEL}:generateContent?key={api_key}"
        body = json.dumps({
            "contents": [{"parts": [
                {"text": "Ekranda qaysi ilova ochiq va asosiy mavzu/matn nima? "
                         "Bir-ikki qisqa jumlada (o'zbekcha), qidiruv uchun kalit so'zlar bilan."},
                {"inline_data": {"mime_type": "image/jpeg", "data": b64}},
            ]}],
            "generationConfig": {"maxOutputTokens": 120, "temperature": 0.1},
        }).encode()
        req = urllib.request.Request(url, data=body,
                                    headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=25) as r:
            data = json.loads(r.read())
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception:
        return ""


# ── Recorder loop ─────────────────────────────────────────────────────────────

def _recorder():
    _THUMBS.mkdir(parents=True, exist_ok=True)
    api_key = _api_key()
    last_hash = None
    print("[TimeMachine] Recorder started.")
    while not _stop.is_set():
        try:
            img = _grab()
            h = _avg_hash(img)
            if last_hash is not None and _hamming(h, last_hash) < _CHANGE_HAMMING:
                _stop.wait(_INTERVAL)
                continue
            last_hash = h

            window = _active_window()
            text   = _gemini_text(img, api_key) if api_key else ""
            ts     = time.time()

            thumb = img.copy()
            if thumb.width > 640:
                thumb = thumb.resize((640, int(thumb.height * 640 / thumb.width)))
            thumb_path = _THUMBS / f"{int(ts)}.jpg"
            thumb.save(str(thumb_path), format="JPEG", quality=60)

            corpus = f"{window}. {text}".strip(". ")
            vec = _embed(corpus, task_type="RETRIEVAL_DOCUMENT") if corpus else None
            blob = vec.tobytes() if vec is not None else None
            dim  = int(vec.shape[0]) if vec is not None else 0

            with _lock:
                conn = _connect()
                conn.execute(
                    "INSERT INTO moments (ts, window, text, thumb, dim, embedding, phash) VALUES (?,?,?,?,?,?,?)",
                    (ts, window, text, str(thumb_path), dim, blob, h),
                )
                conn.commit(); conn.close()
        except Exception as e:
            print(f"[TimeMachine] capture error: {e}")
        _stop.wait(_INTERVAL)
    print("[TimeMachine] Recorder stopped.")


def start_recording():
    global _thread
    try:
        import core.screencast as _sc
        _sc.ensure_started()   # silent (flash-free) capture; one-time Share dialog
    except Exception as e:
        print(f"[TimeMachine] screencast start: {e}")
    with _lock:
        if _thread and _thread.is_alive():
            return
        _stop.clear()
        _state["recording"] = True
        _thread = threading.Thread(target=_recorder, daemon=True, name="TimeMachine")
        _thread.start()


def stop_recording():
    _stop.set()
    _state["recording"] = False


# ── Query ─────────────────────────────────────────────────────────────────────

def _fmt(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def _search(query: str, k: int = 6) -> str:
    qvec = _embed(query, task_type="RETRIEVAL_QUERY")
    with _lock:
        conn = _connect()
        rows = conn.execute("SELECT ts, window, text, thumb, dim, embedding FROM moments").fetchall()
        conn.close()
    if not rows:
        return "Vaqt mashinasi hali hech narsa yozmagan. Avval: time_machine action=start"
    scored = []
    for ts, window, text, thumb, dim, blob in rows:
        if qvec is not None and dim and blob:
            vec = np.frombuffer(blob, dtype=np.float32)
            score = float(np.dot(qvec, vec)) if vec.shape[0] == qvec.shape[0] else 0.0
        else:
            ql = set(query.lower().split()); tl = set((window + " " + (text or "")).lower().split())
            score = len(ql & tl) / max(len(ql), 1)
        scored.append((score, ts, window, text, thumb))
    scored.sort(key=lambda r: r[0], reverse=True)
    top = [r for r in scored if r[0] >= 0.55][:k] or scored[:3]
    lines = [f"'{query}' bo'yicha topilgan lahzalar:"]
    for score, ts, window, text, thumb in top:
        snippet = (text or "")[:90]
        lines.append(f"  • {_fmt(ts)} — {window[:50]}" + (f" | {snippet}" if snippet else ""))
    return "\n".join(lines)


def _timeline(when: str) -> str:
    now = datetime.now()
    target = now
    w = when.lower().strip()
    if "kecha" in w or "yesterday" in w:
        target = now - timedelta(days=1)
    # parse a HH or HH:MM
    import re
    mt = re.search(r"(\d{1,2})(?::(\d{2}))?", w)
    if mt:
        target = target.replace(hour=int(mt.group(1)), minute=int(mt.group(2) or 0), second=0)
    lo = target.timestamp() - 1800
    hi = target.timestamp() + 1800
    with _lock:
        conn = _connect()
        rows = conn.execute(
            "SELECT ts, window, text FROM moments WHERE ts BETWEEN ? AND ? ORDER BY ts", (lo, hi)
        ).fetchall()
        conn.close()
    if not rows:
        return f"{_fmt(target.timestamp())} atrofida yozuv topilmadi."
    lines = [f"{_fmt(target.timestamp())} atrofidagi faoliyat:"]
    seen = set()
    for ts, window, text in rows:
        key = window[:40]
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"  • {_fmt(ts)} — {window[:55]}" + (f" | {(text or '')[:70]}" if text else ""))
    return "\n".join(lines)


def time_machine(parameters=None, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    action = (params.get("action") or "search").lower().strip()

    if action in ("start", "on", "yoq", "record"):
        start_recording(); _save_flag(True)
        return ("⏱️ Vaqt mashinasi YONDI — ekraningiz fonda OVOZSIZ yozib boriladi (chaqnashsiz). "
                "Birinchi marta 'Ekranni ulashish' oynasi chiqsa — 'Butun ekran' tanlab, "
                "'Ulashish'ni bosing (eslab qoladi, qayta so'ramaydi). 'nima qildim' deb so'rang.")

    if action in ("stop", "off", "ochir", "pause"):
        stop_recording(); _save_flag(False)
        return "⏹️ Vaqt mashinasi to'xtatildi."

    if action in ("status", "holat"):
        with _lock:
            conn = _connect()
            cnt = conn.execute("SELECT COUNT(*), MIN(ts), MAX(ts) FROM moments").fetchone()
            conn.close()
        rec = "yozyapti ⏺️" if _state["recording"] else "to'xtagan"
        if cnt and cnt[0]:
            return (f"Vaqt mashinasi: {rec} | {cnt[0]} lahza saqlangan "
                    f"({_fmt(cnt[1])} → {_fmt(cnt[2])})")
        return f"Vaqt mashinasi: {rec} | hali yozuv yo'q"

    if action in ("search", "find", "qidir", "recall"):
        q = params.get("query") or params.get("text") or ""
        if not q:
            return "Nimani qidirishni yozing (query=...)."
        return _search(q, int(params.get("k", 6)))

    if action in ("timeline", "when", "nima_qildim"):
        return _timeline(params.get("when") or params.get("time") or "")

    if action in ("clear", "wipe", "tozala"):
        with _lock:
            conn = _connect(); conn.execute("DELETE FROM moments"); conn.commit(); conn.close()
        try:
            for f in _THUMBS.glob("*.jpg"):
                f.unlink()
        except Exception:
            pass
        return "🗑️ Vaqt mashinasi tarixi tozalandi."

    return "Amallar: start | stop | status | search (query=...) | timeline (when=...) | clear"
