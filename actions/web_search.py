"""web_search.py — robust multi-backend web search.

Backend priority (fastest → slowest, most-reliable → least):
1. Wikipedia summary  — for definitional/biographical/historical queries
2. Gemini google_search — for current events, comparisons, general knowledge
3. DuckDuckGo (ddgs) — fallback when Gemini returns nothing
4. Direct HTTP fetch — when a specific URL is requested
5. Plain Google scrape — last-resort fallback

Modes:
  search   — default; tries the chain above
  compare  — uses Gemini grounding to compare items
  url      — extract readable text from a specific URL
  news     — append "latest news" suffix and prefer Gemini grounding
"""

import json
import re
import sys
import time
import urllib.parse
from pathlib import Path


def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR        = _get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"

_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _get_api_key() -> str:
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]


# ── Backend 1: Wikipedia ──────────────────────────────────────────────────────

def _wikipedia_summary(query: str) -> str | None:
    """Fast, key-less, very reliable for 'what/who is X' queries."""
    try:
        import requests
    except ImportError:
        return None

    # Wikipedia REST API: /api/rest_v1/page/summary/{title}
    for lang in ("en", "ru", "uz"):
        try:
            title = urllib.parse.quote(query.strip().replace(" ", "_"))
            url   = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title}"
            r     = requests.get(url, timeout=4, headers={"User-Agent": _UA})
            if r.status_code != 200:
                continue
            data = r.json()
            if data.get("type") == "disambiguation":
                continue
            extract = (data.get("extract") or "").strip()
            if not extract or len(extract) < 80:
                continue
            page_url = data.get("content_urls", {}).get("desktop", {}).get("page", "")
            result = extract
            if page_url:
                result += f"\n\nManba: {page_url}"
            return result
        except Exception:
            continue
    return None


# ── Backend 2: Gemini google_search ───────────────────────────────────────────

def _gemini_search(query: str) -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=_get_api_key())

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=query,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            # Force the model to actually use the tool and give substantive output
            system_instruction=(
                "You MUST search the web and return a substantive, factual answer. "
                "Use the google_search tool aggressively. Never say 'I don't know' — "
                "if the first query yields nothing, refine it and search again. "
                "Cite sources when possible. Respond in the same language the user used."
            ),
        ),
    )

    # Extract text from all parts (Gemini sometimes splits across thought/text parts)
    text_parts: list[str] = []
    sources: list[str] = []
    try:
        cand = response.candidates[0]
        for part in cand.content.parts:
            t = getattr(part, "text", None)
            if t and t.strip():
                text_parts.append(t.strip())
        # Pull grounding URLs if available
        gm = getattr(cand, "grounding_metadata", None)
        if gm and getattr(gm, "grounding_chunks", None):
            for chunk in gm.grounding_chunks[:5]:
                web = getattr(chunk, "web", None)
                if web and getattr(web, "uri", None):
                    sources.append(web.uri)
    except Exception:
        pass

    text = "\n".join(text_parts).strip()
    if not text:
        raise ValueError("Gemini returned an empty response.")

    if sources:
        text += "\n\nManbalar:\n" + "\n".join(f"  • {u}" for u in sources)
    return text


# ── Backend 3: DuckDuckGo with retry ──────────────────────────────────────────

def _ddg_search(query: str, max_results: int = 6, retries: int = 2) -> list[dict]:
    try:
        from ddgs import DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            return []

    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            results = []
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=max_results):
                    results.append({
                        "title":   r.get("title")  or r.get("Heading", ""),
                        "snippet": r.get("body")   or r.get("Abstract", ""),
                        "url":     r.get("href")   or r.get("FirstURL", ""),
                    })
            if results:
                return results
        except Exception as e:
            last_err = e
            time.sleep(0.8 * (attempt + 1))
            continue

    if last_err:
        print(f"[WebSearch] ⚠️ DDG failed after {retries+1} attempts: {last_err}")
    return []


def _format_ddg(query: str, results: list[dict]) -> str:
    if not results:
        return ""
    lines = [f"Search results for: {query}\n"]
    for i, r in enumerate(results, 1):
        if r.get("title"):   lines.append(f"{i}. {r['title']}")
        if r.get("snippet"): lines.append(f"   {r['snippet']}")
        if r.get("url"):     lines.append(f"   {r['url']}")
        lines.append("")
    return "\n".join(lines).strip()


