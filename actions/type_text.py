"""type_text.py — Type any text into the currently focused window.

Uses xdotool (Linux) for full Unicode/Uzbek support.
Falls back to pyautogui for ASCII-only text.

Useful for: typing into chats, forms, terminals, text editors.
"""

import shutil
import subprocess
import time


def _xdotool_type(text: str, delay_ms: int = 30) -> bool:
    """Type text using xdotool (supports Unicode/Cyrillic/Uzbek)."""
    if not shutil.which("xdotool"):
        return False
    try:
        subprocess.run(
            ["xdotool", "type", "--clearmodifiers", f"--delay={delay_ms}", "--", text],
            timeout=30,
        )
        return True
    except Exception as e:
        print(f"[type_text] xdotool error: {e}")
        return False


def _pyautogui_type(text: str) -> bool:
    try:
        import pyautogui
        pyautogui.write(text, interval=0.04)
        return True
    except Exception as e:
        print(f"[type_text] pyautogui error: {e}")
        return False


def _press_enter():
    if shutil.which("xdotool"):
        try:
            subprocess.run(["xdotool", "key", "Return"], timeout=3)
            return
        except Exception:
            pass
    try:
        import pyautogui
        pyautogui.press("enter")
    except Exception:
        pass


def type_text(parameters=None, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    text   = (params.get("text") or params.get("message") or "").strip()
    send   = str(params.get("send", "false")).lower() in ("true", "1", "yes", "ha", "yuborish")
    delay  = int(params.get("delay", 30))  # ms between keystrokes

    if not text:
        return "Yoziladigan matn ko'rsatilmagan. Masalan: text='Salom, qandaysiz?'"

    if player:
        player.write_log(f"[type_text] Typing: {text[:60]}{'...' if len(text) > 60 else ''}")

    # Small pause so user can focus the target window
    focus_delay = float(params.get("focus_delay", 0.5))
    if focus_delay > 0:
        time.sleep(focus_delay)

    ok = _xdotool_type(text, delay_ms=delay)
    if not ok:
        ok = _pyautogui_type(text)

    if not ok:
        return "Matn yozib bo'lmadi. xdotool yoki pyautogui o'rnatilmagan."

    if send:
        time.sleep(0.1)
        _press_enter()
        return f"✅ Yozildi va yuborildi: {text[:80]}{'...' if len(text) > 80 else ''}"

    return f"✅ Yozildi: {text[:80]}{'...' if len(text) > 80 else ''}"
