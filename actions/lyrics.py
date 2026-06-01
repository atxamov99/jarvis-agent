"""lyrics.py — Song lyrics via lrclib.net (free, no API key)."""
import json
import urllib.request
import urllib.parse


def _search(artist: str, title: str) -> dict | None:
    q = urllib.parse.urlencode({"artist_name": artist, "track_name": title})
    url = f"https://lrclib.net/api/search?{q}"
    req = urllib.request.Request(url, headers={"User-Agent": "JarvisLyrics/1.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        results = json.loads(r.read())
    if not results:
        return None
    return results[0]


def lyrics(parameters=None, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    title  = (params.get("title") or params.get("song") or "").strip()
    artist = (params.get("artist") or params.get("singer") or "").strip()
    mode   = (params.get("mode") or "plain").lower()

    if not title:
        return "Qo'shiq nomini ko'rsating. Masalan: {title: 'Bohemian Rhapsody', artist: 'Queen'}"

    try:
        hit = _search(artist, title)
    except Exception as e:
        return f"Qidirishda xato: {e}"

    if not hit:
        return f"'{title}' qo'shig'i topilmadi."

    track_title  = hit.get("trackName", title)
    track_artist = hit.get("artistName", artist)
    album        = hit.get("albumName", "")
    duration     = hit.get("duration", 0)

    plain_lyrics  = (hit.get("plainLyrics") or "").strip()
    synced_lyrics = (hit.get("syncedLyrics") or "").strip()

    header = f"Qo'shiq: {track_title} — {track_artist}"
    if album:
        header += f" ({album})"
    if duration:
        mins, secs = divmod(int(duration), 60)
        header += f" [{mins}:{secs:02d}]"

    if mode == "synced" and synced_lyrics:
        lines = synced_lyrics.splitlines()[:40]
        return header + "\n\n" + "\n".join(lines)

    if plain_lyrics:
        lines = plain_lyrics.splitlines()[:60]
        return header + "\n\n" + "\n".join(lines)

    if synced_lyrics:
        clean = [l.split("]", 1)[-1].strip() for l in synced_lyrics.splitlines() if "]" in l]
        return header + "\n\n" + "\n".join(clean[:60])

    return f"{header}\n\nSo'z matni mavjud emas."
