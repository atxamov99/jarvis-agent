#computer_settings.py
import json
import os
import re
import shutil
import sys
import time
import subprocess
import platform
from pathlib import Path

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE    = 0.05
    _PYAUTOGUI = True
except Exception:
    _PYAUTOGUI = False

try:
    import pyperclip
    _PYPERCLIP = True
except ImportError:
    _PYPERCLIP = False

_OS      = platform.system()  # "Windows" | "Darwin" | "Linux"
_WAYLAND = bool(os.environ.get("WAYLAND_DISPLAY"))
_WTYPE   = bool(shutil.which("wtype"))
_XDOTOOL = bool(shutil.which("xdotool"))
_WPCTL   = bool(shutil.which("wpctl"))
_AMIXER  = bool(shutil.which("amixer"))

# Key name mapping for wtype (X11 keysym names)
_KEYSYM = {
    "enter": "Return", "return": "Return", "esc": "Escape", "escape": "Escape",
    "space": "space", "tab": "Tab", "delete": "Delete", "del": "Delete",
    "backspace": "BackSpace", "up": "Up", "down": "Down", "left": "Left", "right": "Right",
    "home": "Home", "end": "End", "pageup": "Prior", "pagedown": "Next",
    "f1":"F1","f2":"F2","f3":"F3","f4":"F4","f5":"F5","f6":"F6",
    "f7":"F7","f8":"F8","f9":"F9","f10":"F10","f11":"F11","f12":"F12",
    "volumeup":"XF86AudioRaiseVolume","volumedown":"XF86AudioLowerVolume",
    "volumemute":"XF86AudioMute",
}
_MOD_KEYS = {"ctrl","alt","shift","super","meta","command"}


def _hotkey(*keys):
    """Keyboard shortcut — works on Wayland (wtype) X11 (xdotool) or pyautogui."""
    if _OS == "Darwin":
        if _PYAUTOGUI:
            pyautogui.hotkey(*[k.lower() for k in keys])
        return
    if _WAYLAND and _WTYPE:
        mods = [k for k in keys if k.lower() in _MOD_KEYS]
        regulars = [k for k in keys if k.lower() not in _MOD_KEYS]
        cmd = ["wtype"]
        for m in mods:
            cmd += ["-M", m.lower()]
        for k in regulars:
            cmd += ["-k", _KEYSYM.get(k.lower(), k.lower())]
        for m in reversed(mods):
            cmd += ["-m", m.lower()]
        try:
            subprocess.run(cmd, capture_output=True, timeout=3)
            return
        except Exception:
            pass
    if _XDOTOOL:
        try:
            combo = "+".join(_KEYSYM.get(k.lower(), k.lower()) for k in keys)
            subprocess.run(["xdotool", "key", combo], capture_output=True, timeout=3)
            return
        except Exception:
            pass
    if _PYAUTOGUI:
        pyautogui.hotkey(*[k.lower() for k in keys])


def _focus_window_wayland(title: str) -> bool:
    """Focus a window by title/class on GNOME Wayland via Shell.Eval D-Bus."""
    if not _WAYLAND:
        return False
    t = title.lower().replace("'", "")
    script = (
        "let actors = global.get_window_actors();"
        f"let w = actors.find(a => {{"
        f"  let t = (a.get_meta_window().get_title() || '').toLowerCase();"
        f"  let c = (a.get_meta_window().get_wm_class() || '').toLowerCase();"
        f"  return t.includes('{t}') || c.includes('{t}');"
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


def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

def _get_api_key() -> str:
    path = _get_base_dir() / "config" / "api_keys.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)["openai_api_key"]

def _get_macos_wifi_interface() -> str:
    try:
        result = subprocess.run(
            ["networksetup", "-listallhardwareports"],
            capture_output=True, text=True, timeout=5
        )
        lines = result.stdout.splitlines()
        for i, line in enumerate(lines):
            if "Wi-Fi" in line or "AirPort" in line:
                for j in range(i, min(i + 4, len(lines))):
                    if lines[j].startswith("Device:"):
                        return lines[j].split(":", 1)[1].strip()
    except Exception:
        pass
    return "en0" 

def volume_up():
    if _OS == "Windows":
        for _ in range(5): _hotkey("volumeup")
    elif _OS == "Darwin":
        subprocess.run(["osascript", "-e",
            "set volume output volume (output volume of (get volume settings) + 10)"],
            capture_output=True)
    else:
        if _WPCTL:
            subprocess.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "10%+"], capture_output=True)
        elif _AMIXER:
            subprocess.run(["amixer", "set", "Master", "10%+"], capture_output=True)
        else:
            subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", "+10%"], capture_output=True)

