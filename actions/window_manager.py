"""window_manager.py — Control desktop windows via xdotool (no wmctrl needed).

List open windows, focus an app by name, minimize/maximize, tile left/right,
move between halves, close. "Chrome'ni oldinga chiqar", "oynani chap yarmiga qo'y".
"""
import subprocess


def _run(args, timeout=5):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except Exception as e:
        return 1, "", str(e)


def _display_geom():
    code, out, _ = _run(["xdotool", "getdisplaygeometry"])
    if code == 0 and out:
        try:
            w, h = out.split()
            return int(w), int(h)
        except Exception:
            pass
    return 1920, 1080


def _list_windows():
    code, out, _ = _run(["xdotool", "search", "--onlyvisible", "--name", "."])
    wins = []
    for wid in (out.split() if out else []):
        c2, name, _ = _run(["xdotool", "getwindowname", wid])
        if c2 == 0 and name and name not in ("Desktop", ""):
            wins.append((wid, name))
    return wins


def _find_window(query: str):
    q = query.lower().strip()
    for wid, name in _list_windows():
        if q in name.lower():
            return wid, name
    return None, None


def _active_window():
    code, out, _ = _run(["xdotool", "getactivewindow"])
    return out if code == 0 else None


def window_manager(parameters=None, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    action = (params.get("action") or "list").lower().strip()
    target = (params.get("target") or params.get("name") or params.get("window") or "").strip()

    if action in ("list", "windows", "royxat"):
        wins = _list_windows()
        if not wins:
            return "Ochiq oyna topilmadi."
        return "Ochiq oynalar:\n" + "\n".join(f"  • {name}" for _, name in wins)

    # Resolve the target window: by name, else the active window
    if target:
        wid, name = _find_window(target)
        if not wid:
            return f"'{target}' nomli oyna topilmadi."
    else:
        wid = _active_window()
        name = "faol oyna"
        if not wid:
            return "Faol oyna aniqlanmadi."

    W, H = _display_geom()

    if action in ("focus", "activate", "show", "ochib_ber", "oldinga"):
        _run(["xdotool", "windowactivate", "--sync", wid])
        return f"✅ '{name}' oldinga chiqarildi."

    if action in ("close", "yop"):
        _run(["xdotool", "windowclose", wid])
        return f"✅ '{name}' yopildi."

    if action in ("minimize", "kichiklashtir"):
        _run(["xdotool", "windowminimize", wid])
        return f"✅ '{name}' kichiklashtirildi."

    if action in ("maximize", "kattalashtir", "fullscreen"):
        _run(["xdotool", "windowactivate", "--sync", wid])
        _run(["xdotool", "windowsize", wid, str(W), str(H)])
        _run(["xdotool", "windowmove", wid, "0", "0"])
        return f"✅ '{name}' to'liq ekranga kengaytirildi."

    if action in ("left", "tile_left", "chapga"):
        _run(["xdotool", "windowactivate", "--sync", wid])
        _run(["xdotool", "windowsize", wid, str(W // 2), str(H)])
        _run(["xdotool", "windowmove", wid, "0", "0"])
        return f"✅ '{name}' chap yarmiga qo'yildi."

    if action in ("right", "tile_right", "ongga"):
        _run(["xdotool", "windowactivate", "--sync", wid])
        _run(["xdotool", "windowsize", wid, str(W // 2), str(H)])
        _run(["xdotool", "windowmove", wid, str(W // 2), "0"])
        return f"✅ '{name}' o'ng yarmiga qo'yildi."

    return ("Amallar: list | focus | close | minimize | maximize | left | right "
            "(target=oyna nomi)")
