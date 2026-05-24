"""music_control — control any media player via playerctl (Spotify, VLC, Chrome, etc.)"""
import subprocess


def _playerctl(*args, player: str = "") -> tuple[bool, str]:
    cmd = ["playerctl"]
    if player:
        cmd += ["-p", player]
    cmd += list(args)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    except FileNotFoundError:
        return False, "playerctl not installed"
    except Exception as e:
        return False, str(e)


def music_control(action: str, query: str = "", volume: int = -1, player: str = "") -> str:

    if action == "play":
        ok, out = _playerctl("play", player=player)
        return "Playing." if ok else f"Nothing to play. {out}"

    elif action == "pause":
        ok, out = _playerctl("pause", player=player)
        return "Paused." if ok else f"Could not pause. {out}"

    elif action == "play_pause":
        ok, out = _playerctl("play-pause", player=player)
        return "Toggled play/pause." if ok else out

    elif action == "next":
        ok, out = _playerctl("next", player=player)
        return "Next track." if ok else out

    elif action == "previous":
        ok, out = _playerctl("previous", player=player)
        return "Previous track." if ok else out

    elif action == "stop":
        ok, out = _playerctl("stop", player=player)
        return "Stopped." if ok else out

    elif action == "volume":
        if volume < 0:
            ok, out = _playerctl("volume", player=player)
            if ok:
                try:
                    pct = int(float(out) * 100)
                    return f"Volume: {pct}%."
                except Exception:
                    return out
            return out
        else:
            v = max(0, min(100, volume))
            ok, out = _playerctl("volume", f"{v/100:.2f}", player=player)
            return f"Volume set to {v}%." if ok else out

    elif action == "status":
        ok, out = _playerctl("status", player=player)
        if not ok:
            return "No media player running."
        status = out.strip()
        ok2, title = _playerctl("metadata", "title", player=player)
        ok3, artist = _playerctl("metadata", "artist", player=player)
        parts = [f"Status: {status}"]
        if ok2 and title:
            parts.append(f"Track: {title.strip()}")
        if ok3 and artist:
            parts.append(f"Artist: {artist.strip()}")
        return ". ".join(parts) + "."

    elif action == "current_track":
        ok, title = _playerctl("metadata", "title", player=player)
        ok2, artist = _playerctl("metadata", "artist", player=player)
        if not ok:
            return "Nothing is playing."
        parts = []
        if title:
            parts.append(title.strip())
        if ok2 and artist:
            parts.append(f"by {artist.strip()}")
        return " ".join(parts) if parts else "Unknown track."

    elif action == "list_players":
        try:
            r = subprocess.run(["playerctl", "-l"], capture_output=True, text=True, timeout=5)
            players = r.stdout.strip()
            if not players:
                return "No media players found."
            return f"Active players: {players.replace(chr(10), ', ')}."
        except Exception as e:
            return f"Error: {e}"

    elif action == "open_spotify":
        try:
            subprocess.Popen(["spotify"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return "Opening Spotify."
        except FileNotFoundError:
            try:
                subprocess.Popen(["flatpak", "run", "com.spotify.Client"],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return "Opening Spotify (flatpak)."
            except Exception:
                return "Spotify not found. Install it first."

    else:
        return (f"Unknown action '{action}'. "
                "Use: play/pause/play_pause/next/previous/stop/volume/status/current_track/"
                "list_players/open_spotify")