def volume_down():
    if _OS == "Windows":
        for _ in range(5): _hotkey("volumedown")
    elif _OS == "Darwin":
        subprocess.run(["osascript", "-e",
            "set volume output volume (output volume of (get volume settings) - 10)"],
            capture_output=True)
    else:
        if _WPCTL:
            subprocess.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "10%-"], capture_output=True)
        elif _AMIXER:
            subprocess.run(["amixer", "set", "Master", "10%-"], capture_output=True)
        else:
            subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", "-10%"], capture_output=True)

def volume_mute():
    if _OS == "Windows":
        _hotkey("volumemute")
    elif _OS == "Darwin":
        subprocess.run(["osascript", "-e", "set volume with output muted"], capture_output=True)
    else:
        if _WPCTL:
            subprocess.run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "toggle"], capture_output=True)
        elif _AMIXER:
            subprocess.run(["amixer", "set", "Master", "toggle"], capture_output=True)
        else:
            subprocess.run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"], capture_output=True)

def volume_set(value: int):
    value = max(0, min(100, int(value)))
    if _OS == "Windows":
        try:
            import math
            from ctypes import cast, POINTER
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            devices   = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            vol       = cast(interface, POINTER(IAudioEndpointVolume))
            vol_db    = -65.25 if value == 0 else max(-65.25, 20 * math.log10(value / 100))
            vol.SetMasterVolumeLevel(vol_db, None)
            return
        except Exception as e:
            print(f"[Settings] pycaw failed, using keypress fallback: {e}")
            pyautogui.press("volumemute")
            pyautogui.press("volumemute")
    elif _OS == "Darwin":
        subprocess.run(["osascript", "-e", f"set volume output volume {value}"],
            capture_output=True)
        return
    else:
        if _WPCTL:
            subprocess.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{value}%"], capture_output=True)
        elif _AMIXER:
            subprocess.run(["amixer", "set", "Master", f"{value}%"], capture_output=True)
        else:
            subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{value}%"], capture_output=True)
        return

def brightness_up():
    if _OS == "Darwin":
        subprocess.run(["osascript", "-e",
            'tell application "System Events" to key code 144'],
            capture_output=True)
    elif _OS == "Linux":
        if subprocess.run(["which", "brightnessctl"],
                capture_output=True).returncode == 0:
            subprocess.run(["brightnessctl", "set", "+10%"], capture_output=True)
        else:
            subprocess.run(
                'xrandr --output $(xrandr | grep " connected" | head -1 | cut -d " " -f1)'
                ' --brightness $(python3 -c "import subprocess; '
                'b=float(subprocess.check_output([\"xrandr\",\"--verbose\"]).decode()'
                '.split(\"Brightness:\")[1].split()[0]); print(min(1.0,b+0.1))")',
                shell=True, capture_output=True
            )
    else:
        try:
            subprocess.run(
                ["powershell", "-Command",
                 "(Get-WmiObject -Namespace root/wmi -Class WmiMonitorBrightnessMethods)"
                 ".WmiSetBrightness(1, [math]::Min(100, "
                 "(Get-WmiObject -Namespace root/wmi -Class WmiMonitorBrightness).CurrentBrightness + 10))"],
                capture_output=True, timeout=5
            )
        except Exception as e:
            print(f"[Settings] Brightness up failed on Windows: {e}")

