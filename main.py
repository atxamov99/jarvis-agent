import warnings
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)

import asyncio
import os
import re
import threading
import json
import sys
import time
import traceback
from pathlib import Path

# Fix Windows terminal encoding so emojis/Cyrillic don't crash
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import numpy as np
import sounddevice as sd
from google import genai
from google.genai import types
from ui import JarvisUI
from memory.memory_manager import (
    load_memory, update_memory, format_memory_for_prompt,
    forget, forget_category, forget_all,
)

from actions.file_processor import file_processor
from actions.flight_finder     import flight_finder
from actions.open_app          import open_app
from actions.weather_report    import weather_action
from actions.send_message      import send_message
from actions.reminder          import reminder
from actions.computer_settings import computer_settings
from actions.screen_processor  import screen_process
from actions.youtube_video     import youtube_video
from actions.desktop           import desktop_control
from actions.browser_control   import browser_control
from actions.file_controller   import file_controller
from actions.code_helper       import code_helper
from actions.dev_agent         import dev_agent
from actions.web_search        import web_search as web_search_action
from actions.computer_control  import computer_control
from actions.game_updater      import game_updater
from actions.translate         import translate as translate_action
from actions.clipboard         import clipboard as clipboard_action
from actions.system_info       import system_info as system_info_action
from actions.close_apps        import close_apps as close_apps_action
from actions.terminal_control  import terminal_control
from actions.music_control     import music_control
from actions.gaming_control    import gaming_control
from actions.clap_detector     import ClapDetector
from actions.notes             import notes as notes_action
from actions.pomodoro          import pomodoro as pomodoro_action
from actions.notifier          import notifier as notifier_action
from actions.password_gen      import password_gen as password_gen_action
from actions.archiver          import archiver as archiver_action
from actions.speedtest         import speedtest as speedtest_action
from actions.wifi_control      import wifi_control as wifi_control_action
from actions.voice_memo        import voice_memo as voice_memo_action
from actions.ocr               import ocr as ocr_action
from actions.calculator        import calculator as calculator_action
from actions.google_calendar   import google_calendar as gcal_action
from actions.summarizer        import summarizer as summarizer_action
from actions.pdf_summarizer    import pdf_summarizer as pdf_action
from actions.chat_history      import chat_history as chat_history_action
from actions.totp              import totp as totp_action
from actions.weather_extended  import weather_extended as weather_ext_action
from actions.ssh_control       import ssh_control as ssh_action
from actions.image_gen         import image_gen as image_gen_action
from actions.macro_recorder    import macro_recorder as macro_action
from actions.home_assistant    import home_assistant as ha_action
from actions.system_monitor    import system_monitor as sysmon_action
from actions.alarm             import alarm as alarm_action
from actions.todo              import todo as todo_action
from actions.currency          import currency as currency_action
from actions.yt_downloader     import yt_downloader as ytdl_action
from actions.screen_recorder   import screen_recorder as screenrec_action
from actions.network_tools     import network_tools as network_action
from actions.hash_tool         import hash_tool as hash_action
from actions.qr_code           import qr_code as qr_action
from actions.focus_mode        import focus_mode as focus_action
from actions.disk_manager      import disk_manager as disk_action
from actions.cron_manager      import cron_manager as cron_action
from actions.voice_auth        import voice_auth as voice_auth_action
from actions.face_auth         import face_auth as face_auth_action
from actions.samsung_tv        import samsung_tv as samsung_tv_action
from actions.type_text         import type_text as type_text_action
from actions.wikipedia         import wikipedia as wikipedia_action
from actions.news              import news as news_action
from actions.dictation         import dictation as dictation_action
from actions.joke              import joke as joke_action
from actions.dictionary        import dictionary as dictionary_action
from actions.timezone          import timezone as timezone_action
from actions.crypto            import crypto as crypto_action
from actions.stocks            import stocks as stocks_action
from actions.health_calc       import health_calc as health_calc_action
from actions.unit_converter    import unit_converter as unit_converter_action
from actions.url_tools         import url_tools as url_tools_action
from actions.lyrics            import lyrics as lyrics_action
from actions.movie             import movie as movie_action
from actions.email_send        import email_send as email_action
from actions.timer             import timer as timer_action
from actions.briefing          import briefing as briefing_action
from actions.contacts          import contacts as contacts_action
from actions.math_solver       import math_solver as math_solver_action
from actions.reddit            import reddit as reddit_action
from actions.emotion           import emotion as emotion_action
from actions.gesture_control   import gesture_control as gesture_action
from actions.webcam_vision     import webcam_vision as webcam_vision_action
from actions.smart_memory      import smart_memory as smart_memory_action
from actions.screen_vision      import screen_vision as screen_vision_action
from actions.screen_click       import screen_click as screen_click_action
from actions.doc_chat           import doc_chat as doc_chat_action
from actions.window_manager     import window_manager as window_manager_action
from actions.auto_agent         import auto_agent as auto_agent_action
from actions.watcher            import watcher as watcher_action
from actions.research           import research as research_action
import actions.time_machine as time_machine
from actions.time_machine        import time_machine as time_machine_action
import core.speaker_verifier as speaker_verifier
import core.face_verifier as face_verifier
import core.stt_context as stt_context

try:
    from actions.wake_word import WakeWordDetector
    _WAKE_WORD_AVAILABLE = True
except ImportError as _wake_err:
    print(f"[JARVIS] ⚠️ Wake-word unavailable: {_wake_err}")
    _WAKE_WORD_AVAILABLE = False


def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


def _register_startup_windows() -> None:
    if sys.platform != "win32":
        return
    try:
        import shutil
        startup_dir = Path(os.environ.get("APPDATA", "")) / \
            "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        if not startup_dir.exists():
            return
        dst = startup_dir / "JARVIS.bat"
        src = Path(__file__).parent / "start.bat"
        if dst.exists():
            return
        if not src.exists():
            return
        shutil.copy2(src, dst)
        print(f"[JARVIS] Auto-startup registered: {dst}")
    except Exception as e:
        print(f"[JARVIS] Could not register startup: {e}")


BASE_DIR        = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"
PROMPT_PATH     = BASE_DIR / "core" / "prompt.txt"
_DEFAULT_LIVE_MODEL = "models/gemini-2.5-flash-native-audio-preview-12-2025"
CHANNELS            = 1
SEND_SAMPLE_RATE    = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE          = 1024


def _load_live_model() -> str:
    """Override LIVE_MODEL via api_keys.json -> 'live_model' key. Lets the user
    swap to a newer/different Gemini Live model without editing code."""
    try:
        with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        m = (cfg.get("live_model") or "").strip()
        return m if m else _DEFAULT_LIVE_MODEL
    except Exception:
        return _DEFAULT_LIVE_MODEL


LIVE_MODEL = _load_live_model()

# Noise gate — filters background noise, knocks, brief transients
# Each frame = CHUNK_SIZE/SEND_SAMPLE_RATE = ~64 ms
_GATE_OPEN_RMS    = 60     # RMS level required to consider audio "active" (raised: reduces false activations)
_GATE_ATTACK      = 4      # frames (~256 ms) above threshold before gate opens (raised: avoids brief transients)
_GATE_HOLD        = 28     # frames (~1.8 s) gate stays open after level drops (lowered: faster response)

def _get_api_key() -> str:
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]

def _get_openai_api_key() -> str:
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        d = json.load(f)
    return d.get("openai_api_key", "")


def _openai_quota_ok() -> bool:
    """Quick TTS probe — confirms billing is active. False on 429/insufficient_quota."""
    key = _get_openai_api_key()
    if not key:
        return False
    try:
        from openai import OpenAI
        client = OpenAI(api_key=key, timeout=10.0)
        client.audio.speech.create(model="tts-1", voice="onyx", input=".", response_format="pcm")
        return True
    except Exception as e:
        msg = str(e).lower()
        if "insufficient_quota" in msg or "429" in msg or "exceeded" in msg:
            print(f"[JARVIS] ⚠️ OpenAI quota exhausted — falling back to Gemini Live")
            return False
        # Any other error: assume OK, will surface during use
        return True

def _to_openai_tools(gemini_tools: list) -> list:
    """Convert Gemini tool declarations to OpenAI function-calling format."""
    def _fix_types(obj):
        if isinstance(obj, dict):
            return {
                k: (_fix_types(v) if k != "type" else (v.lower() if isinstance(v, str) else v))
                for k, v in obj.items()
            }
        if isinstance(obj, list):
            return [_fix_types(i) for i in obj]
        return obj
    result = []
    for t in gemini_tools:
        params = _fix_types(t.get("parameters", {"type": "object", "properties": {}}))
        result.append({
            "type": "function",
            "function": {
                "name":        t["name"],
                "description": t.get("description", ""),
                "parameters":  params,
            }
        })
    return result


def _get_openai_key() -> str | None:
    try:
        with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("openai_api_key") or None
    except Exception:
        return None


def _get_anthropic_key() -> str | None:
    try:
        with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("anthropic_api_key") or None
    except Exception:
        return None


def _get_backend_pref() -> str:
    try:
        with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
            return (json.load(f).get("backend") or "auto").lower().strip()
    except Exception:
        return "auto"


def _to_anthropic_tools(gemini_tools: list) -> list:
    """Convert Gemini tool declarations to Anthropic tool-use format.

    Anthropic uses `input_schema` (JSON Schema, lowercase types) instead of
    Gemini's `parameters` with uppercase OBJECT/STRING types.
    """
    def _fix_types(obj):
        if isinstance(obj, dict):
            return {
                k: (_fix_types(v) if k != "type" else (v.lower() if isinstance(v, str) else v))
                for k, v in obj.items()
            }
        if isinstance(obj, list):
            return [_fix_types(i) for i in obj]
        return obj
    out = []
    for t in gemini_tools:
        schema = _fix_types(t.get("parameters", {"type": "object", "properties": {}}))
        schema.setdefault("type", "object")
        schema.setdefault("properties", {})
        out.append({
            "name":         t["name"],
            "description":  t.get("description", ""),
            "input_schema": schema,
        })
    return out


def _load_system_prompt() -> str:
    try:
        return PROMPT_PATH.read_text(encoding="utf-8")
    except Exception:
        return (
            "You are JARVIS, Tony Stark's AI assistant. "
            "Be concise, direct, and always use the provided tools to complete tasks. "
            "Never simulate or guess results — always call the appropriate tool."
        )

_CTRL_RE = re.compile(r"<ctrl\d+>", re.IGNORECASE)

def _clean_transcript(text: str) -> str:
    text = _CTRL_RE.sub("", text)
    text = re.sub(r"[\x00-\x08\x0b-\x1f]", "", text)
    return text.strip()

def _merge_transcript_fragments(fragments: list[str]) -> str:
    """Join streaming transcript fragments correctly.
    Gemini Live sends cumulative partial transcripts (each fragment is a delta).
    We concatenate without extra spaces, then normalize whitespace."""
    merged = "".join(fragments)
    # Collapse multiple spaces into one
    merged = re.sub(r" {2,}", " ", merged).strip()
    return merged


def _ollama_query(args: dict) -> str:
    """Run a prompt against local Ollama. Returns the response text."""
    try:
        import ollama as _ollama

        prompt  = args.get("prompt", "")
        model   = args.get("model", "").strip()
        context = args.get("context", "").strip()

        if not model:
            try:
                models = _ollama.list().get("models", [])
                model = models[0]["name"] if models else "llama3"
            except Exception:
                model = "llama3"

        full_prompt = f"{context}\n\n{prompt}".strip() if context else prompt

        print(f"[Ollama] model={model}  prompt={full_prompt[:80]}")
        resp = _ollama.generate(model=model, prompt=full_prompt, stream=False)
        answer = resp.get("response", "").strip()
        print(f"[Ollama] → {answer[:120]}")
        return answer or "Ollama returned an empty response."

    except Exception as e:
        return f"Ollama unavailable: {e}. Make sure 'ollama serve' is running."

