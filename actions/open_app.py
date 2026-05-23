import time
import subprocess
import platform
import shutil
import os
import re
import shlex
from pathlib import Path

try:
    import psutil
    _PSUTIL = True
except ImportError:
    _PSUTIL = False

_SYSTEM = platform.system()


_DESKTOP_DIRS = [
    Path.home() / ".local/share/applications",
    Path("/usr/share/applications"),
    Path("/usr/local/share/applications"),
    Path("/var/lib/flatpak/exports/share/applications"),
    Path.home() / ".local/share/flatpak/exports/share/applications",
    Path("/var/lib/snapd/desktop/applications"),
]


def _parse_desktop_file(path: Path) -> dict:
    info = {}
    try:
        in_main = False
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line.startswith("["):
                in_main = (line == "[Desktop Entry]")
                continue
            if not in_main or "=" not in line:
                continue
            key, _, val = line.partition("=")
            info.setdefault(key.strip(), val.strip())
    except Exception:
        return {}
    return info


def _find_desktop_file(query: str) -> tuple[Path, dict] | None:
    """Search desktop files for one whose Name/filename matches the query."""
    q = query.lower().strip()
    q_compact = re.sub(r"[^a-z0-9]", "", q)
    candidates: list[tuple[int, Path, dict]] = []

    for d in _DESKTOP_DIRS:
        if not d.is_dir():
            continue
        for entry in d.glob("*.desktop"):
            info = _parse_desktop_file(entry)
            if not info or info.get("NoDisplay", "").lower() == "true":
                continue
            name = info.get("Name", "").lower()
            fname = entry.stem.lower()
            name_compact = re.sub(r"[^a-z0-9]", "", name)
            fname_compact = re.sub(r"[^a-z0-9]", "", fname)

            score = 0
            if name == q or fname == q:
                score = 100
            elif name_compact == q_compact or fname_compact == q_compact:
                score = 90
            elif q_compact and (q_compact in name_compact or q_compact in fname_compact):
                score = 70
            elif q in name or q in fname:
                score = 60

            if score:
                candidates.append((score, entry, info))

    if not candidates:
        return None
    candidates.sort(key=lambda t: -t[0])
    _, path, info = candidates[0]
    return path, info


def _exec_from_desktop(exec_line: str) -> list[str]:
    """Strip desktop-entry field codes (%U, %f, %u, %F, etc.) and split into argv."""
    cleaned = re.sub(r"\s+%[a-zA-Z]", "", exec_line).strip()
    try:
        argv = shlex.split(cleaned)
    except ValueError:
        argv = cleaned.split()
    # Drop trailing '--' (end-of-options marker left over after stripping %U/%F)
    while argv and argv[-1] == "--":
        argv.pop()
    return argv

