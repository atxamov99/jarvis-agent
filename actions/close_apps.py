"""close_apps.py — gracefully close one or more applications by name.

Strategy:
1. Find matching processes via psutil (by name/exe/cmdline).
2. Send SIGTERM (graceful close) — apps get a chance to save state.
3. If still alive after 2s, send SIGKILL.

Works on Linux/macOS via psutil. Falls back to pkill/taskkill if psutil is missing.
"""

import os
import platform
import re
import shutil
import subprocess
import time

_BROWSER_NAMES = {"chrome", "google chrome", "chromium", "firefox", "edge", "brave", "opera"}

try:
    import psutil
    _PSUTIL = True
except ImportError:
    _PSUTIL = False

_OS = platform.system()

_MULTI_SEP_RE = re.compile(
    r"\s*(?:,|;|/|\bva\b|\band\b|\bи\b|&|\+)\s*",
    re.IGNORECASE,
)


def _split_app_names(raw: str) -> list[str]:
    parts = _MULTI_SEP_RE.split(raw or "")
    return [p.strip() for p in parts if p and p.strip()]


# Common aliases — match what user says to actual process names
_APP_PROC_MAP: dict[str, list[str]] = {
    "chrome":           ["chrome", "google-chrome", "google_chrome"],
    "google chrome":    ["chrome", "google-chrome"],
    "firefox":          ["firefox"],
    "edge":             ["msedge", "microsoft-edge"],
    "brave":            ["brave", "brave-browser"],
    "opera":            ["opera"],
    "safari":           ["safari"],
    "telegram":         ["telegram-desktop", "telegram", "Telegram"],
    "whatsapp":         ["whatsapp", "WhatsApp"],
    "discord":          ["discord", "Discord"],
    "signal":           ["signal-desktop", "signal"],
    "slack":            ["slack", "Slack"],
    "zoom":             ["zoom"],
    "spotify":          ["spotify", "Spotify"],
    "vlc":              ["vlc"],
    "vscode":           ["code", "Code"],
    "visual studio code": ["code", "Code"],
    "code":             ["code", "Code"],
    "terminal":         ["gnome-terminal", "konsole", "xterm", "alacritty", "kitty", "Terminal"],
    "files":            ["nautilus", "dolphin", "thunar"],
    "nautilus":         ["nautilus"],
    "obsidian":         ["obsidian"],
    "notion":           ["notion", "Notion"],
    "postman":          ["postman", "Postman"],
    "figma":            ["figma", "Figma"],
    "blender":          ["blender"],
    "steam":            ["steam"],
}


def _candidate_names(query: str) -> list[str]:
    """Return a list of process-name patterns to match against."""
    q = query.lower().strip()
    if q in _APP_PROC_MAP:
        return _APP_PROC_MAP[q]
    # Try fuzzy alias match
    for alias, procs in _APP_PROC_MAP.items():
        if alias in q or q in alias:
            return procs
    # Fallback: assume the user typed the actual process name
    return [q, q.replace(" ", "-"), q.replace(" ", "_")]


def _find_matching_pids(query: str) -> list[int]:
    if not _PSUTIL:
        return []
    candidates = _candidate_names(query)
    candidates_lower = [c.lower() for c in candidates]
    matched: list[int] = []
    for proc in psutil.process_iter(["pid", "name", "exe", "cmdline"]):
        try:
            name = (proc.info.get("name") or "").lower()
            exe  = (proc.info.get("exe") or "").lower()
            cmd  = " ".join(proc.info.get("cmdline") or []).lower()
            if any(c in name or c in exe or c in cmd for c in candidates_lower):
                matched.append(proc.info["pid"])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return matched


def _close_by_window_title(query: str) -> bool:
    """Try closing windows whose title contains query using xdotool. Returns True if any closed."""
    if not shutil.which("xdotool"):
        return False
    try:
        result = subprocess.run(
            ["xdotool", "search", "--name", query],
            capture_output=True, text=True, timeout=5
        )
        wids = [w.strip() for w in result.stdout.splitlines() if w.strip()]
        if not wids:
            return False
        for wid in wids:
            subprocess.run(["xdotool", "windowclose", wid], timeout=3)
        print(f"[close_apps] xdotool closed {len(wids)} window(s) matching '{query}'")
        return True
    except Exception as e:
        print(f"[close_apps] xdotool error: {e}")
        return False