TOOL_DECLARATIONS = [
    {
        "name": "open_app",
        "description": (
            "Opens any application on the computer. "
            "Use this whenever the user asks to open, launch, or start any app, "
            "website, or program. Always call this tool — never just say you opened it. "
            "MULTIPLE APPS: When the user asks to open more than one app at once "
            "(e.g. 'Telegram va Chrome'ni och', 'open WhatsApp and Spotify'), call this tool "
            "ONCE PER APP in sequence — do not skip any. Never combine multiple apps into a single call."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "app_name": {
                    "type": "STRING",
                    "description": "Exact name of ONE application (e.g. 'WhatsApp', 'Chrome', 'Spotify'). For multiple apps, call this tool multiple times — one call per app."
                }
            },
            "required": ["app_name"]
        }
    },
    {
        "name": "web_search",
        "description": (
            "Search the web for ANY factual question. Uses a multi-backend chain: "
            "Wikipedia (for 'what/who is X' queries) → Gemini google_search → DuckDuckGo → direct Google scrape. "
            "ALWAYS returns something — never gives up. "
            "CALL THIS IMMEDIATELY for: news, prices, current events, weather facts, dates, biographies, "
            "definitions, sports results, currency rates, recipes, addresses, opening hours, "
            "technical/programming questions, product comparisons, ANY 'kim/nima/qachon/qayerda/qancha/qanday/who/what/when/where/why/how' question. "
            "MODES:"
            "  • mode='search' (default) — general web search "
            "  • mode='news'  — recent news (adds 'latest news' to the query) "
            "  • mode='url'   — fetch + extract readable text from a specific URL (use the `url` param) "
            "  • mode='compare' — compare items (use the `items` array + `aspect`) "
            "NEVER say 'I don't know', 'kechirasiz topa olmadim', 'internet yo'q' — JUST CALL THIS TOOL. "
            "After it returns, summarize BRIEFLY in Uzbek (2-4 sentences)."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query":  {"type": "STRING", "description": "Search query in the user's natural language"},
                "mode":   {"type": "STRING", "description": "search (default) | news | url | compare"},
                "url":    {"type": "STRING", "description": "URL to fetch when mode='url'"},
                "items":  {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Items to compare (compare mode)"},
                "aspect": {"type": "STRING", "description": "price | specs | reviews | general (compare mode)"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "weather_report",
        "description": "Gives the weather report to user",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "city": {"type": "STRING", "description": "City name"}
            },
            "required": ["city"]
        }
    },
    {
        "name": "send_message",
        "description": "Sends a text message via WhatsApp, Telegram, or other messaging platform.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "receiver":     {"type": "STRING", "description": "Recipient contact name"},
                "message_text": {"type": "STRING", "description": "The message to send"},
                "platform":     {"type": "STRING", "description": "Platform: WhatsApp, Telegram, etc."}
            },
            "required": ["receiver", "message_text", "platform"]
        }
    },
    {
        "name": "reminder",
        "description": "Sets a timed reminder using Task Scheduler.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "date":    {"type": "STRING", "description": "Date in YYYY-MM-DD format"},
                "time":    {"type": "STRING", "description": "Time in HH:MM format (24h)"},
                "message": {"type": "STRING", "description": "Reminder message text"}
            },
            "required": ["date", "time", "message"]
        }
    },
    {
        "name": "youtube_video",
        "description": (
            "Controls YouTube. Use for: playing videos, summarizing a video's content, "
            "getting video info, or showing trending videos."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "play | summarize | get_info | trending (default: play)"},
                "query":  {"type": "STRING", "description": "Search query for play action"},
                "save":   {"type": "BOOLEAN", "description": "Save summary to Notepad (summarize only)"},
                "region": {"type": "STRING", "description": "Country code for trending e.g. TR, US"},
                "url":    {"type": "STRING", "description": "Video URL for get_info action"},
            },
            "required": []
        }
    },
    {
        "name": "screen_process",
        "description": (
            "Captures and analyzes the screen or webcam image. "
            "MUST be called when user asks what is on screen, what you see, "
            "analyze my screen, look at camera, etc. "
            "You have NO visual ability without this tool. "
            "After calling this tool, stay SILENT — the vision module speaks directly."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "angle": {"type": "STRING", "description": "'screen' to capture display, 'camera' for webcam. Default: 'screen'"},
                "text":  {"type": "STRING", "description": "The question or instruction about the captured image"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "computer_settings",
        "description": (
            "Controls the computer: volume, brightness, window management, keyboard shortcuts, "
            "typing text on screen, closing apps, fullscreen, dark mode, WiFi, restart, shutdown, "
            "scrolling, tab management, zoom, screenshots, lock screen, refresh/reload page. "
            "Use for ANY single computer control command. NEVER route to agent_task."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "The action to perform"},
                "description": {"type": "STRING", "description": "Natural language description of what to do"},
                "value":       {"type": "STRING", "description": "Optional value: volume level, text to type, etc."}
            },
            "required": []
        }
    },
    {
        "name": "browser_control",
        "description": (
            "Controls any web browser. Use for: opening websites, searching the web, "
            "clicking elements, filling forms, scrolling, screenshots, navigation, any web-based task. "
            "Always pass the 'browser' parameter when the user specifies a browser (e.g. 'open in Edge', "
            "'use Firefox', 'open Chrome'). Multiple browsers can run simultaneously.\n"
            "IMPORTANT — closing: use action='close_tab' to close just ONE tab/window "
            "(e.g. 'bu oynani yop', 'tabni yop', 'close this tab/window'). Use action='close' "
            "ONLY to quit the ENTIRE browser ('Chrome'ni butunlay yop', 'close the whole browser').\n"
            "VIDEO/MUSIC on a web page (YouTube etc.): use action='media_pause' to stop, "
            "action='media_play' to RESUME/continue ('davom ettir', 'resume', 'continue playing'), "
            "action='media_toggle' to flip. These work on the visible tab via the page's own player."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "go_to | search | click | type | scroll | fill_form | smart_click | smart_type | get_text | get_url | press | new_tab | close_tab (one tab) | media_play (resume video) | media_pause | media_toggle | screenshot | back | forward | reload | switch | list_browsers | close (whole browser) | close_all"},
                "browser":     {"type": "STRING", "description": "Target browser: chrome | edge | firefox | opera | operagx | brave | vivaldi | safari. Omit to use the currently active browser."},
                "url":         {"type": "STRING", "description": "URL for go_to / new_tab action"},
                "query":       {"type": "STRING", "description": "Search query for search action"},
                "engine":      {"type": "STRING", "description": "Search engine: google | bing | duckduckgo | yandex (default: google)"},
                "selector":    {"type": "STRING", "description": "CSS selector for click/type"},
                "text":        {"type": "STRING", "description": "Text to click or type"},
                "description": {"type": "STRING", "description": "Element description for smart_click/smart_type"},
                "direction":   {"type": "STRING", "description": "up | down for scroll"},
                "amount":      {"type": "INTEGER", "description": "Scroll amount in pixels (default: 500)"},
                "key":         {"type": "STRING", "description": "Key name for press action (e.g. Enter, Escape, F5)"},
                "path":        {"type": "STRING", "description": "Save path for screenshot"},
                "incognito":   {"type": "BOOLEAN", "description": "Open in private/incognito mode"},
                "clear_first": {"type": "BOOLEAN", "description": "Clear field before typing (default: true)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "file_controller",
        "description": (
            "Manages files and folders: list, create, delete (to trash), move, copy, rename, read, write, find, disk usage. "
            "MULTI-TARGET DELETE/MOVE/COPY: For 'delete', 'move', 'copy' actions you may pass multiple file names "
            "separated by commas, semicolons, 'va', 'and', '&' or '+' in the `name` field — the tool will operate on "
            "EACH item under the same `path`. Example: name='report.pdf, draft.md, old.txt' deletes all three from the path. "
            "Deletions go to system trash (recoverable), they are NOT permanent. Protected directories (home, Desktop, Downloads, "
            "Documents, Pictures, Music, Videos themselves) cannot be deleted — only files/folders INSIDE them.\n"
            "USE THIS for listing/finding folders & files. Uzbek triggers: 'ish stolidagi papkalar/fayllar', "
            "'ish stolimda nima bor', 'papkalarni ko'rsat', 'yuklamalar papkasi', 'hujjatlardagi fayllar', "
            "'falon faylni top'. For folder shortcuts pass path='desktop' (ish stoli), 'downloads' (yuklamalar), "
            "'documents' (hujjatlar), 'pictures', 'music', 'videos', 'home' — the tool also accepts the Uzbek/Russian "
            "names directly (ish stoli, Рабочий стол). To list everything on the desktop: action='list', path='desktop'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "list | open | create_file | create_folder | delete | move | copy | rename | read | write | find | largest | disk_usage | organize_desktop | info"},
                "path":        {"type": "STRING", "description": "File/folder path or shortcut: desktop, downloads, documents, home, pictures, music, videos. For delete/move/copy: parent directory of the items."},
                "destination": {"type": "STRING", "description": "Destination path for move/copy"},
                "new_name":    {"type": "STRING", "description": "New name for rename"},
                "content":     {"type": "STRING", "description": "Content for create_file/write"},
                "name":        {"type": "STRING", "description": "File/folder name. For multi-target delete/move/copy pass comma-separated names like 'a.txt, b.pdf, oldfolder'."},
                "extension":   {"type": "STRING", "description": "File extension to search (e.g. .pdf)"},
                "count":       {"type": "INTEGER", "description": "Number of results for largest"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "desktop_control",
        "description": "Controls the desktop: wallpaper, organize, clean, list, stats.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "wallpaper | wallpaper_url | organize | clean | list | stats | task"},
                "path":   {"type": "STRING", "description": "Image path for wallpaper"},
                "url":    {"type": "STRING", "description": "Image URL for wallpaper_url"},
                "mode":   {"type": "STRING", "description": "by_type or by_date for organize"},
                "task":   {"type": "STRING", "description": "Natural language desktop task"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "code_helper",
        "description": (
            "Writes, edits, explains, runs, or builds code files in ANY modern programming language — "
            "Python, JavaScript, TypeScript, React (JSX/TSX), Vue, Svelte, HTML, CSS/SCSS, Java, C/C++, "
            "Go, Rust, Ruby, PHP, Bash, SQL, JSON, and more. "
            "THIS IS THE TOOL THE USER WANTS WHEN THEY ASK FOR ANY CODE. "
            "Always available — never claim code writing is unavailable. "
            "TRIGGER (call IMMEDIATELY with action='write'): "
            "'kod yoz', 'skript yoz', 'funksiya yoz', 'komponent yoz', 'reactda kod yoz', "
            "'html sahifa yarat', 'css yoz', 'javascript funksiya', 'python skript', "
            "'bitta funksiyali kod yozib ber', 'manga shunday narsa qilib ber', "
            "'write code', 'create a function', 'build me a component', and any similar phrasing. "
            "Pass the user's request verbatim as `description`. If a specific language is mentioned, "
            "set `language` accordingly; otherwise default to python or infer from context. "
            "Output is auto-saved to the user's Desktop unless output_path is provided."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "write | edit | explain | run | build | auto (default: auto)"},
                "description": {"type": "STRING", "description": "What the code should do (e.g. 'a counter component with + and - buttons', 'function that reverses a string')"},
                "language":    {"type": "STRING", "description": "Language: python | javascript | typescript | react | react-ts | vue | svelte | html | css | java | cpp | go | rust | bash | sql | json (default: python)"},
                "output_path": {"type": "STRING", "description": "Where to save the file (optional — defaults to Desktop)"},
                "file_path":   {"type": "STRING", "description": "Path to existing file for edit/explain/run/build"},
                "code":        {"type": "STRING", "description": "Raw code string for explain"},
                "args":        {"type": "STRING", "description": "CLI arguments for run/build"},
                "timeout":     {"type": "INTEGER", "description": "Execution timeout in seconds (default: 30)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "dev_agent",
        "description": "Builds complete multi-file projects from scratch: plans, writes files, installs deps, opens VSCode, runs and fixes errors.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "description":  {"type": "STRING", "description": "What the project should do"},
                "language":     {"type": "STRING", "description": "Programming language (default: python)"},
                "project_name": {"type": "STRING", "description": "Optional project folder name"},
                "timeout":      {"type": "INTEGER", "description": "Run timeout in seconds (default: 30)"},
            },
            "required": ["description"]
        }
    },
    {
        "name": "agent_task",
        "description": (
            "Executes complex multi-step tasks requiring multiple different tools. "
            "Examples: 'research X and save to file', 'find and organize files'. "
            "DO NOT use for single commands. NEVER use for Steam/Epic — use game_updater."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "goal":     {"type": "STRING", "description": "Complete description of what to accomplish"},
                "priority": {"type": "STRING", "description": "low | normal | high (default: normal)"}
            },
            "required": ["goal"]
        }
    },
    {
        "name": "computer_control",
        "description": "Direct computer control: type, click, hotkeys, scroll, move mouse, screenshots, find elements on screen.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "type | smart_type | click | double_click | right_click | hotkey | press | scroll | move | copy | paste | screenshot | wait | clear_field | focus_window | screen_find | screen_click | random_data | user_data"},
                "text":        {"type": "STRING", "description": "Text to type or paste"},
                "x":           {"type": "INTEGER", "description": "X coordinate"},
                "y":           {"type": "INTEGER", "description": "Y coordinate"},
                "keys":        {"type": "STRING", "description": "Key combination e.g. 'ctrl+c'"},
                "key":         {"type": "STRING", "description": "Single key e.g. 'enter'"},
                "direction":   {"type": "STRING", "description": "up | down | left | right"},
                "amount":      {"type": "INTEGER", "description": "Scroll amount (default: 3)"},
                "seconds":     {"type": "NUMBER",  "description": "Seconds to wait"},
                "title":       {"type": "STRING",  "description": "Window title for focus_window"},
                "description": {"type": "STRING",  "description": "Element description for screen_find/screen_click"},
                "type":        {"type": "STRING",  "description": "Data type for random_data"},
                "field":       {"type": "STRING",  "description": "Field for user_data: name|email|city"},
                "clear_first": {"type": "BOOLEAN", "description": "Clear field before typing (default: true)"},
                "path":        {"type": "STRING",  "description": "Save path for screenshot"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "game_updater",
        "description": (
            "THE ONLY tool for ANY Steam or Epic Games request. "
            "Use for: installing, downloading, updating games, listing installed games, "
            "checking download status, scheduling updates. "
            "ALWAYS call directly for any Steam/Epic/game request. "
            "NEVER use agent_task, browser_control, or web_search for Steam/Epic."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":    {"type": "STRING",  "description": "update | install | list | download_status | schedule | cancel_schedule | schedule_status (default: update)"},
                "platform":  {"type": "STRING",  "description": "steam | epic | both (default: both)"},
                "game_name": {"type": "STRING",  "description": "Game name (partial match supported)"},
                "app_id":    {"type": "STRING",  "description": "Steam AppID for install (optional)"},
                "hour":      {"type": "INTEGER", "description": "Hour for scheduled update 0-23 (default: 3)"},
                "minute":    {"type": "INTEGER", "description": "Minute for scheduled update 0-59 (default: 0)"},
                "shutdown_when_done": {"type": "BOOLEAN", "description": "Shut down PC when download finishes"},
            },
            "required": []
        }
    },
    {
        "name": "flight_finder",
        "description": "Searches Google Flights and speaks the best options.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "origin":      {"type": "STRING",  "description": "Departure city or airport code"},
                "destination": {"type": "STRING",  "description": "Arrival city or airport code"},
                "date":        {"type": "STRING",  "description": "Departure date (any format)"},
                "return_date": {"type": "STRING",  "description": "Return date for round trips"},
                "passengers":  {"type": "INTEGER", "description": "Number of passengers (default: 1)"},
                "cabin":       {"type": "STRING",  "description": "economy | premium | business | first"},
                "save":        {"type": "BOOLEAN", "description": "Save results to Notepad"},
            },
            "required": ["origin", "destination", "date"]
        }
    },
    {
        "name": "shutdown_jarvis",
        "description": (
            "Shuts down the assistant completely. "
            "Call this when the user expresses intent to end the conversation, "
            "close the assistant, say goodbye, or stop Jarvis. "
            "The user can say this in ANY language."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        }
    },
    {
    "name": "file_processor",
    "description": (
        "Processes any file that the user has uploaded or dropped onto the interface. "
        "Use this when the user refers to an uploaded file and wants an action on it. "
        "Supports: images (describe/ocr/resize/compress/convert), "
        "PDFs (summarize/extract_text/to_word), "
        "Word docs & text files (summarize/fix/reformat/translate), "
        "CSV/Excel (analyze/stats/filter/sort/convert), "
        "JSON/XML (validate/format/analyze), "
        "code files (explain/review/fix/optimize/run/document/test), "
        "audio (transcribe/trim/convert/info), "
        "video (trim/extract_audio/extract_frame/compress/transcribe/info), "
        "archives (list/extract), "
        "presentations (summarize/extract_text). "
        "ALWAYS call this tool when a file has been uploaded and the user gives a command about it. "
        "If the user's command is ambiguous, pick the most logical action for that file type."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "file_path": {
                "type": "STRING",
                "description": "Full path to the uploaded file. Leave empty to use the currently uploaded file."
            },
            "action": {
                "type": "STRING",
                "description": (
                    "What to do with the file. Examples by type:\n"
                    "image: describe | ocr | resize | compress | convert | info\n"
                    "pdf: summarize | extract_text | to_word | info\n"
                    "docx/txt: summarize | fix | reformat | translate_hint | word_count | to_bullet\n"
                    "csv/excel: analyze | stats | filter | sort | convert | info\n"
                    "json: validate | format | analyze | to_csv\n"
                    "code: explain | review | fix | optimize | run | document | test\n"
                    "audio: transcribe | trim | convert | info\n"
                    "video: trim | extract_audio | extract_frame | compress | transcribe | info | convert\n"
                    "archive: list | extract\n"
                    "pptx: summarize | extract_text | analyze"
                )
            },
            "instruction": {
                "type": "STRING",
                "description": "Free-form instruction if action doesn't cover it. E.g. 'translate this to Turkish', 'find all email addresses'"
            },
            "format": {
                "type": "STRING",
                "description": "Target format for conversion. E.g. 'mp3', 'pdf', 'csv', 'png'"
            },
            "width":     {"type": "INTEGER", "description": "Target width for image resize"},
            "height":    {"type": "INTEGER", "description": "Target height for image resize"},
            "scale":     {"type": "NUMBER",  "description": "Scale factor for image resize (e.g. 0.5)"},
            "quality":   {"type": "INTEGER", "description": "Quality 1-100 for image/video compress"},
            "start":     {"type": "STRING",  "description": "Start time for trim: seconds or HH:MM:SS"},
            "end":       {"type": "STRING",  "description": "End time for trim: seconds or HH:MM:SS"},
            "timestamp": {"type": "STRING",  "description": "Timestamp for video frame extraction HH:MM:SS"},
            "column":    {"type": "STRING",  "description": "Column name for CSV filter/sort"},
            "value":     {"type": "STRING",  "description": "Filter value for CSV filter"},
            "condition": {"type": "STRING",  "description": "Filter condition: equals|contains|gt|lt"},
            "ascending": {"type": "BOOLEAN", "description": "Sort order for CSV sort (default: true)"},
            "save":      {"type": "BOOLEAN", "description": "Save result to file (default: true)"},
            "destination": {"type": "STRING", "description": "Output folder for archive extract"},
        },
        "required": []
    }
},
    {
        "name": "save_memory",
        "description": (
            "Save information to long-term memory. "
            "MANDATORY TRIGGER — ALWAYS call this tool when the user explicitly asks you to remember/save something. "
            "Explicit Uzbek triggers (MUST call save_memory immediately): "
            "'esda saqla', 'esingda tut', 'esingga saqla', 'hotirangga saqla', 'hotirangda saqla', "
            "'xotirangga saqla', 'eslab qol', 'eslab qol uni', 'shuni saqla', 'shuni eslab qol', "
            "'manga shuni saqlab qoy', 'buni esingga olib qol'. "
            "Explicit Russian/English triggers: 'запомни', 'сохрани', 'remember this', 'save this'. "
            "ALSO call silently (without explicit request) when user reveals: name, age, city, job, "
            "preferences, hobbies, relationships, projects, or future plans. "
            "When the user gives an EXPLICIT save command, confirm BRIEFLY in Uzbek (e.g. 'Eslab qoldim.') after calling the tool. "
            "When called silently (no explicit request), do NOT announce. "
            "Do NOT call for: weather, reminders, searches, or one-time commands. "
            "Values should be concise and clear — any language is fine."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "category": {
                    "type": "STRING",
                    "description": (
                        "identity — name, age, birthday, city, job, language, nationality | "
                        "preferences — favorite food/color/music/film/game/sport, hobbies | "
                        "projects — active projects, goals, things being built | "
                        "relationships — friends, family, partner, colleagues | "
                        "wishes — future plans, things to buy, travel dreams | "
                        "notes — habits, schedule, anything else worth remembering"
                    )
                },
                "key":   {"type": "STRING", "description": "Short snake_case key (e.g. name, favorite_food, sister_name)"},
                "value": {"type": "STRING", "description": "Concise value in English (e.g. Fatih, pizza, older sister)"},
            },
            "required": ["category", "key", "value"]
        }
    },
    {
        "name": "translate_text",
        "description": (
            "Translate text from any language to any language. "
            "TRIGGER on Uzbek phrases: 'tarjima qil', 'tarjima qilib ber', 'tarjima qilib bering', "
            "'inglizchaga oʻgir', 'rus tiliga oʻgir', 'oʻzbekchaga oʻgir', 'oʻgir', 'translate'. "
            "When the user says 'shuni inglizchaga tarjima qil: <matn>' — call with text=<matn>, target_language='english'. "
            "When the user says 'mana shuni tarjima qil' without specifying language, default target_language='uzbek'. "
            "When the user says 'menga rus tilida ayt: <matn>' — call with text=<matn>, target_language='russian'. "
            "After the tool returns the translated text, speak it back in full (do NOT shorten it)."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "text":            {"type": "STRING", "description": "The exact text to translate (verbatim from user)"},
                "target_language": {"type": "STRING", "description": "Target language in English (e.g. 'uzbek', 'english', 'russian', 'turkish', 'arabic', 'french')"},
                "source_language": {"type": "STRING", "description": "Optional source language hint in English. Leave empty for auto-detect."},
            },
            "required": ["text", "target_language"]
        }
    },
    {
        "name": "delete_memory",
        "description": (
            "Delete information from long-term memory. "
            "MANDATORY TRIGGER — ALWAYS call this when the user explicitly asks you to forget/delete/erase memory. "
            "Uzbek triggers: 'esdan chiqar', 'unut', 'unutib yubor', 'xotirangdan oʻchir', 'hotirangdan oʻchir', "
            "'xotirangni oʻchir', 'hotirangni oʻchir', 'malumotlarni oʻchir', 'hammasini oʻchir', "
            "'esda saqlaganlaringni oʻchir', 'tozala'. "
            "Russian/English triggers: 'забудь', 'удали из памяти', 'forget', 'delete memory', 'wipe memory'. "
            "Scope parameter controls what to delete: "
            "'all' = wipe entire long-term memory (use when user says hammasini/all/everything). "
            "'category' = clear one category (requires category param). "
            "'entry' = delete one specific item (requires category and key). "
            "After deleting, briefly confirm in Uzbek (e.g. 'Oʻchirildi.' or 'Hammasi tozalandi.')."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "scope":    {"type": "STRING", "description": "all | category | entry"},
                "category": {"type": "STRING", "description": "identity | preferences | projects | relationships | wishes | notes (required for scope=category|entry)"},
                "key":      {"type": "STRING", "description": "Specific key to delete (required for scope=entry)"},
            },
            "required": ["scope"]
        }
    },
    {
        "name": "ollama_query",
        "description": (
            "Run a query on the local Ollama AI model running on this machine. "
            "Use when: user says 'think locally', 'use local AI', 'ask ollama', 'offline mode', "
            "or when internet is unavailable. Fast, private, no cloud. "
            "Returns the model's response as text — speak it back."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "prompt":   {"type": "STRING", "description": "The question or task for Ollama"},
                "model":    {"type": "STRING", "description": "Model name e.g. llama3, mistral, phi3. Leave empty to auto-select."},
                "context":  {"type": "STRING", "description": "Optional extra context to prepend"},
            },
            "required": ["prompt"]
        }
    },
    {
        "name": "toggle_mute",
        "description": (
            "Mute or unmute the microphone. "
            "TRIGGER when user says: 'молчать', 'замолчи', 'тихо', 'выключи микрофон', "
            "'mute', 'shut up', 'be quiet', 'silence', 'unmute', 'включи микрофон', "
            "'speak', 'говори'. "
            "Use action='mute' to mute, action='unmute' to unmute. "
            "After muting say a short goodbye (1 sentence max). "
            "After unmuting say a short hello."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "mute | unmute"
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "clipboard",
        "description": (
            "Read from or write to the system clipboard. "
            "TRIGGER when user says: 'clipboard', 'буфер', 'nusxa olganimni o'qib ber', "
            "'shu matnni clipboardga ko'chir', 'copy this to clipboard', 'paste qil', "
            "'nimaga copy qilganman'. "
            "Use action='get' to read current clipboard, action='set' with text=... to write."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "get | set | clear"},
                "text":   {"type": "STRING", "description": "Text to copy (only required when action=set)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "system_info",
        "description": (
            "Report computer system metrics: CPU, RAM, disk usage, battery, network, uptime, OS. "
            "TRIGGER when user asks: 'akkumulyator qancha qoldi', 'batareya', 'RAM qancha bo'sh', "
            "'disk to'lganmi', 'kompyuter holat', 'CPU yuk', 'sistema info', 'qancha qoldi diskda', "
            "'ish vaqti', 'uptime', 'battery', 'storage'. "
            "Pass metric='battery' for battery alone, 'cpu' for CPU, 'ram' for memory, 'disk' for storage, "
            "'all' (default) for a full summary."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "metric": {"type": "STRING", "description": "all | cpu | ram | disk | battery | network | uptime | os"},
                "path":   {"type": "STRING", "description": "Disk path to check (default: /)"},
            },
            "required": []
        }
    },
    {
        "name": "close_apps",
        "description": (
            "Close one or more running applications by name. Sends a graceful terminate signal first, "
            "force-kills only if the app does not exit within 2 seconds. "
            "TRIGGER when user says: 'yop', 'yopib qoy', 'o'chir' (in app context), 'close', "
            "'shut down Telegram', 'Telegram va Chrome'ni yop', 'hammasini yop'. "
            "MULTI-TARGET: app_name can be a single name OR a comma/va-separated list "
            "(e.g. 'Telegram, Chrome, Spotify' or 'Telegram va Chrome') — all matching processes will be closed. "
            "This DOES NOT uninstall the app, only closes the running instance."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "app_name": {"type": "STRING", "description": "Single app name OR comma/'va'-separated list (e.g. 'Chrome' or 'Telegram, Chrome, Spotify')"},
            },
            "required": ["app_name"]
        }
    },
    {
        "name": "terminal_control",
        "description": (
            "Run shell commands, terminal operations, git commands on the computer. "
            "Use for: running scripts, git commit/push/pull/status/log, listing files, "
            "checking processes, executing any shell command the user asks."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "run | git_status | git_commit | git_push | git_pull | git_log | list_dir | processes"
                },
                "command": {"type": "STRING", "description": "Shell command to run (for action=run)"},
                "path":    {"type": "STRING", "description": "Working directory path (optional)"},
                "message": {"type": "STRING", "description": "Git commit message (for git_commit)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "music_control",
        "description": (
            "Control music and media playback. Works with Spotify, VLC, YouTube in browser, "
            "and any media player. Use for: play/pause, next/previous track, volume, "
            "check what's playing, open Spotify."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "play | pause | play_pause | next | previous | stop | volume | status | current_track | list_players | open_spotify"
                },
                "volume": {"type": "INTEGER", "description": "Volume level 0-100 (for action=volume)"},
                "player": {"type": "STRING", "description": "Specific player name (optional, auto-detects)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "gaming_control",
        "description": (
            "Gaming features: launch games by name, check what games are running, "
            "close games, activate gaming mode (performance), get CPU/GPU stats, open Steam."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "launch | what_is_running | kill_game | system_for_gaming | fps_info | open_steam"
                },
                "game": {"type": "STRING", "description": "Game name (e.g. 'Minecraft', 'CS2', 'Steam')"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "notes",
        "description": (
            "Create, read, list, search, append to, or delete personal notes. "
            "Notes are saved as markdown files in ~/Notes/. "
            "Trigger: 'eslatma yoz', 'nota qo'sh', 'eslatmalarni ko'rsat', "
            "'X haqida nota', 'eslatmalarimda X ni qidir', 'notani o'chir'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":  {"type": "STRING",
                            "description": "create | read | list | search | append | delete"},
                "title":   {"type": "STRING", "description": "Note title"},
                "content": {"type": "STRING", "description": "Note content (for create/append)"},
                "query":   {"type": "STRING", "description": "Search keyword (for search)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "pomodoro",
        "description": (
            "Pomodoro timer — start a work/break cycle with desktop notifications. "
            "Trigger: 'pomodoro boshlash', '25 daqiqa ish', 'taymer boshlash', "
            "'pomodorani to'xtat', 'qancha vaqt qoldi'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":        {"type": "STRING",
                                  "description": "start | stop | status"},
                "work_minutes":  {"type": "INTEGER",
                                  "description": "Work duration in minutes (default 25)"},
                "break_minutes": {"type": "INTEGER",
                                  "description": "Break duration in minutes (default 5)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "notifier",
        "description": (
            "Schedule a desktop notification popup after N minutes or seconds. "
            "Trigger: '10 daqiqadan keyin eslatib ber', 'X vaqtdan keyin xabar ber', "
            "'30 soniyadan keyin bildirish yubor', 'hozir xabar ber'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "message": {"type": "STRING",
                            "description": "Notification message text"},
                "minutes": {"type": "NUMBER",
                            "description": "Delay in minutes (0 for immediate)"},
                "seconds": {"type": "NUMBER",
                            "description": "Additional delay in seconds"},
            },
            "required": ["message"]
        }
    },
    {
        "name": "yt_downloader",
        "description": (
            "Download YouTube videos (MP4) or audio (MP3) via yt-dlp. "
            "Trigger: 'bu videoni yuklab ol', 'YouTube dan musiqa yukla', "
            "'720p da yukla', 'video haqida ma'lumot ber'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "url":     {"type": "STRING",
                            "description": "YouTube video URL"},
                "mode":    {"type": "STRING",
                            "description": "video | audio | info (default: video)"},
                "quality": {"type": "STRING",
                            "description": "best | 1080 | 720 | 480 | 360 (default: best)"},
            },
            "required": ["url"]
        }
    },
    {
        "name": "currency",
        "description": (
            "Real-time currency conversion: USD, EUR, RUB, UZS, GBP, CNY, TRY, KZT, AED and more. "
            "No API key needed. Trigger: '100 dollar necha so'm', '1 evro necha rubl', "
            "'valyuta kurslari', 'dollar kursi'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":   {"type": "STRING",
                             "description": "convert | rates (default: convert)"},
                "amount":   {"type": "NUMBER",
                             "description": "Amount to convert (default: 1)"},
                "from":     {"type": "STRING",
                             "description": "Source currency: 'USD', 'dollar', 'evro', 'som', 'rubl'..."},
                "to":       {"type": "STRING",
                             "description": "Target currency"},
                "base":     {"type": "STRING",
                             "description": "Base currency for rates table (default: USD)"},
            },
            "required": []
        }
    },
    {
        "name": "todo",
        "description": (
            "Structured task list with priorities (high/medium/low) and deadlines. "
            "Trigger: 'vazifa qo'sh', 'bugungi vazifalar', 'bajarildi', "
            "'vazifalarni ko'rsat', 'kechikkan vazifalar'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":   {"type": "STRING",
                             "description": "add | list | done | delete | search | today"},
                "title":    {"type": "STRING",
                             "description": "Task title (for add/done/delete)"},
                "priority": {"type": "STRING",
                             "description": "high | medium | low (default: medium)"},
                "deadline": {"type": "STRING",
                             "description": "Deadline: 'bugun', 'ertaga', '2025-06-01'"},
                "filter":   {"type": "STRING",
                             "description": "pending | done | all (for list, default: pending)"},
                "query":    {"type": "STRING",
                             "description": "Search keyword"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "alarm",
        "description": (
            "Set alarms at specific times (once or recurring daily). "
            "Trigger: 'soat 7:30 da uyg'ot', 'ertaga 9 da signal qo'y', "
            "'har kuni 8 da signal', 'signalni bekor qil'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING",
                           "description": "set | list | delete"},
                "time":   {"type": "STRING",
                           "description": "Time: '07:30', 'ertaga 08:00', '2025-06-01 09:00'"},
                "label":  {"type": "STRING",
                           "description": "Alarm label/name (default: Signal)"},
                "repeat": {"type": "BOOLEAN",
                           "description": "Repeat daily (default: false)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "system_monitor",
        "description": (
            "Real-time CPU, RAM, disk, network, battery stats and process list. "
            "Can set threshold alerts (notify when CPU/RAM > N%). "
            "Trigger: 'CPU qancha', 'RAM holati', 'disk joy', 'top jarayonlar', "
            "'batareya zaryadi', 'tizim holati'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":        {"type": "STRING",
                                  "description": "status | cpu | ram | disk | top | battery | alert"},
                "count":         {"type": "INTEGER",
                                  "description": "Number of top processes to show (default: 10)"},
                "cpu_threshold": {"type": "INTEGER",
                                  "description": "CPU % alert threshold (default: 85)"},
                "ram_threshold": {"type": "INTEGER",
                                  "description": "RAM % alert threshold (default: 85)"},
                "interval":      {"type": "INTEGER",
                                  "description": "Alert check interval in seconds (default: 30)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "home_assistant",
        "description": (
            "Control smart home devices via Home Assistant REST API. "
            "Turn lights on/off, check device status, list all entities. "
            "Trigger: 'chiroqni yoq', 'yoritgichni o'chir', 'smart uy qurilmalari', "
            "'X qurilmasini yoq/o'chir'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING",
                           "description": "setup | list | on | off | toggle | status"},
                "entity": {"type": "STRING",
                           "description": "Entity ID (e.g. light.living_room, switch.fan)"},
                "domain": {"type": "STRING",
                           "description": "Filter entities by domain (e.g. light, switch, sensor)"},
                "url":    {"type": "STRING",
                           "description": "Home Assistant URL (for setup)"},
                "token":  {"type": "STRING",
                           "description": "Long-lived access token (for setup)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "macro_recorder",
        "description": (
            "Record keyboard and mouse actions as macros, then replay them. "
            "Trigger: 'makro yozishni boshlash', 'makroni to'xtat va saqlash', "
            "'makroni ijro et', 'makrolarni ko'rsat'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":  {"type": "STRING",
                            "description": "record | stop | play | list | delete"},
                "name":    {"type": "STRING",
                            "description": "Macro name (for stop/play/delete)"},
                "seconds": {"type": "NUMBER",
                            "description": "Auto-stop recording after N seconds (optional)"},
                "speed":   {"type": "NUMBER",
                            "description": "Playback speed multiplier (default: 1.0, 2.0 = 2x faster)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "image_gen",
        "description": (
            "Generate AI images from text description. Uses DALL-E 3 if OpenAI key is available, "
            "otherwise Pollinations.ai (free, no key needed). Saves to ~/Pictures/JarvisAI/. "
            "Trigger: 'rasm yaratib ber', 'surat chiz', 'AI rasm', 'DALL-E bilan'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "prompt":  {"type": "STRING",
                            "description": "Image description in English for best results"},
                "size":    {"type": "STRING",
                            "description": "Image size: 1024x1024 (default) | 1792x1024 | 1024x1792"},
                "backend": {"type": "STRING",
                            "description": "auto | dalle | pollinations (default: auto)"},
            },
            "required": ["prompt"]
        }
    },
    {
        "name": "ssh_control",
        "description": (
            "Execute commands on remote servers via SSH; manage saved host profiles. "
            "Trigger: 'serverda X buyrug'ini ishlat', 'SSH orqali X bajar', "
            "'remote server holati', 'SSH host qo'sh'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":  {"type": "STRING",
                            "description": "run | add | list | delete"},
                "name":    {"type": "STRING",
                            "description": "Saved host name (profile)"},
                "command": {"type": "STRING",
                            "description": "Shell command to execute remotely"},
                "host":    {"type": "STRING",
                            "description": "IP or hostname (for direct connection or add)"},
                "user":    {"type": "STRING",
                            "description": "SSH username"},
                "port":    {"type": "INTEGER",
                            "description": "SSH port (default: 22)"},
                "key":     {"type": "STRING",
                            "description": "Path to SSH private key (optional)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "weather_extended",
        "description": (
            "Get real-time weather data with temperature, humidity, wind, precipitation. "
            "Supports current, multi-day forecast, and hourly breakdown. No API key needed. "
            "Trigger: 'ob-havo', 'harorat', 'yomg'ir yog'adimi', '3 kunlik prognoz', 'soatlik ob-havo'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "city": {"type": "STRING",
                         "description": "City name (default: Tashkent)"},
                "mode": {"type": "STRING",
                         "description": "current | forecast | hourly (default: current)"},
                "days": {"type": "INTEGER",
                         "description": "Forecast days 1-7 (default: 3, only for forecast mode)"},
            },
            "required": []
        }
    },
    {
        "name": "totp",
        "description": (
            "Generate TOTP 2FA codes; add/list/delete saved secrets. "
            "Secrets stored encrypted at ~/.config/jarvis/totp_secrets.json. "
            "Trigger: 'Github TOTP kodi', '2FA kodni ber', 'authenticator kodi'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING",
                           "description": "get | add | list | delete"},
                "name":   {"type": "STRING",
                           "description": "Account name (e.g. 'Github', 'Google')"},
                "secret": {"type": "STRING",
                           "description": "Base32 TOTP secret (for add action)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "chat_history",
        "description": (
            "Show, search, save, or count the current conversation history. "
            "Trigger: 'suhbat tarixini ko'rsat', 'X deb nimaydi avval', "
            "'tarixni saqlash', 'nechta savol berdim'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING",
                           "description": "show | search | save | count"},
                "query":  {"type": "STRING",
                           "description": "Search term (for search action)"},
                "count":  {"type": "INTEGER",
                           "description": "Number of recent exchanges to show (default: 10)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "pdf_summarizer",
        "description": (
            "Extract text from a PDF file and summarize it using Gemini AI. "
            "Trigger: 'bu PDFni xulosa qil', 'PDF faylni o'qi', "
            "'mana bu hujjatni tushuntir', 'PDF dan nima deyilgan'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path":      {"type": "STRING",
                              "description": "Absolute or ~ path to the PDF file"},
                "language":  {"type": "STRING",
                              "description": "Summary language: uz (default) | ru | en"},
                "max_pages": {"type": "INTEGER",
                              "description": "Max pages to read (default: 20)"},
            },
            "required": ["path"]
        }
    },
    {
        "name": "summarizer",
        "description": (
            "Summarize a web page URL or plain text using Gemini AI. "
            "Trigger: 'bu sahifani xulosa qil', 'mana bu linkni o'qi', "
            "'qisqacha tushuntir', 'bu matnni xulosa qil'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "url":      {"type": "STRING",
                             "description": "Web page URL to fetch and summarize"},
                "text":     {"type": "STRING",
                             "description": "Plain text to summarize (alternative to url)"},
                "language": {"type": "STRING",
                             "description": "Summary language: uz (default) | ru | en"},
            },
            "required": []
        }
    },
    {
        "name": "google_calendar",
        "description": (
            "List upcoming events, create new events, or delete events in Google Calendar. "
            "Requires OAuth2 credentials at ~/.config/jarvis/gcal_credentials.json. "
            "Trigger: 'kalendar voqealarini ko'rsat', 'uchrashuvni qo'sh', "
            "'bugun nima bor', 'X voqeani o'chir'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":             {"type": "STRING",
                                       "description": "list | create | delete"},
                "days":               {"type": "INTEGER",
                                       "description": "Days ahead to list (default: 7)"},
                "title":              {"type": "STRING",
                                       "description": "Event title (for create/delete)"},
                "start":              {"type": "STRING",
                                       "description": "Start date/time: 'bugun', 'ertaga', '2025-06-01 14:00'"},
                "duration_minutes":   {"type": "INTEGER",
                                       "description": "Duration in minutes (default: 60)"},
                "location":           {"type": "STRING",
                                       "description": "Event location (optional)"},
                "description":        {"type": "STRING",
                                       "description": "Event description (optional)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "calculator",
        "description": (
            "Evaluate math expressions and convert units (km↔mile, kg↔lb, °C↔°F, etc.). "
            "Trigger: '2+2', 'sqrt(144)', '10 km to mile', '100 kg to lb', "
            "'hisobla', 'qancha', 'aylantir'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "expression": {"type": "STRING",
                               "description": "Math expression or unit conversion (e.g. '2+2', '10 km to mile')"},
            },
            "required": ["expression"]
        }
    },
    {
        "name": "ocr",
        "description": (
            "Extract text from screen or image using Gemini Vision (OCR). "
            "Can also translate or summarize the extracted text. "
            "Trigger: 'ekrandan matn o'qi', 'skrinshotdagi matnni ko'rsat', "
            "'bu rasmda nima yozilgan', 'ekranni o'qi'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "mode":       {"type": "STRING",
                               "description": "extract | translate | summarize | describe (default: extract)"},
                "image_path": {"type": "STRING",
                               "description": "Path to image file (optional; takes screenshot if omitted)"},
            },
            "required": []
        }
    },
    {
        "name": "voice_memo",
        "description": (
            "Record, save, list, play, or delete voice memos (WAV files in ~/VoiceMemos/). "
            "Trigger: 'ovoz yoz', 'yozishni to'xtat', 'ovoz yozuvlarini ko'rsat', "
            "'X yozuvni o'yna', 'ovoz yozuvini o'chir'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":  {"type": "STRING",
                            "description": "record | stop | list | play | delete"},
                "seconds": {"type": "INTEGER",
                            "description": "Recording duration in seconds (default: 30)"},
                "name":    {"type": "STRING",
                            "description": "Memo name (for stop/play/delete)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "wifi_control",
        "description": (
            "List WiFi networks, connect/disconnect, turn WiFi on/off, check status. "
            "Trigger: 'WiFi tarmoqlarini ko'rsat', 'X tarmog'iga ul', "
            "'WiFi o'chir', 'qaysi WiFiga ulangan'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":   {"type": "STRING",
                             "description": "status | list | connect | disconnect | on | off"},
                "ssid":     {"type": "STRING",
                             "description": "Network name to connect to"},
                "password": {"type": "STRING",
                             "description": "WiFi password (if needed for connection)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "speedtest",
        "description": (
            "Measure internet speed: download, upload, ping. "
            "Trigger: 'internet tezligini o'lcha', 'speedtest qil', "
            "'qancha mbps bor', 'internet sekinmi'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "archiver",
        "description": (
            "Zip, unzip, or list archive contents. Supports .zip, .tar.gz, .tar.bz2. "
            "Trigger: 'X papkasini arxivla', 'X.zip ni oч', 'arxiv tarkibini ko'rsat'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING",
                                "description": "zip | unzip | list"},
                "source":      {"type": "STRING",
                                "description": "Source file or folder path"},
                "destination": {"type": "STRING",
                                "description": "Output path (optional; auto-named if omitted)"},
            },
            "required": ["action", "source"]
        }
    },
    {
        "name": "password_gen",
        "description": (
            "Generate secure random passwords, PINs, or passphrases. "
            "Trigger: 'parol yaratib ber', 'kuchli parol', '6 xonali PIN', "
            "'yangi parol kerak', 'tasodifiy parol'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "mode":    {"type": "STRING",
                            "description": "password | pin | passphrase (default: password)"},
                "length":  {"type": "INTEGER",
                            "description": "Length of password or PIN (default: 16)"},
                "count":   {"type": "INTEGER",
                            "description": "How many to generate (default: 1, max: 10)"},
                "charset": {"type": "STRING",
                            "description": "all | alphanumeric | letters | digits | symbols (default: all)"},
            },
            "required": []
        }
    },
    {
        "name": "screen_recorder",
        "description": (
            "Record the screen to MP4 via ffmpeg x11grab. "
            "Trigger: 'ekranni yozishni boshlash', 'yozuvni to'xtat', "
            "'ekran yozuv holati', 'yozuvlar ro'yxati'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING",
                           "description": "start | stop | status | list"},
                "fps":    {"type": "INTEGER",
                           "description": "Frame rate (default: 30)"},
                "audio":  {"type": "BOOLEAN",
                           "description": "Record system audio via PulseAudio (default: false)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "network_tools",
        "description": (
            "Network diagnostics: my public IP, IP geolocation lookup, ping, DNS resolve, port scan. "
            "Trigger: 'mening IP manzilim', 'google.com ping', 'DNS tekshir', "
            "'port skan', '8.8.8.8 haqida ma'lumot'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING",
                           "description": "myip | lookup | ping | dns | scan"},
                "host":   {"type": "STRING",
                           "description": "Hostname or IP (for ping/dns/scan/lookup)"},
                "count":  {"type": "INTEGER",
                           "description": "Ping packet count (default: 4)"},
                "ports":  {"type": "STRING",
                           "description": "Comma-separated ports to scan (default: common ports)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "hash_tool",
        "description": (
            "Compute and verify cryptographic hashes: MD5, SHA1, SHA256, SHA512 for text or files. "
            "Trigger: 'bu matnning SHA256', 'fayl heshi', 'heshni tekshir'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":   {"type": "STRING",
                             "description": "hash | file | verify | all"},
                "algo":     {"type": "STRING",
                             "description": "md5 | sha1 | sha256 | sha512 | sha224 | sha384 (default: sha256)"},
                "text":     {"type": "STRING",
                             "description": "Text to hash (for action=hash or all)"},
                "file":     {"type": "STRING",
                             "description": "File path to hash (for action=file/verify/all)"},
                "expected": {"type": "STRING",
                             "description": "Expected hash digest for verification"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "qr_code",
        "description": (
            "Generate QR codes from text/URL, decode QR images, list saved QR codes. "
            "Trigger: 'QR kod yaratib ber', 'bu URL uchun QR', 'QR kodini o'qi'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING",
                           "description": "generate | decode | list"},
                "data":   {"type": "STRING",
                           "description": "Text, URL, or data to encode (for generate)"},
                "name":   {"type": "STRING",
                           "description": "Output filename without extension (default: qr)"},
                "size":   {"type": "INTEGER",
                           "description": "Box size in pixels (default: 10)"},
                "file":   {"type": "STRING",
                           "description": "Image file path to decode (for decode)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "focus_mode",
        "description": (
            "Block distracting websites (YouTube, Twitter, Instagram, TikTok, Reddit...) "
            "by editing /etc/hosts. Requires pkexec or sudo. "
            "Trigger: 'fokus rejimini yoq', 'saytlarni blokla', 'fokusni o'chir', "
            "'30 daqiqa fokus rejimi'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":   {"type": "STRING",
                             "description": "start | stop | status | list"},
                "duration": {"type": "INTEGER",
                             "description": "Auto-stop after N minutes (0 = until manual stop)"},
                "sites":    {"type": "STRING",
                             "description": "Comma-separated domains to block (default: 16 popular sites)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "disk_manager",
        "description": (
            "Disk usage analysis: partition overview, directory sizes, largest directories, "
            "find large files. Trigger: 'disk holati', 'qaysi papka katta', "
            "'100MB dan katta fayllar', 'uy papkasi hajmi'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING",
                           "description": "overview | usage | top | large"},
                "path":   {"type": "STRING",
                           "description": "Directory path (default: home directory)"},
                "count":  {"type": "INTEGER",
                           "description": "Number of results to show (default: 10)"},
                "min_mb": {"type": "INTEGER",
                           "description": "Minimum file size in MB for large action (default: 100)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "cron_manager",
        "description": (
            "View, add, and remove cron jobs from user crontab. "
            "Trigger: 'cron ro'yxati', 'cron qo'sh', 'har kuni skript ishga tushir', "
            "'cron o'chir'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":   {"type": "STRING",
                             "description": "list | add | delete | clear"},
                "schedule": {"type": "STRING",
                             "description": "Cron schedule: '0 8 * * *' or alias: har_kun|har_soat|har_daqiqa|har_haftada|har_oyda"},
                "command":  {"type": "STRING",
                             "description": "Shell command to run"},
                "index":    {"type": "INTEGER",
                             "description": "1-based index to delete (from list output)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "voice_auth",
        "description": (
            "Enroll the owner's voice profile so JARVIS only responds to them. "
            "Once enrolled, other people's voices are silently ignored. "
            "Trigger: 'ovozimni esla', 'voice enroll', 'ovoz profili holati', "
            "'ovoz profilini o'chir', 'ovoz testini qil'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":    {"type": "STRING",
                              "description": "enroll | test | reset | status | threshold"},
                "seconds":   {"type": "INTEGER",
                              "description": "Enrollment duration in seconds (default: 15, min: 5, max: 60)"},
                "threshold": {"type": "NUMBER",
                              "description": "Log-likelihood threshold (default: -25.0, higher = stricter)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "face_auth",
        "description": (
            "Enroll owner's face from webcam so JARVIS watches and only listens when owner is visible. "
            "If enrolled: Jarvis auto-mutes when face disappears, unmutes when owner is seen. "
            "Trigger: 'yuzimni esla', 'face enroll', 'yuz profilini tekshir', 'yuz profilini o'chir'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":    {"type": "STRING",
                              "description": "enroll | verify | reset | status | threshold"},
                "seconds":   {"type": "INTEGER",
                              "description": "Enrollment duration in seconds (default: 5, max: 30)"},
                "cam":       {"type": "INTEGER",
                              "description": "Camera index (default: 0)"},
                "threshold": {"type": "NUMBER",
                              "description": "Euclidean distance threshold (default: 0.55, lower = stricter)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "samsung_tv",
        "description": (
            "Control Samsung Smart TV over WiFi (same network, no cable). "
            "Power on/off, volume, channels, launch apps (YouTube, Netflix...), navigation. "
            "Trigger: 'TVni yoq', 'ovozni oshir', 'Netflix och', 'TVni o'chir', "
            "'kanal 5', 'TV holati', 'YouTubeni och'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":  {"type": "STRING",
                            "description": "setup | on | off | vol+ | vol- | mute | volume | ch+ | ch- | channel | app | key | status | up | down | left | right | ok | back | home | play | pause | netflix | youtube"},
                "ip":      {"type": "STRING",
                            "description": "TV IP address (only for setup)"},
                "mac":     {"type": "STRING",
                            "description": "TV MAC address for Wake-on-LAN (only for setup/on)"},
                "level":   {"type": "INTEGER",
                            "description": "Volume level 0-100 (for action=volume)"},
                "steps":   {"type": "INTEGER",
                            "description": "Steps for vol+/vol- (default: 3)"},
                "channel": {"type": "INTEGER",
                            "description": "Channel number (for action=channel)"},
                "app":     {"type": "STRING",
                            "description": "App name: youtube | netflix | prime | spotify | plex | browser"},
                "key":     {"type": "STRING",
                            "description": "Remote key name (for action=key)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "type_text",
        "description": (
            "Type any text into the currently focused window (chat, form, terminal, etc). "
            "Use when user says 'chatga yoz', 'shu textni yoz', 'quyidagini yozib ber', "
            "'xabar yoz', 'matn kirit'. Can optionally press Enter to send. "
            "Works with Uzbek, Russian, English text."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "text":        {"type": "STRING",
                                "description": "The exact text to type"},
                "send":        {"type": "STRING",
                                "description": "true to press Enter after typing (send/yuborish)"},
                "delay":       {"type": "INTEGER",
                                "description": "Milliseconds between keystrokes (default 30)"},
                "focus_delay": {"type": "NUMBER",
                                "description": "Seconds to wait before typing (default 0.5)"},
            },
            "required": ["text"]
        }
    },
    {
        "name": "wikipedia",
        "description": (
            "Search Wikipedia and return a summary of any topic, person, place, event, or concept. "
            "Use when user asks: 'Wikipedia dan toping', 'kim u?', 'nima bu?', "
            "'Einstein haqida ayt', 'Python nima', 'Toshkent haqida', 'who is X', 'what is X'. "
            "Supports English (en), Uzbek (uz), Russian (ru) Wikipedia."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query":     {"type": "STRING",
                              "description": "Search term or topic to look up"},
                "sentences": {"type": "INTEGER",
                              "description": "Number of summary sentences (default 4, max 10)"},
                "lang":      {"type": "STRING",
                              "description": "Wikipedia language code: en (default), uz, ru"},
            },
            "required": ["query"]
        }
    },
    {
        "name": "news",
        "description": (
            "Fetch top news headlines from trusted RSS sources (BBC, Kun.uz, HackerNews). "
            "Use when user asks: 'yangiliklar', 'bugungi xabarlar', 'top news', 'texnologiya yangiliklari', "
            "'dunyo yangiliklari', 'sport yangiliklari', 'sogliq yangiliklari', 'biznes yangiliklari'. "
            "Categories: top, world, tech, science, business, sport, health, uz (Uzbek), hn (HackerNews)."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "category": {"type": "STRING",
                             "description": "Category: top, world, tech, science, business, sport, health, uz, hn"},
                "limit":    {"type": "INTEGER",
                             "description": "Number of headlines to fetch (default 5, max 10)"},
            },
            "required": []
        }
    },
    {
        "name": "dictation",
        "description": (
            "Voice dictation mode: records user speech for N seconds, transcribes it with Whisper, "
            "then types the result into the active window (or copies to clipboard). "
            "Use when user says: 'diktovka boshla', 'gapimni yoz', 'nutqimni matnda yoz', "
            "'dictate this', 'type what I say', 'ovozdan matn'. "
            "Perfect for composing messages, emails, or documents by voice."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "seconds":  {"type": "INTEGER",
                             "description": "How many seconds to record (default 8, max 60)"},
                "language": {"type": "STRING",
                             "description": "Speech language code: uz (default), en, ru"},
                "output":   {"type": "STRING",
                             "description": "Output mode: type (default, types in active window), clipboard, text (return only)"},
            },
            "required": []
        }
    },
    {
        "name": "joke",
        "description": (
            "Tells a joke, fun fact, motivational quote, or does a coin flip / dice roll / random number. "
            "Use when user says: 'hazil ayt', 'anekdot ayt', 'qiziq fakt', 'motivatsiya', "
            "'tanga tashlash', 'kub otish', 'tasodifiy son', 'joke', 'tell me a joke', 'fun fact', 'quote'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING",
                           "description": "joke|fact|quote|bored|coin|dice|random|all (default: joke)"},
                "sides":  {"type": "INTEGER", "description": "Dice sides (default 6)"},
                "count":  {"type": "INTEGER", "description": "Number of dice (default 1)"},
                "min":    {"type": "INTEGER", "description": "Random number min (default 1)"},
                "max":    {"type": "INTEGER", "description": "Random number max (default 100)"},
            },
            "required": []
        }
    },
    {
        "name": "dictionary",
        "description": (
            "Looks up English word definitions, pronunciation, synonyms, and examples using Free Dictionary API. "
            "Use when user asks: 'bu so'zning ma'nosi nima', 'define X', 'what does X mean', "
            "'X so'zini izohla', 'X ning sinonimlari', 'X talaffuzi qanday'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "word":   {"type": "STRING", "description": "Word to look up (required)"},
                "detail": {"type": "BOOLEAN", "description": "True for extended output with examples and synonyms"},
            },
            "required": ["word"]
        }
    },
    {
        "name": "timezone",
        "description": (
            "Shows current time in any city or timezone. "
            "Use when user asks: 'Tokioda soat necha', 'Londonda vaqt qanday', 'New Yorkda hozir necha', "
            "'what time is it in Paris', 'Dubai time', 'Moskva vaqti'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "city": {"type": "STRING", "description": "City or timezone name (e.g. Tokyo, London, Dubai, New York)"},
            },
            "required": ["city"]
        }
    },
    {
        "name": "crypto",
        "description": (
            "Gets real-time cryptocurrency prices and market data using CoinGecko (free, no key). "
            "Use when user asks: 'Bitcoin narxi', 'ETH qancha', 'kripto narxlari', "
            "'BTC price', 'top kriptolar', 'Ethereum qancha dollar'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING",
                           "description": "price|top|search (default: price)"},
                "coin":   {"type": "STRING",
                           "description": "Coin name or symbol: BTC, ETH, SOL, BNB, etc."},
                "currency": {"type": "STRING",
                             "description": "Currency code: usd (default), uzs, eur, rub"},
                "limit":  {"type": "INTEGER",
                           "description": "Number of top coins to show (for action=top, default 10)"},
            },
            "required": []
        }
    },
    {
        "name": "stocks",
        "description": (
            "Gets real-time stock prices using Yahoo Finance (free, no key). "
            "Use when user asks: 'Apple aksiyasi', 'Tesla narxi', 'AAPL qancha', "
            "'stock price', 'S&P 500', 'NASDAQ', 'oltin narxi', 'neft narxi'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING",
                           "description": "price|top (default: price)"},
                "symbol": {"type": "STRING",
                           "description": "Stock ticker: AAPL, TSLA, MSFT, GOOGL, AMZN, META, NVDA, etc."},
                "symbols": {"type": "STRING",
                            "description": "Comma-separated list of tickers for batch lookup"},
            },
            "required": []
        }
    },
    {
        "name": "health_calc",
        "description": (
            "Calculates health metrics: BMI (body mass index), BMR (basal metabolic rate), "
            "TDEE (daily calorie needs), water intake. "
            "Use when user asks: 'mening BMIm qancha', 'kunlik kaloriya', 'suv me'yori', "
            "'BMI hisoblash', 'ideal vazn', 'kaloriya hisobi'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":   {"type": "STRING",
                             "description": "bmi|bmr|calories|water|all (default: bmi)"},
                "weight":   {"type": "NUMBER", "description": "Weight in kilograms"},
                "height":   {"type": "NUMBER", "description": "Height in centimeters"},
                "age":      {"type": "INTEGER", "description": "Age in years"},
                "gender":   {"type": "STRING", "description": "male or female"},
                "activity": {"type": "STRING",
                             "description": "sedentary|light|moderate|active|very_active"},
            },
            "required": []
        }
    },
    {
        "name": "unit_converter",
        "description": (
            "Converts units: length, weight/mass, temperature, speed, volume, area, data storage, number bases. "
            "Use when user asks: 'km ni milga', '100 funt necha kg', '37 Celsius Fahrenheit', "
            "'convert 5 miles to km', 'GB ni MB ga', 'binary decimal', 'hex to decimal'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "value":    {"type": "NUMBER", "description": "Value to convert"},
                "from_unit": {"type": "STRING", "description": "Source unit (e.g. km, kg, celsius, mph, GB)"},
                "to_unit":   {"type": "STRING", "description": "Target unit (e.g. miles, lbs, fahrenheit, kph, MB)"},
                "category": {"type": "STRING",
                             "description": "Category: length|mass|temperature|speed|volume|area|data|number (auto-detected if omitted)"},
            },
            "required": ["value", "from_unit", "to_unit"]
        }
    },
    {
        "name": "url_tools",
        "description": (
            "URL utilities: shortens URLs, expands short URLs, checks if a URL is up. "
            "Use when user says: 'bu linkni qisqartir', 'URL shorten', 'bu linkni tekshir', "
            "'is this URL working', 'expand this short link', 'shorten this URL'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING",
                           "description": "shorten|expand|check (default: shorten)"},
                "url":    {"type": "STRING", "description": "URL to process"},
            },
            "required": ["url"]
        }
    },
    {
        "name": "lyrics",
        "description": (
            "Finds and shows song lyrics using lrclib.net (free, no key). "
            "Use when user asks: 'bu qo\'shiqning so\'zlari', 'lyrics of X', 'X qo\'shig\'i matni', "
            "'X by Y song lyrics', 'qo\'shiq so\'zlari'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "title":  {"type": "STRING", "description": "Song title (required)"},
                "artist": {"type": "STRING", "description": "Artist/singer name (optional but helps accuracy)"},
                "mode":   {"type": "STRING", "description": "plain (default) or synced (with timestamps)"},
            },
            "required": ["title"]
        }
    },
    {
        "name": "movie",
        "description": (
            "Gets movie or TV show info: plot, director, cast, IMDb rating, year, genre. "
            "Uses OMDb (Open Movie Database). "
            "Use when user asks: 'Inception haqida', 'bu film qachon chiqgan', 'film reytingi', "
            "'movie info', 'tell me about X movie', 'who directed X', 'X filmning rejissyori kim'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "title":  {"type": "STRING", "description": "Movie or TV show title (required)"},
                "year":   {"type": "INTEGER", "description": "Release year (optional, helps find correct version)"},
                "type":   {"type": "STRING", "description": "movie|series|episode (optional)"},
                "action": {"type": "STRING", "description": "search (default, gets details) | list (returns multiple matches)"},
            },
            "required": ["title"]
        }
    },
    {
        "name": "email_send",
        "description": (
            "Sends an email via Gmail SMTP. "
            "Use when user says: 'email yuborish', 'xat yubor', 'pochta yuborish', "
            "'send email to X', 'email X ga yubor', 'mail jo'nat'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "to":      {"type": "STRING", "description": "Recipient email address"},
                "subject": {"type": "STRING", "description": "Email subject/mavzu"},
                "body":    {"type": "STRING", "description": "Email body text/matn"},
            },
            "required": ["to", "body"]
        }
    },
    {
        "name": "timer",
        "description": (
            "Sets a countdown timer that notifies when time is up. "
            "Unlike alarm (clock-based), timer counts DOWN from now. "
            "Use when user says: 'taymer o'rnat', '5 daqiqa taymer', 'set a timer for X minutes', "
            "'timer for 30 seconds', '10 daqiqadan keyin eslatib qo'y', "
            "'countdown', 'taymerni bekor qil'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":   {"type": "STRING",
                             "description": "set (default)|list|cancel"},
                "duration": {"type": "NUMBER",
                             "description": "Timer duration (number)"},
                "unit":     {"type": "STRING",
                             "description": "Time unit: minutes (default)|seconds|hours"},
                "minutes":  {"type": "NUMBER", "description": "Duration in minutes (shortcut)"},
                "seconds":  {"type": "NUMBER", "description": "Duration in seconds (shortcut)"},
                "hours":    {"type": "NUMBER", "description": "Duration in hours (shortcut)"},
                "label":    {"type": "STRING", "description": "Timer label/name"},
                "id":       {"type": "INTEGER", "description": "Timer ID for cancel"},
            },
            "required": []
        }
    },
    {
        "name": "briefing",
        "description": (
            "Daily morning briefing: aggregates weather, top news, todos, and reminders into one summary. "
            "Use when user says: 'bugungi brifing', 'kunlik xulosa', 'morning briefing', "
            "'bugun nima bor', 'daily summary', 'xayrli tong', 'bugungi rejam'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "city": {"type": "STRING", "description": "City for weather (default: from config)"},
            },
            "required": []
        }
    },
    {
        "name": "contacts",
        "description": (
            "Personal phone book: add, search, list, update, delete contacts. "
            "Stored locally in SQLite. "
            "Use when user says: 'kontakt qo'sh', 'telefon raqamini saqla', "
            "'Alining raqami', 'kontaktlar ro'yxati', 'add contact', 'find contact X', "
            "'X ning nomeri nima'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING",
                           "description": "add|list|search|get|update|delete (default: list)"},
                "name":   {"type": "STRING", "description": "Contact name"},
                "phone":  {"type": "STRING", "description": "Phone number"},
                "email":  {"type": "STRING", "description": "Email address"},
                "notes":  {"type": "STRING", "description": "Notes/eslatma"},
                "id":     {"type": "INTEGER", "description": "Contact ID for get/update/delete"},
                "query":  {"type": "STRING", "description": "Search query for search action"},
            },
            "required": []
        }
    },
    {
        "name": "smart_memory",
        "description": (
            "SEMANTIC long-term memory (RAG) — remembers free-form facts and recalls "
            "them by MEANING, not keywords. This is separate from save_memory: use it for "
            "richer, free-text knowledge that should be searchable later.\n"
            "• action='remember' (text=...) — store a fact the user shares about themselves, "
            "their life, preferences, people, plans, or anything worth recalling later. "
            "Triggers: 'eslab qol', 'esingda bo'lsin', 'remember that...', 'manga aytib qo'y'.\n"
            "• action='recall' (query=...) — BEFORE answering a question that may depend on "
            "something the user told you earlier (their car, family, plans, preferences, past "
            "facts), call recall to fetch relevant memories. Triggers: 'men aytgan edim', "
            "'esingdami', 'mening ... nima edi', 'what did I tell you about...'.\n"
            "• action='forget' (target=id/text/'all'), action='list'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING",
                           "description": "remember | recall | forget | list (default: recall)"},
                "text":   {"type": "STRING",
                           "description": "Fact to remember (for action=remember)"},
                "query":  {"type": "STRING",
                           "description": "What to search for by meaning (for action=recall)"},
                "target": {"type": "STRING",
                           "description": "id, matching text, or 'all' (for action=forget)"},
                "k":      {"type": "INTEGER", "description": "Max results for recall (default 4)"},
            },
            "required": []
        }
    },
    {
        "name": "screen_vision",
        "description": (
            "JARVIS EKRANNI KO'RADI — kompyuter ekranini suratga olib, u haqida savol-javob qiladi. "
            "Use when user asks about what's ON THEIR SCREEN: 'ekranimda nima bor', 'bu xatoni o'qi', "
            "'ekrandagini xulosa qil', 'shu sahifada nima yozilgan', 'what's on my screen', "
            "'read this error', 'what does this say'. Reads text, errors, dialogs, articles, anything visible."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":   {"type": "STRING",
                             "description": "describe | read | summarize | error | important (default: describe)"},
                "question": {"type": "STRING",
                             "description": "Free-form question about the screen (overrides action)"},
                "monitor":  {"type": "INTEGER", "description": "0=all monitors, 1=primary (default 0)"},
            },
            "required": []
        }
    },
    {
        "name": "screen_click",
        "description": (
            "VISION-GUIDED CLICK — clicks any on-screen element by describing it (computer use). "
            "JARVIS ekranni ko'rib, tasvirlangan elementni topadi va bosadi. "
            "Use when user says: 'X tugmasini bos', 'Login tugmasini bos', 'qizil X ni bos', "
            "'click the search box', 'press the OK button'. Works on ANY app, not just browsers."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "target": {"type": "STRING",
                           "description": "What to click, described in words (e.g. 'the blue Login button')"},
                "button": {"type": "STRING",
                           "description": "left | right | middle | double (default: left)"},
                "monitor":{"type": "INTEGER", "description": "Monitor index (default 1 = primary)"},
            },
            "required": ["target"]
        }
    },
    {
        "name": "doc_chat",
        "description": (
            "CHAT WITH DOCUMENTS — indexes local files (txt, md, pdf, docx, code) and answers "
            "questions grounded in their content (RAG). "
            "Use when user says: 'shu faylni o'qi va savol beraman', 'hujjatlarimdan top', "
            "'rezyumemda nima yozilgan', 'bu papkadagi fayllarni xulosa qil', "
            "'chat with this PDF', 'index my Documents folder'. "
            "First action='index' (path=fayl/papka), then action='ask' (query=savol)."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING",
                           "description": "index | ask | list | clear (default: ask)"},
                "path":   {"type": "STRING",
                           "description": "File or folder path to index (for action=index)"},
                "query":  {"type": "STRING",
                           "description": "Question about the indexed documents (for action=ask)"},
            },
            "required": []
        }
    },
    {
        "name": "auto_agent",
        "description": (
            "AUTONOMOUS IN-APP TASK AGENT — give it a GOAL and it does the WHOLE task inside ANY "
            "application by itself: opens/focuses the app, then looks at the screen, clicks, types, "
            "searches, scrolls, repeats until done. THIS is the tool for doing things INSIDE apps. "
            "Use whenever the user wants an action performed within an app, e.g.: "
            "'Telegramda Ali ni topib salom yoz', 'YouTube dan lofi qidirib qo'y', "
            "'WhatsApp dan onamga xabar yoz', 'Chrome da GitHub ochib repo qidir', "
            "'sozlamalarni och va wifi ni yoq', 'falon chatni topib shu textni yoz'. "
            "Works in Telegram, WhatsApp, YouTube, browsers, editors, settings — EVERY app. "
            "It can find a specific chat/contact/video and type the text the user dictated. "
            "By default it WRITES/PREPARES the text but does NOT send/post unless the goal clearly "
            "says to send/post/yubor. For a SINGLE click use screen_click; for one app launch use open_app."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "goal":      {"type": "STRING",
                              "description": "The full in-app task in the user's words (include the app, the target like a contact/chat/video, and the exact text to type if any)"},
                "app":       {"type": "STRING",
                              "description": "App to open/focus first (e.g. telegram, youtube, chrome). Optional — auto-detected from goal if omitted."},
                "max_steps": {"type": "INTEGER", "description": "Max actions (default 10, cap 15)"},
            },
            "required": ["goal"]
        }
    },
    {
        "name": "watcher",
        "description": (
            "PROACTIVE MONITOR — watches a condition in the background and ALERTS you (voice + "
            "notification) when it happens, then stops. Use when user says: "
            "'yuklab olish/render tugasa ayt', 'CPU 90% dan oshsa xabar ber', "
            "'bu fayl paydo bo'lsa bildiri', 'batareya 20% ga tushsa ogohlantir', "
            "'bu sahifa yangilansa ayt', 'tell me when X finishes/starts'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":    {"type": "STRING", "description": "add (default) | list | cancel"},
                "condition": {"type": "STRING",
                              "description": "process_done | process_start | file_exists | cpu_above | cpu_below | battery_below | battery_full | url_changed"},
                "value":     {"type": "STRING",
                              "description": "Process name / file path / percent / URL depending on condition"},
                "note":      {"type": "STRING", "description": "Optional reminder text to say on alert"},
                "id":        {"type": "STRING", "description": "Watcher id to cancel (or 'all')"},
            },
            "required": []
        }
    },
    {
        "name": "time_machine",
        "description": (
            "PERFECT RECALL / TIME MACHINE — JARVIS records your screen activity in the "
            "background (locally) and lets you search your past by MEANING. The killer feature: "
            "ask what you were doing or find something you saw earlier.\n"
            "Use when user says: 'vaqt mashinasini yoq' (start), 'kecha soat 3da nima qilayotgan edim', "
            "'o'sha ... ni qachon ko'rgandim', 'find when I saw X', 'what was I doing', "
            "'vaqt mashinasini to'xtat' (stop). action='start' first to begin recording."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING",
                           "description": "start | stop | status | search | timeline | clear (default: search)"},
                "query":  {"type": "STRING", "description": "What to recall, by meaning (action=search)"},
                "when":   {"type": "STRING", "description": "Time/day to look at, e.g. 'kecha 15:00', 'today 9' (action=timeline)"},
            },
            "required": []
        }
    },
    {
        "name": "research",
        "description": (
            "DEEP RESEARCH AGENT — for COMPLEX questions, JARVIS autonomously searches multiple "
            "web sources, reads them, and writes ONE thorough Uzbek answer with [n] citations + a "
            "sources list (Perplexity-style). Use for questions needing real research/comparison/"
            "current info, NOT simple facts. Triggers: 'chuqur izlan', 'tadqiq qil', 'X haqida "
            "batafsil ma'lumot top', 'X va Y ni solishtir', 'research X', 'investigate X', "
            "'X haqida manbalar bilan ayt'. For a quick single fact use web_search instead."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {"type": "STRING", "description": "The research question/topic"},
                "depth": {"type": "STRING",
                          "description": "quick (3 sources) | normal (5) | deep (8). Default: normal"},
            },
            "required": ["query"]
        }
    },
    {
        "name": "window_manager",
        "description": (
            "Manage desktop windows: list, focus, close, minimize, maximize, tile left/right. "
            "Use when user says: 'ochiq oynalarni ko'rsat', 'Chrome'ni oldinga chiqar', "
            "'oynani chap yarmiga qo'y', 'bu oynani kichiklashtir', 'focus Firefox', "
            "'tile this window left', 'maximize the window'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING",
                           "description": "list | focus | close | minimize | maximize | left | right (default: list)"},
                "target": {"type": "STRING",
                           "description": "Window/app name to act on (omit = active window)"},
            },
            "required": []
        }
    },
    {
        "name": "math_solver",
        "description": (
            "Symbolic math: solve equations, simplify/expand/factor expressions, "
            "compute derivatives and integrals using sympy. "
            "Use when user says: 'tenglamani yech', 'solve x^2-4=0', "
            "'hosilasini top', 'integral hisob', 'ifodani soddalash', "
            "'x^3 + 2x simplify', 'factor x^2-1'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "expression": {"type": "STRING",
                               "description": "Math expression or equation (e.g. 'x^2 - 4 = 0')"},
                "action":     {"type": "STRING",
                               "description": "solve|simplify|expand|factor|diff|integrate|eval (default: solve)"},
                "variable":   {"type": "STRING",
                               "description": "Variable to solve for (default: x)"},
                "from":       {"type": "NUMBER", "description": "Lower bound for definite integral"},
                "to":         {"type": "NUMBER", "description": "Upper bound for definite integral"},
                "order":      {"type": "INTEGER", "description": "Derivative order (default: 1)"},
            },
            "required": ["expression"]
        }
    },
    {
        "name": "reddit",
        "description": (
            "Browse Reddit posts from any subreddit or search Reddit (no API key needed). "
            "Use when user says: 'reddit', 'r/programming toppostlari', 'Reddit dan yangiliklar', "
            "'Reddit worldnews', 'subreddit ko'rsat', 'Reddit izla X'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "subreddit": {"type": "STRING",
                              "description": "Subreddit name: worldnews|technology|programming|science|games etc."},
                "action":    {"type": "STRING",
                              "description": "browse (default)|search|popular"},
                "sort":      {"type": "STRING",
                              "description": "hot (default)|new|top|rising"},
                "limit":     {"type": "INTEGER",
                              "description": "Number of posts (default 5, max 15)"},
                "query":     {"type": "STRING",
                              "description": "Search query (for action=search)"},
            },
            "required": []
        }
    },
    {
        "name": "emotion",
        "description": (
            "Detects the user's facial emotion from webcam in real-time using AI (DeepFace). "
            "Recognizes: happy, sad, angry, surprise, fear, disgust, neutral. "
            "Use when user says: 'hissiyotimni aniqla', 'kayfiyatimni ko\'r', "
            "'emotion detect', 'yuzimni tahlil qil', 'men qanday ko\'rinaman', "
            "'how do I look', 'what emotion am I showing'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING",
                           "description": "detect (default, fresh capture)|last (reuse last result)"},
            },
            "required": []
        }
    },
    {
        "name": "gesture_control",
        "description": (
            "Activates hand gesture control via webcam using MediaPipe. "
            "Gestures: fist=mute, open palm=stop, pinch+move=volume, V-sign=screenshot. "
            "Use when user says: 'gest boshqaruv', 'qo\'l bilan boshqar', "
            "'gesture control on', 'hand gesture volume', 'gestlarni yoq', "
            "'tovushni qo\'l bilan boshqar'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING",
                                "description": "start (default)|stop|status"},
                "duration":    {"type": "NUMBER",
                                "description": "How many seconds to listen for gestures (default 30)"},
                "sensitivity": {"type": "NUMBER",
                                "description": "Volume change sensitivity 0.5-2.0 (default 1.0)"},
            },
            "required": []
        }
    },
    {
        "name": "webcam_vision",
        "description": (
            "Captures webcam frame and describes/analyzes it using Gemini Vision AI. "
            "Can describe the scene, count objects, read text in frame, detect emotions. "
            "Use when user says: 'kamerada nima ko\'rinayapti', 'meni tasvir qil', "
            "'webcam tasvirini o\'qi', 'kamerani tahlil qil', "
            "'what do you see', 'describe what you see', 'how many people', "
            "'surat ol', 'kameradan o\'qi'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING",
                           "description": "describe|people|read|count|emotion|save (default: describe)"},
                "prompt": {"type": "STRING",
                           "description": "Custom question/prompt about the webcam image"},
                "object": {"type": "STRING",
                           "description": "Object to count (for action=count)"},
            },
            "required": []
        }
    },
]