def brightness_down():
    if _OS == "Darwin":
        subprocess.run(["osascript", "-e",
            'tell application "System Events" to key code 145'],
            capture_output=True)
    elif _OS == "Linux":
        if subprocess.run(["which", "brightnessctl"],
                capture_output=True).returncode == 0:
            subprocess.run(["brightnessctl", "set", "10%-"], capture_output=True)
        else:
            subprocess.run(
                'xrandr --output $(xrandr | grep " connected" | head -1 | cut -d " " -f1)'
                ' --brightness $(python3 -c "import subprocess; '
                'b=float(subprocess.check_output([\"xrandr\",\"--verbose\"]).decode()'
                '.split(\"Brightness:\")[1].split()[0]); print(max(0.1,b-0.1))")',
                shell=True, capture_output=True
            )
    else:
        try:
            subprocess.run(
                ["powershell", "-Command",
                 "(Get-WmiObject -Namespace root/wmi -Class WmiMonitorBrightnessMethods)"
                 ".WmiSetBrightness(1, [math]::Max(0, "
                 "(Get-WmiObject -Namespace root/wmi -Class WmiMonitorBrightness).CurrentBrightness - 10))"],
                capture_output=True, timeout=5
            )
        except Exception as e:
            print(f"[Settings] Brightness down failed on Windows: {e}")

def close_app():
    if _OS == "Darwin": _hotkey("command", "q")
    else:               _hotkey("alt", "f4")

def close_window():
    if _OS == "Darwin": _hotkey("command", "w")
    else:               _hotkey("ctrl", "w")

def full_screen():
    if _OS == "Darwin": _hotkey("ctrl", "command", "f")
    else:               _hotkey("f11")

def minimize_window():
    if _OS == "Darwin": _hotkey("command", "m")
    else:               _hotkey("super", "down")

def maximize_window():
    if _OS == "Darwin":
        subprocess.run(["osascript", "-e",
            'tell application "System Events" to keystroke "f" '
            'using {control down, command down}'],
            capture_output=True)
    elif _OS == "Windows":
        pyautogui.hotkey("win", "up")
    else:
        try:
            subprocess.run(["wmctrl", "-r", ":ACTIVE:", "-b", "add,maximized_vert,maximized_horz"],
                capture_output=True)
        except Exception:
            pyautogui.hotkey("super", "up")

def snap_left():
    if _OS == "Windows":
        pyautogui.hotkey("win", "left")
    elif _OS == "Linux":
        try:
            subprocess.run(["wmctrl", "-r", ":ACTIVE:", "-e", "0,0,0,960,1080"],
                capture_output=True)
        except Exception:
            pass

def snap_right():
    if _OS == "Windows":
        pyautogui.hotkey("win", "right")
    elif _OS == "Linux":
        try:
            subprocess.run(["wmctrl", "-r", ":ACTIVE:", "-e", "0,960,0,960,1080"],
                capture_output=True)
        except Exception:
            pass

def switch_window():
    if _OS == "Darwin": _hotkey("command", "tab")
    else:               _hotkey("alt", "tab")

def show_desktop():
    if _OS == "Darwin":   _hotkey("fn", "f11")
    elif _OS == "Windows": _hotkey("super", "d")
    else:                  _hotkey("super", "d")

def open_task_manager():
    if _OS == "Windows":
        _hotkey("ctrl", "shift", "esc")
    elif _OS == "Darwin":
        subprocess.Popen(["open", "-a", "Activity Monitor"])
    else:
        for cmd in [["gnome-system-monitor"], ["xfce4-taskmanager"], ["htop"]]:
            if subprocess.run(["which", cmd[0]], capture_output=True).returncode == 0:
                subprocess.Popen(cmd)
                break


def focus_search():
    if _OS == "Darwin": _hotkey("command", "l")
    else:               _hotkey("ctrl", "l")

def pause_video():
    # Focus media window first (Chrome/browser), then send Space
    if _WAYLAND:
        for title in ("chrome", "firefox", "chromium", "vlc", "mpv"):
            if _focus_window_wayland(title):
                import time as _t; _t.sleep(0.12)
                break
    _hotkey("space")