def _close_active_window() -> str:
    """Close whichever window is currently focused."""
    if shutil.which("xdotool"):
        try:
            subprocess.run(["xdotool", "getactivewindow", "windowclose"], timeout=3)
            return "Active window closed."
        except Exception:
            pass
    # Wayland: wtype Alt+F4
    if shutil.which("wtype") and os.environ.get("WAYLAND_DISPLAY"):
        try:
            subprocess.run(["wtype", "-M", "alt", "-k", "F4", "-m", "alt"], timeout=3)
            return "Active window closed (Alt+F4)."
        except Exception:
            pass
    try:
        import pyautogui
        pyautogui.hotkey("alt", "f4")
        return "Active window closed (Alt+F4)."
    except Exception as e:
        return f"Could not close active window: {e}"


_WTYPE_MOD_KEYS = {"ctrl", "alt", "shift", "super", "meta"}

def _send_key_combo(keys: list[str]) -> bool:
    """Send keyboard shortcut — works on Wayland (wtype), X11 (xdotool), or pyautogui."""
    # Wayland: wtype
    if shutil.which("wtype") and os.environ.get("WAYLAND_DISPLAY"):
        mods     = [k for k in keys if k.lower() in _WTYPE_MOD_KEYS]
        regulars = [k for k in keys if k.lower() not in _WTYPE_MOD_KEYS]
        cmd = ["wtype"]
        for m in mods:
            cmd += ["-M", m.lower()]
        for k in regulars:
            cmd += ["-k", k.lower()]
        for m in reversed(mods):
            cmd += ["-m", m.lower()]
        try:
            subprocess.run(cmd, capture_output=True, timeout=3)
            return True
        except Exception:
            pass
    # X11: xdotool
    if shutil.which("xdotool"):
        try:
            combo = "+".join(k.lower() for k in keys)
            subprocess.run(["xdotool", "key", combo], timeout=3)
            return True
        except Exception:
            pass
    try:
        import pyautogui
        pyautogui.hotkey(*[k.lower() for k in keys])
        return True
    except Exception:
        return False


_BROWSER_CLASS_MAP: dict[str, list[str]] = {
    "chrome":        ["Google-chrome", "google-chrome"],
    "google chrome": ["Google-chrome", "google-chrome"],
    "chromium":      ["Chromium",      "chromium-browser"],
    "firefox":       ["Firefox",       "firefox"],
    "edge":          ["Microsoft-edge"],
    "brave":         ["Brave-browser", "brave-browser"],
    "opera":         ["Opera",         "opera"],
}


def _get_stacking_wids() -> list[int]:
    """Window IDs from _NET_CLIENT_LIST_STACKING in stacking order (topmost last)."""
    try:
        out = subprocess.run(
            ["xprop", "-root", "_NET_CLIENT_LIST_STACKING"],
            capture_output=True, text=True, timeout=3
        ).stdout
        m = re.search(r"#\s*([\dx, ]+)", out)
        if m:
            return [int(x.strip(), 16) for x in m.group(1).split(",") if x.strip()]
    except Exception:
        pass
    return []


def _get_windows_by_class(class_names: list[str]) -> list[int]:
    """Window IDs matching any WM_CLASS name, in stacking order (topmost last)."""
    matched: set[int] = set()
    if shutil.which("xdotool"):
        for cls in class_names:
            try:
                out = subprocess.run(
                    ["xdotool", "search", "--onlyvisible", "--class", cls],
                    capture_output=True, text=True, timeout=5
                ).stdout
                for s in out.split():
                    if s.strip():
                        matched.add(int(s.strip()))
            except Exception:
                continue
    if not matched:
        return []
    stacking = _get_stacking_wids()
    ordered  = [w for w in stacking if w in matched]
    return ordered if ordered else list(matched)


def _focus_browser_wayland(browser: str) -> bool:
    """Focus browser window via GNOME Shell D-Bus (Wayland)."""
    t = browser.lower()
    script = (
        "let actors = global.get_window_actors();"
        f"let w = actors.find(a => {{"
        f"  let c = (a.get_meta_window().get_wm_class() || '').toLowerCase();"
        f"  return c.includes('{t}');"
        f"}});"
        "if (w) { w.get_meta_window().activate(0); true; } else false;"
    )
    try:
        r = subprocess.run(
            ["gdbus", "call", "--session",
             "--dest", "org.gnome.Shell",
             "--object-path", "/org/gnome/Shell",
             "--method", "org.gnome.Shell.Eval",
             script],
            capture_output=True, text=True, timeout=5
        )
        return r.returncode == 0 and "(true," in r.stdout
    except Exception:
        return False


