"""todo.py — Structured task list with deadlines and priorities."""
import json
import time
from datetime import datetime
from pathlib import Path

_TODO_FILE = Path.home() / "Notes" / "tasks.json"


def _load() -> list:
    try: return json.loads(_TODO_FILE.read_text(encoding="utf-8"))
    except Exception: return []


def _save(data: list):
    _TODO_FILE.parent.mkdir(exist_ok=True)
    _TODO_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _parse_deadline(text: str) -> str | None:
    if not text: return None
    text = text.strip().lower()
    now  = datetime.now()
    maps = {"bugun": 0, "today": 0, "ertaga": 1, "tomorrow": 1,
            "indinga": 2, "hafta": 7, "week": 7}
    for word, days in maps.items():
        if text == word:
            return (now.replace(hour=23, minute=59) + __import__("datetime").timedelta(days=days)).strftime("%Y-%m-%d")
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        try: return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError: pass
    return text


_PRIORITY_ICON = {"high": "🔴", "medium": "🟡", "low": "🟢"}
_STATUS_ICON   = {"pending": "⏳", "done": "✅", "cancelled": "❌"}


def todo(parameters=None, response=None, player=None, session_memory=None) -> str:
    params   = parameters or {}
    action   = (params.get("action") or "list").lower().strip()
    title    = (params.get("title") or "").strip()
    priority = (params.get("priority") or "medium").lower().strip()
    deadline = _parse_deadline(params.get("deadline") or "")
    query    = (params.get("query") or "").strip().lower()
    filter_s = (params.get("filter") or "pending").lower().strip()

    # ── ADD ───────────────────────────────────────────────────────────────────
    if action in ("add", "qo'sh", "yarat", "create"):
        if not title:
            return "Vazifa matni ko'rsatilmagan."
        task = {
            "id":       int(time.time() * 1000),
            "title":    title,
            "priority": priority if priority in ("high", "medium", "low") else "medium",
            "deadline": deadline,
            "status":   "pending",
            "created":  datetime.now().strftime("%Y-%m-%d"),
        }
        tasks = _load()
        tasks.append(task)
        _save(tasks)
        dl = f" (deadline: {deadline})" if deadline else ""
        pi = _PRIORITY_ICON.get(task["priority"], "🟡")
        if player: player.write_log(f"[Todo] Added: {title}")
        return f"{pi} Vazifa qo'shildi: {title}{dl}"

    # ── LIST ──────────────────────────────────────────────────────────────────
    if action in ("list", "ko'rsat", "hammasi", "ro'yxat"):
        tasks = _load()
        if not tasks:
            return "Vazifalar yo'q."
        if filter_s == "all":
            shown = tasks
        elif filter_s == "done":
            shown = [t for t in tasks if t["status"] == "done"]
        else:
            shown = [t for t in tasks if t["status"] == "pending"]

        # Sort: high → medium → low, then by deadline
        priority_order = {"high": 0, "medium": 1, "low": 2}
        shown.sort(key=lambda t: (priority_order.get(t.get("priority", "medium"), 1),
                                  t.get("deadline") or "9999"))

        if not shown:
            return f"'{filter_s}' holati bilan vazifalar yo'q."

        today = datetime.now().strftime("%Y-%m-%d")
        lines = []
        for i, t in enumerate(shown, 1):
            pi  = _PRIORITY_ICON.get(t.get("priority", "medium"), "🟡")
            si  = _STATUS_ICON.get(t.get("status", "pending"), "⏳")
            dl  = t.get("deadline", "")
            dlm = f" [{dl}{'⚠️' if dl and dl < today else ''}]" if dl else ""
            lines.append(f"{i}. {si}{pi} {t['title']}{dlm}")

        header = f"Vazifalar ({len(shown)}/{len(tasks)}, filter: {filter_s})"
        return header + ":\n" + "\n".join(lines)

    # ── DONE ──────────────────────────────────────────────────────────────────
    if action in ("done", "bajarildi", "tugat", "complete"):
        if not title and not query:
            return "Qaysi vazifa bajarildi? title yoki query ko'rsating."
        tasks = _load()
        q     = (title or query).lower()
        target = next((t for t in tasks if q in t["title"].lower() and t["status"] == "pending"), None)
        if not target:
            return f"'{q}' nomi bilan faol vazifa topilmadi."
        target["status"] = "done"
        target["done_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        _save(tasks)
        if player: player.write_log(f"[Todo] Done: {target['title']}")
        return f"✅ Bajarildi: {target['title']}"

    # ── DELETE ────────────────────────────────────────────────────────────────
    if action in ("delete", "o'chir", "remove"):
        q     = (title or query).lower()
        tasks = _load()
        target = next((t for t in tasks if q in t["title"].lower()), None)
        if not target:
            return f"'{q}' topilmadi."
        tasks.remove(target)
        _save(tasks)
        return f"O'chirildi: {target['title']}"

    # ── SEARCH ────────────────────────────────────────────────────────────────
    if action in ("search", "qidir"):
        if not query:
            return "query ko'rsatilmagan."
        tasks = _load()
        found = [t for t in tasks if query in t["title"].lower()]
        if not found:
            return f"'{query}' topilmadi."
        lines = [f"• {_STATUS_ICON.get(t['status'],'⏳')} {t['title']} [{t.get('deadline','-')}]"
                 for t in found]
        return f"'{query}' natijalar ({len(found)}):\n" + "\n".join(lines)

    # ── TODAY ─────────────────────────────────────────────────────────────────
    if action in ("today", "bugun"):
        today = datetime.now().strftime("%Y-%m-%d")
        tasks = _load()
        due   = [t for t in tasks if t.get("deadline") == today and t["status"] == "pending"]
        late  = [t for t in tasks if t.get("deadline") and t["deadline"] < today and t["status"] == "pending"]
        lines = []
        if late:
            lines.append(f"⚠️ Kechikkan ({len(late)}):")
            lines += [f"  🔴 {t['title']} [{t['deadline']}]" for t in late]
        if due:
            lines.append(f"📅 Bugun ({len(due)}):")
            lines += [f"  {_PRIORITY_ICON.get(t.get('priority','medium'),'🟡')} {t['title']}"
                      for t in due]
        if not lines:
            return "Bugun uchun vazifalar yo'q!"
        return "\n".join(lines)

    return "Amallar: add | list | done | delete | search | today"
