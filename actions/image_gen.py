"""image_gen.py — Generate images via DALL-E 3 (OpenAI) or Pollinations.ai (free)."""
import json
import os
import subprocess
import urllib.request
from datetime import datetime
from pathlib import Path

_IMG_DIR = Path.home() / "Pictures" / "JarvisAI"


def _img_dir() -> Path:
    _IMG_DIR.mkdir(parents=True, exist_ok=True)
    return _IMG_DIR


def _load_openai_key() -> str | None:
    cfg = Path(__file__).parent.parent / "config" / "api_keys.json"
    try:
        data = json.loads(cfg.read_text())
        return data.get("openai_api_key") or None
    except Exception:
        return None


def _dalle3(prompt: str, size: str = "1024x1024") -> str:
    from openai import OpenAI
    client = OpenAI(api_key=_load_openai_key())
    resp = client.images.generate(
        model="dall-e-3", prompt=prompt, n=1, size=size,
        response_format="url",
    )
    url = resp.data[0].url
    ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = _img_dir() / f"dalle_{ts}.png"
    urllib.request.urlretrieve(url, str(out))
    return str(out)


def _pollinations(prompt: str, width: int = 1024, height: int = 1024,
                  model: str = "flux") -> str:
    from urllib.parse import quote
    url = f"https://image.pollinations.ai/prompt/{quote(prompt)}?width={width}&height={height}&model={model}&nologo=true"
    ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = _img_dir() / f"ai_{ts}.png"
    req = urllib.request.Request(url, headers={"User-Agent": "JarvisAI/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        out.write_bytes(r.read())
    return str(out)


def _open_image(path: str):
    for viewer in ("eog", "feh", "gimp", "display", "xdg-open"):
        import shutil
        if shutil.which(viewer):
            subprocess.Popen([viewer, path])
            return


def image_gen(parameters=None, response=None, player=None, session_memory=None) -> str:
    params  = parameters or {}
    prompt  = (params.get("prompt") or "").strip()
    size    = (params.get("size") or "1024x1024").strip()
    backend = (params.get("backend") or "auto").lower().strip()
    show    = params.get("show", True)

    if not prompt:
        return "Rasm tavsifi (prompt) ko'rsatilmagan."

    if player: player.write_log(f"[ImageGen] '{prompt[:50]}' via {backend}")

    try:
        if backend == "dalle" or (backend == "auto" and _load_openai_key()):
            path = _dalle3(prompt, size)
            source = "DALL-E 3"
        else:
            w, h = (1024, 1024)
            if "x" in size:
                parts = size.split("x")
                w, h  = int(parts[0]), int(parts[1])
            path = _pollinations(prompt, w, h)
            source = "Pollinations.ai (bepul)"
    except Exception as e:
        # Fallback to pollinations
        if backend != "pollinations":
            try:
                path = _pollinations(prompt)
                source = "Pollinations.ai (fallback)"
            except Exception as e2:
                return f"Rasm yaratishda xato: {e}\nFallback: {e2}"
        else:
            return f"Rasm yaratishda xato: {e}"

    if show:
        _open_image(path)

    if player: player.write_log(f"[ImageGen] Saved: {Path(path).name}")
    return f"Rasm tayyor ({source}):\n{path}"
