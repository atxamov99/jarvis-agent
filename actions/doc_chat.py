"""doc_chat.py — "Chat with your documents" (local file RAG).

Index local files (txt, md, pdf, docx, code) into a vector store, then answer
questions grounded in their content. "Mening rezyumemda nima yozilgan?",
"shu papkadagi hujjatlarni xulosa qil", "qaysi faylda X haqida gap bor?".

Reuses the Gemini embeddings from smart_memory; answers via gemini-2.0-flash.
"""
import sqlite3
import subprocess
import time
import zipfile
import re
from pathlib import Path
from threading import Lock

import numpy as np

from actions.smart_memory import _embed, _get_client

_BASE    = Path(__file__).resolve().parent.parent
_DB_PATH = _BASE / "data" / "doc_chat.db"
_lock    = Lock()

_TEXT_EXT = {".txt", ".md", ".markdown", ".py", ".js", ".ts", ".json", ".csv",
             ".html", ".css", ".java", ".c", ".cpp", ".go", ".rs", ".sh", ".log", ".rtf"}
_MAX_FILE_BYTES = 5_000_000


def _connect() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chunks (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            file      TEXT NOT NULL,
            chunk_idx INTEGER,
            text      TEXT NOT NULL,
            ts        REAL,
            dim       INTEGER,
            embedding BLOB
        )
    """)
    return conn


def _extract_text(path: Path) -> str:
    ext = path.suffix.lower()
    try:
        if ext == ".pdf":
            r = subprocess.run(["pdftotext", "-layout", str(path), "-"],
                               capture_output=True, text=True, timeout=60)
            return r.stdout
        if ext == ".docx":
            with zipfile.ZipFile(str(path)) as z:
                xml = z.read("word/document.xml").decode("utf-8", "ignore")
            xml = xml.replace("</w:p>", "\n")
            return re.sub(r"<[^>]+>", "", xml)
        if ext in _TEXT_EXT or ext == "":
            return path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        print(f"[DocChat] extract error {path.name}: {e}")
    return ""


def _chunk(text: str, size: int = 380, overlap: int = 60) -> list:
    words = text.split()
    if not words:
        return []
    out, i = [], 0
    while i < len(words):
        out.append(" ".join(words[i:i + size]))
        i += size - overlap
    return out


def _index_file(path: Path) -> int:
    if not path.is_file() or path.stat().st_size > _MAX_FILE_BYTES:
        return 0
    text = _extract_text(path).strip()
    if not text:
        return 0
    chunks = _chunk(text)
    stored = 0
    with _lock:
        conn = _connect()
        conn.execute("DELETE FROM chunks WHERE file=?", (str(path),))  # re-index fresh
        for idx, ch in enumerate(chunks):
            vec = _embed(ch, task_type="RETRIEVAL_DOCUMENT")
            blob = vec.tobytes() if vec is not None else None
            dim  = int(vec.shape[0]) if vec is not None else 0
            conn.execute(
                "INSERT INTO chunks (file, chunk_idx, text, ts, dim, embedding) VALUES (?,?,?,?,?,?)",
                (str(path), idx, ch, time.time(), dim, blob),
            )
            stored += 1
        conn.commit()
        conn.close()
    return stored


def _index_path(target: str) -> str:
    p = Path(target).expanduser()
    if not p.exists():
        return f"Topilmadi: {target}"
    files, total = [], 0
    if p.is_file():
        files = [p]
    else:
        for f in p.rglob("*"):
            if f.is_file() and (f.suffix.lower() in _TEXT_EXT or f.suffix.lower() in (".pdf", ".docx")):
                files.append(f)
    if not files:
        return "Indekslash uchun qo'llab-quvvatlanadigan fayl topilmadi."
    done = 0
    for f in files[:200]:
        n = _index_file(f)
        if n:
            total += n
            done += 1
    return f"✅ {done} ta fayl indekslandi ({total} ta bo'lak). Endi savol bering."


def _ask(query: str, k: int = 6) -> str:
    qvec = _embed(query, task_type="RETRIEVAL_QUERY")
    with _lock:
        conn = _connect()
        rows = conn.execute("SELECT file, text, dim, embedding FROM chunks").fetchall()
        conn.close()
    if not rows:
        return "Hali hujjat indekslanmagan. Avval: doc_chat action=index path=..."

    scored = []
    for file, text, dim, blob in rows:
        if qvec is not None and dim and blob:
            vec = np.frombuffer(blob, dtype=np.float32)
            score = float(np.dot(qvec, vec)) if vec.shape[0] == qvec.shape[0] else 0.0
        else:
            ql = set(query.lower().split()); tl = set(text.lower().split())
            score = len(ql & tl) / max(len(ql), 1)
        scored.append((score, file, text))
    scored.sort(key=lambda r: r[0], reverse=True)
    top = scored[:k]

    context, used = [], []
    budget = 7000
    for score, file, text in top:
        snippet = f"[{Path(file).name}]\n{text}"
        if budget - len(snippet) < 0:
            break
        context.append(snippet); budget -= len(snippet)
        if Path(file).name not in used:
            used.append(Path(file).name)

    client = _get_client()
    if client is None:
        return "Hujjatlardan topildi, lekin javob modeli ulanmadi:\n\n" + "\n\n".join(context[:2])

    prompt = (
        "Quyidagi hujjat bo'laklaridan FOYDALANIB savolga o'zbek tilida aniq javob ber. "
        "Faqat shu kontentga tayan; agar javob yo'q bo'lsa, 'hujjatlarda topilmadi' de. "
        "Qaysi fayldan olganingni qavsda ko'rsat.\n\n"
        f"=== HUJJATLAR ===\n{chr(10).join(context)}\n\n=== SAVOL ===\n{query}"
    )
    try:
        res = client.models.generate_content(model="gemini-2.5-flash-lite", contents=prompt)
        ans = (res.text or "").strip()
        return ans + (f"\n\n📄 Manba: {', '.join(used)}" if used else "")
    except Exception as e:
        return f"Javob yaratishda xato: {e}\n\nTopilgan bo'laklar: {', '.join(used)}"


def doc_chat(parameters=None, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    action = (params.get("action") or "ask").lower().strip()

    if action in ("index", "add", "ingest", "indeks"):
        target = params.get("path") or params.get("target") or params.get("folder") or ""
        if not target:
            return "Indekslash uchun fayl/papka yo'lini bering (path=...)."
        if player:
            player.write_log(f"[DocChat] Indekslanmoqda: {target}")
        return _index_path(target)

    if action in ("ask", "query", "savol", "search"):
        q = params.get("query") or params.get("question") or params.get("text") or ""
        if not q:
            return "Savolingizni yozing (query=...)."
        if player:
            player.write_log(f"[DocChat] Savol: {q[:50]}")
        return _ask(q, int(params.get("k", 6)))

    if action in ("list", "files", "royxat"):
        with _lock:
            conn = _connect()
            rows = conn.execute(
                "SELECT file, COUNT(*) FROM chunks GROUP BY file ORDER BY MAX(ts) DESC"
            ).fetchall()
            conn.close()
        if not rows:
            return "Hech qanday hujjat indekslanmagan."
        lines = [f"Indekslangan hujjatlar ({len(rows)} ta):"]
        for file, cnt in rows:
            lines.append(f"  • {Path(file).name} ({cnt} bo'lak)")
        return "\n".join(lines)

    if action in ("clear", "reset", "tozala", "delete"):
        target = params.get("path") or params.get("target") or ""
        with _lock:
            conn = _connect()
            if target:
                cur = conn.execute("DELETE FROM chunks WHERE file LIKE ?", (f"%{target}%",))
                msg = f"🗑️ {cur.rowcount} bo'lak o'chirildi."
            else:
                conn.execute("DELETE FROM chunks")
                msg = "🗑️ Barcha indeks tozalandi."
            conn.commit(); conn.close()
        return msg

    return "Amallar: index (path=...), ask (query=...), list, clear"
