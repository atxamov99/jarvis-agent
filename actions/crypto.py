"""crypto.py — Real-time cryptocurrency prices.

Inspired by: sukeesh/Jarvis (stock/crypto), thevickypedia/Jarvis (Robinhood tracking)

API: CoinGecko API v3 — completely free, no key required.
"""
import json
import urllib.parse
import urllib.request

_BASE = "https://api.coingecko.com/api/v3"

_ALIASES = {
    "bitcoin": "bitcoin", "btc": "bitcoin",
    "ethereum": "ethereum", "eth": "ethereum",
    "tether": "tether", "usdt": "tether",
    "bnb": "binancecoin", "binance": "binancecoin",
    "solana": "solana", "sol": "solana",
    "xrp": "ripple", "ripple": "ripple",
    "usdc": "usd-coin",
    "cardano": "cardano", "ada": "cardano",
    "dogecoin": "dogecoin", "doge": "dogecoin",
    "polkadot": "polkadot", "dot": "polkadot",
    "tron": "tron", "trx": "tron",
    "litecoin": "litecoin", "ltc": "litecoin",
    "avalanche": "avalanche-2", "avax": "avalanche-2",
    "chainlink": "chainlink", "link": "chainlink",
    "polygon": "matic-network", "matic": "matic-network",
    "shiba": "shiba-inu", "shib": "shiba-inu",
    "ton": "the-open-network",
    "near": "near",
    "atom": "cosmos", "cosmos": "cosmos",
}

def _get(path: str, params: dict = {}) -> dict | list | None:
    qs = "?" + urllib.parse.urlencode(params) if params else ""
    url = f"{_BASE}{path}{qs}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "JarvisAI/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"error": str(e)}


def _fmt_price(p: float) -> str:
    if p >= 1:
        return f"${p:,.2f}"
    elif p >= 0.001:
        return f"${p:.6f}"
    else:
        return f"${p:.8f}"


def crypto(parameters=None, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    action = (params.get("action") or "price").lower().strip()
    coin   = (params.get("coin") or params.get("symbol") or "bitcoin").lower().strip()
    vs     = (params.get("currency") or "usd").lower().strip()

    coin_id = _ALIASES.get(coin, coin.replace(" ", "-"))

    if action in ("price", "narx", "qancha"):
        data = _get("/simple/price", {
            "ids": coin_id,
            "vs_currencies": vs,
            "include_24hr_change": "true",
            "include_market_cap": "true",
        })
        if not data or "error" in data or coin_id not in data:
            return f"'{coin}' kriptovalyutasi topilmadi."
        d       = data[coin_id]
        price   = d.get(vs, 0)
        change  = d.get(f"{vs}_24h_change", 0)
        mcap    = d.get(f"{vs}_market_cap", 0)
        arrow   = "📈" if change >= 0 else "📉"
        return (
            f"💰 **{coin.upper()}** narxi:\n"
            f"  Joriy narx: {_fmt_price(price)}\n"
            f"  24s o'zgarish: {arrow} {change:+.2f}%\n"
            f"  Bozor kapitali: ${mcap:,.0f}"
        )

    if action in ("top", "eng_yaxshi", "rating"):
        n    = min(int(params.get("limit", 10)), 25)
        data = _get("/coins/markets", {
            "vs_currency": vs,
            "order": "market_cap_desc",
            "per_page": n,
            "page": 1,
            "sparkline": "false",
        })
        if not data or "error" in data:
            return "Top kriptovalyutalar ro'yxatini olishda xato."
        lines = [f"🏆 **Top {n} kriptovalyuta** ({vs.upper()}):\n"]
        for i, c in enumerate(data, 1):
            chg   = c.get("price_change_percentage_24h", 0) or 0
            arrow = "📈" if chg >= 0 else "📉"
            lines.append(f"{i:2}. {c['symbol'].upper():6} {_fmt_price(c['current_price']):>12}  {arrow} {chg:+.1f}%  — {c['name']}")
        return "\n".join(lines)

    if action in ("search", "qidir"):
        data = _get(f"/search", {"query": coin})
        if not data or "error" in data:
            return "Qidiruv xatosi."
        coins = data.get("coins", [])[:5]
        if not coins:
            return f"'{coin}' topilmadi."
        lines = [f"🔍 '{coin}' uchun natijalar:"]
        for c in coins:
            lines.append(f"  • {c['symbol'].upper()} — {c['name']} (id: {c['id']})")
        return "\n".join(lines)

    return f"Noma'lum amal: {action}. price|top|search"
