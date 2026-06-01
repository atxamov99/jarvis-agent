"""research.py — Deep Research Agent (Perplexity-style).

Given a question, JARVIS autonomously:
  1. plans several focused sub-queries (Gemini),
  2. runs multiple web searches (DuckDuckGo),
  3. reads the top source pages (readable extraction),
  4. synthesizes ONE comprehensive Uzbek answer with inline [n] citations
     and a sources list.

Reuses web_search's DDG + URL-fetch; synthesizes with gemini-2.5-flash-lite.
"""
import json
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from actions.web_search import _ddg_search, _fetch_url

_BASE  = Path(__file__).resolve().parent.parent
_API   = _BASE / "config" / "api_keys.json"
_MODEL = "gemini-2.5-flash-lite"


def _api_key() -> str:
    try:
        return json.loads(_API.read_text(encoding="utf-8")).get("gemini_api_key", "").strip()
    except Exception:
        return ""


def _gemini(prompt: str, api_key: str, max_tokens: int = 1400) -> str:
    import core.gemini_rest as _gr
    out = _gr.generate_text(prompt, max_tokens=max_tokens, temperature=0.3, timeout=40)
    if not out:
        raise RuntimeError("Gemini javob bermadi (kvota/tarmoq)")
    return out


def _plan(question: str, api_key: str) -> list:
    """Break the question into 3-4 focused web-search queries."""
    prompt = (
        "Quyidagi savolga chuqur javob topish uchun 3-4 ta ANIQ, SPESIFIK veb-qidiruv so'rovini yoz "
        "(ingliz tilida). Aniq nomlar/atamalardan foydalan; 'best', 'top' kabi umumiy so'zlardan "
        "qoch (brendlar bilan chalkashadi). Masalan 'best framework' o'rniga 'Django vs FastAPI "
        "performance benchmark'. FAQAT JSON massiv qaytar: [\"query 1\", \"query 2\", ...]\n\n"
        f"Savol: {question}"
    )
    try:
        raw = _gemini(prompt, api_key, max_tokens=200)
        m = re.search(r"\[.*\]", raw, re.DOTALL)
        if m:
            qs = json.loads(m.group(0))
            qs = [q.strip() for q in qs if isinstance(q, str) and q.strip()]
            if qs:
                return qs[:4]
    except Exception:
        pass
    return [question]


def _gather_urls(queries: list, limit: int) -> list:
    """Search each sub-query (max 3 each) and interleave for source diversity,
    so a single off-topic query cannot fill every slot."""
    import time
    per_query = []
    for q in queries:
        urls = []
        for r in _ddg_search(q, max_results=4):
            u = r.get("url", "")
            if u and u.startswith("http"):
                urls.append({"url": u, "title": r.get("title", ""), "snippet": r.get("snippet", "")})
        per_query.append(urls[:3])
        time.sleep(0.4)   # be gentle with DuckDuckGo
    seen, out = set(), []
    for rank in range(3):
        for urls in per_query:
            if rank < len(urls) and urls[rank]["url"] not in seen:
                seen.add(urls[rank]["url"])
                out.append(urls[rank])
                if len(out) >= limit:
                    return out
    return out


def research(parameters=None, response=None, player=None, session_memory=None) -> str:
    params   = parameters or {}
    question = (params.get("query") or params.get("question") or params.get("topic") or "").strip()
    if not question:
        return "Tadqiqot savolini ayting (query=...)."

    depth = (params.get("depth") or "normal").lower().strip()
    n_sources = {"quick": 3, "normal": 5, "deep": 8}.get(depth, 5)

    api_key = _api_key()
    if not api_key:
        return "Gemini API kaliti topilmadi."

    def log(msg):
        print(f"[Research] {msg}")
        if player:
            try: player.write_log(f"🔬 {msg}")
            except Exception: pass

    log(f"Tadqiqot boshlandi: {question}")

    # 1) Plan sub-queries
    queries = _plan(question, api_key)
    log(f"{len(queries)} ta qidiruv yo'nalishi: {', '.join(queries)}")

    # 2) Search → collect URLs
    sources = _gather_urls(queries, n_sources + 3)
    if not sources:
        return "Internetdan manba topilmadi (qidiruv ishlamadi yoki internet yo'q)."
    sources = sources[:n_sources + 3]
    log(f"{len(sources)} ta manba topildi, o'qilmoqda...")

    # 3) Fetch source pages in parallel
    def _read(src):
        txt = _fetch_url(src["url"], max_chars=4000)
        return {**src, "text": txt or src.get("snippet", "")}

    with ThreadPoolExecutor(max_workers=6) as ex:
        read = list(ex.map(_read, sources))
    read = [r for r in read if r.get("text")][:n_sources]
    if not read:
        return "Manbalar topildi, lekin matn o'qib bo'lmadi."

    # 4) Build numbered context
    blocks, used = [], []
    for i, r in enumerate(read, 1):
        blocks.append(f"[{i}] {r['title']}\nURL: {r['url']}\n{r['text'][:3500]}")
        used.append((i, r['title'], r['url']))
    context = "\n\n".join(blocks)
    log(f"{len(read)} ta manba o'qildi, xulosa tayyorlanmoqda...")

    # 5) Synthesize a cited Uzbek answer
    prompt = (
        "Sen tadqiqot yordamchisisan. Quyidagi MANBALAR asosida savolga O'ZBEK TILIDA "
        "to'liq, aniq va tartibli javob yoz. Muhim faktlardan keyin [raqam] bilan manbaga "
        "havola qil. Faqat manbalardagi ma'lumotga tayan; qarama-qarshilik bo'lsa ayt. "
        "Oxirida qisqa xulosa qil.\n\n"
        f"=== SAVOL ===\n{question}\n\n=== MANBALAR ===\n{context}"
    )
    try:
        answer = _gemini(prompt, api_key, max_tokens=1600)
    except Exception as e:
        return f"Xulosa tayyorlashda xato: {e}"

    src_list = "\n".join(f"  [{i}] {title[:70]} — {url}" for i, title, url in used)
    log("Tadqiqot tayyor ✅")
    return f"{answer}\n\n📚 Manbalar:\n{src_list}"
