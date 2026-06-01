"""smart_memory.py — Semantic long-term memory (RAG) for JARVIS.

Unlike the flat keyword store in memory/memory_manager.py, this remembers
free-form knowledge and recalls it by *meaning* using vector embeddings.

Pipeline:
  • remember(text)  → embed (Gemini text-embedding-004) → store vector in SQLite
  • recall(query)   → embed query → cosine similarity → top-k relevant memories
  • Offline / no-key fallback → lexical (token-overlap) scoring, so it still works.

This is what lets Jarvis answer "men senga aytgan edim..." / "what do you know
about X" by surfacing only the relevant past facts instead of dumping everything.
"""
import json
import sqlite3
import time
from pathlib import Path
from threading import Lock

import numpy as np

_BASE_DIR = Path(__file__).resolve().parent.parent
_DB_PATH  = _BASE_DIR / "data" / "smart_memory.db"
_API_PATH = _BASE_DIR / "config" / "api_keys.json"

_EMBED_MODEL = "gemini-embedding-001"   # Gemini embeddings (3072-dim)
_lock = Lock()
_client = None          # cached genai client
_client_tried = False   # avoid re-initialising on every call


# -- Storage -------------------------------------------------------------------

def _connect() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            text      TEXT NOT NULL,
            source    TEXT DEFAULT 'user',
            ts        REAL NOT NULL,
            dim       INTEGER DEFAULT 0,
            embedding BLOB
        )
    """)
    return conn


# -- Embeddings ----------------------------------------------------------------

def _get_client():
    """Lazily build a cached genai client. Returns None if unavailable."""
    global _client, _client_tried
    if _client is not None:
        return _client
    if _client_tried:
        return None
    _client_tried = True
    try:
        from google import genai
        key = json.loads(_API_PATH.read_text(encoding="utf-8")).get("gemini_api_key")
        if not key:
            return None
        _client = genai.Client(api_key=key)
        return _client
    except Exception as e:
        print(f"[SmartMemory] Embedding client unavailable: {e}")
        return None


_EMBED_DIM = 768   # MRL-truncated output (gemini-embedding-001 supports this)


def _embed(text: str, task_type: str = "RETRIEVAL_DOCUMENT"):
    """Return an L2-normalised embedding vector, or None if embeddings unavailable.

    task_type follows the asymmetric-retrieval convention:
      • stored memories → RETRIEVAL_DOCUMENT
      • search queries  → RETRIEVAL_QUERY
    This sharply improves separation between relevant and irrelevant hits.
    """
    client = _get_client()
    if client is None:
        return None
    try:
        from google.genai import types
        res = client.models.embed_content(
            model=_EMBED_MODEL,
            contents=text,
            config=types.EmbedContentConfig(
                task_type=task_type,
                output_dimensionality=_EMBED_DIM,
            ),
        )
        vec = np.asarray(res.embeddings[0].values, dtype=np.float32)
        norm = np.linalg.norm(vec)
        return vec / norm if norm > 0 else vec
    except Exception as e:
        print(f"[SmartMemory] Embed failed: {e}")
        return None


def _tokens(text: str) -> set:
    return {t for t in "".join(c.lower() if c.isalnum() else " " for c in text).split() if len(t) > 1}


def _lexical_score(query: str, text: str) -> float:
    """Token-overlap (Jaccard-ish) score -- offline fallback for recall."""
    q, t = _tokens(query), _tokens(text)
    if not q or not t:
        return 0.0
    return len(q & t) / len(q)


# -- Public operations ---------------------------------------------------------

def remember(text: str, source: str = "user") -> str:
    text = (text or "").strip()
    if not text:
        return "Eslab qolish uchun matn yo'q."
    vec = _embed(text)
    blob = vec.tobytes() if vec is not None else None
    dim  = int(vec.shape[0]) if vec is not None else 0
    with _lock:
        conn = _connect()
        cur = conn.execute(
            "INSERT INTO memories (text, source, ts, dim, embedding) VALUES (?,?,?,?,?)",
            (text, source, time.time(), dim, blob),
        )
        mem_id = cur.lastrowid
        conn.commit()
        conn.close()
    mode = "semantik" if dim else "matnli"
    return f"Eslab qoldim (#{mem_id}, {mode}): {text[:80]}"


def recall(query: str, k: int = 4, min_score: float = 0.64) -> list:
    """Return up to k relevant memories: [{id, text, score, source, ts}]."""
    query = (query or "").strip()
    if not query:
        return []
    qvec = _embed(query, task_type="RETRIEVAL_QUERY")
    with _lock:
        conn = _connect()
        rows = conn.execute(
            "SELECT id, text, source, ts, dim, embedding FROM memories"
        ).fetchall()
        conn.close()

    scored = []
    for mem_id, text, source, ts, dim, blob in rows:
        if qvec is not None and dim and blob:
            vec = np.frombuffer(blob, dtype=np.float32)
            if vec.shape[0] == qvec.shape[0]:
                score = float(np.dot(qvec, vec))   # both normalised -> cosine
            else:
                score = _lexical_score(query, text)
        else:
            score = _lexical_score(query, text)
        scored.append({"id": mem_id, "text": text, "score": score,
                       "source": source, "ts": ts})

    scored.sort(key=lambda r: r["score"], reverse=True)
    if not scored:
        return []
    # Relative cutoff: keep the best hit, then only others close to it.
    # Embeddings on short text compress scores, so an adaptive gap beats a
    # fixed floor at separating "relevant" from "everything else".
    top = scored[0]["score"]
    if top < min_score:
        return []   # even the best match isn't relevant enough
    cutoff = top - 0.07   # keep the best, plus others clearly close to it
    return [r for r in scored if r["score"] >= cutoff][:k]


def forget(target: str) -> str:
    """Delete by id ('#3' or '3'), by matching text, or 'all'."""
    target = (target or "").strip()
    if not target:
        return "Nimani o'chirishni ko'rsating (id, matn yoki 'all')."
    with _lock:
        conn = _connect()
        if target.lower() in ("all", "hammasi", "barchasi"):
            n = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
            conn.execute("DELETE FROM memories")
            conn.commit(); conn.close()
            return f"Butun semantik xotira o'chirildi ({n} ta yozuv)."
        clean = target.lstrip("#")
        if clean.isdigit():
            cur = conn.execute("DELETE FROM memories WHERE id=?", (int(clean),))
            conn.commit(); conn.close()
            return f"#{clean} o'chirildi." if cur.rowcount else f"#{clean} topilmadi."
        cur = conn.execute("DELETE FROM memories WHERE text LIKE ?", (f"%{target}%",))
        conn.commit(); conn.close()
        return f"{cur.rowcount} ta mos yozuv o'chirildi."


def list_memories(limit: int = 20) -> list:
    with _lock:
        conn = _connect()
        rows = conn.execute(
            "SELECT id, text, source, ts FROM memories ORDER BY ts DESC LIMIT ?",
            (limit,),
        ).fetchall()
        conn.close()
    return [{"id": r[0], "text": r[1], "source": r[2], "ts": r[3]} for r in rows]


# -- Tool entry point ----------------------------------------------------------

def smart_memory(parameters=None, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    action = (params.get("action") or "recall").lower().strip()

    if action in ("remember", "save", "store", "esla", "eslab_qol"):
        return remember(params.get("text", ""), source=params.get("source", "user"))

    if action in ("recall", "search", "query", "esla_chi", "qidir"):
        query = params.get("query") or params.get("text", "")
        k = int(params.get("k", 5))
        hits = recall(query, k=k)
        if not hits:
            return f"'{query}' bo'yicha tegishli xotira topilmadi."
        lines = [f"'{query}' bo'yicha {len(hits)} ta tegishli xotira:"]
        for h in hits:
            lines.append(f"  - (#{h['id']}, {h['score']:.0%}) {h['text']}")
        return "\n".join(lines)

    if action in ("forget", "delete", "remove", "unut", "ochir"):
        return forget(params.get("target") or params.get("text", ""))

    if action in ("list", "all", "royxat"):
        mems = list_memories(int(params.get("limit", 20)))
        if not mems:
            return "Semantik xotira bo'sh."
        lines = [f"Semantik xotira ({len(mems)} ta):"]
        for m in mems:
            lines.append(f"  - #{m['id']} [{m['source']}] {m['text'][:90]}")
        return "\n".join(lines)

    return ("Noma'lum action. Mavjud: remember (text=...), "
            "recall (query=...), forget (target=...), list")