_APP_ALIASES: dict[str, dict[str, str]] = {

    "chrome":             {"Windows": "chrome",                  "Darwin": "Google Chrome",        "Linux": "google-chrome"},
    "google chrome":      {"Windows": "chrome",                  "Darwin": "Google Chrome",        "Linux": "google-chrome"},
    "firefox":            {"Windows": "firefox",                 "Darwin": "Firefox",              "Linux": "firefox"},
    "edge":               {"Windows": "msedge",                  "Darwin": "Microsoft Edge",       "Linux": "microsoft-edge"},
    "brave":              {"Windows": "brave",                   "Darwin": "Brave Browser",        "Linux": "brave-browser"},
    "safari":             {"Windows": "msedge",                  "Darwin": "Safari",               "Linux": "firefox"},
    "opera":              {"Windows": "opera",                   "Darwin": "Opera",                "Linux": "opera"},
    "whatsapp":           {"Windows": "WhatsApp",                "Darwin": "WhatsApp",             "Linux": "whatsapp"},
    "telegram":           {"Windows": "Telegram",                "Darwin": "Telegram",             "Linux": "telegram"},
    "discord":            {"Windows": "Discord",                 "Darwin": "Discord",              "Linux": "discord"},
    "slack":              {"Windows": "Slack",                   "Darwin": "Slack",                "Linux": "slack"},
    "zoom":               {"Windows": "Zoom",                    "Darwin": "zoom.us",              "Linux": "zoom"},
    "teams":              {"Windows": "msteams",                 "Darwin": "Microsoft Teams",      "Linux": "teams"},
    "skype":              {"Windows": "skype",                   "Darwin": "Skype",                "Linux": "skype"},
    "signal":             {"Windows": "signal",                  "Darwin": "Signal",               "Linux": "signal"},
    "spotify":            {"Windows": "Spotify",                 "Darwin": "Spotify",              "Linux": "spotify"},
    "vlc":                {"Windows": "vlc",                     "Darwin": "VLC",                  "Linux": "vlc"},
    "netflix":            {"Windows": "Netflix",                 "Darwin": "Netflix",              "Linux": "firefox"},
    "vscode":             {"Windows": "code",                    "Darwin": "Visual Studio Code",   "Linux": "code"},
    "visual studio code": {"Windows": "code",                    "Darwin": "Visual Studio Code",   "Linux": "code"},
    "code":               {"Windows": "code",                    "Darwin": "Visual Studio Code",   "Linux": "code"},
    "terminal":           {"Windows": "wt",                      "Darwin": "Terminal",             "Linux": "gnome-terminal"},
    "cmd":                {"Windows": "cmd.exe",                 "Darwin": "Terminal",             "Linux": "bash"},
    "powershell":         {"Windows": "powershell.exe",          "Darwin": "Terminal",             "Linux": "bash"},
    "postman":            {"Windows": "Postman",                 "Darwin": "Postman",              "Linux": "postman"},
    "git":                {"Windows": "git-bash",                "Darwin": "Terminal",             "Linux": "bash"},
    "figma":              {"Windows": "Figma",                   "Darwin": "Figma",                "Linux": "figma"},
    "blender":            {"Windows": "blender",                 "Darwin": "Blender",              "Linux": "blender"},
    "word":               {"Windows": "winword",                 "Darwin": "Microsoft Word",       "Linux": "libreoffice --writer"},
    "excel":              {"Windows": "excel",                   "Darwin": "Microsoft Excel",      "Linux": "libreoffice --calc"},
    "powerpoint":         {"Windows": "powerpnt",                "Darwin": "Microsoft PowerPoint", "Linux": "libreoffice --impress"},
    "libreoffice":        {"Windows": "soffice",                 "Darwin": "LibreOffice",          "Linux": "libreoffice"},
    "notepad":            {"Windows": "notepad.exe",             "Darwin": "TextEdit",             "Linux": "gedit"},
    "textedit":           {"Windows": "notepad.exe",             "Darwin": "TextEdit",             "Linux": "gedit"},
    "explorer":           {"Windows": "explorer.exe",            "Darwin": "Finder",               "Linux": "nautilus"},
    "file explorer":      {"Windows": "explorer.exe",            "Darwin": "Finder",               "Linux": "nautilus"},
    "finder":             {"Windows": "explorer.exe",            "Darwin": "Finder",               "Linux": "nautilus"},
    "task manager":       {"Windows": "taskmgr.exe",             "Darwin": "Activity Monitor",     "Linux": "gnome-system-monitor"},
    "settings":           {"Windows": "ms-settings:",            "Darwin": "System Preferences",   "Linux": "gnome-control-center"},
    "calculator":         {"Windows": "calc.exe",                "Darwin": "Calculator",           "Linux": "gnome-calculator"},
    "paint":              {"Windows": "mspaint.exe",             "Darwin": "Preview",              "Linux": "gimp"},
    "instagram":          {"Windows": "Instagram",               "Darwin": "Instagram",            "Linux": "firefox"},
    "tiktok":             {"Windows": "TikTok",                  "Darwin": "TikTok",               "Linux": "firefox"},
    "notion":             {"Windows": "Notion",                  "Darwin": "Notion",               "Linux": "notion"},
    "obsidian":           {"Windows": "Obsidian",                "Darwin": "Obsidian",             "Linux": "obsidian"},
    "capcut":             {"Windows": "CapCut",                  "Darwin": "CapCut",               "Linux": "capcut"},
    "steam":              {"Windows": "steam",                   "Darwin": "Steam",                "Linux": "steam"},
    "epic":               {"Windows": "EpicGamesLauncher",       "Darwin": "Epic Games Launcher",  "Linux": "legendary"},
    "epic games":         {"Windows": "EpicGamesLauncher",       "Darwin": "Epic Games Launcher",  "Linux": "legendary"},
}


def _steam_library_paths() -> list[Path]:
    """Return all Steam library roots from libraryfolders.vdf."""
    roots: list[Path] = []
    default = Path("C:/Program Files (x86)/Steam")
    candidates = [default]
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                             r"SOFTWARE\WOW6432Node\Valve\Steam")
        install_path = winreg.QueryValueEx(key, "InstallPath")[0]
        candidates.insert(0, Path(install_path))
    except Exception:
        pass

    for steam_root in candidates:
        vdf = steam_root / "steamapps" / "libraryfolders.vdf"
        if vdf.exists():
            roots.append(steam_root)
            try:
                text = vdf.read_text(encoding="utf-8", errors="ignore")
                for m in re.finditer(r'"path"\s+"([^"]+)"', text):
                    p = Path(m.group(1))
                    if p.is_dir():
                        roots.append(p)
            except Exception:
                pass
    return roots


