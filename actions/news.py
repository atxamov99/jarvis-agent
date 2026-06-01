"""news.py — Top news headlines from free RSS feeds (no API key needed)."""
import html
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime


_FEEDS = {
    # English international (BBC)
    "world":    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "tech":     "https://feeds.bbci.co.uk/news/technology/rss.xml",
    "science":  "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml",
    "business": "https://feeds.bbci.co.uk/news/business/rss.xml",
    "sport":    "https://feeds.bbci.co.uk/news/sport/rss.xml",
    "health":   "https://feeds.bbci.co.uk/news/health/rss.xml",
    "top":      "https://feeds.bbci.co.uk/news/rss.xml",
    # Uzbek sources
    "uz":       "https://www.gazeta.uz/oz/rss/",
    "uzbek":    "https://www.gazeta.uz/oz/rss/",
    "gazeta":   "https://www.gazeta.uz/oz/rss/",
    # Tech / Dev
    "hackernews": "https://hnrss.org/frontpage",
    "hn":         "https://hnrss.org/frontpage",
    "dev":        "https://hnrss.org/frontpage",
}

_ALIAS = {
    "dunyo": "world", "texnologiya": "tech", "fan": "science",
    "biznes": "business", "sport": "sport", "soglik": "health",
    "salomatlik": "health", "eng muhim": "top", "asosiy": "top",
    "bosh": "top", "hn": "hackernews",
}


def _clean(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"<[^>]+>", "", text)  # strip HTML tags
    return text.strip()


def _fetch_rss(url: str, limit: int) -> list[dict]:
    req = urllib.request.Request(url, headers={"User-Agent": "JarvisAI/1.0"})
    with urllib.request.urlopen(req, timeout=12) as r:
        root = ET.fromstring(r.read())

    items = []
    for item in root.iter("item"):
        title = _clean(item.findtext("title", ""))
        desc  = _clean(item.findtext("description", ""))
        link  = _clean(item.findtext("link", ""))
        if title:
            items.append({"title": title, "desc": desc[:160] if desc else "", "link": link})
        if len(items) >= limit:
            break
    return items


def news(parameters=None, response=None, player=None, session_memory=None) -> str:
    params   = parameters or {}
    cat_raw  = (params.get("category") or "top").lower().strip()
    category = _ALIAS.get(cat_raw, cat_raw)
    limit    = min(int(params.get("limit", 5)), 10)

    feed_url = _FEEDS.get(category, _FEEDS["top"])

    try:
        items = _fetch_rss(feed_url, limit)
        if not items:
            return "Yangiliklar topilmadi."

        today = datetime.now().strftime("%d %B %Y")
        lines = [f"📰 **{category.upper()} yangiliklari** — {today}\n"]
        for i, it in enumerate(items, 1):
            lines.append(f"{i}. {it['title']}")
            if it["desc"] and it["desc"] != it["title"]:
                lines.append(f"   {it['desc']}")

        return "\n".join(lines)

    except Exception as e:
        return f"Yangiliklar xatolik: {e}"
