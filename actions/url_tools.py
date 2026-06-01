"""url_tools.py — URL shortener, expander, and checker.

Inspired by: swapagarwal/JARVIS-on-Messenger (URL shorten/expand), BolisettySujith/J.A.R.V.I.S

APIs: is.gd (free, no key), tinyurl.com (free, no key)
"""
import json
import urllib.parse
import urllib.request


def _shorten_isgd(url: str) -> str:
    api = f"https://is.gd/create.php?format=json&url={urllib.parse.quote(url)}"
    req = urllib.request.Request(api, headers={"User-Agent": "JarvisAI/1.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        d = json.loads(r.read())
    short = d.get("shorturl", "")
    if not short:
        raise ValueError(d.get("errormessage", "is.gd xatosi"))
    return short


def _shorten_tinyurl(url: str) -> str:
    api = f"https://tinyurl.com/api-create.php?url={urllib.parse.quote(url)}"
    req = urllib.request.Request(api, headers={"User-Agent": "JarvisAI/1.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.read().decode().strip()


def _expand(url: str) -> str:
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "JarvisAI/1.0"})
    req.get_method = lambda: "HEAD"
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.url


def _check(url: str) -> tuple[int, str]:
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "JarvisAI/1.0"})
        req.get_method = lambda: "HEAD"
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.status, r.url
    except urllib.error.HTTPError as e:
        return e.code, url
    except Exception as e:
        return 0, str(e)


def url_tools(parameters=None, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    action = (params.get("action") or "shorten").lower().strip()
    url    = (params.get("url") or "").strip()

    if not url and action not in ("help",):
        return "URL manzilini kiriting (url parametri)."

    # Normalize URL
    if url and not url.startswith(("http://", "https://")):
        url = "https://" + url

    if action in ("shorten", "qisqar", "kichkina"):
        try:
            short = _shorten_isgd(url)
            return f"🔗 Qisqartirildi:\n  Asl: {url}\n  Qisqa: **{short}**"
        except Exception:
            pass
        try:
            short = _shorten_tinyurl(url)
            return f"🔗 Qisqartirildi (TinyURL):\n  Asl: {url}\n  Qisqa: **{short}**"
        except Exception as e:
            return f"URL qisqartirishda xato: {e}"

    if action in ("expand", "ochiq", "uzun"):
        try:
            long_url = _expand(url)
            if long_url == url:
                return f"ℹ️ '{url}' allaqachon to'liq URL."
            return f"🔓 Kengaytirildi:\n  Qisqa: {url}\n  To'liq: **{long_url}**"
        except Exception as e:
            return f"URL kengaytirishda xato: {e}"

    if action in ("check", "tekshir", "status"):
        code, final = _check(url)
        emoji = "✅" if 200 <= code < 300 else "⚠️" if 300 <= code < 400 else "❌"
        status_text = {
            200: "OK", 201: "Created", 301: "Moved Permanently",
            302: "Found (Redirect)", 403: "Forbidden", 404: "Not Found",
            500: "Server Error", 503: "Service Unavailable",
        }.get(code, f"HTTP {code}")
        return f"{emoji} **{url}**\n  Status: {code} — {status_text}\n  Final URL: {final}"

    return "Noma'lum amal. shorten|expand|check"