class JarvisLive:

    def __init__(self, ui: JarvisUI):
        self.ui             = ui
        self.session        = None
        self.audio_in_queue = None
        self.out_queue      = None
        self._loop          = None
        self._is_speaking   = False
        self._speaking_lock = threading.Lock()
        self.ui.on_text_command = self._on_text_command
        self._turn_done_event: asyncio.Event | None = None

        # Noise gate state (per-frame counters, safe inside GIL)
        self._gate_open         = False
        self._gate_attack_count = 0
        self._gate_hold_count   = 0

        # Wake-word detector ("hey jarvis"). Always starts muted; unmutes on wake or F4.
        self.ui.muted = True
        self._wake_detector = None
        if _WAKE_WORD_AVAILABLE:
            try:
                self._wake_detector = WakeWordDetector(on_wake=self._on_wake_word)
                print("[JARVIS] 💤 Wake-word active — say 'hey jarvis' to wake")
            except Exception as e:
                print(f"[JARVIS] ⚠️ Wake-word init failed: {e}")
                print("[JARVIS] 💤 Sleeping — press F4 to activate")
                self._wake_detector = None
        else:
            print("[JARVIS] 💤 Sleeping — press F4 to activate (wake-word unavailable)")

    def _on_wake_word(self):
        """Called by WakeWordDetector when 'hey jarvis' is heard.
        Three cases:
          1. Muted     → unmute and start listening.
          2. Speaking  → BARGE-IN: stop Jarvis mid-sentence, drain audio queue,
                         start listening to the user immediately.
          3. Already listening → just acknowledge.
        """
        was_muted    = self.ui.muted
        with self._speaking_lock:
            was_speaking = self._is_speaking

        # Cancel any pending auto-sleep timer in every case
        if hasattr(self, "_sleep_timer") and self._sleep_timer:
            try:
                self._sleep_timer.cancel()
            except Exception:
                pass
            self._sleep_timer = None

        if was_speaking:
            # BARGE-IN: interrupt Jarvis's current speech.
            print("[JARVIS] 🛑 Wake-word during speech — BARGE-IN")
            self.ui.write_log("🛑 'Hey Jarvis' — to'xtatdim, eshityapman")
            # Drain the playback queue so audio cuts off ASAP
            if self.audio_in_queue is not None:
                try:
                    while not self.audio_in_queue.empty():
                        self.audio_in_queue.get_nowait()
                except Exception:
                    pass
            # Signal that we're no longer speaking — listening resumes
            with self._speaking_lock:
                self._is_speaking = False
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
            # Tell Gemini Live the user is taking the turn — best-effort
            if self.session and self._loop:
                try:
                    asyncio.run_coroutine_threadsafe(
                        self._send_user_interrupt(),
                        self._loop,
                    )
                except Exception as e:
                    print(f"[JARVIS] interrupt-send failed: {e}")
            return

        if was_muted:
            self.ui.muted = False
            self.ui.write_log("🟢 'Hey Jarvis' — uyg'ondim, eshityapman")
            print("[JARVIS] 🟢 Wake-word triggered — unmuted")
            return

        # Already listening — just acknowledge so the user knows it was heard
        self.ui.write_log("🟢 'Hey Jarvis' — allaqachon tinglayman")
        print("[JARVIS] 🟢 Wake-word fired (already unmuted)")

    async def _send_user_interrupt(self):
        """Send an empty client-content turn so Gemini Live closes its current
        generation and waits for the next user input."""
        if not self.session:
            return
        try:
            await self.session.send_client_content(
                turns={"parts": [{"text": ""}]},
                turn_complete=False,
            )
        except Exception as e:
            print(f"[JARVIS] interrupt msg failed: {e}")

    def _on_text_command(self, text: str):
        if not self._loop or not self.session:
            return
        if face_verifier.is_access_blocked():
            self.ui.write_log("[Security] Begona yuz aniqlandi — matn bloklanди.")
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"parts": [{"text": text}]},
                turn_complete=True
            ),
            self._loop
        )

    def set_speaking(self, value: bool):
        with self._speaking_lock:
            self._is_speaking = value
        if value:
            self.ui.set_state("SPEAKING")
        elif not self.ui.muted:
            self.ui.set_state("LISTENING")
            # Schedule auto-mute after Jarvis finishes speaking (wake-word mode only)
            # Skip when face watcher is running — it manages muting via face detection
            if self._wake_detector and not self._is_speaking and not face_verifier.is_enabled():
                if hasattr(self, "_sleep_timer") and self._sleep_timer:
                    self._sleep_timer.cancel()
                self._sleep_timer = threading.Timer(25.0, self._auto_sleep)
                self._sleep_timer.daemon = True
                self._sleep_timer.start()

    def _auto_sleep(self):
        """Re-mute after grace period so user must say 'hey jarvis' again."""
        if face_verifier.is_enabled():
            return  # face watcher handles muting
        if not self.ui.muted and not self._is_speaking:
            self.ui.muted = True
            print("[JARVIS] 💤 Auto-sleep — say 'hey jarvis' to wake")
            self.ui.write_log("💤 Sleeping — say 'hey jarvis'")

    def speak(self, text: str):
        if not self._loop or not self.session:
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"parts": [{"text": text}]},
                turn_complete=True
            ),
            self._loop
        )

    def speak_error(self, tool_name: str, error: str):
        short = str(error)[:120]
        self.ui.write_log(f"ERR: {tool_name} — {short}")
        self.speak(f"Tool '{tool_name}' failed: {short}. What should I do next?")

    def _build_config(self) -> types.LiveConnectConfig:
        from datetime import datetime

        memory     = load_memory()
        mem_str    = format_memory_for_prompt(memory)
        sys_prompt = _load_system_prompt()

        now      = datetime.now()
        time_str = now.strftime("%A, %B %d, %Y — %I:%M %p")
        time_ctx = (
            f"[CURRENT DATE & TIME]\n"
            f"Right now it is: {time_str}\n"
            f"Use this to calculate exact times for reminders.\n\n"
        )

        parts = [time_ctx]
        if mem_str:
            parts.append(mem_str)
        vocab = stt_context.system_vocab_block()
        if vocab:
            parts.append(vocab)
        parts.append(sys_prompt)

        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            output_audio_transcription={},
            input_audio_transcription={},
            system_instruction="\n".join(parts),
            tools=[{"function_declarations": TOOL_DECLARATIONS}],
            session_resumption=types.SessionResumptionConfig(),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name="Charon"
                    )
                ),
            ),
        )

    async def _execute_tool(self, fc) -> types.FunctionResponse:
        name = fc.name
        args = dict(fc.args or {})

        print(f"[JARVIS] 🔧 {name}  {args}")
        self.ui.set_state("EXECUTING")

        if name == "save_memory":
            category = args.get("category", "notes")
            key      = args.get("key", "")
            value    = args.get("value", "")
            if key and value:
                update_memory({category: {key: {"value": value}}})
                print(f"[Memory] 💾 save_memory: {category}/{key} = {value}")
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": "ok", "silent": True}
            )

        if name == "delete_memory":
            scope    = (args.get("scope") or "").lower().strip()
            category = args.get("category", "")
            key      = args.get("key", "")
            try:
                if scope == "all":
                    result_msg = forget_all()
                elif scope == "category" and category:
                    result_msg = forget_category(category)
                elif scope == "entry" and category and key:
                    result_msg = forget(key, category)
                else:
                    result_msg = f"Invalid delete params: scope={scope!r} category={category!r} key={key!r}"
                print(f"[Memory] 🗑️  delete_memory: {result_msg}")
            except Exception as e:
                result_msg = f"Delete failed: {e}"
                print(f"[Memory] ❌ {result_msg}")
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": result_msg}
            )

        loop   = asyncio.get_event_loop()
        result = "Done."

        try:
            if name == "open_app":
                r = await loop.run_in_executor(None, lambda: open_app(parameters=args, response=None, player=self.ui))
                result = r or f"Opened {args.get('app_name')}."

            elif name == "weather_report":
                r = await loop.run_in_executor(None, lambda: weather_action(parameters=args, player=self.ui))
                result = r or "Weather delivered."

            elif name == "browser_control":
                r = await loop.run_in_executor(None, lambda: browser_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "file_controller":
                r = await loop.run_in_executor(None, lambda: file_controller(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "send_message":
                r = await loop.run_in_executor(None, lambda: send_message(parameters=args, response=None, player=self.ui, session_memory=None))
                result = r or f"Message sent to {args.get('receiver')}."

            elif name == "reminder":
                r = await loop.run_in_executor(None, lambda: reminder(parameters=args, response=None, player=self.ui))
                result = r or "Reminder set."

            elif name == "youtube_video":
                r = await loop.run_in_executor(None, lambda: youtube_video(parameters=args, response=None, player=self.ui))
                result = r or "Done."

            elif name == "screen_process":
                threading.Thread(
                    target=screen_process,
                    kwargs={"parameters": args, "response": None,
                            "player": self.ui, "session_memory": None},
                    daemon=True
                ).start()
                result = "Vision module activated. Stay completely silent — vision module will speak directly."

            elif name == "computer_settings":
                r = await loop.run_in_executor(None, lambda: computer_settings(parameters=args, response=None, player=self.ui))
                result = r or "Done."

            elif name == "desktop_control":
                r = await loop.run_in_executor(None, lambda: desktop_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "code_helper":
                r = await loop.run_in_executor(None, lambda: code_helper(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "dev_agent":
                r = await loop.run_in_executor(None, lambda: dev_agent(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "agent_task":
                from agent.task_queue import get_queue, TaskPriority
                priority_map = {"low": TaskPriority.LOW, "normal": TaskPriority.NORMAL, "high": TaskPriority.HIGH}
                priority = priority_map.get(args.get("priority", "normal").lower(), TaskPriority.NORMAL)
                task_id  = get_queue().submit(goal=args.get("goal", ""), priority=priority, speak=self.speak)
                result   = f"Task started (ID: {task_id})."

            elif name == "web_search":
                r = await loop.run_in_executor(None, lambda: web_search_action(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "translate_text":
                r = await loop.run_in_executor(None, lambda: translate_action(parameters=args, player=self.ui))
                result = r or "Done."
            elif name == "file_processor":
                if not args.get("file_path") and self.ui.current_file:
                    args["file_path"] = self.ui.current_file
                r = await loop.run_in_executor(
                    None,
                    lambda: file_processor(parameters=args, player=self.ui, speak=self.speak)
                )
                result = r or "Done."

            elif name == "computer_control":
                r = await loop.run_in_executor(None, lambda: computer_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "game_updater":
                r = await loop.run_in_executor(None, lambda: game_updater(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "flight_finder":
                r = await loop.run_in_executor(None, lambda: flight_finder(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "ollama_query":
                result = await loop.run_in_executor(None, lambda: _ollama_query(args))

            elif name == "toggle_mute":
                action = args.get("action", "mute").lower()
                if action == "mute":
                    self.ui.muted = True
                    # Make sure wake-word detector is awake so user can
                    # re-wake with "hey jarvis" — pause() would have
                    # silenced it forever.
                    if self._wake_detector:
                        try:
                            self._wake_detector.resume()
                        except Exception:
                            pass
                    result = "Microphone muted — say 'hey jarvis' to wake me back up."
                else:
                    self.ui.muted = False
                    result = "Microphone active."

            elif name == "clipboard":
                r = await loop.run_in_executor(None, lambda: clipboard_action(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "system_info":
                r = await loop.run_in_executor(None, lambda: system_info_action(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "close_apps":
                r = await loop.run_in_executor(None, lambda: close_apps_action(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "terminal_control":
                r = await loop.run_in_executor(None, lambda: terminal_control(**args))
                result = r or "Done."

            elif name == "music_control":
                r = await loop.run_in_executor(None, lambda: music_control(**args))
                result = r or "Done."

            elif name == "gaming_control":
                r = await loop.run_in_executor(None, lambda: gaming_control(**args))
                result = r or "Done."

            elif name == "notes":
                r = await loop.run_in_executor(None, lambda: notes_action(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "pomodoro":
                r = await loop.run_in_executor(
                    None, lambda: pomodoro_action(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "notifier":
                r = await loop.run_in_executor(
                    None, lambda: notifier_action(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "password_gen":
                r = await loop.run_in_executor(
                    None, lambda: password_gen_action(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "archiver":
                r = await loop.run_in_executor(
                    None, lambda: archiver_action(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "speedtest":
                r = await loop.run_in_executor(
                    None, lambda: speedtest_action(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "wifi_control":
                r = await loop.run_in_executor(
                    None, lambda: wifi_control_action(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "voice_memo":
                r = await loop.run_in_executor(
                    None, lambda: voice_memo_action(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "ocr":
                r = await loop.run_in_executor(
                    None, lambda: ocr_action(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "calculator":
                r = await loop.run_in_executor(
                    None, lambda: calculator_action(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "google_calendar":
                r = await loop.run_in_executor(
                    None, lambda: gcal_action(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "summarizer":
                r = await loop.run_in_executor(
                    None, lambda: summarizer_action(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "pdf_summarizer":
                r = await loop.run_in_executor(
                    None, lambda: pdf_action(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "chat_history":
                result = "Suhbat tarixi faqat OpenAI rejimida mavjud."

            elif name == "totp":
                r = await loop.run_in_executor(
                    None, lambda: totp_action(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "weather_extended":
                r = await loop.run_in_executor(
                    None, lambda: weather_ext_action(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "ssh_control":
                r = await loop.run_in_executor(
                    None, lambda: ssh_action(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "image_gen":
                r = await loop.run_in_executor(
                    None, lambda: image_gen_action(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "macro_recorder":
                r = await loop.run_in_executor(
                    None, lambda: macro_action(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "home_assistant":
                r = await loop.run_in_executor(
                    None, lambda: ha_action(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "system_monitor":
                r = await loop.run_in_executor(
                    None, lambda: sysmon_action(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "alarm":
                r = await loop.run_in_executor(
                    None, lambda: alarm_action(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "todo":
                r = await loop.run_in_executor(
                    None, lambda: todo_action(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "currency":
                r = await loop.run_in_executor(
                    None, lambda: currency_action(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "yt_downloader":
                r = await loop.run_in_executor(
                    None, lambda: ytdl_action(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "screen_recorder":
                r = await loop.run_in_executor(
                    None, lambda: screenrec_action(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "network_tools":
                r = await loop.run_in_executor(
                    None, lambda: network_action(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "hash_tool":
                r = await loop.run_in_executor(
                    None, lambda: hash_action(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "qr_code":
                r = await loop.run_in_executor(
                    None, lambda: qr_action(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "focus_mode":
                r = await loop.run_in_executor(
                    None, lambda: focus_action(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "disk_manager":
                r = await loop.run_in_executor(
                    None, lambda: disk_action(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "cron_manager":
                r = await loop.run_in_executor(
                    None, lambda: cron_action(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "voice_auth":
                r = await loop.run_in_executor(
                    None, lambda: voice_auth_action(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "face_auth":
                r = await loop.run_in_executor(
                    None, lambda: face_auth_action(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "samsung_tv":
                r = await loop.run_in_executor(
                    None, lambda: samsung_tv_action(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "type_text":
                r = await loop.run_in_executor(
                    None, lambda: type_text_action(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "wikipedia":
                r = await loop.run_in_executor(
                    None, lambda: wikipedia_action(parameters=args, player=self.ui))
                result = r or "Natija topilmadi."

            elif name == "news":
                r = await loop.run_in_executor(
                    None, lambda: news_action(parameters=args, player=self.ui))
                result = r or "Yangiliklar topilmadi."

            elif name == "dictation":
                r = await loop.run_in_executor(
                    None, lambda: dictation_action(parameters=args, player=self.ui))
                result = r or "Diktovka tugadi."

            elif name == "joke":
                r = await loop.run_in_executor(
                    None, lambda: joke_action(parameters=args, player=self.ui))
                result = r or "Hazil topilmadi."

            elif name == "dictionary":
                r = await loop.run_in_executor(
                    None, lambda: dictionary_action(parameters=args, player=self.ui))
                result = r or "So'z topilmadi."

            elif name == "timezone":
                r = await loop.run_in_executor(
                    None, lambda: timezone_action(parameters=args, player=self.ui))
                result = r or "Vaqt maʼlumoti topilmadi."

            elif name == "crypto":
                r = await loop.run_in_executor(
                    None, lambda: crypto_action(parameters=args, player=self.ui))
                result = r or "Kripto maʼlumoti topilmadi."

            elif name == "stocks":
                r = await loop.run_in_executor(
                    None, lambda: stocks_action(parameters=args, player=self.ui))
                result = r or "Aksiya maʼlumoti topilmadi."

            elif name == "health_calc":
                r = await loop.run_in_executor(
                    None, lambda: health_calc_action(parameters=args, player=self.ui))
                result = r or "Hisob-kitob amalga oshmadi."

            elif name == "unit_converter":
                r = await loop.run_in_executor(
                    None, lambda: unit_converter_action(parameters=args, player=self.ui))
                result = r or "Konvertatsiya amalga oshmadi."

            elif name == "url_tools":
                r = await loop.run_in_executor(
                    None, lambda: url_tools_action(parameters=args, player=self.ui))
                result = r or "URL amaliyoti bajarilmadi."

            elif name == "lyrics":
                r = await loop.run_in_executor(
                    None, lambda: lyrics_action(parameters=args, player=self.ui))
                result = r or "So'z matni topilmadi."

            elif name == "movie":
                r = await loop.run_in_executor(
                    None, lambda: movie_action(parameters=args, player=self.ui))
                result = r or "Film maʼlumoti topilmadi."

            elif name == "email_send":
                r = await loop.run_in_executor(None, lambda: email_action(parameters=args, player=self.ui))
                result = r or "Email yuborildi."

            elif name == "timer":
                r = await loop.run_in_executor(None, lambda: timer_action(parameters=args, player=self.ui))
                result = r or "Taymer o'rnatildi."

            elif name == "briefing":
                r = await loop.run_in_executor(None, lambda: briefing_action(parameters=args, player=self.ui))
                result = r or "Brifing tayyor."

            elif name == "contacts":
                r = await loop.run_in_executor(None, lambda: contacts_action(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "math_solver":
                r = await loop.run_in_executor(None, lambda: math_solver_action(parameters=args, player=self.ui))
                result = r or "Yechim topilmadi."

            elif name == "reddit":
                r = await loop.run_in_executor(None, lambda: reddit_action(parameters=args, player=self.ui))
                result = r or "Reddit postlari topilmadi."

            elif name == "emotion":
                r = await loop.run_in_executor(None, lambda: emotion_action(parameters=args, player=self.ui))
                result = r or "Hissiyot aniqlanmadi."

            elif name == "gesture_control":
                r = await loop.run_in_executor(None, lambda: gesture_action(parameters=args, player=self.ui))
                result = r or "Imo-ishora boshqaruvi bajarildi."

            elif name == "webcam_vision":
                r = await loop.run_in_executor(None, lambda: webcam_vision_action(parameters=args, player=self.ui))
                result = r or "Tasvir tahlil qilinmadi."

            elif name == "smart_memory":
                r = await loop.run_in_executor(None, lambda: smart_memory_action(parameters=args, player=self.ui))
                result = r or "Xotira amali bajarildi."

            elif name == "screen_vision":
                r = await loop.run_in_executor(None, lambda: screen_vision_action(parameters=args, player=self.ui))
                result = r or "Ekran tahlil qilinmadi."

            elif name == "screen_click":
                r = await loop.run_in_executor(None, lambda: screen_click_action(parameters=args, player=self.ui))
                result = r or "Bosilmadi."

            elif name == "doc_chat":
                r = await loop.run_in_executor(None, lambda: doc_chat_action(parameters=args, player=self.ui))
                result = r or "Hujjat amali bajarilmadi."

            elif name == "window_manager":
                r = await loop.run_in_executor(None, lambda: window_manager_action(parameters=args, player=self.ui))
                result = r or "Oyna amali bajarilmadi."

            elif name == "auto_agent":
                r = await loop.run_in_executor(None, lambda: auto_agent_action(parameters=args, player=self.ui))
                result = r or "Vazifa bajarilmadi."

            elif name == "watcher":
                r = await loop.run_in_executor(None, lambda: watcher_action(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Kuzatuvchi amali bajarilmadi."

            elif name == "research":
                r = await loop.run_in_executor(None, lambda: research_action(parameters=args, player=self.ui))
                result = r or "Tadqiqot natijasi topilmadi."

            elif name == "time_machine":
                r = await loop.run_in_executor(None, lambda: time_machine_action(parameters=args, player=self.ui))
                result = r or "Vaqt mashinasi amali bajarilmadi."

            elif name == "shutdown_jarvis":
                self.ui.write_log("SYS: Shutdown requested.")
                self.speak("All systems standing by. Shutting down gracefully. Goodbye, sir.")
                def _shutdown():
                    # Wait for speech to start, then wait for it to finish
                    deadline = time.time() + 12
                    while time.time() < deadline:
                        with self._speaking_lock:
                            speaking = self._is_speaking
                        if speaking:
                            break
                        time.sleep(0.05)
                    # Now wait for it to finish
                    deadline = time.time() + 15
                    while time.time() < deadline:
                        with self._speaking_lock:
                            speaking = self._is_speaking
                        if not speaking:
                            break
                        time.sleep(0.05)
                    time.sleep(1.5)
                    os._exit(0)
                threading.Thread(target=_shutdown, daemon=True).start()

            else:
                result = f"Unknown tool: {name}"

        except Exception as e:
            self.ui._win.hud.trigger_error()
            result = f"Tool '{name}' failed: {e}"
            traceback.print_exc()
            self.speak_error(name, e)

        if not self.ui.muted:
            self.ui.set_state("LISTENING")

        print(f"[JARVIS] 📤 {name} → {str(result)[:80]}")
        return types.FunctionResponse(
            id=fc.id, name=name,
            response={"result": result}
        )

    def _enqueue_audio(self, msg):
        """Put an audio chunk on out_queue, dropping the oldest frame when full.

        Runs in the event-loop thread (via call_soon_threadsafe). Prevents the
        QueueFull spam that occurs when the mic produces audio faster than
        _send_realtime can drain it — we keep the freshest audio instead.
        """
        q = self.out_queue
        try:
            q.put_nowait(msg)
        except asyncio.QueueFull:
            try:
                q.get_nowait()      # drop oldest, make room
            except Exception:
                pass
            try:
                q.put_nowait(msg)
            except Exception:
                pass

    async def _send_realtime(self):
        while True:
            msg = await self.out_queue.get()
            await self.session.send_realtime_input(media=msg)

    async def _listen_audio(self):
        print("[JARVIS] 🎤 Mic started")
        loop = asyncio.get_event_loop()

        # Speaker pre-verification buffer (accumulated before streaming to Gemini)
        _sv_pre_buf:   list  = []   # raw PCM chunks collected before verify
        _sv_verified:  bool  = False
        _sv_rejected:  bool  = False
        _prev_blocked: bool  = False  # tracks previous is_access_blocked() state
        _SV_PRE_FRAMES = 10  # ~10 * 64ms ≈ 0.64s before running verify

        def callback(indata, frames, time_info, status):
            nonlocal _sv_pre_buf, _sv_verified, _sv_rejected, _prev_blocked
            with self._speaking_lock:
                jarvis_speaking = self._is_speaking

            # Feed wake-word detector whenever:
            #   • Jarvis is muted (so 'Hey Jarvis' wakes it up), OR
            #   • Jarvis is speaking (so 'Hey Jarvis' interrupts / barges in).
            # The detector's 2s cooldown + 0.42 threshold + Speex noise suppression
            # keep false-triggers from Jarvis's own voice rare.
            if self._wake_detector and (self.ui.muted or jarvis_speaking):
                try:
                    self._wake_detector.feed(indata)
                except Exception as e:
                    print(f"[WakeWord] feed error: {e}")

            if not jarvis_speaking and not self.ui.muted:
                _cur_blocked = face_verifier.is_access_blocked()

                # Transition: face just reappeared (blocked→unblocked) — full reset.
                # Needed because ui.muted=True can prevent the face gate from running,
                # leaving _sv_rejected stale when the owner reappears.
                if _prev_blocked and not _cur_blocked:
                    self._gate_attack_count = 0
                    self._gate_open         = False
                    self._gate_hold_count   = 0
                    _sv_pre_buf  = []
                    _sv_verified = False
                    _sv_rejected = False
                _prev_blocked = _cur_blocked

                # Face gate: if owner enrolled but not visible — block audio
                if _cur_blocked:
                    self._gate_attack_count = 0
                    self._gate_open         = False
                    self._gate_hold_count   = 0
                    _sv_pre_buf  = []
                    _sv_verified = False
                    _sv_rejected = False
                    return

                # Noise gate: reject background noise and brief transients
                arr = np.frombuffer(indata, dtype=np.int16)
                rms = float(np.sqrt(np.mean(arr.astype(np.float32) ** 2)))

                # Feed RMS level to UI waveform
                try:
                    self.ui._win.hud.set_audio_level(rms)
                except Exception:
                    pass

                # Lip-assisted gate: lower threshold when owner's lips are moving
                lips_active  = face_verifier.is_speaking() and face_verifier.is_owner_seen()
                _live_rms_th = int(_GATE_OPEN_RMS * 0.75) if lips_active else _GATE_OPEN_RMS

                if rms >= _live_rms_th:
                    self._gate_attack_count += 1
                    if self._gate_attack_count >= _GATE_ATTACK:
                        # User is speaking — cancel auto-sleep timer
                        if hasattr(self, '_sleep_timer') and self._sleep_timer:
                            try:
                                self._sleep_timer.cancel()
                                self._sleep_timer = None
                            except Exception:
                                pass
                        # Gate wants to open — check speaker first
                        if not _sv_verified and not _sv_rejected:
                            _sv_pre_buf.append(indata.tobytes())
                            if len(_sv_pre_buf) >= _SV_PRE_FRAMES:
                                raw = b"".join(_sv_pre_buf)
                                if speaker_verifier.verify(raw, SEND_SAMPLE_RATE):
                                    _sv_verified = True
                                    self._gate_open = True
                                    # Flush pre-buffer to Gemini
                                    for chunk in _sv_pre_buf:
                                        loop.call_soon_threadsafe(
                                            self._enqueue_audio,
                                            {"data": chunk, "mime_type": "audio/pcm"},
                                        )
                                    _sv_pre_buf = []
                                else:
                                    print("[SpeakerVerifier] ❌ Rejected — unknown speaker (Live)")
                                    _sv_rejected = True
                                    _sv_pre_buf  = []
                        elif _sv_verified:
                            self._gate_open = True
                    self._gate_hold_count = _GATE_HOLD
                else:
                    self._gate_attack_count = 0
                    if self._gate_hold_count > 0:
                        self._gate_hold_count -= 1
                    else:
                        # Gate closes — reset per-utterance speaker state
                        self._gate_open = False
                        _sv_pre_buf  = []
                        _sv_verified = False
                        _sv_rejected = False

                if self._gate_open and _sv_verified:
                    loop.call_soon_threadsafe(
                        self._enqueue_audio,
                        {"data": indata.tobytes(), "mime_type": "audio/pcm"}
                    )

        try:
            with sd.InputStream(
                samplerate=SEND_SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=CHUNK_SIZE,
                callback=callback,
            ):
                print("[JARVIS] 🎤 Mic stream open")
                while True:
                    await asyncio.sleep(0.1)
        except Exception as e:
            print(f"[JARVIS] ❌ Mic: {e}")
            raise

    async def _receive_audio(self):
        print("[JARVIS] 👂 Recv started")
        out_buf, in_buf = [], []

        try:
            while True:
                async for response in self.session.receive():

                    if response.data:
                        if self._turn_done_event and self._turn_done_event.is_set():
                            self._turn_done_event.clear()
                        self.audio_in_queue.put_nowait(response.data)

                    if response.server_content:
                        sc = response.server_content

                        if sc.output_transcription and sc.output_transcription.text:
                            txt = _clean_transcript(sc.output_transcription.text)
                            if txt:
                                out_buf.append(txt)

                        if sc.input_transcription and sc.input_transcription.text:
                            txt = _clean_transcript(sc.input_transcription.text)
                            if txt:
                                in_buf.append(txt)

                        if sc.turn_complete:
                            if self._turn_done_event:
                                self._turn_done_event.set()

                            full_in = _merge_transcript_fragments(in_buf)
                            if full_in:
                                self.ui.write_log(f"You: {full_in}")
                            in_buf = []

                            full_out = _merge_transcript_fragments(out_buf)
                            if full_out:
                                self.ui.write_log(f"Jarvis: {full_out}")
                                self.ui.push_notification(full_out[:60] if full_out else "Response received")
                            out_buf = []

                    if response.tool_call:
                        fn_responses = []
                        for fc in response.tool_call.function_calls:
                            print(f"[JARVIS] 📞 {fc.name}")
                            fr = await self._execute_tool(fc)
                            fn_responses.append(fr)
                        await self.session.send_tool_response(
                            function_responses=fn_responses
                        )
        except Exception as e:
            print(f"[JARVIS] ❌ Recv: {e}")
            traceback.print_exc()
            raise

    async def _play_audio(self):
        print("[JARVIS] 🔊 Play started")

        stream = sd.RawOutputStream(
            samplerate=RECEIVE_SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=CHUNK_SIZE,
        )
        stream.start()

        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(
                        self.audio_in_queue.get(),
                        timeout=0.1
                    )
                except asyncio.TimeoutError:
                    if (
                        self._turn_done_event
                        and self._turn_done_event.is_set()
                        and self.audio_in_queue.empty()
                    ):
                        self.set_speaking(False)
                        self._turn_done_event.clear()
                    continue
                self.set_speaking(True)
                await asyncio.to_thread(stream.write, chunk)
        except Exception as e:
            print(f"[JARVIS] ❌ Play: {e}")
            raise
        finally:
            self.set_speaking(False)
            stream.stop()
            stream.close()

    async def run(self):
        client = genai.Client(
            api_key=_get_api_key(),
            http_options={"api_version": "v1beta"}
        )

        while True:
            try:
                print("[JARVIS] 🔌 Connecting...")
                self.ui.set_state("THINKING")
                config = self._build_config()

                async with (
                    client.aio.live.connect(model=LIVE_MODEL, config=config) as session,
                    asyncio.TaskGroup() as tg,
                ):
                    self.session        = session
                    self._loop          = asyncio.get_event_loop()
                    self.audio_in_queue = asyncio.Queue()
                    self.out_queue      = asyncio.Queue(maxsize=10)
                    self._turn_done_event = asyncio.Event()

                    print("[JARVIS] ✅ Connected.")
                    self.ui.set_state("LISTENING")
                    self.ui.write_log("SYS: JARVIS online.")
                    self.ui.push_notification("JARVIS systems online")
                    self.speak("JARVIS systems online. Ready.")
                    if face_verifier.is_active() and face_verifier.is_enabled():
                        face_verifier.start_face_watcher(self.ui, cam_index=0)
                        # Face watcher controls ui.muted — don't override here
                    else:
                        # Face ID OFF (or no profile) → camera stays off, mic always on
                        self.ui.muted = False

                    tg.create_task(self._send_realtime())
                    tg.create_task(self._listen_audio())
                    tg.create_task(self._receive_audio())
                    tg.create_task(self._play_audio())

            except Exception as e:
                print(f"[JARVIS] ⚠️ {e}")
                traceback.print_exc()
            self.set_speaking(False)
            self.ui.set_state("THINKING")
            print("[JARVIS] 🔄 Reconnecting in 3s...")
            await asyncio.sleep(3)

OPENAI_TOOLS = _to_openai_tools(TOOL_DECLARATIONS)
ANTHROPIC_TOOLS = _to_anthropic_tools(TOOL_DECLARATIONS)


class JarvisOpenAI:
    """GPT-4o powered JARVIS: Whisper STT → GPT-4o + tools → edge-tts voice."""

    def __init__(self, ui: JarvisUI):
        from openai import OpenAI as _OAI
        self.ui = ui
        self._client = _OAI(api_key=_get_openai_api_key())
        self._history: list[dict] = []
        self._is_speaking   = False
        self._speaking_lock = threading.Lock()
        self._processing    = False
        # Backend-specific greetings (overridden by JarvisClaude)
        self._ready_print  = "[JARVIS] ✅ GPT-4o pipeline ready."
        self._online_log   = "SYS: JARVIS online (GPT-4o)."
        self._online_speak = "J.A.R.V.I.S systems online. GPT-4 ready."

        self.ui.on_text_command = self._on_text_command

        # Noise gate
        self._gate_open         = False
        self._gate_attack_count = 0
        self._gate_hold_count   = 0

        # Always start muted; wake-word or F4 unmutes
        self.ui.muted = True
        self._wake_detector = None
        if _WAKE_WORD_AVAILABLE:
            try:
                self._wake_detector = WakeWordDetector(on_wake=self._on_wake_word)
                print("[JARVIS] 💤 Wake-word active — say 'hey jarvis' to wake")
            except Exception as e:
                print(f"[JARVIS] ⚠️ Wake-word init failed: {e}")
                print("[JARVIS] 💤 Sleeping — press F4 to activate")
        else:
            print("[JARVIS] 💤 Sleeping — press F4 to activate (wake-word unavailable)")

    # ── Wake-word ─────────────────────────────────────────────────────

    def _on_wake_word(self):
        if self.ui.muted:
            self.ui.muted = False
            self.ui.write_log("🟢 Wake-word detected — listening")
            print("[JARVIS] 🟢 Wake-word triggered — unmuted")

    # ── Speaking state ────────────────────────────────────────────────

    def set_speaking(self, value: bool):
        with self._speaking_lock:
            self._is_speaking = value
        if value:
            self.ui.set_state("SPEAKING")
        elif not self.ui.muted:
            self.ui.set_state("LISTENING")
            if self._wake_detector and not face_verifier.is_enabled():
                if hasattr(self, "_sleep_timer") and self._sleep_timer:
                    self._sleep_timer.cancel()
                self._sleep_timer = threading.Timer(25.0, self._auto_sleep)
                self._sleep_timer.daemon = True
                self._sleep_timer.start()

    def _auto_sleep(self):
        if face_verifier.is_enabled():
            return  # face watcher handles muting
        with self._speaking_lock:
            speaking = self._is_speaking
        if not self.ui.muted and not speaking:
            self.ui.muted = True
            print("[JARVIS] 💤 Auto-sleep")
            self.ui.write_log("💤 Sleeping — say 'hey jarvis'")

    # ── TTS ───────────────────────────────────────────────────────────

    def speak(self, text: str):
        self.set_speaking(True)  # mark BEFORE thread starts to block mic
        threading.Thread(target=self._speak_bg, args=(text,), daemon=True).start()

    def _speak_bg(self, text: str):
        try:
            response = self._client.audio.speech.create(
                model="tts-1",
                voice="onyx",
                input=text,
                response_format="pcm",
            )
            pcm = response.content
            arr = np.frombuffer(pcm, dtype=np.int16)
            sd.play(arr, samplerate=24000)
            sd.wait()
        except Exception as e:
            err_str = str(e)
            if "insufficient_quota" in err_str or "429" in err_str:
                print(f"[TTS] OpenAI quota exceeded — falling back to edge-tts")
                self._speak_edge_tts(text)
            else:
                print(f"[TTS] Error: {e}")
        finally:
            self.set_speaking(False)

    def _speak_edge_tts(self, text: str):
        """Free fallback when OpenAI TTS quota is exhausted."""
        try:
            import edge_tts, soundfile as sf, io, asyncio as _aio, tempfile, os as _os
            voice = "en-US-GuyNeural"
            async def _gen(path):
                communicate = edge_tts.Communicate(text, voice)
                await communicate.save(path)
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tf:
                tmp_path = tf.name
            try:
                _aio.run(_gen(tmp_path))
                data, sr = sf.read(tmp_path, dtype="int16")
                sd.play(data, samplerate=sr)
                sd.wait()
            finally:
                try: _os.unlink(tmp_path)
                except Exception: pass
        except Exception as e:
            print(f"[TTS] edge-tts fallback failed: {e}")

    def speak_error(self, tool_name: str, error: str):
        self.ui.write_log(f"ERR: {tool_name} — {str(error)[:120]}")
        self.speak(f"Tool {tool_name} failed. {str(error)[:80]}")

    # ── System prompt ─────────────────────────────────────────────────

    def _system_prompt(self) -> str:
        from datetime import datetime
        memory  = load_memory()
        mem_str = format_memory_for_prompt(memory)
        sys_p   = _load_system_prompt()
        now     = datetime.now()
        ts      = now.strftime("%A, %B %d, %Y — %I:%M %p")
        parts   = [f"[CURRENT DATE & TIME]\nRight now it is: {ts}\n"]
        if mem_str:
            parts.append(mem_str)
        vocab = stt_context.system_vocab_block()
        if vocab:
            parts.append(vocab)
        parts.append(sys_p)
        return "\n".join(parts)

    # ── Tool execution ────────────────────────────────────────────────

    def _execute_tool(self, name: str, args: dict) -> str:
        print(f"[JARVIS] 🔧 {name}  {args}")
        self.ui.set_state("EXECUTING")

        try:
            if name == "save_memory":
                category = args.get("category", "notes")
                key      = args.get("key", "")
                value    = args.get("value", "")
                if key and value:
                    update_memory({category: {key: {"value": value}}})
                return "ok"

            if name == "delete_memory":
                scope    = (args.get("scope") or "").lower().strip()
                category = args.get("category", "")
                key      = args.get("key", "")
                if scope == "all":
                    return forget_all()
                elif scope == "category" and category:
                    return forget_category(category)
                elif scope == "entry" and category and key:
                    return forget(key, category)
                return "Invalid params."

            if name == "open_app":
                return open_app(parameters=args, response=None, player=self.ui) or "Done."
            if name == "weather_report":
                return weather_action(parameters=args, player=self.ui) or "Done."
            if name == "browser_control":
                return browser_control(parameters=args, player=self.ui) or "Done."
            if name == "file_controller":
                return file_controller(parameters=args, player=self.ui) or "Done."
            if name == "send_message":
                return send_message(parameters=args, response=None, player=self.ui, session_memory=None) or "Done."
            if name == "reminder":
                return reminder(parameters=args, response=None, player=self.ui) or "Done."
            if name == "youtube_video":
                return youtube_video(parameters=args, response=None, player=self.ui) or "Done."
            if name == "screen_process":
                threading.Thread(
                    target=screen_process,
                    kwargs={"parameters": args, "response": None,
                            "player": self.ui, "session_memory": None},
                    daemon=True,
                ).start()
                return "Vision module activated."
            if name == "computer_settings":
                return computer_settings(parameters=args, response=None, player=self.ui) or "Done."
            if name == "desktop_control":
                return desktop_control(parameters=args, player=self.ui) or "Done."
            if name == "code_helper":
                return code_helper(parameters=args, player=self.ui, speak=self.speak) or "Done."
            if name == "dev_agent":
                return dev_agent(parameters=args, player=self.ui, speak=self.speak) or "Done."
            if name == "agent_task":
                from agent.task_queue import get_queue, TaskPriority
                pmap = {"low": TaskPriority.LOW, "normal": TaskPriority.NORMAL, "high": TaskPriority.HIGH}
                pri  = pmap.get(args.get("priority", "normal").lower(), TaskPriority.NORMAL)
                tid  = get_queue().submit(goal=args.get("goal", ""), priority=pri, speak=self.speak)
                return f"Task started (ID: {tid})."
            if name == "web_search":
                return web_search_action(parameters=args, player=self.ui) or "Done."
            if name == "translate_text":
                return translate_action(parameters=args, player=self.ui) or "Done."
            if name == "file_processor":
                if not args.get("file_path") and self.ui.current_file:
                    args["file_path"] = self.ui.current_file
                return file_processor(parameters=args, player=self.ui, speak=self.speak) or "Done."
            if name == "computer_control":
                return computer_control(parameters=args, player=self.ui) or "Done."
            if name == "game_updater":
                return game_updater(parameters=args, player=self.ui, speak=self.speak) or "Done."
            if name == "flight_finder":
                return flight_finder(parameters=args, player=self.ui) or "Done."
            if name == "ollama_query":
                return _ollama_query(args)
            if name == "toggle_mute":
                if args.get("action", "mute").lower() == "mute":
                    self.ui.muted = True; return "Muted."
                self.ui.muted = False; return "Active."
            if name == "clipboard":
                return clipboard_action(parameters=args, player=self.ui) or "Done."
            if name == "system_info":
                return system_info_action(parameters=args, player=self.ui) or "Done."
            if name == "close_apps":
                return close_apps_action(parameters=args, player=self.ui) or "Done."
            if name == "terminal_control":
                return terminal_control(**args) or "Done."
            if name == "music_control":
                return music_control(**args) or "Done."
            if name == "gaming_control":
                return gaming_control(**args) or "Done."
            if name == "notes":
                return notes_action(parameters=args, player=self.ui) or "Done."
            if name == "pomodoro":
                return pomodoro_action(parameters=args, player=self.ui) or "Done."
            if name == "notifier":
                return notifier_action(parameters=args, player=self.ui) or "Done."
            if name == "password_gen":
                return password_gen_action(parameters=args, player=self.ui) or "Done."
            if name == "archiver":
                return archiver_action(parameters=args, player=self.ui) or "Done."
            if name == "speedtest":
                return speedtest_action(parameters=args, player=self.ui) or "Done."
            if name == "wifi_control":
                return wifi_control_action(parameters=args, player=self.ui) or "Done."
            if name == "voice_memo":
                return voice_memo_action(parameters=args, player=self.ui) or "Done."
            if name == "ocr":
                return ocr_action(parameters=args, player=self.ui) or "Done."
            if name == "calculator":
                return calculator_action(parameters=args, player=self.ui) or "Done."
            if name == "google_calendar":
                return gcal_action(parameters=args, player=self.ui) or "Done."
            if name == "summarizer":
                return summarizer_action(parameters=args, player=self.ui) or "Done."
            if name == "pdf_summarizer":
                return pdf_action(parameters=args, player=self.ui) or "Done."
            if name == "chat_history":
                args["_history"] = self._history
                return chat_history_action(parameters=args, player=self.ui) or "Done."
            if name == "totp":
                return totp_action(parameters=args, player=self.ui) or "Done."
            if name == "weather_extended":
                return weather_ext_action(parameters=args, player=self.ui) or "Done."
            if name == "ssh_control":
                return ssh_action(parameters=args, player=self.ui) or "Done."
            if name == "image_gen":
                return image_gen_action(parameters=args, player=self.ui) or "Done."
            if name == "macro_recorder":
                return macro_action(parameters=args, player=self.ui) or "Done."
            if name == "home_assistant":
                return ha_action(parameters=args, player=self.ui) or "Done."
            if name == "system_monitor":
                return sysmon_action(parameters=args, player=self.ui) or "Done."
            if name == "alarm":
                return alarm_action(parameters=args, player=self.ui) or "Done."
            if name == "todo":
                return todo_action(parameters=args, player=self.ui) or "Done."
            if name == "currency":
                return currency_action(parameters=args, player=self.ui) or "Done."
            if name == "yt_downloader":
                return ytdl_action(parameters=args, player=self.ui) or "Done."
            if name == "screen_recorder":
                return screenrec_action(parameters=args, player=self.ui) or "Done."
            if name == "network_tools":
                return network_action(parameters=args, player=self.ui) or "Done."
            if name == "hash_tool":
                return hash_action(parameters=args, player=self.ui) or "Done."
            if name == "qr_code":
                return qr_action(parameters=args, player=self.ui) or "Done."
            if name == "focus_mode":
                return focus_action(parameters=args, player=self.ui) or "Done."
            if name == "disk_manager":
                return disk_action(parameters=args, player=self.ui) or "Done."
            if name == "cron_manager":
                return cron_action(parameters=args, player=self.ui) or "Done."
            if name == "voice_auth":
                return voice_auth_action(parameters=args, player=self.ui) or "Done."
            if name == "face_auth":
                return face_auth_action(parameters=args, player=self.ui) or "Done."
            if name == "samsung_tv":
                return samsung_tv_action(parameters=args, player=self.ui) or "Done."
            if name == "type_text":
                return type_text_action(parameters=args, player=self.ui) or "Done."
            if name == "wikipedia":
                return wikipedia_action(parameters=args, player=self.ui) or "Natija topilmadi."
            if name == "news":
                return news_action(parameters=args, player=self.ui) or "Yangiliklar topilmadi."
            if name == "dictation":
                return dictation_action(parameters=args, player=self.ui) or "Diktovka tugadi."
            if name == "joke":
                return joke_action(parameters=args, player=self.ui) or "Hazil topilmadi."
            if name == "dictionary":
                return dictionary_action(parameters=args, player=self.ui) or "So'z topilmadi."
            if name == "timezone":
                return timezone_action(parameters=args, player=self.ui) or "Vaqt ma'lumoti topilmadi."
            if name == "crypto":
                return crypto_action(parameters=args, player=self.ui) or "Kripto ma'lumoti topilmadi."
            if name == "stocks":
                return stocks_action(parameters=args, player=self.ui) or "Aksiya ma'lumoti topilmadi."
            if name == "health_calc":
                return health_calc_action(parameters=args, player=self.ui) or "Hisob-kitob amalga oshmadi."
            if name == "unit_converter":
                return unit_converter_action(parameters=args, player=self.ui) or "Konvertatsiya amalga oshmadi."
            if name == "url_tools":
                return url_tools_action(parameters=args, player=self.ui) or "URL amaliyoti bajarilmadi."
            if name == "lyrics":
                return lyrics_action(parameters=args, player=self.ui) or "So'z matni topilmadi."
            if name == "movie":
                return movie_action(parameters=args, player=self.ui) or "Film ma'lumoti topilmadi."
            if name == "email_send":
                return email_action(parameters=args, player=self.ui) or "Email yuborildi."
            if name == "timer":
                return timer_action(parameters=args, player=self.ui) or "Taymer o'rnatildi."
            if name == "briefing":
                return briefing_action(parameters=args, player=self.ui) or "Brifing tayyor."
            if name == "contacts":
                return contacts_action(parameters=args, player=self.ui) or "Done."
            if name == "math_solver":
                return math_solver_action(parameters=args, player=self.ui) or "Yechim topilmadi."
            if name == "reddit":
                return reddit_action(parameters=args, player=self.ui) or "Reddit postlari topilmadi."
            if name == "emotion":
                return emotion_action(parameters=args, player=self.ui) or "Hissiyot aniqlanmadi."
            if name == "gesture_control":
                return gesture_action(parameters=args, player=self.ui) or "Imo-ishora boshqaruvi bajarildi."
            if name == "webcam_vision":
                return webcam_vision_action(parameters=args, player=self.ui) or "Tasvir tahlil qilinmadi."
            if name == "smart_memory":
                return smart_memory_action(parameters=args, player=self.ui) or "Xotira amali bajarildi."
            if name == "screen_vision":
                return screen_vision_action(parameters=args, player=self.ui) or "Ekran tahlil qilinmadi."
            if name == "screen_click":
                return screen_click_action(parameters=args, player=self.ui) or "Bosilmadi."
            if name == "doc_chat":
                return doc_chat_action(parameters=args, player=self.ui) or "Hujjat amali bajarilmadi."
            if name == "window_manager":
                return window_manager_action(parameters=args, player=self.ui) or "Oyna amali bajarilmadi."
            if name == "auto_agent":
                return auto_agent_action(parameters=args, player=self.ui) or "Vazifa bajarilmadi."
            if name == "watcher":
                return watcher_action(parameters=args, player=self.ui, speak=self.speak) or "Kuzatuvchi amali bajarilmadi."
            if name == "research":
                return research_action(parameters=args, player=self.ui) or "Tadqiqot natijasi topilmadi."
            if name == "time_machine":
                return time_machine_action(parameters=args, player=self.ui) or "Vaqt mashinasi amali bajarilmadi."
            if name == "shutdown_jarvis":
                self.ui.write_log("SYS: Shutdown requested.")
                def _bye():
                    time.sleep(2); os._exit(0)
                threading.Thread(target=_bye, daemon=True).start()
                return "Shutting down."
            return f"Unknown tool: {name}"

        except Exception as e:
            self.ui._win.hud.trigger_error()
            traceback.print_exc()
            self.speak_error(name, e)
            return f"Error: {e}"
        finally:
            if not self.ui.muted:
                self.ui.set_state("LISTENING")

    # ── LLM pipeline ─────────────────────────────────────────────────

    def _on_text_command(self, text: str):
        if face_verifier.is_access_blocked():
            self.ui.write_log("[Security] Begona yuz aniqlandi — matn bloklandi.")
            return
        threading.Thread(target=self._process, args=(text,), daemon=True).start()

    def _process(self, user_text: str):
        if self._processing:
            return
        self._processing = True
        try:
            self.ui.set_state("THINKING")
            self.ui.write_log(f"You: {user_text}")
            self._history.append({"role": "user", "content": user_text})

            # Keep context under control
            if len(self._history) > 30:
                self._history = self._history[-28:]

            messages = [{"role": "system", "content": self._system_prompt()}] + self._history

            response = self._client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                tools=OPENAI_TOOLS,
                tool_choice="auto",
                max_tokens=1024,
            )
            msg = response.choices[0].message

            # Tool-call loop
            while msg.tool_calls:
                # Append assistant's tool-call turn (must include tool_calls list)
                assistant_entry = {"role": "assistant", "content": msg.content or ""}
                if msg.tool_calls:
                    assistant_entry["tool_calls"] = [
                        {
                            "id":   tc.id,
                            "type": "function",
                            "function": {
                                "name":      tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in msg.tool_calls
                    ]
                self._history.append(assistant_entry)

                tool_results = []
                for tc in msg.tool_calls:
                    args   = json.loads(tc.function.arguments)
                    result = self._execute_tool(tc.function.name, args)
                    print(f"[JARVIS] 📤 {tc.function.name} → {str(result)[:80]}")
                    tool_results.append({
                        "role":         "tool",
                        "tool_call_id": tc.id,
                        "content":      str(result),
                    })

                self._history.extend(tool_results)
                messages = [{"role": "system", "content": self._system_prompt()}] + self._history
                self.ui.set_state("THINKING")
                response = self._client.chat.completions.create(
                    model="gpt-4o",
                    messages=messages,
                    tools=OPENAI_TOOLS,
                    tool_choice="auto",
                    max_tokens=1024,
                )
                msg = response.choices[0].message

            final = (msg.content or "").strip()
            if final:
                self._history.append({"role": "assistant", "content": final})
                self.ui.write_log(f"Jarvis: {final}")
                self.ui.push_notification(final[:60])
                self.speak(final)
            else:
                if not self.ui.muted:
                    self.ui.set_state("LISTENING")

        except Exception as e:
            print(f"[JARVIS] ❌ {e}")
            traceback.print_exc()
            self.ui._win.hud.trigger_error()
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
        finally:
            self._processing = False

    # ── STT: Whisper ──────────────────────────────────────────────────

    def _transcribe(self, audio_chunks: list):
        try:
            import io, wave
            raw = b"".join(audio_chunks)

            # Speaker verification — reject if not owner's voice
            if not speaker_verifier.verify(raw, SEND_SAMPLE_RATE):
                print("[SpeakerVerifier] ❌ Rejected — unknown speaker")
                if not self.ui.muted:
                    self.ui.set_state("LISTENING")
                return

            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf:
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(2)
                wf.setframerate(SEND_SAMPLE_RATE)
                wf.writeframes(raw)
            buf.seek(0)
            buf.name = "audio.wav"
            self.ui.set_state("THINKING")
            tx = self._client.audio.transcriptions.create(
                model="whisper-1",
                file=buf,
                language="uz",
                prompt=stt_context.whisper_prompt(),
            )
            text = tx.text.strip()
            print(f"[Whisper] → {text[:80]}")
            if text:
                corrected = stt_context.correct(text)
                if corrected != text:
                    print(f"[STTCorrect] → {corrected[:80]}")
                self._process(corrected)
            else:
                if not self.ui.muted:
                    self.ui.set_state("LISTENING")
        except Exception as e:
            print(f"[Whisper] Error: {e}")
            if not self.ui.muted:
                self.ui.set_state("LISTENING")

    # ── Mic loop ──────────────────────────────────────────────────────

    def run(self):
        print(self._ready_print)
        self.ui.set_state("LISTENING")
        self.ui.write_log(self._online_log)
        self.ui.push_notification("JARVIS systems online")
        self.speak(self._online_speak)
        if face_verifier.is_active() and face_verifier.is_enabled():
            face_verifier.start_face_watcher(self.ui, cam_index=0)
            # Face watcher controls ui.muted — don't override here
        else:
            # Face ID OFF (or no profile) → camera stays off, mic always on
            self.ui.muted = False

        audio_buffer:  list = []
        gate_open          = False
        attack_count       = 0
        hold_count         = 0
        prev_blocked: bool = False  # tracks previous is_access_blocked() state

        def callback(indata, frames, time_info, status):
            nonlocal gate_open, attack_count, hold_count, audio_buffer, prev_blocked

            with self._speaking_lock:
                jarvis_speaking = self._is_speaking

            if self._wake_detector and self.ui.muted and not jarvis_speaking:
                try:
                    self._wake_detector.feed(indata)
                except Exception:
                    pass

            if jarvis_speaking or self.ui.muted or self._processing:
                return

            cur_blocked = face_verifier.is_access_blocked()

            # Transition: face just reappeared — reset gate state for fresh start
            if prev_blocked and not cur_blocked:
                gate_open    = False
                attack_count = 0
                hold_count   = 0
                audio_buffer = []
            prev_blocked = cur_blocked

            # Face gate: if owner enrolled but not visible — block audio
            if cur_blocked:
                gate_open    = False
                attack_count = 0
                hold_count   = 0
                audio_buffer = []
                return

            arr = np.frombuffer(indata, dtype=np.int16)
            rms = float(np.sqrt(np.mean(arr.astype(np.float32) ** 2)))

            try:
                self.ui._win.hud.set_audio_level(rms)
            except Exception:
                pass

            # Lip-assisted gate: if face watcher detects owner speaking, lower threshold
            lips_active = face_verifier.is_speaking() and face_verifier.is_owner_seen()
            effective_rms = int(_GATE_OPEN_RMS * 0.75) if lips_active else _GATE_OPEN_RMS

            if rms >= effective_rms:
                attack_count += 1
                if attack_count >= _GATE_ATTACK:
                    gate_open = True
                hold_count = _GATE_HOLD
            else:
                attack_count = 0
                if hold_count > 0:
                    hold_count -= 1
                else:
                    if gate_open:
                        gate_open = False
                        if audio_buffer:
                            buf_copy    = audio_buffer.copy()
                            audio_buffer = []
                            threading.Thread(
                                target=self._transcribe,
                                args=(buf_copy,),
                                daemon=True,
                            ).start()

            if gate_open:
                audio_buffer.append(indata.tobytes())

        with sd.InputStream(
            samplerate=SEND_SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=CHUNK_SIZE,
            callback=callback,
        ):
            print("[JARVIS] 🎤 Mic stream open (GPT-4o / Whisper)")
            while True:
                time.sleep(0.1)


class JarvisClaude(JarvisOpenAI):
    """Claude (Anthropic Opus 4.8) powered JARVIS.

    Reuses the GPT-4o pipeline end-to-end — Whisper STT, edge-tts/OpenAI TTS,
    wake-word, the 97-tool executor — and only swaps the brain to Anthropic's
    Messages API with adaptive thinking + tool use (manual loop so tools run
    through the existing _execute_tool dispatch).
    """

    def __init__(self, ui: "JarvisUI"):
        super().__init__(ui)
        import anthropic
        self._claude = anthropic.Anthropic(api_key=_get_anthropic_key())
        self._anthropic_tools = ANTHROPIC_TOOLS
        # Command-execution quality lever: high = excellent tool selection +
        # intent understanding (xhigh is even more thorough but slower).
        try:
            with open(API_CONFIG_PATH, "r", encoding="utf-8") as _cf:
                self._claude_effort = (json.load(_cf).get("claude_effort") or "high").lower()
        except Exception:
            self._claude_effort = "high"
        self._ready_print  = "[JARVIS] ✅ Claude (Opus 4.8) pipeline ready."
        self._online_log   = "SYS: JARVIS online (Claude Opus 4.8)."
        self._online_speak = "J.A.R.V.I.S systems online. Claude ready."

    def _trim_history(self):
        # Keep history bounded, but always start at a clean {user, str} turn so
        # the API never sees an orphaned tool_result or a leading assistant msg.
        if len(self._history) <= 30:
            return
        cut = len(self._history) - 28
        while cut < len(self._history) and not (
            self._history[cut].get("role") == "user"
            and isinstance(self._history[cut].get("content"), str)
        ):
            cut += 1
        if cut < len(self._history):
            self._history = self._history[cut:]

    def _process(self, user_text: str):
        if self._processing:
            return
        self._processing = True
        try:
            self.ui.set_state("THINKING")
            self.ui.write_log(f"You: {user_text}")
            self._history.append({"role": "user", "content": user_text})
            self._trim_history()

            system = self._system_prompt()
            final_text = ""

            for _round in range(6):  # cap tool-use rounds per turn
                with self._claude.messages.stream(
                    model="claude-opus-4-8",
                    max_tokens=16000,
                    thinking={"type": "adaptive"},
                    output_config={"effort": self._claude_effort},
                    system=system,
                    tools=self._anthropic_tools,
                    messages=self._history,
                ) as stream:
                    resp = stream.get_final_message()

                # Preserve the FULL content (incl. thinking blocks) — required to
                # continue a tool-use turn on the next request.
                self._history.append({"role": "assistant", "content": resp.content})

                if resp.stop_reason == "tool_use":
                    tool_results = []
                    for block in resp.content:
                        if block.type == "tool_use":
                            self.ui.set_state("EXECUTING")
                            print(f"[Claude] \U0001f527 {block.name} {dict(block.input)}")
                            try:
                                result = self._execute_tool(block.name, dict(block.input))
                            except Exception as e:
                                result = f"Tool '{block.name}' failed: {e}"
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": str(result)[:6000],
                            })
                    self._history.append({"role": "user", "content": tool_results})
                    continue

                final_text = "".join(
                    b.text for b in resp.content if getattr(b, "type", "") == "text"
                ).strip()
                break

            if final_text:
                self.ui.write_log(f"JARVIS: {final_text}")
                self.speak(final_text)
        except Exception as e:
            self.ui._win.hud.trigger_error()
            self.ui.write_log(f"ERR: Claude — {e}")
            traceback.print_exc()
        finally:
            self._processing = False
            if not self.ui.muted:
                self.ui.set_state("LISTENING")


def _ensure_single_instance() -> bool:
    """Return True if we are the first instance. Focus existing window and return False otherwise."""
    if sys.platform != "win32":
        return True
    import ctypes
    mutex = ctypes.windll.kernel32.CreateMutexW(None, True, "JarvisAgentSingleInstance")
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        # Another instance is running — bring its window to front
        try:
            hwnd = ctypes.windll.user32.FindWindowW(None, "J.A.R.V.I.S — MARK XXXIX")
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 9)   # SW_RESTORE
                ctypes.windll.user32.SetForegroundWindow(hwnd)
        except Exception:
            pass
        return False
    return True


def _setup_echo_cancel() -> str | None:
    """Load PulseAudio/PipeWire echo cancel module and set as default source.

    Fixes: YouTube/speaker audio leaking into microphone — AI hears both user
    and speaker output simultaneously (acoustic echo).
    Returns the original default source name so we can restore it on exit.
    """
    import subprocess as _sp
    SOURCE = "jarvis_mic_clean"
    try:
        # Save original default so we can restore on exit
        original = _sp.run(
            ["pactl", "get-default-source"],
            capture_output=True, text=True, timeout=3
        ).stdout.strip()

        # Load module if not already present
        modules = _sp.run(
            ["pactl", "list", "modules", "short"],
            capture_output=True, text=True, timeout=5
        ).stdout
        if "module-echo-cancel" not in modules:
            r = _sp.run([
                "pactl", "load-module", "module-echo-cancel",
                "aec_method=webrtc",
                f"source_name={SOURCE}",
                "sink_name=jarvis_sink_clean",
                "source_master=@DEFAULT_SOURCE@",
                "sink_master=@DEFAULT_SINK@",
            ], capture_output=True, text=True, timeout=5)
            if r.returncode != 0:
                print(f"[Audio] Echo cancel load failed: {r.stderr.strip()}")
                return None
            print("[Audio] ✅ Echo cancellation (WebRTC AEC) yoqildi.")
        else:
            print("[Audio] ✅ Echo cancellation allaqachon faol.")

        # Set as system default source → sd.InputStream(device=None) will use it
        _sp.run(["pactl", "set-default-source", SOURCE],
                capture_output=True, timeout=3)
        print(f"[Audio] Default mic → {SOURCE}")
        return original
    except FileNotFoundError:
        print("[Audio] pactl topilmadi — echo cancellation o'tkazib yuborildi.")
    except Exception as e:
        print(f"[Audio] Echo cancel setup xatosi: {e}")
    return None


def _restore_default_source(original: str | None) -> None:
    """Restore the original default source on exit."""
    if not original:
        return
    try:
        import subprocess as _sp
        _sp.run(["pactl", "set-default-source", original],
                capture_output=True, timeout=3)
        print(f"[Audio] Default mic qayta tiklandi → {original}")
    except Exception:
        pass


def main():
    if not _ensure_single_instance():
        print("[JARVIS] Already running — focused existing window.")
        return

    speaker_verifier.load_profile()
    speaker_verifier._load_active()   # restore persisted Voice ID (owner-only) toggle
    time_machine.load_flag()
    if time_machine._state.get("recording"):
        time_machine.start_recording()   # resume Time Machine if it was ON
    face_verifier.load_profile()
    face_verifier._load_active()   # restore persisted Face ID ON/OFF toggle
    _original_mic = _setup_echo_cancel()  # AEC: cancels speaker echo in microphone
    import atexit as _atexit
    _atexit.register(_restore_default_source, _original_mic)
    ui = JarvisUI("face.png")

    def _auto_enroll_if_needed():
        """If Face ID is ON but no profile exists, open enrollment on the main thread."""
        import time as _t
        _t.sleep(3)  # wait for UI to finish loading
        if face_verifier.is_active() and not face_verifier.is_enabled():
            ui.write_log("📷 Yuz profili topilmadi — ro'yxatdan o'tkazish oynasi ochilmoqda...")
            _t.sleep(1)
            ui.open_enroll_dialog(cam_index=0)  # signal → runs on main Qt thread

    threading.Thread(target=_auto_enroll_if_needed, daemon=True).start()

    # ── Double-clap-to-mute DISABLED ──────────────────────────────────────────
    # Root cause of erratic muting: ClapDetector (RMS threshold 0.45 + "2 loud
    # frames within 0.8s") false-triggered on normal speech / laughter / noise,
    # toggling mute while the user was talking. Mute is now controlled only by
    # F4, the on-screen mic button, and the "hey jarvis" wake word / toggle_mute.
    # (Qayta yoqish uchun bu blokni va ClapDetector ishga tushirishni tiklang.)

    def runner():
        ui.wait_for_api_key()
        # Backend selection — config "backend" key: auto | claude | openai | gemini.
        # In auto mode, prefer Claude if its key exists (user added it on purpose),
        # else GPT-4o when OpenAI has quota, else Gemini Live.
        pref          = _get_backend_pref()
        anthropic_key = _get_anthropic_key()
        use_claude = (pref == "claude") or (pref == "auto" and bool(anthropic_key))
        use_openai = (pref == "openai") or (pref == "auto" and not anthropic_key
                                            and _get_openai_api_key() and _openai_quota_ok())

        if use_claude and anthropic_key:
            print("[JARVIS] 🧠 Backend: Claude (Opus 4.8 — Anthropic)")
            jarvis = JarvisClaude(ui)
            try:
                jarvis.run()
            except KeyboardInterrupt:
                print("\n🔴 Shutting down...")
        elif use_openai or (pref == "openai" and _get_openai_api_key()):
            print("[JARVIS] 🧠 Backend: GPT-4o (OpenAI)")
            jarvis = JarvisOpenAI(ui)
            try:
                jarvis.run()
            except KeyboardInterrupt:
                print("\n🔴 Shutting down...")
        else:
            print("[JARVIS] 🧠 Backend: Gemini Live")
            jarvis = JarvisLive(ui)
            try:
                asyncio.run(jarvis.run())
            except KeyboardInterrupt:
                print("\n🔴 Shutting down...")

    threading.Thread(target=runner, daemon=True).start()
    ui.root.mainloop()

if __name__ == "__main__":
    _register_startup_windows()
    main()