"""wikipedia.py — Quick Wikipedia article summaries (no API key required)."""
import json
import urllib.parse
import urllib.request


_LANG_MAP = {
    "uzbek": "uz", "ingliz": "en", "rus": "ru", "english": "en",
    "russian": "ru", "uzbekcha": "uz", "o'zbek": "uz",
}


def wikipedia(parameters=None, response=None, player=None, session_memory=None) -> str:
    params    = parameters or {}
    query     = (params.get("query") or "").strip()
    sentences = min(int(params.get("sentences", 4)), 10)
    lang_raw  = (params.get("lang") or "en").lower().strip()
    lang      = _LANG_MAP.get(lang_raw, lang_raw)  # normalize

    if not query:
        return "Qidiruv so'zini kiriting."

    headers = {"User-Agent": "JarvisAI/1.0 (educational project)"}

    def _api(lang_code: str, **kw) -> dict:
        url = f"https://{lang_code}.wikipedia.org/w/api.php?" + urllib.parse.urlencode(
            {"format": "json", "utf8": 1, **kw}
        )
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())

    try:
        # Step 1: Find best article title via search
        srdata = _api(lang, action="query", list="search",
                      srsearch=query, srlimit=1)
        results = srdata.get("query", {}).get("search", [])
        if not results:
            # Retry in English if no results in target lang
            if lang != "en":
                srdata = _api("en", action="query", list="search",
                              srsearch=query, srlimit=1)
                results = srdata.get("query", {}).get("search", [])
                lang = "en"
            if not results:
                return f"Wikipedia'da '{query}' bo'yicha hech narsa topilmadi."

        title = results[0]["title"]

        # Step 2: Fetch article extract
        exdata = _api(lang, action="query", titles=title,
                      prop="extracts", exsentences=sentences,
                      exintro=True, explaintext=True)
        pages   = exdata.get("query", {}).get("pages", {})
        page    = next(iter(pages.values()))
        extract = page.get("extract", "").strip()

        if not extract:
            return f"Wikipedia: '{title}' mavjud, lekin matn topilmadi."

        wiki_url = (
            f"https://{lang}.wikipedia.org/wiki/"
            + urllib.parse.quote(title.replace(" ", "_"))
        )
        return f"📖 **{title}** (Wikipedia)\n\n{extract}\n\n🔗 {wiki_url}"

    except Exception as e:
        return f"Wikipedia xatolik: {e}"
