"""gaming_control — launch games, detect what's running, Steam integration."""
import subprocess
import os
import psutil
from pathlib import Path


_GAME_MAP = {
    # Common games → launch commands
    "minecraft":      ["minecraft-launcher", "minecraft"],
    "steam":          ["steam"],
    "cs2":            ["steam", "steam://rungameid/730"],
    "csgo":           ["steam", "steam://rungameid/730"],
    "dota":           ["steam", "steam://rungameid/570"],
    "valorant":       ["steam", "steam://rungameid/2694490"],
    "gta5":           ["steam", "steam://rungameid/271590"],
    "gta v":          ["steam", "steam://rungameid/271590"],
    "fortnite":       ["steam", "steam://rungameid/1172620"],
    "cyberpunk":      ["steam", "steam://rungameid/1091500"],
    "elden ring":     ["steam", "steam://rungameid/1245620"],
    "apex":           ["steam", "steam://rungameid/1172470"],
    "pubg":           ["steam", "steam://rungameid/578080"],
    "roblox":         ["roblox-player", "flatpak run org.roblox.RobloxPlayer"],
}

_GAME_PROCESSES = [
    "minecraft", "java", "steam", "csgo_linux64", "dota2", "cs2",
    "GTA5", "RocketLeague", "hl2", "chrome", "firefox",
]


def gaming_control(action: str, game: str = "", query: str = "") -> str:

    if action == "launch":
        if not game:
            return "Specify a game name."
        game_l = game.lower().strip()

        # Find in map
        cmd = None
        for key, launch_cmd in _GAME_MAP.items():
            if key in game_l or game_l in key:
                cmd = launch_cmd
                break

        if not cmd:
            # Try to find executable directly
            for candidate in [game_l, game_l.replace(" ", ""), game_l.replace(" ", "-")]:
                try:
                    result = subprocess.run(["which", candidate], capture_output=True, text=True)
                    if result.returncode == 0:
                        cmd = [candidate]
                        break
                except Exception:
                    pass

        if not cmd:
            # Try Steam search
            try:
                subprocess.Popen(["steam", f"steam://search/{game}"],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return f"Searching for {game} on Steam."
            except Exception:
                return f"Game '{game}' not found. Opening Steam."

        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return f"Launching {game}."
        except FileNotFoundError:
            return f"Could not launch {game}. Not installed?"
        except Exception as e:
            return f"Error launching {game}: {e}"

    elif action == "what_is_running":
        running_games = []
        for proc in psutil.process_iter(['name', 'pid', 'cpu_percent', 'memory_percent']):
            try:
                name = proc.info['name'].lower()
                for g in _GAME_PROCESSES:
                    if g.lower() in name:
                        running_games.append(
                            f"{proc.info['name']} (CPU: {proc.info['cpu_percent']:.0f}%)"
                        )
                        break
            except Exception:
                pass
        if not running_games:
            return "No games currently running."
        return "Running: " + ", ".join(running_games[:5])

    elif action == "kill_game":
        if not game:
            return "Specify a game to close."
        killed = []
        game_l = game.lower()
        for proc in psutil.process_iter(['name', 'pid']):
            try:
                if game_l in proc.info['name'].lower():
                    proc.kill()
                    killed.append(proc.info['name'])
            except Exception:
                pass
        if killed:
            return f"Closed: {', '.join(killed)}."
        return f"Game '{game}' not found running."

    elif action == "system_for_gaming":
        # Performance mode: disable notifications, set CPU performance governor
        results = []
        try:
            # Try to set CPU governor to performance
            r = subprocess.run(
                ["pkexec", "cpupower", "frequency-set", "-g", "performance"],
                capture_output=True, text=True, timeout=5
            )
            if r.returncode == 0:
                results.append("CPU set to performance mode")
        except Exception:
            pass

        try:
            # Kill unnecessary apps
            for app in ["discord", "slack", "telegram-desktop"]:
                subprocess.run(["pkill", "-f", app], capture_output=True)
            results.append("Background apps closed")
        except Exception:
            pass

        if not results:
            return "Gaming mode: could not change system settings. Try running as admin."
        return "Gaming mode activated: " + ", ".join(results) + "."

    elif action == "fps_info":
        try:
            cpu = psutil.cpu_percent(interval=0.5)
            mem = psutil.virtual_memory()
            freq = psutil.cpu_freq()
            result = f"CPU: {cpu:.0f}%, RAM: {mem.percent:.0f}% used"
            if freq:
                result += f", CPU freq: {freq.current:.0f} MHz"
            try:
                r = subprocess.run(
                    ["nvidia-smi", "--query-gpu=utilization.gpu,temperature.gpu",
                     "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, timeout=2
                )
                if r.returncode == 0:
                    parts = r.stdout.strip().split(",")
                    if len(parts) >= 2:
                        result += f", GPU: {parts[0].strip()}%, GPU temp: {parts[1].strip()}°C"
            except Exception:
                pass
            return result + "."
        except Exception as e:
            return f"Error getting system info: {e}"

    elif action == "open_steam":
        try:
            subprocess.Popen(["steam"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return "Opening Steam."
        except FileNotFoundError:
            return "Steam not installed."

    else:
        return (f"Unknown action '{action}'. "
                "Use: launch/what_is_running/kill_game/system_for_gaming/fps_info/open_steam")
