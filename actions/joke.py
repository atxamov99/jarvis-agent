"""joke.py — Jokes, facts, quotes, coin flip, dice roll, activity suggestions.

Inspired by: sukeesh/Jarvis, swapagarwal/JARVIS-on-Messenger, kishanrajput23/Jarvis-Desktop-Voice-Assistant

APIs used (all free, no key):
- icanhazdadjoke.com — dad jokes
- api.quotable.io — inspirational quotes
- uselessfacts.jsph.pl — random facts
- www.boredapi.com — activity suggestions when bored
- Official-Joke-API — programming jokes
"""
import json
import random
import urllib.request


def _get(url: str) -> dict | None:
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "JarvisAI/1.0",
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.loads(r.read())
    except Exception:
        return None


def _dad_joke() -> str:
    d = _get("https://icanhazdadjoke.com/")
    return d.get("joke", "") if d else ""


def _random_joke() -> str:
    d = _get("https://official-joke-api.appspot.com/random_joke")
    if d:
        return f"{d.get('setup', '')} — {d.get('punchline', '')}"
    return ""


def _quote() -> str:
    d = _get("https://api.quotable.io/random")
    if d:
        return f'"{d.get("content", "")}" — {d.get("author", "")}'
    # Fallback offline quotes
    quotes = [
        '"The only way to do great work is to love what you do." — Steve Jobs',
        '"In the middle of every difficulty lies opportunity." — Albert Einstein',
        '"It always seems impossible until it\'s done." — Nelson Mandela',
        '"The future belongs to those who believe in the beauty of their dreams." — Eleanor Roosevelt',
        '"Success is not final, failure is not fatal: It is the courage to continue that counts." — Winston Churchill',
        '"Be yourself; everyone else is already taken." — Oscar Wilde',
        '"Two things are infinite: the universe and human stupidity; and I\'m not sure about the universe." — Albert Einstein',
        '"Life is what happens when you\'re busy making other plans." — John Lennon',
    ]
    return random.choice(quotes)


def _fact() -> str:
    d = _get("https://uselessfacts.jsph.pl/api/v2/facts/random?language=en")
    if d:
        return d.get("text", "")
    # Fallback facts
    facts = [
        "Honey never spoils. Archaeologists have found 3,000-year-old honey in Egyptian tombs.",
        "A day on Venus is longer than a year on Venus.",
        "Octopuses have three hearts and blue blood.",
        "The shortest war in history lasted 38 to 45 minutes.",
        "Bananas are berries, but strawberries are not.",
        "The average person walks about 100,000 miles in their lifetime.",
        "Water can boil and freeze at the same time (called the triple point).",
        "A group of flamingos is called a 'flamboyance'.",
    ]
    return random.choice(facts)


def _bored_activity() -> str:
    d = _get("https://bored.api.lewagon.com/api/activity")
    if d:
        activity = d.get("activity", "")
        typ = d.get("type", "")
        participants = d.get("participants", 1)
        return f"🎯 Tavsiya: {activity} (tur: {typ}, ishtirokchilar: {participants})"
    # Fallback activities
    activities = [
        "📚 Yangi kitob o'qing",
        "🧘 10 daqiqa meditatsiya qiling",
        "🎨 Biror narsa chizing yoki bo'yang",
        "🚶 Tashqarida 20 daqiqa yuring",
        "🎵 Yangi musiqa eshiting",
        "🍳 Yangi taom pishirishni sinab ko'ring",
        "📝 Bugungi kun uchun 3 ta maqsad yozing",
        "📹 Yangi ko'nikma haqida video ko'ring",
        "🧩 Jumboq yoki o'yin o'ynang",
        "✉️ Yaqin do'stingizga xabar yuboring",
    ]
    return random.choice(activities)


def _coin_flip() -> str:
    result = random.choice(["BOSH", "DUMBA"])
    emoji  = "🪙 Bosh" if result == "BOSH" else "🪙 Dumba"
    return f"{emoji}! Tanga {result} tushdi."


def _dice_roll(sides: int = 6, count: int = 1) -> str:
    rolls = [random.randint(1, sides) for _ in range(count)]
    total = sum(rolls)
    if count == 1:
        return f"🎲 {sides} qirrali zar: **{rolls[0]}**"
    return f"🎲 {count}×d{sides}: {rolls} → Jami: {total}"


def _random_number(lo: int, hi: int) -> str:
    n = random.randint(lo, hi)
    return f"🎯 {lo}–{hi} oralig'idan tasodifiy son: **{n}**"


def joke(parameters=None, response=None, player=None, session_memory=None) -> str:
    params  = parameters or {}
    action  = (params.get("action") or "joke").lower().strip()
    sides   = int(params.get("sides", 6))
    count   = min(int(params.get("count", 1)), 10)
    lo      = int(params.get("min", 1))
    hi      = int(params.get("max", 100))

    if action in ("joke", "hazil", "latifa"):
        result = _dad_joke() or _random_joke()
        return f"😄 {result}" if result else "Hazil topilmadi."

    if action in ("fact", "fakt", "bilim", "qizig'ich"):
        result = _fact()
        return f"💡 {result}" if result else "Fakt topilmadi."

    if action in ("quote", "sitata", "iqtibos", "ilhom"):
        return f"✨ {_quote()}"

    if action in ("bored", "zerikdim", "nima_qilsam", "tavsiya"):
        return _bored_activity()

    if action in ("coin", "tanga", "coin_flip"):
        return _coin_flip()

    if action in ("dice", "zar", "kubik"):
        return _dice_roll(sides, count)

    if action in ("random", "tasodifiy", "son"):
        return _random_number(lo, hi)

    if action in ("all", "hammasi"):
        return "\n".join([
            "😄 " + (_dad_joke() or "Hazil yo'q"),
            "💡 " + _fact(),
            "✨ " + _quote(),
        ])

    return f"Noma'lum amal: {action}. joke|fact|quote|bored|coin|dice|random"
