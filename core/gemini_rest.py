"""gemini_rest.py — Resilient Gemini generateContent calls (retry + model fallback).

Centralizes the REST call every vision/text helper duplicates, and makes it
quota-proof: on 429 (quota) it falls through a chain of models; on 503/overload
or transient network errors it retries with backoff. Returns "" on total failure
(callers already treat empty as "no result").
"""
import json
import time
import urllib.request
import urllib.error
from pathlib import Path

_API = Path(__file__).resolve().parent.parent / "config" / "api_keys.json"

# Tried in order; first with quota wins. gemini-2.0-flash is last (often exhausted).
_MODEL_CHAIN = ["gemini-2.5-flash-lite", "gemini-flash-lite-latest", "gemini-2.0-flash"]


def _key() -> str:
    try:
        return json.loads(_API.read_text(encoding="utf-8")).get("gemini_api_key", "").strip()
    except Exception:
        return ""


def generate(parts: list, max_tokens: int = 800, temperature: float = 0.2,
             models: list | None = None, timeout: int = 30, retries: int = 1) -> str:
    """parts: list of {"text":...} / {"inline_data":...} content parts.
    Returns the model's text, or "" if every model+retry failed."""
    api_key = _key()
    if not api_key:
        return ""
    chain = models or _MODEL_CHAIN
    body = json.dumps({
        "contents": [{"parts": parts}],
        "generationConfig": {"maxOutputTokens": max_tokens, "temperature": temperature},
    }).encode()

    for model in chain:
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{model}:generateContent?key={api_key}")
        for attempt in range(retries + 1):
            try:
                req = urllib.request.Request(
                    url, data=body, headers={"Content-Type": "application/json"}, method="POST")
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    data = json.loads(r.read())
                return data["candidates"][0]["content"]["parts"][0]["text"].strip()
            except urllib.error.HTTPError as e:
                code = e.code
                if code == 429:
                    # Per-minute rate limit — wait briefly and retry the SAME
                    # model once (RPM windows reset fast). Only jump to the next
                    # model if it persists. This keeps long agent loops (many
                    # vision calls/min) from dying on a transient RPM spike.
                    if attempt < retries:
                        time.sleep(2.5 * (attempt + 1))
                        continue
                    break          # persistent quota — next model
                if code in (500, 503, 529) and attempt < retries:
                    time.sleep(0.8 * (attempt + 1))
                    continue       # transient overload — retry same model
                break              # other 4xx — try next model
            except Exception:
                if attempt < retries:
                    time.sleep(0.8 * (attempt + 1))
                    continue
                break
    return ""


def generate_text(prompt: str, **kw) -> str:
    """Convenience for text-only prompts."""
    return generate([{"text": prompt}], **kw)
