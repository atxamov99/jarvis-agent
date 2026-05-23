"""clipboard.py — read/write the system clipboard.

Works across:
- Linux Wayland: wl-copy / wl-paste
- Linux X11:     xclip / xsel
- macOS:         pbcopy / pbpaste
- Windows:       pyperclip (already installed)

The tool exposes two actions:
- get / read  → return current clipboard text
- set / copy  → place provided text into the clipboard
"""

import platform
import shutil
import subprocess

_OS = platform.system()


def _wayland_active() -> bool:
    import os
    return bool(os.environ.get("WAYLAND_DISPLAY"))


def _linux_get() -> str:
    if _wayland_active() and shutil.which("wl-paste"):
        r = subprocess.run(["wl-paste", "-n"], capture_output=True, text=True, timeout=3)
        if r.returncode == 0:
            return r.stdout
    if shutil.which("xclip"):
        r = subprocess.run(
            ["xclip", "-selection", "clipboard", "-o"],
            capture_output=True, text=True, timeout=3,
        )
        if r.returncode == 0:
            return r.stdout
    if shutil.which("xsel"):
        r = subprocess.run(
            ["xsel", "--clipboard", "--output"],
            capture_output=True, text=True, timeout=3,
        )
        if r.returncode == 0:
            return r.stdout
    return ""


def _linux_set(text: str) -> bool:
    if _wayland_active() and shutil.which("wl-copy"):
        r = subprocess.run(["wl-copy"], input=text, text=True, timeout=3)
        return r.returncode == 0
    if shutil.which("xclip"):
        r = subprocess.run(
            ["xclip", "-selection", "clipboard"],
            input=text, text=True, timeout=3,
        )
        return r.returncode == 0
    if shutil.which("xsel"):
        r = subprocess.run(
            ["xsel", "--clipboard", "--input"],
            input=text, text=True, timeout=3,
        )
        return r.returncode == 0
    return False


def _macos_get() -> str:
    r = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=3)
    return r.stdout if r.returncode == 0 else ""


def _macos_set(text: str) -> bool:
    r = subprocess.run(["pbcopy"], input=text, text=True, timeout=3)
    return r.returncode == 0


def _pyperclip_get() -> str:
    try:
        import pyperclip
        return pyperclip.paste() or ""
    except Exception:
        return ""


def _pyperclip_set(text: str) -> bool:
    try:
        import pyperclip
        pyperclip.copy(text)
        return True
    except Exception:
        return False


def _clipboard_get() -> str:
    if _OS == "Linux":
        out = _linux_get()
        return out if out else _pyperclip_get()
    if _OS == "Darwin":
        return _macos_get()
    return _pyperclip_get()


def _clipboard_set(text: str) -> bool:
    if _OS == "Linux":
        return _linux_set(text) or _pyperclip_set(text)
    if _OS == "Darwin":
        return _macos_set(text) or _pyperclip_set(text)
    return _pyperclip_set(text)


def clipboard(parameters=None, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    action = (params.get("action") or "get").lower().strip()
    text   = params.get("text", "")

    if action in ("get", "read", "paste", "show"):
        content = _clipboard_get()
        if not content:
            msg = "Clipboard is empty."
        else:
            preview = content if len(content) < 400 else content[:400] + f"... (+{len(content)-400} chars)"
            msg = f"Clipboard ({len(content)} chars):\n{preview}"
        if player:
            player.write_log(f"[clipboard] get → {len(content)} chars")
        return msg

    if action in ("set", "copy", "write", "put"):
        if not text:
            return "No text provided to copy."
        ok = _clipboard_set(text)
        if player:
            player.write_log(f"[clipboard] set ({len(text)} chars) {'✓' if ok else '✗'}")
        return f"Copied {len(text)} chars to clipboard." if ok else "Clipboard write failed (no clipboard tool found)."

    if action in ("clear", "empty"):
        ok = _clipboard_set("")
        return "Clipboard cleared." if ok else "Could not clear clipboard."

    return f"Unknown clipboard action: '{action}'. Try: get | set | clear"