def refresh_page():
    if _OS == "Darwin": _hotkey("command", "r")
    else:               _hotkey("f5")

def close_tab():
    if _OS == "Darwin": _hotkey("command", "w")
    else:               _hotkey("ctrl", "w")

def new_tab():
    if _OS == "Darwin": _hotkey("command", "t")
    else:               _hotkey("ctrl", "t")

def next_tab():
    if _OS == "Darwin": _hotkey("command", "shift", "bracketright")
    else:               _hotkey("ctrl", "tab")

def prev_tab():
    if _OS == "Darwin": _hotkey("command", "shift", "bracketleft")
    else:               _hotkey("ctrl", "shift", "tab")

def go_back():
    if _OS == "Darwin": _hotkey("command", "left")
    else:               _hotkey("alt", "left")

def go_forward():
    if _OS == "Darwin": _hotkey("command", "right")
    else:               _hotkey("alt", "right")

def zoom_in():
    if _OS == "Darwin": _hotkey("command", "equal")
    else:               _hotkey("ctrl", "equal")

def zoom_out():
    if _OS == "Darwin": _hotkey("command", "minus")
    else:               _hotkey("ctrl", "minus")

def zoom_reset():
    if _OS == "Darwin": _hotkey("command", "0")
    else:               _hotkey("ctrl", "0")

def find_on_page():
    if _OS == "Darwin": _hotkey("command", "f")
    else:               _hotkey("ctrl", "f")

def reload_page_n(n: int):
    for _ in range(max(1, n)):
        refresh_page()
        time.sleep(0.8)