def _close_browser_window_only(browser: str) -> str:
    """Close the topmost browser window without killing the process."""
    browser_key = browser.lower().strip()

    # Wayland path: GNOME Shell D-Bus focus + Ctrl+Shift+W
    if os.environ.get("WAYLAND_DISPLAY") and shutil.which("wtype"):
        focused = _focus_browser_wayland(browser_key)
        if focused:
            time.sleep(0.15)
            # Ctrl+Shift+W = close Chrome window (all tabs in this window)
            subprocess.run(
                ["wtype", "-M", "ctrl", "-M", "shift", "-k", "w", "-m", "ctrl", "-m", "shift"],
                capture_output=True, timeout=3
            )
            return f"{browser.capitalize()} oynasi yopildi."
        # Fallback: Alt+F4 on whatever is focused
        subprocess.run(["wtype", "-M", "alt", "-k", "F4", "-m", "alt"], capture_output=True, timeout=3)
        return f"Faol oyna yopildi (Alt+F4)."

    # X11 path
    class_names = _BROWSER_CLASS_MAP.get(browser_key, [browser_key, browser_key.capitalize()])
    wids = _get_windows_by_class(class_names)
    if not wids:
        if _close_by_window_title(browser):
            return f"{browser.capitalize()} oynasi yopildi."
        return f"{browser.capitalize()} oynasi topilmadi."
    try:
        subprocess.run(["xdotool", "windowclose", str(wids[-1])], timeout=3)
        return f"{browser.capitalize()} oynasi yopildi (ilova ochiq qoldi)."
    except Exception as e:
        return f"Yopa olmadim: {e}"


def _close_one(app_name: str) -> str:
    q = app_name.lower().strip()

    # Special keyword: close active/current window
    if q in ("active", "current", "bu", "shu", "hozirgi", "faol"):
        return _close_active_window()

    # Tab close: Ctrl+W on focused window
    if "tab" in q or "sahifa" in q or "вкладка" in q:
        browser = next((b for b in _BROWSER_NAMES if b in q), None)
        ok = _send_key_combo(["ctrl", "w"])
        name = browser.capitalize() if browser else "Brauzer"
        return f"{name} tabini yopdi (Ctrl+W)." if ok else "Tab yopa olmadim."

    # Window close (not entire app): close only the focused window
    if any(w in q for w in ("oyna", "window", "форточка")):
        browser = next((b for b in _BROWSER_NAMES if b in q), None)
        if browser:
            return _close_browser_window_only(browser)
        return _close_active_window()

    if _PSUTIL:
        pids = _find_matching_pids(app_name)
        if pids:
            terminated = []
            killed = []
            for pid in pids:
                try:
                    p = psutil.Process(pid)
                    p.terminate()
                    terminated.append(pid)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            time.sleep(2.0)

            for pid in terminated:
                try:
                    p = psutil.Process(pid)
                    if p.is_running():
                        p.kill()
                        killed.append(pid)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            if killed:
                return f"Closed {app_name} ({len(terminated)} processes, {len(killed)} force-killed)."
            return f"Closed {app_name} ({len(terminated)} process{'es' if len(terminated) != 1 else ''})."

        # Process not found — try closing by window title
        if _close_by_window_title(app_name):
            return f"Closed window(s) matching '{app_name}'."
        return f"No running process or window found for '{app_name}'."

    # Fallback: pkill / taskkill
    if _OS == "Windows":
        if shutil.which("taskkill"):
            r = subprocess.run(
                ["taskkill", "/IM", f"{app_name}.exe", "/F"],
                capture_output=True, text=True, timeout=5,
            )
            return f"Closed {app_name}." if r.returncode == 0 else f"taskkill failed: {r.stderr.strip()}"
    else:
        if shutil.which("pkill"):
            for cand in _candidate_names(app_name):
                r = subprocess.run(["pkill", "-f", cand], capture_output=True, timeout=5)
                if r.returncode == 0:
                    return f"Closed {app_name}."
        # Try window title as last resort
        if _close_by_window_title(app_name):
            return f"Closed window(s) matching '{app_name}'."
        return f"No running process matched '{app_name}'."
    return f"No close mechanism available for '{app_name}'."


def close_apps(parameters=None, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    raw    = (params.get("app_name") or params.get("app_names") or "").strip()

    # "active window" shorthand
    if not raw or raw.lower() in ("active", "current", "bu", "shu", "hozirgi", "faol"):
        if player:
            player.write_log("[close_apps] Closing active window")
        return _close_active_window()

    apps = _split_app_names(raw)
    if not apps:
        apps = [raw]

    if player:
        player.write_log(f"[close_apps] {', '.join(apps)}")

    results = [_close_one(a) for a in apps]
    return " ".join(results)
