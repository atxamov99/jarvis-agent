"""stocks.py — Real-time stock prices via yfinance (Yahoo Finance wrapper).

pip install yfinance  (already in requirements or install manually)
"""

_ALIASES: dict[str, str] = {
    "apple": "AAPL", "aapl": "AAPL",
    "microsoft": "MSFT", "msft": "MSFT",
    "google": "GOOGL", "alphabet": "GOOGL", "googl": "GOOGL",
    "amazon": "AMZN", "amzn": "AMZN",
    "tesla": "TSLA", "tsla": "TSLA",
    "meta": "META", "facebook": "META",
    "nvidia": "NVDA", "nvda": "NVDA",
    "netflix": "NFLX", "nflx": "NFLX",
    "samsung": "005930.KS",
    "alibaba": "BABA", "baba": "BABA",
    "berkshire": "BRK-B",
    "sp500": "^GSPC", "s&p500": "^GSPC", "s&p": "^GSPC", "sp": "^GSPC",
    "nasdaq": "^IXIC",
    "dow": "^DJI", "dow jones": "^DJI",
    "gold": "GC=F", "oltin": "GC=F",
    "silver": "SI=F", "kumush": "SI=F",
    "oil": "CL=F", "neft": "CL=F", "crude": "CL=F",
    "bitcoin": "BTC-USD", "btc": "BTC-USD",
    "ethereum": "ETH-USD", "eth": "ETH-USD",
}

_TOP_SYMBOLS = ["AAPL","MSFT","GOOGL","AMZN","NVDA","META","TSLA","BRK-B","AVGO","JPM"]


def _resolve(s: str) -> str:
    return _ALIASES.get(s.lower().strip(), s.upper().strip())


def _fmt_number(n) -> str:
    if n is None:
        return "N/A"
    if abs(n) >= 1e12:
        return f"${n/1e12:.2f}T"
    if abs(n) >= 1e9:
        return f"${n/1e9:.2f}B"
    if abs(n) >= 1e6:
        return f"${n/1e6:.2f}M"
    return f"${n:,.2f}"


def _get_quote(symbol: str) -> dict:
    import yfinance as yf
    ticker = yf.Ticker(symbol)
    fi = ticker.fast_info
    hist = ticker.history(period="2d")

    price = getattr(fi, "last_price", None)
    prev  = getattr(fi, "previous_close", None)

    change = None
    change_pct = None
    if price is not None and prev is not None and prev != 0:
        change     = price - prev
        change_pct = (change / prev) * 100

    high = getattr(fi, "day_high", None)
    low  = getattr(fi, "day_low", None)
    cap  = getattr(fi, "market_cap", None)
    vol  = getattr(fi, "three_month_average_volume", None)
    currency = getattr(fi, "currency", "USD")

    name = symbol
    try:
        info = ticker.info
        name = info.get("shortName") or info.get("longName") or symbol
    except Exception:
        pass

    return {
        "symbol": symbol, "name": name,
        "price": price, "prev": prev,
        "change": change, "change_pct": change_pct,
        "high": high, "low": low,
        "market_cap": cap, "volume": vol,
        "currency": currency,
    }


def _fmt_quote(q: dict) -> str:
    lines = [f"📈 **{q['name']}** ({q['symbol']})"]

    price = q["price"]
    cur   = q.get("currency", "USD")
    if price is not None:
        lines.append(f"  Narx: {price:,.2f} {cur}")

    cp = q.get("change_pct")
    if cp is not None:
        arrow = "📈" if cp >= 0 else "📉"
        lines.append(f"  24s o'zgarish: {arrow} {cp:+.2f}%  ({q['change']:+.2f})")

    if q.get("high"):
        lines.append(f"  Kun: {q['low']:,.2f} – {q['high']:,.2f}")
    if q.get("market_cap"):
        lines.append(f"  Bozor kap.: {_fmt_number(q['market_cap'])}")

    return "\n".join(lines)


def stocks(parameters=None, response=None, player=None, session_memory=None) -> str:
    try:
        import yfinance  # noqa: F401
    except ImportError:
        return "yfinance kutubxonasi kerak: pip install yfinance"

    params  = parameters or {}
    action  = (params.get("action") or "price").lower().strip()
    symbol  = (params.get("symbol") or params.get("ticker") or params.get("stock") or "").strip()
    symbols_raw = (params.get("symbols") or "").strip()

    # ── BATCH ─────────────────────────────────────────────────────────────────
    if symbols_raw:
        syms = [_resolve(s.strip()) for s in symbols_raw.split(",") if s.strip()]
        results = []
        for sym in syms[:6]:
            try:
                results.append(_fmt_quote(_get_quote(sym)))
            except Exception as e:
                results.append(f"{sym}: xato — {e}")
        return "\n\n".join(results)

    # ── TOP ───────────────────────────────────────────────────────────────────
    if action in ("top", "best", "popular"):
        results = []
        for sym in _TOP_SYMBOLS[:5]:
            try:
                results.append(_fmt_quote(_get_quote(sym)))
            except Exception as e:
                results.append(f"{sym}: xato — {e}")
        return "\n\n".join(results)

    # ── SINGLE PRICE ──────────────────────────────────────────────────────────
    if not symbol:
        symbol = "AAPL"
    symbol = _resolve(symbol)

    try:
        q = _get_quote(symbol)
        if player:
            player.write_log(f"[Stocks] {symbol} = {q['price']}")
        return _fmt_quote(q)
    except Exception as e:
        return f"'{symbol}' aksiya ma'lumotini olishda xato: {e}"
