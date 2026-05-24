"""yt_downloader.py — Download YouTube videos/audio via yt-dlp."""
import subprocess
import sys
from pathlib import Path

_DL_DIR = Path.home() / "Downloads" / "YouTube"


def _dl_dir() -> Path:
    _DL_DIR.mkdir(parents=True, exist_ok=True)
    return _DL_DIR


def _yt_dlp(*args, timeout: int = 300) -> tuple[int, str, str]:
    cmd = [sys.executable, "-m", "yt_dlp"] + list(args)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "Vaqt tugadi (>5 daqiqa)"
    except Exception as e:
        return -1, "", str(e)


def yt_downloader(parameters=None, response=None, player=None, session_memory=None) -> str:
    params  = parameters or {}
    url     = (params.get("url") or "").strip()
    mode    = (params.get("mode") or "video").lower().strip()
    quality = (params.get("quality") or "best").lower().strip()
    out_dir = str(_dl_dir())

    if not url:
        return "YouTube URL ko'rsatilmagan."

    if player: player.write_log(f"[YTDl] {mode}: {url[:60]}")

    # ── INFO ──────────────────────────────────────────────────────────────────
    if mode in ("info", "malumot"):
        rc, out, err = _yt_dlp(
            "--print", "%(title)s\n%(duration_string)s\n%(uploader)s\n%(view_count)s views",
            "--no-playlist", url
        )
        if rc == 0:
            lines = out.splitlines()
            return (
                f"📺 {lines[0] if lines else '?'}\n"
                f"⏱  {lines[1] if len(lines) > 1 else '?'}\n"
                f"👤 {lines[2] if len(lines) > 2 else '?'}\n"
                f"👁  {lines[3] if len(lines) > 3 else '?'}"
            )
        return f"Ma'lumot olishda xato: {err[:200]}"

    # ── AUDIO (MP3) ───────────────────────────────────────────────────────────
    if mode in ("audio", "mp3", "musiqa", "music"):
        rc, out, err = _yt_dlp(
            "-x", "--audio-format", "mp3",
            "--audio-quality", "0",
            "-o", f"{out_dir}/%(title)s.%(ext)s",
            "--no-playlist",
            url,
        )
        if rc == 0:
            lines = [l for l in out.splitlines() if "Destination" in l or "[ExtractAudio]" in l]
            fname = lines[-1].split("Destination:")[-1].strip() if lines else out_dir
            if player: player.write_log(f"[YTDl] Audio saved")
            return f"🎵 MP3 saqlandi:\n{fname}"
        return f"Audio yuklab bo'lmadi:\n{err[-300:]}"

    # ── VIDEO ─────────────────────────────────────────────────────────────────
    quality_map = {
        "best": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "1080": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]",
        "720":  "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]",
        "480":  "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480]",
        "360":  "bestvideo[height<=360][ext=mp4]+bestaudio/best[height<=360]",
    }
    fmt = quality_map.get(quality, quality_map["best"])
    rc, out, err = _yt_dlp(
        "-f", fmt,
        "--merge-output-format", "mp4",
        "-o", f"{out_dir}/%(title)s.%(ext)s",
        "--no-playlist",
        url,
    )
    if rc == 0:
        lines = [l for l in out.splitlines() if "Destination" in l or "Merging" in l]
        fname = lines[-1].split("Destination:")[-1].strip() if lines else out_dir
        if player: player.write_log(f"[YTDl] Video saved")
        return f"🎬 Video saqlandi ({quality}):\n{fname}"
    return f"Video yuklab bo'lmadi:\n{err[-300:]}"
