"""currency.py — Real-time currency conversion via frankfurter.app (no API key)."""
import json
import time
import urllib.request
from urllib.parse import urlencode

_CACHE: dict = {"rates": {}, "base": "", "ts": 0.0}
_TTL = 3600  # 1 hour cache


def _get_rates(base: str = "USD") -> dict:
    now = time.time()
    if _CACHE["base"] == base and now - _CACHE["ts"] < _TTL and _CACHE["rates"]:
        return _CACHE["rates"]
    # open.er-api.com — free, no key, includes UZS + RUB
    url  = f"https://open.er-api.com/v6/latest/{base.upper()}"
    req  = urllib.request.Request(url, headers={"User-Agent": "JarvisCurrency/1.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.loads(r.read())
    if data.get("result") != "success":
        raise ValueError(data.get("error-type", "API xatosi"))
    rates = data.get("rates", {})
    rates[base.upper()] = 1.0
    _CACHE.update({"rates": rates, "base": base.upper(), "ts": now})
    return rates


# Common aliases
_ALIASES = {
    "dollar": "USD", "usd": "USD", "dollar": "USD",
    "euro": "EUR", "evro": "EUR", "eur": "EUR",
    "rubl": "RUB", "ruble": "RUB", "rub": "RUB",
    "som": "UZS", "uzs": "UZS", "so'm": "UZS", "soum": "UZS",
    "funt": "GBP", "pound": "GBP", "gbp": "GBP",
    "yen": "JPY", "iena": "JPY", "jpy": "JPY",
    "yuan": "CNY", "cny": "CNY", "xitoy": "CNY",
    "lira": "TRY", "turk": "TRY", "try": "TRY",
    "tenge": "KZT", "qozoq": "KZT", "kzt": "KZT",
    "tolar": "AED", "dirham": "AED", "aed": "AED",
    "won": "KRW", "koreys": "KRW",
}


def _resolve(code: str) -> str:
    c = code.strip().lower()
    return _ALIASES.get(c, code.strip().upper())


def currency(parameters=None, response=None, player=None, session_memory=None) -> str:
    params   = parameters or {}
    action   = (params.get("action") or "convert").lower().strip()
    amount   = float(params.get("amount", 1))
    from_cur = _resolve(params.get("from") or params.get("from_currency") or "USD")
    to_cur   = _resolve(params.get("to")   or params.get("to_currency")   or "UZS")

    # ── CONVERT ───────────────────────────────────────────────────────────────
    if action in ("convert", "aylantir", "qancha", "hisob"):
        try:
            rates = _get_rates(from_cur)
        except Exception as e:
            return f"Valyuta ma'lumotlarini olishda xato: {e}"

        if to_cur not in rates:
            return f"'{to_cur}' valyuta kodi topilmadi."

        result = amount * rates[to_cur]
        if result >= 1000:
            result_str = f"{result:,.0f}"
        else:
            result_str = f"{result:.4g}"

        if player: player.write_log(f"[Currency] {amount} {from_cur} = {result_str} {to_cur}")
        return f"{amount:g} {from_cur} = {result_str} {to_cur}"

    # ── RATES ─────────────────────────────────────────────────────────────────
    if action in ("rates", "kurslar", "list"):
        base = _resolve(params.get("base") or "USD")
        show = [c.upper() for c in (params.get("currencies") or
                "EUR,RUB,UZS,GBP,JPY,CNY,TRY,KZT,AED").split(",")]
        try:
            rates = _get_rates(base)
        except Exception as e:
            return f"Xato: {e}"
        lines = [f"1 {base} ="]
        for code in show:
            if code in rates:
                r = rates[code]
                lines.append(f"  {r:>12,.2f} {code}" if r >= 100 else f"  {r:>8.4g} {code}")
        return "\n".join(lines)

    return "Amallar: convert | rates"
