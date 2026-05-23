"""close_apps.py — gracefully close one or more applications by name.

Strategy:
1. Find matching processes via psutil (by name/exe/cmdline).
2. Send SIGTERM (graceful close) — apps get a chance to save state.
3. If still alive after 2s, send SIGKILL.

Works on Linux/macOS via psutil. Falls back to pkill/taskkill if psutil is missing.
"""

import platform
import re
import shutil
import subprocess
import time

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


def _close_one(app_name: str) -> str:
    if _PSUTIL:
        pids = _find_matching_pids(app_name)
        if not pids:
            return f"No running process found for '{app_name}'."

        terminated = []
        killed = []
        for pid in pids:
            try:
                p = psutil.Process(pid)
                p.terminate()
                terminated.append(pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        # Give them 2 seconds to shut down gracefully
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
            return f"No running process matched '{app_name}'."
    return f"No close mechanism available for '{app_name}'."


def close_apps(parameters=None, response=None, player=None, session_memory=None) -> str:
    params   = parameters or {}
    raw      = (params.get("app_name") or params.get("app_names") or "").strip()

    if not raw:
        return "No application name provided."

    apps = _split_app_names(raw)
    if not apps:
        apps = [raw]

    if player:
        player.write_log(f"[close_apps] {', '.join(apps)}")

    results = [_close_one(a) for a in apps]
    return " ".join(results)