# ── Backend 4: Direct URL fetch (readable extraction) ─────────────────────────

def _fetch_url(url: str, max_chars: int = 6000) -> str | None:
    try:
        import requests
    except ImportError:
        return None

    try:
        r = requests.get(
            url, timeout=8,
            headers={
                "User-Agent": _UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9,ru;q=0.8,uz;q=0.7",
            },
        )
        if r.status_code != 200:
            return None
    except Exception as e:
        print(f"[WebSearch] URL fetch failed: {e}")
        return None

    html = r.text

    # Try readability-lxml first if installed; otherwise fall back to BS4-strip
    try:
        from readability import Document
        doc = Document(html)
        title = doc.title() or url
        # doc.summary() returns HTML, strip tags
        body_html = doc.summary()
        text = re.sub(r"<[^>]+>", " ", body_html)
    except ImportError:
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style", "noscript", "nav", "footer", "header"]):
                tag.decompose()
            title = (soup.title.string if soup.title else url) or url
            text = soup.get_text("\n")
        except ImportError:
            # Crude fallback — strip tags with regex
            title = re.search(r"<title[^>]*>([^<]+)</title>", html, re.IGNORECASE)
            title = title.group(1) if title else url
            text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.IGNORECASE | re.DOTALL)
            text = re.sub(r"<style[^>]*>.*?</style>",   "", text, flags=re.IGNORECASE | re.DOTALL)
            text = re.sub(r"<[^>]+>", " ", text)

    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    if not text:
        return None
    if len(text) > max_chars:
        text = text[:max_chars] + f"\n\n... (truncated, {len(text)-max_chars} more chars)"
    return f"📄 {title}\n{url}\n\n{text}"


# ── Backend 5: Plain Google scrape (last resort) ──────────────────────────────

def _google_scrape(query: str, max_results: int = 5) -> list[dict]:
    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError:
        return []

    try:
        q = urllib.parse.quote_plus(query)
        url = f"https://www.google.com/search?q={q}&hl=en&num={max_results}"
        r = requests.get(url, timeout=6, headers={"User-Agent": _UA})
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        results: list[dict] = []
        for g in soup.select("div.g, div.tF2Cxc")[:max_results]:
            title_el = g.select_one("h3")
            link_el  = g.select_one("a")
            snip_el  = g.select_one("div.VwiC3b, span.aCOpRe")
            if not title_el or not link_el:
                continue
            href = link_el.get("href", "")
            if href.startswith("/url?q="):
                href = urllib.parse.unquote(href.split("/url?q=")[1].split("&")[0])
            results.append({
                "title":   title_el.get_text(strip=True),
                "url":     href,
                "snippet": snip_el.get_text(" ", strip=True) if snip_el else "",
            })
        return results
    except Exception as e:
        print(f"[WebSearch] Google scrape failed: {e}")
        return []


# ── Compare (Gemini grounded) ─────────────────────────────────────────────────

def _compare(items: list[str], aspect: str) -> str:
    query = (
        f"Compare {', '.join(items)} in terms of {aspect}. "
        "Give specific facts, numbers, and concrete differences."
    )
    try:
        return _gemini_search(query)
    except Exception as e:
        print(f"[WebSearch] ⚠️ Gemini compare failed: {e} — falling back to DDG")

    all_results: dict[str, list] = {}
    for item in items:
        try:
            all_results[item] = _ddg_search(f"{item} {aspect}", max_results=3)
        except Exception:
            all_results[item] = []

    lines = [f"Comparison — {aspect.upper()}", "─" * 40]
    for item in items:
        lines.append(f"\n▸ {item}")
        for r in all_results.get(item, [])[:2]:
            if r.get("snippet"):
                lines.append(f"  • {r['snippet']}")
    return "\n".join(lines)


# ── Heuristics ────────────────────────────────────────────────────────────────

_WIKI_TRIGGERS = re.compile(
    r"\b(kim|nima|when was|who is|what is|define|biography|biografiya|tarjimai hol|kimligi|nimaligi)\b",
    re.IGNORECASE,
)

