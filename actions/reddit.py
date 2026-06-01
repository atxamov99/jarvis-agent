"""reddit.py — Browse Reddit via public JSON API (no auth/key needed).

Works with any public subreddit. Uses Reddit's unofficial JSON endpoint.
"""
import json
import urllib.request
import urllib.parse
import html
import re

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Accept": "application/json, text/javascript, */*",
    "Accept-Language": "en-US,en;q=0.5",
    "DNT": "1",
}

_POPULAR = [
    "worldnews", "technology", "science", "programming",
    "todayilearned", "askscience", "space", "games",
]

_ALIASES = {
    "news":        "worldnews",
    "yangiliklar": "worldnews",
    "texnologiya": "technology",
    "tech":        "technology",
    "fan":         "science",
    "kod":         "programming",
    "prog":        "programming",
    "dasturlash":  "programming",
    "oyinlar":     "games",
    "games":       "games",
    "ilm":         "askscience",
    "kosmik":      "space",
    "cosmos":      "space",
    "til":         "todayilearned",
}


def _strip(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[*_~`#>]+", "", text)
    return text.strip()


def _fetch(subreddit: str, sort: str = "hot", limit: int = 10, time_filter: str = "day") -> list:
    sort = sort.lower()
    if sort not in ("hot", "new", "top", "rising"):
        sort = "hot"
    url = f"https://old.reddit.com/r/{subreddit}/{sort}.json?limit={limit}&t={time_filter}&raw_json=1"
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=12) as r:
        data = json.loads(r.read())
    posts = data.get("data", {}).get("children", [])
    return [p["data"] for p in posts if p.get("kind") == "t3"]


def reddit(parameters=None, response=None, player=None, session_memory=None) -> str:
    params    = parameters or {}
    action    = (params.get("action") or "browse").lower().strip()
    subreddit = (params.get("subreddit") or params.get("sub") or params.get("topic") or "").strip()
    subreddit = _ALIASES.get(subreddit.lower(), subreddit) if subreddit else ""
    sort      = (params.get("sort") or "hot").lower()
    limit     = min(int(params.get("limit") or params.get("count") or 5), 15)

    # ── POPULAR LIST ──────────────────────────────────────────────────────────
    if action in ("popular", "list", "categories", "top_subs"):
        return "Mashhur subredditlar:\n" + "\n".join(f"  • r/{s}" for s in _POPULAR)

    # ── BROWSE ────────────────────────────────────────────────────────────────
    if not subreddit:
        subreddit = "worldnews"

    try:
        posts = _fetch(subreddit, sort=sort, limit=limit)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return f"r/{subreddit} subredditi topilmadi."
        return f"Reddit xatosi: HTTP {e.code}"
    except Exception as e:
        return f"Reddit ma'lumot olishda xato: {e}"

    if not posts:
        return f"r/{subreddit} dan post topilmadi."

    # ── SEARCH ────────────────────────────────────────────────────────────────
    query = (params.get("query") or params.get("q") or "").strip()
    if query or action == "search":
        q = query or subreddit
        url = f"https://old.reddit.com/search.json?q={urllib.parse.quote(q)}&sort={sort}&limit={limit}&raw_json=1"
        try:
            req = urllib.request.Request(url, headers=_HEADERS)
            with urllib.request.urlopen(req, timeout=12) as r:
                data = json.loads(r.read())
            posts = [p["data"] for p in data.get("data", {}).get("children", []) if p.get("kind") == "t3"]
        except Exception as e:
            return f"Qidiruvda xato: {e}"
        header = f"Reddit qidirish: '{q}'"
    else:
        header = f"r/{subreddit} — {sort.upper()} ({limit} ta post)"

    if not posts:
        return f"Hech narsa topilmadi."

    lines = [header, ""]
    for i, p in enumerate(posts, 1):
        title  = _strip(p.get("title", ""))
        author = p.get("author", "?")
        ups    = p.get("ups", 0)
        cmts   = p.get("num_comments", 0)
        sub    = p.get("subreddit", "")
        score  = f"⬆{ups:,}  💬{cmts}"
        lines.append(f"{i}. {title}")
        lines.append(f"   {score}  by u/{author}  r/{sub}")
        if action == "detailed":
            selftext = _strip(p.get("selftext", ""))
            if selftext:
                lines.append(f"   {selftext[:200]}{'...' if len(selftext)>200 else ''}")
        lines.append("")

    return "\n".join(lines).strip()
