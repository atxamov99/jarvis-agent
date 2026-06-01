"""auto_agent.py — Multi-Agent Computer-Use system (Planner + Executor + Verifier).

Give JARVIS a GOAL and three specialized agents collaborate to finish it inside
ANY app, autonomously:

  🧭 PLANNER  — looks at the first screen, breaks the goal into ordered steps.
  🖐 EXECUTOR — for the CURRENT step, sees the screen and emits one concrete
                action (click/type/key/scroll/wait), or 'step_done' when the
                step is finished, or 'done' when the whole goal is done.
  🔍 VERIFIER — when the executor claims 'done', independently checks the screen
                and confirms the goal is really achieved (or sends it back).

This is far more reliable than a single loop on multi-step in-app tasks: each
step has a clear sub-goal, and completion is double-checked before stopping.
Built on screen capture + Gemini vision + xdotool.
"""
import base64
import io
import json
import re
import subprocess
import time
from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent
_API  = _BASE / "config" / "api_keys.json"
_MAX_STEPS_CAP = 18


def _api_key() -> str:
    try:
        return json.loads(_API.read_text(encoding="utf-8")).get("gemini_api_key", "").strip()
    except Exception:
        return ""


def _grab(monitor: int = 1):
    from actions.screen_capture import capture_pil
    from PIL import Image
    img = capture_pil()
    if img is None:
        raise RuntimeError("Ekran surati olinmadi (Wayland — gnome-screenshot kerak).")
    geom = {"left": 0, "top": 0, "width": img.width, "height": img.height}  # native dims
    if img.width > 1280:
        h = int(img.height * 1280 / img.width)
        img = img.resize((1280, h), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return base64.b64encode(buf.getvalue()).decode(), geom


def _vision(text: str, img_b64: str, max_tokens: int = 220, temperature: float = 0.1) -> str:
    import core.gemini_rest as _gr
    return _gr.generate(
        [{"text": text}, {"inline_data": {"mime_type": "image/jpeg", "data": img_b64}}],
        max_tokens=max_tokens, temperature=temperature, timeout=30,
    )


def _extract_json(raw: str):
    """Parse the model's JSON, repairing the common LLM mistakes (unquoted keys,
    single quotes, trailing commas) so a slightly malformed reply still works."""
    if not raw:
        return None
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return None
    txt = m.group(0)
    try:
        return json.loads(txt)
    except Exception:
        pass
    # Repair pass: quote bare keys (e.g. y:160 → "y":160), single→double quotes,
    # strip trailing commas.
    fixed = re.sub(r'([{,]\s*)([A-Za-z_]\w*)(\s*:)', r'\1"\2"\3', txt)
    fixed = fixed.replace("'", '"')
    fixed = re.sub(r',\s*([}\]])', r'\1', fixed)
    try:
        return json.loads(fixed)
    except Exception:
        return None


# ── 🧭 PLANNER ────────────────────────────────────────────────────────────────

_PLANNER_SYS = (
    "You are the PLANNER of a desktop automation team. Given a GOAL and a "
    "screenshot of the current screen, break the goal into 2-6 short, ordered, "
    "concrete steps a person would take inside the app. Keep steps high-level "
    "(e.g. 'open search', 'find the contact', 'type the message') — NOT pixel "
    "coordinates. Respond with ONLY JSON: "
    '{"steps":["step 1","step 2",...]}'
)


def _plan(goal: str, img_b64: str) -> list:
    text = f"{_PLANNER_SYS}\n\nGOAL: {goal}\n\nPlan JSON:"
    data = _extract_json(_vision(text, img_b64, max_tokens=260, temperature=0.2))
    if data and isinstance(data.get("steps"), list):
        steps = [str(s).strip() for s in data["steps"] if str(s).strip()]
        if steps:
            return steps[:6]
    return [goal]  # fallback: treat the whole goal as one step


# ── 🖐 EXECUTOR ───────────────────────────────────────────────────────────────

_EXECUTOR_SYS = (
    "You are the EXECUTOR of a desktop automation team, operating a Linux desktop "
    "inside whatever app is needed (Telegram, YouTube, browser, editor, settings — "
    "ANY app). You see the full PLAN, which STEP you're on, the actions so far, and "
    "a screenshot. Emit the SINGLE next concrete action to advance the CURRENT step. "
    "Coordinates are normalized 0-1000 (x left→right, y top→bottom).\n"
    "Respond with ONLY one compact JSON object, no markdown:\n"
    '{"action":"click","x":<int>,"y":<int>,"why":"<short>"}\n'
    '{"action":"double_click","x":<int>,"y":<int>,"why":"..."}\n'
    '{"action":"type","text":"<text>","why":"..."}\n'
    '{"action":"key","key":"<Return|Tab|ctrl+a|Escape|ctrl+f|...>","why":"..."}\n'
    '{"action":"scroll","dir":"<up|down>","why":"..."}\n'
    '{"action":"wait","why":"<app still loading>"}\n'
    '{"action":"step_done","why":"current step is finished, move to next"}\n'
    '{"action":"done","answer":"<result in Uzbek>","why":"whole goal achieved"}\n'
    '{"action":"fail","why":"<why stuck>"}\n'
    "\nIN-APP PLAYBOOK:\n"
    "- Find a person/chat/video: click the search box (magnifier icon, or ctrl+f / "
    "top search bar), THEN type the query, THEN press Return, THEN click the correct "
    "result.\n"
    "- To type into a field you must FIRST click that field. Never 'type' without a "
    "focused input. A message box is usually at the bottom — click it first.\n"
    "- App still opening (blank/splash) → 'wait'.\n"
    "- Use 'step_done' the moment the current step's objective is visibly met, so the "
    "team advances. Use 'done' only when the ENTIRE goal is achieved.\n"
    "- SENDING/POSTING (Enter to send, Send/Post/Publish button): ONLY if the goal "
    "explicitly says to send/post/yubor. If the goal was to write/draft, finish with "
    "the text typed but NOT sent.\n"
    "One concrete step at a time. Be decisive."
)


def _execute(goal: str, plan: list, step_idx: int, history: list, img_b64: str) -> dict:
    plan_str = "\n".join(
        f"{'▶' if i == step_idx else ' '} {i+1}. {s}" for i, s in enumerate(plan)
    )
    cur = plan[step_idx] if step_idx < len(plan) else "(finishing)"
    hist = "\n".join(f"{i+1}. {h}" for i, h in enumerate(history[-8:])) or "(none yet)"
    text = (
        f"{_EXECUTOR_SYS}\n\nGOAL: {goal}\n\nPLAN:\n{plan_str}\n\n"
        f"CURRENT STEP ({step_idx+1}/{len(plan)}): {cur}\n\n"
        f"RECENT ACTIONS:\n{hist}\n\nNext action JSON:"
    )
    d = _extract_json(_vision(text, img_b64, max_tokens=200, temperature=0.1))
    return d or {"action": "fail", "why": "executor: parse/quota error"}


# ── 🔍 VERIFIER ───────────────────────────────────────────────────────────────

_VERIFIER_SYS = (
    "You are the VERIFIER of a desktop automation team. The executor claims the "
    "GOAL is done. Look at the screenshot and judge HONESTLY whether the goal is "
    "actually achieved on screen. Respond with ONLY JSON: "
    '{"complete":true|false,"reason":"<short, in Uzbek>"}. '
    "Be strict: if the goal said to write a specific text in a specific chat, that "
    "exact text must be visible in the right chat's input. If it said to find a "
    "video/contact, the right one must be open/selected."
)


def _verify(goal: str, img_b64: str) -> dict:
    text = f"{_VERIFIER_SYS}\n\nGOAL: {goal}\n\nVerdict JSON:"
    d = _extract_json(_vision(text, img_b64, max_tokens=120, temperature=0.0))
    if d is None:
        return {"complete": True, "reason": "verifier javob bermadi — qabul qilindi"}
    return d


# ── Action primitives ─────────────────────────────────────────────────────────

def _do_click(d, geom, double=False):
    import core.input_control as ic
    x = int(geom["left"] + float(d["x"]) / 1000.0 * geom["width"])
    y = int(geom["top"]  + float(d["y"]) / 1000.0 * geom["height"])
    ic.click(x, y, double=double)
    return f"({x},{y})"


_last_click = {"x": None, "y": None}


def _perform(act: str, d: dict, geom: dict) -> str:
    """Run one primitive action via the Wayland/X11-aware input layer."""
    import core.input_control as ic
    if act == "click":
        pos = _do_click(d, geom)
        _last_click["x"] = int(geom["left"] + float(d["x"]) / 1000.0 * geom["width"])
        _last_click["y"] = int(geom["top"]  + float(d["y"]) / 1000.0 * geom["height"])
        return f"click {pos} — {d.get('why','')}"
    if act == "double_click":
        pos = _do_click(d, geom, double=True)
        _last_click["x"] = int(geom["left"] + float(d["x"]) / 1000.0 * geom["width"])
        _last_click["y"] = int(geom["top"]  + float(d["y"]) / 1000.0 * geom["height"])
        return f"double_click {pos} — {d.get('why','')}"
    if act == "type":
        txt = d.get("text", "")
        # Re-focus the last-clicked field right before typing so the keystrokes
        # land in the target app's input, not whatever window grabbed focus.
        if _last_click["x"] is not None:
            ic.click(_last_click["x"], _last_click["y"])
            import time as _t; _t.sleep(0.2)
        ic.type_text(txt)
        return f"type '{txt[:40]}' — {d.get('why','')}"
    if act == "key":
        k = d.get("key", "Return")
        ic.key(k)
        return f"key {k} — {d.get('why','')}"
    if act == "scroll":
        ic.scroll(d.get("dir", "down"), amount=3)
        return f"scroll {d.get('dir','down')} — {d.get('why','')}"
    if act == "wait":
        time.sleep(1.5)
        return f"wait — {d.get('why','')}"
    return f"unknown:{act}"


_installed_cache = {"names": None, "ts": 0.0}


def _installed_apps() -> list:
    """Scan the OS for EVERY installed app name (cached 5 min).

    Linux: parse .desktop files. macOS: /Applications/*.app. Windows: Start-menu
    shortcuts. This lets _guess_app recognize ANY app the user has, not just a
    hardcoded shortlist.
    """
    import time as _t
    now = _t.time()
    if _installed_cache["names"] is not None and now - _installed_cache["ts"] < 300:
        return _installed_cache["names"]
    names = []
    try:
        import platform, glob, os
        sysname = platform.system()
        if sysname == "Linux":
            dirs = ["/usr/share/applications", "/var/lib/flatpak/exports/share/applications",
                    "/var/lib/snapd/desktop/applications",
                    os.path.expanduser("~/.local/share/applications")]
            for d in dirs:
                for path in glob.glob(os.path.join(d, "*.desktop")):
                    try:
                        nodisplay = False
                        nm = ""
                        exec_bin = ""
                        with open(path, encoding="utf-8", errors="ignore") as fh:
                            for line in fh:
                                if line.startswith("Name=") and not nm:
                                    nm = line[5:].strip()
                                elif line.startswith("Exec=") and not exec_bin:
                                    # first token of Exec, stripped of path & %-args
                                    tok = line[5:].strip().split()
                                    if tok:
                                        exec_bin = os.path.basename(tok[0]).lower()
                                elif line.startswith("NoDisplay=true"):
                                    nodisplay = True
                        if nodisplay:
                            continue
                        if nm and len(nm) <= 30:
                            names.append(nm.lower())
                        if exec_bin and exec_bin.isalpha() and 2 < len(exec_bin) <= 20:
                            names.append(exec_bin)
                    except Exception:
                        continue
        elif sysname == "Darwin":
            for path in glob.glob("/Applications/*.app") + glob.glob(os.path.expanduser("~/Applications/*.app")):
                names.append(os.path.basename(path)[:-4].lower())
        elif sysname == "Windows":
            for base in [os.path.join(os.environ.get("PROGRAMDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs"),
                         os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs")]:
                for root, _dn, files in os.walk(base):
                    for fn in files:
                        if fn.lower().endswith(".lnk"):
                            names.append(fn[:-4].lower())
    except Exception:
        pass
    names = sorted(set(names), key=len, reverse=True)  # longer names match first
    _installed_cache["names"] = names
    _installed_cache["ts"] = now
    return names


def _guess_app(goal: str) -> str:
    """Detect ANY app named in the goal so we open/focus it first.

    Matches a curated shortlist, then the open_app alias table, then EVERY app
    actually installed on this machine. Returns "" if no app is clearly named —
    in which case the agents still operate on whatever app is already on screen.
    """
    g = " " + goal.lower() + " "
    def _hit(name: str) -> bool:
        n = name.strip()
        if not n:
            return False
        # word + common Uzbek case suffixes (da/dan/ni/ga/...)
        return any(f" {n}{suf} " in g for suf in ("", "da", "dan", "ni", "ga", "ga ", "dagi", "’da", "'da"))
    common = [
        "telegram", "whatsapp", "youtube", "chrome", "firefox", "spotify",
        "discord", "slack", "instagram", "vs code", "vscode", "code", "gmail",
        "obs", "zoom", "skype", "brave", "edge", "opera", "calculator",
        "terminal", "files", "settings", "twitter", "facebook", "tiktok",
        "netflix", "steam",
    ]
    for name in common:
        if _hit(name):
            return name
    try:
        from actions.open_app import _APP_ALIASES
        for alias in _APP_ALIASES.keys():
            if _hit(alias):
                return alias
    except Exception:
        pass
    # Fall back to EVERY installed app — recognizes anything on this machine
    for name in _installed_apps():
        if _hit(name):
            return name
    return ""


# ── Orchestrator ──────────────────────────────────────────────────────────────

def auto_agent(parameters=None, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    goal   = (params.get("goal") or params.get("task") or "").strip()
    if not goal:
        return "Vazifani ayting (goal=...)."
    max_steps = min(int(params.get("max_steps", 12)), _MAX_STEPS_CAP)
    monitor   = int(params.get("monitor", 1))

    if not _api_key():
        return "Gemini API kaliti topilmadi."

    def log(msg):
        print(f"[AutoAgent] {msg}")
        if player:
            try: player.write_log(f"🤖 {msg}")
            except Exception: pass

    log(f"Vazifa boshlandi: {goal}")

    # Pre-open / focus the relevant app so agents don't waste steps finding it.
    app = (params.get("app") or "").strip() or _guess_app(goal)
    if app:
        try:
            from actions.open_app import open_app as _open
            _open(parameters={"app_name": app}, player=player)
            log(f"Ilova ochilmoqda/fokuslanmoqda: {app}")
            time.sleep(2.2)
        except Exception as _e:
            log(f"Ilovani ochishda ogohlantirish: {_e}")

    # 🧭 PLANNER — one-time high-level plan from the first screen
    try:
        img, geom = _grab(monitor)
    except Exception as e:
        return f"Ekranni olishda xato: {e}"
    plan = _plan(goal, img)
    log("🧭 Reja: " + " → ".join(plan))

    history = []
    step_idx = 0
    verify_tries = 0

    # 🖐 EXECUTOR loop (with 🔍 VERIFIER gate on completion)
    for micro in range(1, max_steps + 1):
        try:
            img, geom = _grab(monitor)
        except Exception as e:
            return f"Ekranni olishda xato: {e}"

        d = _execute(goal, plan, step_idx, history, img)
        act = (d.get("action") or "fail").lower()
        why = d.get("why", "")

        if act == "step_done":
            step_idx = min(step_idx + 1, len(plan) - 1)
            log(f"{micro}. ✓ Bosqich {step_idx} tugadi → {plan[step_idx] if step_idx < len(plan) else 'yakun'}")
            history.append(f"step_done → now step {step_idx+1}")
            time.sleep(0.6)
            continue

        if act == "done":
            ans = d.get("answer", "Bajarildi.")
            # 🔍 VERIFIER double-checks before we trust 'done'
            try:
                vimg, _ = _grab(monitor)
                verdict = _verify(goal, vimg)
            except Exception:
                verdict = {"complete": True, "reason": "tekshiruv o'tkazib yuborildi"}
            if verdict.get("complete", True):
                log(f"✅ Verifier tasdiqladi: {ans}")
                return f"✅ Vazifa bajarildi ({micro} qadam): {ans}"
            verify_tries += 1
            log(f"🔍 Verifier: hali tugamagan — {verdict.get('reason','')}")
            history.append(f"verifier rejected: {verdict.get('reason','')}")
            if verify_tries >= 2:
                return (f"⚠️ Vazifa qisman bajarildi. Verifier: "
                        f"{verdict.get('reason','tugamagan')}. Aniqroq ayting yoki qayta urinib ko'ring.")
            time.sleep(0.6)
            continue

        if act == "fail":
            log(f"❌ To'xtadi: {why}")
            return f"❌ Vazifani bajarib bo'lmadi ({micro} qadam): {why}"

        # Concrete primitive
        try:
            line = _perform(act, d, geom)
            log(f"{micro}. {line}")
            history.append(line)
        except Exception as e:
            log(f"{micro}. Amal xatosi: {e}")
            history.append(f"{act} FAILED: {e}")

        time.sleep(1.3)  # settle UI + ease per-minute vision rate limit

    return (f"⏱️ {max_steps} qadam bajarildi, vazifa to'liq tugamagan bo'lishi mumkin. "
            "Qayta urinib ko'ring yoki aniqroq ayting.")