def _looks_definitional(query: str) -> bool:
    """Cheap heuristic: does this query look like 'what is X' / 'kim u' / 'biography of Y'?"""
    return bool(_WIKI_TRIGGERS.search(query))


def _looks_like_url(text: str) -> bool:
    return bool(re.match(r"https?://", text.strip()))


# ── Backend 6: GPT-4o search-preview ─────────────────────────────────────────

def _gpt4o_search(query: str) -> str | None:
    """OpenAI gpt-4o-search-preview — has built-in web browsing."""
    try:
        from actions.openai_client import get_client, available
        if not available():
            return None
        client = get_client()
        resp = client.chat.completions.create(
            model="gpt-4o-search-preview",
            messages=[{"role": "user", "content": query}],
        )
        text = (resp.choices[0].message.content or "").strip()
        return text if len(text) > 30 else None
    except Exception as e:
        print(f"[WebSearch] ⚠️ GPT-4o search failed: {e}")
        return None


# ── Main entry ────────────────────────────────────────────────────────────────

def web_search(
    parameters:     dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params = parameters or {}
    query  = (params.get("query") or "").strip()
    mode   = (params.get("mode")  or "search").lower().strip()
    items  = params.get("items", [])
    aspect = (params.get("aspect") or "general").strip() or "general"
    url    = (params.get("url")    or "").strip()

    if not query and not items and not url:
        return "Please provide a search query, sir."

    if items and mode != "compare":
        mode = "compare"
    if url and mode != "url":
        mode = "url"

    if player:
        player.write_log(f"[Search] {mode}: {url or query or ', '.join(items)}")

    print(f"[WebSearch] 🔍 mode={mode}  query={query!r}")

    # ── URL mode: just fetch and extract ──────────────────────────────────
    if mode == "url" and url:
        result = _fetch_url(url)
        if result:
            return result
        return f"Couldn't fetch URL: {url}"

    # ── Compare mode ──────────────────────────────────────────────────────
    if mode == "compare" and items:
        print(f"[WebSearch] 📊 Comparing: {items}")
        return _compare(items, aspect)

    # ── News mode: nudge Gemini toward fresh results ──────────────────────
    if mode == "news":
        query = f"latest news {query}"

    # ── 1. Wikipedia for definitional queries ─────────────────────────────
    if _looks_definitional(query):
        print("[WebSearch] 📚 Trying Wikipedia...")
        wiki = _wikipedia_summary(query)
        if wiki:
            print("[WebSearch] ✅ Wikipedia hit.")
            return wiki

    # ── 2. Gemini google_search ───────────────────────────────────────────
    print("[WebSearch] 🌐 Trying Gemini google_search...")
    try:
        result = _gemini_search(query)
        print("[WebSearch] ✅ Gemini OK.")
        return result
    except Exception as e:
        print(f"[WebSearch] ⚠️ Gemini failed: {e}")

    # ── 3. DuckDuckGo ─────────────────────────────────────────────────────
    print("[WebSearch] 🦆 Trying DuckDuckGo...")
    ddg_results = _ddg_search(query)
    if ddg_results:
        print(f"[WebSearch] ✅ DDG: {len(ddg_results)} results.")
        return _format_ddg(query, ddg_results)

    # ── 4. Plain Google scrape (last resort) ──────────────────────────────
    print("[WebSearch] 🔎 Trying Google scrape...")
    google_results = _google_scrape(query)
    if google_results:
        print(f"[WebSearch] ✅ Google scrape: {len(google_results)} results.")
        return _format_ddg(query, google_results)

    # ── 5. Final fallback: Wikipedia even without trigger ─────────────────
    print("[WebSearch] 📚 Last-resort Wikipedia...")
    wiki = _wikipedia_summary(query)
    if wiki:
        return wiki

    # ── 6. GPT-4o search-preview ──────────────────────────────────────────
    print("[WebSearch] 🤖 Trying GPT-4o search-preview...")
    gpt_result = _gpt4o_search(query)
    if gpt_result:
        print("[WebSearch] ✅ GPT-4o search OK.")
        return gpt_result

    return (
        f"Hech bir manbada '{query}' bo'yicha ma'lumot topa olmadim, sir. "
        f"Internet ulanishini tekshiring yoki so'rovni boshqacharoq qilib qaytaring."
    )
