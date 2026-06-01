"""email_send.py — Send emails via Gmail SMTP (or any SMTP server).

Config (config/api_keys.json):
  "email_sender":   "your@gmail.com"
  "email_password": "your_app_password"   (Gmail App Password, not account password)
"""
import json
import smtplib
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path


def _cfg() -> dict:
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
    try:
        return json.loads((base / "config" / "api_keys.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def _send(sender: str, password: str, to: str, subject: str, body: str,
          smtp_host: str = "smtp.gmail.com", smtp_port: int = 587) -> str:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to
    msg.attach(MIMEText(body, "plain", "utf-8"))

    with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
        server.ehlo()
        server.starttls()
        server.login(sender, password)
        server.sendmail(sender, to, msg.as_string())
    return f"Email '{subject}' → {to} ga muvaffaqiyatli yuborildi."


def email_send(parameters=None, response=None, player=None, session_memory=None) -> str:
    params  = parameters or {}
    cfg     = _cfg()

    sender   = cfg.get("email_sender", "").strip()
    password = cfg.get("email_password", "").strip()

    if not sender or not password:
        return (
            "Email sozlanmagan. config/api_keys.json ga quyidagilarni qo'shing:\n"
            '  "email_sender": "your@gmail.com",\n'
            '  "email_password": "your_app_password"\n'
            "Gmail App Password olish uchun: myaccount.google.com/apppasswords"
        )

    to      = (params.get("to") or params.get("recipient") or params.get("email") or "").strip()
    subject = (params.get("subject") or params.get("mavzu") or "Jarvis xabari").strip()
    body    = (params.get("body") or params.get("message") or params.get("matn") or "").strip()

    if not to:
        return "Qabul qiluvchi email manzilini ko'rsating (to parametri)."
    if not body:
        return "Email matnini ko'rsating (body parametri)."
    if "@" not in to:
        return f"'{to}' to'g'ri email manzil emas."

    smtp_host = cfg.get("smtp_host", "smtp.gmail.com")
    smtp_port = int(cfg.get("smtp_port", 587))

    try:
        result = _send(sender, password, to, subject, body, smtp_host, smtp_port)
        if player:
            player.write_log(f"[Email] Yuborildi → {to}")
        return result
    except smtplib.SMTPAuthenticationError:
        return "Email autentifikatsiya xatosi. Gmail App Password to'g'riligini tekshiring."
    except smtplib.SMTPException as e:
        return f"SMTP xatosi: {e}"
    except Exception as e:
        return f"Email yuborishda xato: {e}"
