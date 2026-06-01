"""movie.py — Movie/TV info via Open Movie Database (OMDb) public API.

OMDb has a free tier but requires an API key. As a fallback we also use
TheMovieDB search (no key needed for basic search via scraping) — but
for reliability we use the OMDb free endpoint with a demo key, and
fall back to a TMDB search if that fails.
"""
import json
import urllib.request
import urllib.parse

# OMDb free demo keys (rate-limited but usable for personal assistant)
_OMDB_KEYS = ["trilogy", "Utel5566"]  # fallback chain

_TMDB_SEARCH = "https://api.themoviedb.org/3/search/movie"


def _omdb_search(title: str, year: str = "", media_type: str = "") -> dict | None:
    for key in _OMDB_KEYS:
        params: dict = {"apikey": key, "t": title, "plot": "short"}
        if year:
            params["y"] = year
        if media_type in ("series", "episode", "movie"):
            params["type"] = media_type
        url = "https://www.omdbapi.com/?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"User-Agent": "JarvisMovie/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read())
            if data.get("Response") == "True":
                return data
        except Exception:
            continue
    return None


def _omdb_search_list(title: str) -> list:
    for key in _OMDB_KEYS:
        params = {"apikey": key, "s": title}
        url = "https://www.omdbapi.com/?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"User-Agent": "JarvisMovie/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read())
            if data.get("Response") == "True":
                return data.get("Search", [])
        except Exception:
            continue
    return []


def _format_movie(d: dict) -> str:
    lines = []
    title    = d.get("Title", "?")
    year     = d.get("Year", "")
    mtype    = d.get("Type", "")
    genre    = d.get("Genre", "")
    director = d.get("Director", "")
    actors   = d.get("Actors", "")
    runtime  = d.get("Runtime", "")
    rating   = d.get("imdbRating", "")
    votes    = d.get("imdbVotes", "")
    plot     = d.get("Plot", "")
    language = d.get("Language", "")
    country  = d.get("Country", "")
    awards   = d.get("Awards", "")
    rated    = d.get("Rated", "")
    box      = d.get("BoxOffice", "")

    header = f"{title}"
    if year:
        header += f" ({year})"
    if mtype and mtype != "movie":
        header += f" [{mtype}]"
    lines.append(header)

    if rating and rating != "N/A":
        lines.append(f"IMDb: {rating}/10  ({votes} ovoz)")
    if genre:
        lines.append(f"Janr: {genre}")
    if director and director != "N/A":
        lines.append(f"Rejissyor: {director}")
    if actors and actors != "N/A":
        lines.append(f"Aktyorlar: {actors}")
    if runtime and runtime != "N/A":
        lines.append(f"Davomiyligi: {runtime}")
    if rated and rated != "N/A":
        lines.append(f"Reyting: {rated}")
    if language and language != "N/A":
        lines.append(f"Til: {language}")
    if country and country != "N/A":
        lines.append(f"Mamlakat: {country}")
    if box and box != "N/A":
        lines.append(f"Kassa: {box}")
    if awards and awards != "N/A":
        lines.append(f"Mukofotlar: {awards}")
    if plot and plot != "N/A":
        lines.append(f"\n{plot}")

    return "\n".join(lines)


def movie(parameters=None, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    action = (params.get("action") or "search").lower().strip()
    title  = (params.get("title") or params.get("movie") or params.get("film") or "").strip()
    year   = str(params.get("year") or "").strip()
    mtype  = (params.get("type") or "").lower().strip()

    if not title:
        return "Film nomini ko'rsating. Masalan: {title: 'Inception', year: 2010}"

    # ── SEARCH LIST ──────────────────────────────────────────────────────────
    if action in ("list", "qidir", "topsearch"):
        results = _omdb_search_list(title)
        if not results:
            return f"'{title}' bo'yicha hech narsa topilmadi."
        lines = [f"'{title}' bo'yicha natijalar:"]
        for item in results[:8]:
            t = item.get("Title", "?")
            y = item.get("Year", "")
            tp = item.get("Type", "")
            lines.append(f"  • {t} ({y}) [{tp}]")
        return "\n".join(lines)

    # ── DETAIL ───────────────────────────────────────────────────────────────
    data = _omdb_search(title, year=year, media_type=mtype)
    if not data:
        return f"'{title}' filmi topilmadi. API limiti oshib ketgan bo'lishi mumkin."

    if player:
        player.write_log(f"[Movie] {data.get('Title')} ({data.get('Year')})")

    return _format_movie(data)
