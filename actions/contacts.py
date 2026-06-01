"""contacts.py — Personal phone book stored in SQLite.

Database: data/contacts.db (created automatically).
"""
import json
import re
import sqlite3
import sys
from pathlib import Path


def _db_path() -> Path:
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
    db_dir = base / "data"
    db_dir.mkdir(exist_ok=True)
    return db_dir / "contacts.db"


def _conn():
    con = sqlite3.connect(str(_db_path()))
    con.execute("""
        CREATE TABLE IF NOT EXISTS contacts (
            id    INTEGER PRIMARY KEY AUTOINCREMENT,
            name  TEXT NOT NULL,
            phone TEXT,
            email TEXT,
            notes TEXT
        )
    """)
    con.commit()
    return con


def _fmt(row) -> str:
    rid, name, phone, email, notes = row
    parts = [f"[{rid}] {name}"]
    if phone:  parts.append(f"  Tel: {phone}")
    if email:  parts.append(f"  Email: {email}")
    if notes:  parts.append(f"  Eslatma: {notes}")
    return "\n".join(parts)


def contacts(parameters=None, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    action = (params.get("action") or "list").lower().strip()

    con = _conn()
    cur = con.cursor()

    try:
        # ── ADD ───────────────────────────────────────────────────────────────
        if action in ("add", "create", "qosh", "yangi"):
            name  = (params.get("name") or "").strip()
            if not name:
                return "Kontakt nomini ko'rsating (name parametri)."
            phone = (params.get("phone") or params.get("tel") or "").strip()
            email = (params.get("email") or "").strip()
            notes = (params.get("notes") or params.get("note") or "").strip()
            cur.execute("INSERT INTO contacts (name,phone,email,notes) VALUES (?,?,?,?)",
                        (name, phone, email, notes))
            con.commit()
            return f"'{name}' kontaktlar kitobiga qo'shildi (ID: {cur.lastrowid})."

        # ── SEARCH / FIND ─────────────────────────────────────────────────────
        if action in ("search", "find", "qidir", "izla"):
            query = (params.get("query") or params.get("name") or params.get("q") or "").strip()
            if not query:
                return "Qidiruv so'zini ko'rsating."
            like = f"%{query}%"
            rows = cur.execute(
                "SELECT * FROM contacts WHERE name LIKE ? OR phone LIKE ? OR email LIKE ?",
                (like, like, like)
            ).fetchall()
            if not rows:
                return f"'{query}' bo'yicha kontakt topilmadi."
            return "\n\n".join(_fmt(r) for r in rows)

        # ── LIST ──────────────────────────────────────────────────────────────
        if action in ("list", "all", "barchasi", "ko'rsat"):
            rows = cur.execute("SELECT * FROM contacts ORDER BY name").fetchall()
            if not rows:
                return "Kontaktlar kitobi bo'sh."
            return f"Jami {len(rows)} ta kontakt:\n\n" + "\n\n".join(_fmt(r) for r in rows)

        # ── DELETE ────────────────────────────────────────────────────────────
        if action in ("delete", "remove", "o'chir"):
            cid = params.get("id")
            name = (params.get("name") or "").strip()
            if cid:
                cur.execute("DELETE FROM contacts WHERE id=?", (int(cid),))
                con.commit()
                return f"Kontakt #{cid} o'chirildi."
            if name:
                cur.execute("DELETE FROM contacts WHERE name LIKE ?", (f"%{name}%",))
                con.commit()
                return f"'{name}' nomli kontaktlar o'chirildi."
            return "O'chirish uchun ID yoki nom ko'rsating."

        # ── UPDATE ────────────────────────────────────────────────────────────
        if action in ("update", "edit", "tahrir"):
            cid = params.get("id")
            if not cid:
                return "Yangilash uchun kontakt ID sini ko'rsating."
            fields = []
            vals   = []
            for col in ("name", "phone", "email", "notes"):
                val = params.get(col)
                if val is not None:
                    fields.append(f"{col}=?")
                    vals.append(str(val).strip())
            if not fields:
                return "Yangilanadigan maydon ko'rsating (name/phone/email/notes)."
            vals.append(int(cid))
            cur.execute(f"UPDATE contacts SET {', '.join(fields)} WHERE id=?", vals)
            con.commit()
            return f"Kontakt #{cid} yangilandi."

        # ── GET ───────────────────────────────────────────────────────────────
        if action in ("get", "info", "ko'r"):
            cid = params.get("id")
            name = (params.get("name") or "").strip()
            if cid:
                row = cur.execute("SELECT * FROM contacts WHERE id=?", (int(cid),)).fetchone()
            elif name:
                row = cur.execute("SELECT * FROM contacts WHERE name LIKE ? LIMIT 1",
                                  (f"%{name}%",)).fetchone()
            else:
                return "ID yoki nom ko'rsating."
            if not row:
                return "Kontakt topilmadi."
            return _fmt(row)

        return "Amallar: add | list | search | get | update | delete"

    finally:
        con.close()