def _steam_appid_for_dir(steam_root: Path, game_dir_name: str) -> str | None:
    """Look up Steam App ID from appmanifest_*.acf files."""
    acf_dir = steam_root / "steamapps"
    if not acf_dir.is_dir():
        return None
    q = game_dir_name.lower()
    for acf in acf_dir.glob("appmanifest_*.acf"):
        try:
            text = acf.read_text(encoding="utf-8", errors="ignore")
            install_m = re.search(r'"installdir"\s+"([^"]+)"', text)
            if install_m and install_m.group(1).lower() == q:
                appid_m = re.search(r'"appid"\s+"(\d+)"', text)
                if appid_m:
                    return appid_m.group(1)
        except Exception:
            pass
    return None


def _find_steam_exe() -> Path | None:
    for lib in _steam_library_paths():
        exe = lib / "steam.exe"
        if exe.exists():
            return exe
    default = Path("C:/Program Files (x86)/Steam/steam.exe")
    return default if default.exists() else None


def _find_game_exe(query: str) -> tuple[Path, str | None] | None:
    """Search Steam/Epic library folders for a game.
    Returns (exe_path, steam_appid_or_None)."""
    q = re.sub(r"[^a-z0-9]", "", query.lower())

    steam_libs = _steam_library_paths()
    search_roots: list[tuple[Path, Path | None]] = []  # (games_root, steam_root)
    for lib in steam_libs:
        search_roots.append((lib / "steamapps" / "common", lib))

    for epic_root in [
        Path("C:/Program Files/Epic Games"),
        Path("C:/Program Files (x86)/Epic Games"),
    ]:
        if epic_root.is_dir():
            search_roots.append((epic_root, None))

    best: tuple[int, Path, str | None] | None = None
    for root, steam_root in search_roots:
        if not root.is_dir():
            continue
        for game_dir in root.iterdir():
            if not game_dir.is_dir():
                continue
            dir_norm = re.sub(r"[^a-z0-9]", "", game_dir.name.lower())
            if q not in dir_norm and dir_norm not in q:
                continue
            appid = _steam_appid_for_dir(steam_root, game_dir.name) if steam_root else None
            for exe in sorted(game_dir.glob("*.exe")):
                n = exe.name.lower()
                if any(x in n for x in ("unins", "crash", "setup", "redist",
                                        "update", "helper", "launcher_helper")):
                    continue
                score = 100 if re.sub(r"[^a-z0-9]", "", n[:-4]) == dir_norm else 50
                if best is None or score > best[0]:
                    best = (score, exe, appid)
    return (best[1], best[2]) if best else None


def _search_registry(query: str) -> str | None:
    """Search HKLM App Paths registry for an installed exe."""
    if _SYSTEM != "Windows":
        return None
    q = re.sub(r"[^a-z0-9]", "", query.lower())
    try:
        import winreg
        for hive in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
            for subkey_path in [
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths",
                r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths",
            ]:
                try:
                    key = winreg.OpenKey(hive, subkey_path)
                except OSError:
                    continue
                i = 0
                while True:
                    try:
                        name = winreg.EnumKey(key, i); i += 1
                    except OSError:
                        break
                    name_norm = re.sub(r"[^a-z0-9]", "", name.lower().replace(".exe", ""))
                    if q not in name_norm and name_norm not in q:
                        continue
                    try:
                        subkey = winreg.OpenKey(key, name)
                        path = winreg.QueryValue(subkey, "")
                        path = path.strip('"').strip()
                        if path and Path(path).exists():
                            print(f"[open_app] Registry hit: {path}")
                            return path
                    except Exception:
                        pass
    except Exception:
        pass
    return None


def _resolve_lnk(lnk_path: Path) -> str | None:
    """Resolve a .lnk shortcut to its target exe path."""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"(New-Object -COM WScript.Shell).CreateShortcut('{lnk_path}').TargetPath"],
            capture_output=True, text=True, timeout=4,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        target = result.stdout.strip()
        if target and Path(target).exists():
            return target
    except Exception:
        pass
    return None


_SKIP_EXE = {"update.exe", "uninstall.exe", "unins000.exe", "setup.exe",
             "crashpad_handler.exe", "crashreporter.exe", "helper.exe"}

