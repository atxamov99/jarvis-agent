"""dictionary.py — Word definitions, synonyms, examples.

Inspired by: GauravSingh9356/J.A.R.V.I.S, sukeesh/Jarvis

API: api.dictionaryapi.dev — completely free, no key required.
"""
import json
import urllib.parse
import urllib.request


def _fetch(word: str) -> list | None:
    url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{urllib.parse.quote(word)}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "JarvisAI/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception:
        return None


def dictionary(parameters=None, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    word   = (params.get("word") or "").strip()
    detail = str(params.get("detail", "false")).lower() == "true"

    if not word:
        return "So'z kiriting (word parametri)."

    data = _fetch(word)
    if not data or (isinstance(data, dict) and "title" in data):
        return f"'{word}' so'zi lug'atda topilmadi."

    entry    = data[0]
    phonetic = entry.get("phonetic", "")
    meanings = entry.get("meanings", [])

    lines = [f"📖 **{word}**" + (f" /{phonetic}/" if phonetic else "")]

    for meaning in meanings[:3 if detail else 2]:
        pos = meaning.get("partOfSpeech", "")
        defs = meaning.get("definitions", [])
        if not defs:
            continue
        lines.append(f"\n**{pos}:**")
        for d in defs[:2 if detail else 1]:
            defn    = d.get("definition", "")
            example = d.get("example", "")
            lines.append(f"  • {defn}")
            if example and detail:
                lines.append(f"    _Misol: {example}_")
        synonyms = meaning.get("synonyms", [])
        if synonyms and detail:
            lines.append(f"  Sinonimlar: {', '.join(synonyms[:5])}")

    return "\n".join(lines)
