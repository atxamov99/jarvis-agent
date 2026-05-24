"""notes.py — create/read/search/delete markdown notes in ~/Notes/"""
import re
import sys
from datetime import datetime
from pathlib import Path

def _notes_dir() -> Path:
    d = Path.home() / "Notes"
    d.mkdir(exist_ok=True)
    return d

def _safe_name(title: str) -> str:
    return re.sub(r'[^\w\s-]', '', title).strip().replace(' ', '_') or "untitled"

def _find(title: str) -> Path | None:
    d = _notes_dir()
    slug = _safe_name(title).lower()
    for f in d.glob("*.md"):
        if f.stem.lower() == slug or slug in f.stem.lower():
            return f
    return None

def notes(parameters=None, response=None, player=None, session_memory=None) -> str:
    params  = parameters or {}
    action  = (params.get("action") or "list").lower().strip()
    title   = (params.get("title") or "").strip()
    content = (params.get("content") or "").strip()
    query   = (params.get("query") or "").strip()

    if action in ("create", "write", "add", "yoz", "yarat"):
        if not title:
            title = f"note_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        path = _notes_dir() / f"{_safe_name(title)}.md"
        ts   = datetime.now().strftime("%Y-%m-%d %H:%M")
        path.write_text(f"# {title}\n*{ts}*\n\n{content}\n", encoding="utf-8")
        if player: player.write_log(f"[Notes] Created: {path.name}")
        return f"Note saved: {path.name}"

    if action in ("append", "qo'sh", "davom"):
        path = _find(title)
        if not path:
            return f"Note not found: '{title}'"
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"\n{datetime.now().strftime('%H:%M')} — {content}\n")
        return f"Appended to {path.name}."

    if action in ("read", "open", "o'qi", "ko'rsat"):
        path = _find(title)
        if not path:
            return f"Note not found: '{title}'"
        text = path.read_text(encoding="utf-8")
        return text[:2000] + ("…" if len(text) > 2000 else "")

    if action in ("list", "all", "hammasi", "ro'yxat"):
        files = sorted(_notes_dir().glob("*.md"))
        if not files:
            return "No notes yet."
        lines = [f"{i+1}. {f.stem.replace('_',' ')} ({f.stat().st_size}B)"
                 for i, f in enumerate(files)]
        return f"Notes ({len(files)}):\n" + "\n".join(lines)

    if action in ("search", "qidir", "top"):
        q = query.lower()
        results = []
        for f in _notes_dir().glob("*.md"):
            text = f.read_text(encoding="utf-8").lower()
            if q in text:
                snippet = text[max(0, text.index(q)-40):text.index(q)+80].replace("\n"," ")
                results.append(f"• {f.stem}: …{snippet}…")
        return "\n".join(results) if results else f"Nothing found for '{query}'."

    if action in ("delete", "o'chir", "remove"):
        path = _find(title)
        if not path:
            return f"Note not found: '{title}'"
        path.unlink()
        return f"Deleted: {path.name}"

    return "Unknown action. Try: create | read | list | search | append | delete"