def _search_start_menu(query: str) -> str | None:
    """Search Start Menu .lnk shortcuts and resolve them to exe paths."""
    q = re.sub(r"[^a-z0-9]", "", query.lower())
    dirs = [
        Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
        Path("C:/ProgramData/Microsoft/Windows/Start Menu/Programs"),
    ]
    best: tuple[int, str] | None = None
    for d in dirs:
        if not d.is_dir():
            continue
        for lnk in d.rglob("*.lnk"):
            stem = re.sub(r"[^a-z0-9]", "", lnk.stem.lower())
            if q not in stem and stem not in q:
                continue
            target = _resolve_lnk(lnk)
            if not target:
                continue
            if Path(target).name.lower() in _SKIP_EXE:
                continue
            score = 100 if stem == q else (80 if q in stem else 60)
            if best is None or score > best[0]:
                best = (score, target)
                print(f"[open_app] Start Menu hit: {lnk.name} -> {target}")
    return best[1] if best else None


def _normalize(raw: str) -> str:
    key = raw.lower().strip()
    if key in _APP_ALIASES:
        return _APP_ALIASES[key].get(_SYSTEM, raw)
    for alias_key, os_map in _APP_ALIASES.items():
        if alias_key in key or key in alias_key:
            return os_map.get(_SYSTEM, raw)
    return raw