def scroll_up(amount: int = 500):
    if _PYAUTOGUI:
        pyautogui.scroll(amount)
    elif _XDOTOOL:
        subprocess.run(["xdotool", "click", "--repeat", str(max(1, amount // 100)), "4"], capture_output=True)

def scroll_down(amount: int = 500):
    if _PYAUTOGUI:
        pyautogui.scroll(-amount)
    elif _XDOTOOL:
        subprocess.run(["xdotool", "click", "--repeat", str(max(1, amount // 100)), "5"], capture_output=True)

def scroll_top():
    if _OS == "Darwin": _hotkey("command", "up")
    else:               _hotkey("ctrl", "home")

def scroll_bottom():
    if _OS == "Darwin": _hotkey("command", "down")
    else:               _hotkey("ctrl", "end")

def page_up():   _hotkey("pageup")
def page_down(): _hotkey("pagedown")


def copy():
    if _OS == "Darwin": _hotkey("command", "c")
    else:               _hotkey("ctrl", "c")

def paste():
    if _OS == "Darwin": _hotkey("command", "v")
    else:               _hotkey("ctrl", "v")

def cut():
    if _OS == "Darwin": _hotkey("command", "x")
    else:               _hotkey("ctrl", "x")

def undo():
    if _OS == "Darwin": _hotkey("command", "z")
    else:               _hotkey("ctrl", "z")

def redo():
    if _OS == "Darwin": _hotkey("command", "shift", "z")
    else:               _hotkey("ctrl", "y")

def select_all():
    if _OS == "Darwin": _hotkey("command", "a")
    else:               _hotkey("ctrl", "a")

def save_file():
    if _OS == "Darwin": _hotkey("command", "s")
    else:               _hotkey("ctrl", "s")

def press_enter():   _hotkey("enter")
def press_escape():  _hotkey("escape")
def press_key(key: str): _hotkey(key)

def type_text(text: str, press_enter_after: bool = False):
    if not text:
        return
    text = str(text)
    time.sleep(0.3)  # let target window receive focus

    # Wayland-native typing (works inside Telegram, etc.)
    import os as _os, shutil as _shutil, subprocess as _sp
    is_wayland = bool(_os.environ.get("WAYLAND_DISPLAY")) and _os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"
    typed = False
    try:
        if is_wayland and _shutil.which("wtype"):
            _sp.run(["wtype", "-d", "30", text], check=True, timeout=30)
            typed = True
        elif _shutil.which("xdotool"):
            _sp.run(["xdotool", "type", "--delay", "30", "--", text], check=True, timeout=30)
            typed = True
    except Exception as e:
        print(f"[ComputerSettings] native type failed: {e}")

    if not typed:
        # Fallback: clipboard + paste, or raw pyautogui
        if _PYPERCLIP:
            pyperclip.copy(text)
            time.sleep(0.15)
            paste()
        else:
            pyautogui.write(text, interval=0.03)

    if press_enter_after:
        time.sleep(0.1)
        pyautogui.press("enter")

def take_screenshot():
    if _OS == "Windows":
        _hotkey("super", "shift", "s")
    elif _OS == "Darwin":
        _hotkey("command", "shift", "3")
    else:
        for cmd in [["scrot"], ["gnome-screenshot"], ["import", "-window", "root", "screenshot.png"]]:
            if subprocess.run(["which", cmd[0]], capture_output=True).returncode == 0:
                subprocess.Popen(cmd)
                return
        pyautogui.hotkey("ctrl", "print_screen")

def lock_screen():
    if _OS == "Windows":
        _hotkey("super", "l")
    elif _OS == "Darwin":
        subprocess.run(["pmset", "displaysleepnow"], capture_output=True)
    else:
        for cmd in [
            ["gnome-screensaver-command", "-l"],
            ["xdg-screensaver", "lock"],
            ["loginctl", "lock-session"],
        ]:
            if subprocess.run(["which", cmd[0]], capture_output=True).returncode == 0:
                subprocess.run(cmd, capture_output=True)
                return

def open_system_settings():
    if _OS == "Windows":
        _hotkey("super", "i")
    elif _OS == "Darwin":
        subprocess.Popen(["open", "-a", "System Preferences"])
    else:
        for cmd in [["gnome-control-center"], ["xfce4-settings-manager"], ["kcmshell5"]]:
            if subprocess.run(["which", cmd[0]], capture_output=True).returncode == 0:
                subprocess.Popen(cmd)
                return

def open_file_explorer():
    if _OS == "Windows":
        _hotkey("super", "e")
    elif _OS == "Darwin":
        subprocess.Popen(["open", str(Path.home())])
    else:
        for cmd in [["nautilus"], ["thunar"], ["dolphin"], ["nemo"]]:
            if subprocess.run(["which", cmd[0]], capture_output=True).returncode == 0:
                subprocess.Popen(cmd)
                return
        subprocess.Popen(["xdg-open", str(Path.home())])

def sleep_display():
    if _OS == "Windows":
        try:
            import ctypes
            ctypes.windll.user32.SendMessageW(0xFFFF, 0x0112, 0xF170, 2)
        except Exception as e:
            print(f"[Settings] sleep_display failed: {e}")
    elif _OS == "Darwin":
        subprocess.run(["pmset", "displaysleepnow"], capture_output=True)
    else:
        subprocess.run(["xset", "dpms", "force", "off"], capture_output=True)

def open_run():
    if _OS == "Windows":
        _hotkey("super", "r")

def dark_mode():
    if _OS == "Darwin":
        subprocess.run(["osascript", "-e",
            'tell app "System Events" to tell appearance preferences '
            'to set dark mode to not dark mode'],
            capture_output=True)
    elif _OS == "Windows":
        try:
            import winreg
            key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Themes\Personalize"
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS)
            current, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            winreg.SetValueEx(key, "AppsUseLightTheme", 0, winreg.REG_DWORD, 1 - current)
            winreg.SetValueEx(key, "SystemUsesLightTheme", 0, winreg.REG_DWORD, 1 - current)
            winreg.CloseKey(key)
        except Exception as e:
            print(f"[Settings] dark_mode registry failed: {e}")
    else:
        try:
            result = subprocess.run(
                ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
                capture_output=True, text=True
            )
            current = result.stdout.strip()
            new_scheme = "'default'" if "dark" in current else "'prefer-dark'"
            subprocess.run(
                ["gsettings", "set", "org.gnome.desktop.interface", "color-scheme", new_scheme],
                capture_output=True
            )
        except Exception as e:
            print(f"[Settings] dark_mode Linux failed: {e}")

def toggle_wifi():
    if _OS == "Darwin":
        iface = _get_macos_wifi_interface()
        result = subprocess.run(
            ["networksetup", "-getairportpower", iface],
            capture_output=True, text=True
        )
        state = "off" if "On" in result.stdout else "on"
        subprocess.run(["networksetup", "-setairportpower", iface, state],
            capture_output=True)
    elif _OS == "Windows":
        try:
            subprocess.run(
                ["powershell", "-Command",
                 "$adapter = Get-NetAdapter | Where-Object {$_.PhysicalMediaType -eq 'Native 802.11'};"
                 "if ($adapter.Status -eq 'Up') { Disable-NetAdapter -Name $adapter.Name -Confirm:$false }"
                 "else { Enable-NetAdapter -Name $adapter.Name -Confirm:$false }"],
                capture_output=True, timeout=10
            )
        except Exception as e:
            print(f"[Settings] toggle_wifi Windows failed: {e}")
    else:
        try:
            result = subprocess.run(["nmcli", "radio", "wifi"], capture_output=True, text=True)
            state  = "off" if "enabled" in result.stdout else "on"
            subprocess.run(["nmcli", "radio", "wifi", state], capture_output=True)
        except Exception as e:
            print(f"[Settings] toggle_wifi Linux failed: {e}")

def restart_computer():
    if _OS == "Windows":
        subprocess.run(["shutdown", "/r", "/t", "10"], capture_output=True)
    elif _OS == "Darwin":
        subprocess.run(["osascript", "-e",
            'tell application "System Events" to restart'],
            capture_output=True)
    else:
        subprocess.run(["systemctl", "reboot"], capture_output=True)

def shutdown_computer():
    if _OS == "Windows":
        subprocess.run(["shutdown", "/s", "/t", "10"], capture_output=True)
    elif _OS == "Darwin":
        subprocess.run(["osascript", "-e",
            'tell application "System Events" to shut down'],
            capture_output=True)
    else:
        subprocess.run(["systemctl", "poweroff"], capture_output=True)


def focus_window(title: str = ""):
    """Focus a window whose title contains `title`."""
    if not title:
        return
    if _OS == "Linux":
        # Wayland: GNOME Shell D-Bus
        if _focus_window_wayland(title):
            return
        # X11 fallback
        if _XDOTOOL:
            r = subprocess.run(
                ["xdotool", "search", "--name", title],
                capture_output=True, text=True, timeout=5,
            )
            wids = [w.strip() for w in r.stdout.splitlines() if w.strip()]
            if wids:
                subprocess.run(["xdotool", "windowfocus", "--sync", wids[0]], timeout=3)
                subprocess.run(["xdotool", "windowraise", wids[0]], timeout=3)
                return
        _hotkey("alt", "tab")
    elif _OS == "Darwin":
        subprocess.run(
            ["osascript", "-e", f'tell application "{title}" to activate'],
            capture_output=True,
        )
    else:
        _hotkey("alt", "tab")


def window_move(x: int = 0, y: int = 0):
    """Move the active window to (x, y) on screen using xdotool."""
    if _OS == "Linux" and shutil.which("xdotool"):
        wid_r = subprocess.run(
            ["xdotool", "getactivewindow"],
            capture_output=True, text=True, timeout=3,
        )
        wid = wid_r.stdout.strip()
        if wid:
            subprocess.run(["xdotool", "windowmove", wid, str(x), str(y)], timeout=3)


def window_resize(width: int = 800, height: int = 600):
    """Resize the active window to width×height using xdotool."""
    if _OS == "Linux" and shutil.which("xdotool"):
        wid_r = subprocess.run(
            ["xdotool", "getactivewindow"],
            capture_output=True, text=True, timeout=3,
        )
        wid = wid_r.stdout.strip()
        if wid:
            subprocess.run(
                ["xdotool", "windowsize", wid, str(width), str(height)],
                timeout=3,
            )


def dismiss_notifications():
    """Dismiss system notification popups (Escape key, then Super+V to clear all on GNOME)."""
    _hotkey("escape")
    if _OS == "Linux":
        # GNOME notification center toggle — clears pending
        try:
            subprocess.run(
                ["gdbus", "call", "--session",
                 "--dest", "org.gnome.Shell",
                 "--object-path", "/org/gnome/Shell",
                 "--method", "org.gnome.Shell.Eval",
                 "Main.panel.statusArea.dateMenu.menu.toggle();"],
                capture_output=True, timeout=3,
            )
        except Exception:
            pass


def alt_tab():
    """Switch to the previous window (Alt+Tab)."""
    _hotkey("alt", "tab")


def force_kill_process(name: str):
    """Immediately SIGKILL a process by name without grace period."""
    try:
        import psutil
        for proc in psutil.process_iter(["pid", "name", "exe", "cmdline"]):
            try:
                n = (proc.info.get("name") or "").lower()
                e = (proc.info.get("exe") or "").lower()
                if name.lower() in n or name.lower() in e:
                    proc.kill()
            except Exception:
                continue
    except ImportError:
        if shutil.which("pkill"):
            subprocess.run(["pkill", "-9", "-f", name], timeout=5)


ACTION_MAP: dict[str, callable] = {
    "volume_up":           volume_up,
    "volume_down":         volume_down,
    "mute":                volume_mute,
    "unmute":              volume_mute,
    "toggle_mute":         volume_mute,
    "brightness_up":       brightness_up,
    "brightness_down":     brightness_down,
    "sleep_display":       sleep_display,
    "screen_off":          sleep_display,
    "pause_video":         pause_video,
    "play_pause":          pause_video,
    "close_app":           close_app,
    "close_window":        close_window,
    "full_screen":         full_screen,
    "fullscreen":          full_screen,
    "minimize":            minimize_window,
    "maximize":            maximize_window,
    "snap_left":           snap_left,
    "snap_right":          snap_right,
    "switch_window":       switch_window,
    "show_desktop":        show_desktop,
    "task_manager":        open_task_manager,
    "focus_search":        focus_search,
    "refresh_page":        refresh_page,
    "reload":              refresh_page,
    "close_tab":           close_tab,
    "new_tab":             new_tab,
    "next_tab":            next_tab,
    "prev_tab":            prev_tab,
    "go_back":             go_back,
    "go_forward":          go_forward,
    "zoom_in":             zoom_in,
    "zoom_out":            zoom_out,
    "zoom_reset":          zoom_reset,
    "find_on_page":        find_on_page,
    "scroll_up":           scroll_up,
    "scroll_down":         scroll_down,
    "scroll_top":          scroll_top,
    "scroll_bottom":       scroll_bottom,
    "page_up":             page_up,
    "page_down":           page_down,
    "copy":                copy,
    "paste":               paste,
    "cut":                 cut,
    "undo":                undo,
    "redo":                redo,
    "select_all":          select_all,
    "save":                save_file,
    "enter":               press_enter,
    "escape":              press_escape,
    "screenshot":          take_screenshot,
    "lock_screen":         lock_screen,
    "open_settings":       open_system_settings,
    "file_explorer":       open_file_explorer,
    "open_run":            open_run,
    "dark_mode":           dark_mode,
    "toggle_wifi":              toggle_wifi,
    "restart":                  restart_computer,
    "shutdown":                 shutdown_computer,
    "focus_window":             focus_window,
    "window_move":              window_move,
    "window_resize":            window_resize,
    "dismiss_notifications":    dismiss_notifications,
    "alt_tab":                  alt_tab,
    "app_switcher":             alt_tab,
    "force_kill":               force_kill_process,
}

_DANGEROUS_ACTIONS = {"restart", "shutdown"}



def _detect_action(description: str) -> dict:
    from actions.openai_client import get_client
    client = get_client()

    available = ", ".join(sorted(ACTION_MAP.keys())) + \
                ", volume_set, type_text, press_key, reload_n"

    prompt = f"""You are an intent detector for a computer control assistant.

The user issued a command (possibly in any language): "{description}"

Available actions: {available}

Return ONLY a valid JSON object:
{{"action": "action_name", "value": null_or_value}}

Rules:
- Pick the single best matching action from the available list.
- For volume_set: value is an integer 0-100.
- For type_text: value is the exact text to type.
- For press_key: value is the key name (e.g. "f5", "tab", "enter").
- For reload_n: value is an integer (number of times to reload).
- If no clear match, pick the closest action.
- Return ONLY the JSON, no explanation, no markdown."""

    try:
        resp = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
        )
        text = re.sub(r"```(?:json)?", "", resp.choices[0].message.content).strip().rstrip("`").strip()
        return json.loads(text)
    except Exception as e:
        print(f"[Settings] Intent detection failed: {e}")
        return {"action": description.lower().replace(" ", "_"), "value": None}

def computer_settings(
    parameters: dict = None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params      = parameters or {}
    raw_action  = params.get("action", "").strip()
    description = params.get("description", "").strip()
    value       = params.get("value", None)

    if not raw_action and description:
        detected   = _detect_action(description)
        raw_action = detected.get("action", "")
        if value is None:
            value = detected.get("value")

    action = raw_action.lower().strip().replace(" ", "_").replace("-", "_")

    if not action:
        return "No action could be determined."

    print(f"[Settings] Action: {action}  Value: {value}  OS: {_OS}")
    if player:
        player.write_log(f"[Settings] {action}")

    if action in _DANGEROUS_ACTIONS:
        confirmed = str(params.get("confirmed", "")).lower()
        if confirmed not in ("yes", "true", "1", "confirm"):
            return (
                f"This will {action} the computer. "
                f"Please confirm by calling again with confirmed=yes."
            )

    if action == "volume_set":
        try:
            volume_set(int(value or 50))
            return f"Volume set to {value}%."
        except Exception as e:
            return f"Could not set volume: {e}"

    if action in ("type_text", "write_on_screen", "type", "write"):
        text = str(value or params.get("text", "")).strip()
        if not text:
            return "No text provided to type."
        enter_after = str(params.get("press_enter", "false")).lower() in ("true", "1", "yes")
        type_text(text, press_enter_after=enter_after)
        return f"Typed: {text[:80]}"

    if action == "press_key":
        key = str(value or params.get("key", "")).strip()
        if not key:
            return "No key specified."
        press_key(key)
        return f"Pressed: {key}"

    if action in ("reload_n", "refresh_n", "reload_page_n"):
        try:
            reload_page_n(int(value or 1))
            return f"Reloaded {value or 1} time(s)."
        except Exception as e:
            return f"Reload failed: {e}"

    if action == "scroll_up":
        scroll_up(int(value or 500))
        return "Scrolled up."

    if action == "scroll_down":
        scroll_down(int(value or 500))
        return "Scrolled down."

    if action == "focus_window":
        title = str(value or params.get("title", "")).strip()
        if not title:
            return "No window title provided."
        focus_window(title)
        return f"Focused window: '{title}'."

    if action == "window_move":
        x = int(params.get("x", value or 0))
        y = int(params.get("y", 0))
        window_move(x, y)
        return f"Window moved to ({x}, {y})."

    if action == "window_resize":
        w = int(params.get("width", value or 800))
        h = int(params.get("height", 600))
        window_resize(w, h)
        return f"Window resized to {w}×{h}."

    if action in ("force_kill", "kill"):
        name = str(value or params.get("name", params.get("app_name", ""))).strip()
        if not name:
            return "No process name provided."
        force_kill_process(name)
        return f"Force-killed '{name}'."

    func = ACTION_MAP.get(action)
    if not func:
        return f"Unknown action: '{raw_action}'."

    try:
        func()
        return f"Done: {action}."
    except Exception as e:
        print(f"[Settings] Action failed ({action}): {e}")
        return f"Action failed ({action}): {e}"