def _launch_exe(path: str, cwd: str | None = None) -> bool:
    try:
        subprocess.Popen(
            path, cwd=cwd or str(Path(path).parent),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        time.sleep(1.5)
        return True
    except Exception as e:
        print(f"[open_app] launch_exe failed: {e}")
        return False


def _launch_windows(app_name: str) -> bool:

    # 1. Direct PATH hit
    found = shutil.which(app_name) or shutil.which(app_name.split(".")[0])
    if found:
        if _launch_exe(found):
            return True

    # 2. Windows Registry — App Paths (most apps register here on install)
    reg_path = _search_registry(app_name)
    if reg_path and _launch_exe(reg_path):
        return True

    # 3. Start Menu .lnk shortcuts
    lnk_target = _search_start_menu(app_name)
    if lnk_target and _launch_exe(lnk_target):
        return True

    # 4. Steam / Epic library scan
    game_result = _find_game_exe(app_name)
    if game_result:
        game_exe, appid = game_result
        # Prefer Steam -applaunch (handles DRM, runs as if launched from Steam)
        if appid:
            steam_exe = _find_steam_exe()
            if steam_exe:
                print(f"[open_app] Steam launch: appid={appid}")
                try:
                    subprocess.Popen(
                        [str(steam_exe), "-applaunch", appid],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    )
                    time.sleep(2.0)
                    return True
                except Exception as e:
                    print(f"[open_app] steam -applaunch failed: {e}")
        # Fallback: direct exe
        if _launch_exe(str(game_exe), str(game_exe.parent)):
            return True

    # 5. ms-settings: and other URI schemes
    if ":" in app_name:
        try:
            subprocess.Popen(f'start "" "{app_name}"', shell=True,
                             creationflags=subprocess.CREATE_NO_WINDOW)
            time.sleep(1.0)
            return True
        except Exception:
            pass

    # 6. Last resort: Start Menu GUI search via pyautogui
    try:
        import pyautogui
        pyautogui.PAUSE = 0.05
        pyautogui.press("win")
        time.sleep(1.0)
        pyautogui.write(app_name, interval=0.04)
        time.sleep(1.5)
        pyautogui.press("enter")
        time.sleep(2.0)
        return True
    except Exception as e:
        print(f"[open_app] pyautogui fallback failed: {e}")

    return False


def _launch_macos(app_name: str) -> bool:

    try:
        result = subprocess.run(
            ["open", "-a", app_name],
            capture_output=True, timeout=8
        )
        if result.returncode == 0:
            time.sleep(1.0)
            return True
    except Exception:
        pass

    try:
        result = subprocess.run(
            ["open", "-a", f"{app_name}.app"],
            capture_output=True, timeout=8
        )
        if result.returncode == 0:
            time.sleep(1.0)
            return True
    except Exception:
        pass

    binary = shutil.which(app_name) or shutil.which(app_name.lower())
    if binary:
        try:
            subprocess.Popen(
                [binary],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            time.sleep(1.0)
            return True
        except Exception:
            pass

    try:
        import pyautogui
        pyautogui.hotkey("command", "space")
        time.sleep(0.6)
        pyautogui.write(app_name, interval=0.05)
        time.sleep(0.8)
        pyautogui.press("enter")
        time.sleep(1.5)
        return True
    except Exception as e:
        print(f"[open_app] Spotlight failed: {e}")

    return False


def _launch_linux(app_name: str) -> bool:

    # 1. Try PATH binary
    binary = (
        shutil.which(app_name) or
        shutil.which(app_name.lower()) or
        shutil.which(app_name.lower().replace(" ", "-")) or
        shutil.which(app_name.lower().replace(" ", "_"))
    )
    if binary:
        try:
            subprocess.Popen(
                [binary],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            time.sleep(1.0)
            return True
        except Exception:
            pass

    # 2. Search .desktop files (handles Telegram, Flatpak, custom installs)
    found = _find_desktop_file(app_name)
    if found:
        desktop_path, info = found
        # 2a. Prefer `gio launch` — respects DBusActivatable & desktop semantics
        if shutil.which("gio"):
            try:
                result = subprocess.run(
                    ["gio", "launch", str(desktop_path)],
                    capture_output=True, timeout=8
                )
                if result.returncode == 0:
                    time.sleep(0.8)
                    return True
            except Exception:
                pass

        # 2b. gtk-launch by basename
        if shutil.which("gtk-launch"):
            try:
                result = subprocess.run(
                    ["gtk-launch", desktop_path.stem],
                    capture_output=True, timeout=8
                )
                if result.returncode == 0:
                    time.sleep(0.8)
                    return True
            except Exception:
                pass

        # 2c. Direct Exec= line from the .desktop file
        exec_line = info.get("Exec", "")
        if exec_line:
            argv = _exec_from_desktop(exec_line)
            if argv:
                try:
                    subprocess.Popen(
                        argv,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True,
                        cwd=os.path.expanduser("~"),
                    )
                    time.sleep(1.0)
                    return True
                except Exception as e:
                    print(f"[open_app] desktop Exec failed: {e}")

    # 3. xdg-open fallback (URLs, mime types)
    try:
        result = subprocess.run(
            ["xdg-open", app_name],
            capture_output=True, timeout=5
        )
        if result.returncode == 0:
            return True
    except Exception:
        pass

    # 4. gtk-launch with common name variations
    if shutil.which("gtk-launch"):
        for desktop_name in [
            app_name.lower(),
            app_name.lower().replace(" ", "-"),
            app_name.lower().replace(" ", ""),
        ]:
            try:
                result = subprocess.run(
                    ["gtk-launch", desktop_name],
                    capture_output=True, timeout=5
                )
                if result.returncode == 0:
                    return True
            except Exception:
                pass

    return False


_OS_LAUNCHERS = {
    "Windows": _launch_windows,
    "Darwin":  _launch_macos,
    "Linux":   _launch_linux,
}

_MULTI_SEP_RE = re.compile(
    r"\s*(?:,|;|/|\bva\b|\bband\b|\band\b|\bи\b|&|\+)\s*",
    re.IGNORECASE,
)


def _split_app_names(raw: str) -> list[str]:
    """Split a string like 'Telegram va Chrome' or 'WhatsApp, Spotify' into parts.

    Returns a list of cleaned, non-empty app names in the original order.
    """
    parts = _MULTI_SEP_RE.split(raw)
    return [p.strip() for p in parts if p and p.strip()]


def _launch_one(app_name: str) -> str:
    launcher   = _OS_LAUNCHERS.get(_SYSTEM)
    normalized = _normalize(app_name)
    print(f"[open_app] Launching: '{app_name}' → '{normalized}' ({_SYSTEM})")
    try:
        if launcher(normalized):
            return f"Opened {app_name}."
        if normalized.lower() != app_name.lower() and launcher(app_name):
            return f"Opened {app_name}."
        return (
            f"Could not confirm that {app_name} launched. "
            f"It may still be loading, or it might not be installed."
        )
    except Exception as e:
        print(f"[open_app] Error: {e}")
        return f"Failed to open {app_name}: {e}"


def open_app(
    parameters=None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    app_name = (parameters or {}).get("app_name", "").strip()

    if not app_name:
        return "No application name provided."

    if _OS_LAUNCHERS.get(_SYSTEM) is None:
        return f"Unsupported operating system: {_SYSTEM}"

    apps = _split_app_names(app_name)
    if not apps:
        apps = [app_name]

    if player:
        if len(apps) == 1:
            player.write_log(f"[open_app] {apps[0]}")
        else:
            player.write_log(f"[open_app] {', '.join(apps)}")

    results = [_launch_one(a) for a in apps]
    return " ".join(results)