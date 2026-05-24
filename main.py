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
_GATE_OPEN_RMS    = 80     # RMS level required to consider audio "active"
_GATE_ATTACK      = 2      # frames (~128 ms) above threshold before gate opens
_GATE_HOLD        = 28     # frames (~1.8 s) gate stays open after level drops

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
            "'use Firefox', 'open Chrome'). Multiple browsers can run simultaneously."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "go_to | search | click | type | scroll | fill_form | smart_click | smart_type | get_text | get_url | press | new_tab | close_tab | screenshot | back | forward | reload | switch | list_browsers | close | close_all"},
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
            "Documents, Pictures, Music, Videos themselves) cannot be deleted — only files/folders INSIDE them."
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
            # Schedule auto-mute after Jarvis finishes speaking (wake-word mode)
            if self._wake_detector and not self._is_speaking:
                if hasattr(self, "_sleep_timer") and self._sleep_timer:
                    self._sleep_timer.cancel()
                self._sleep_timer = threading.Timer(8.0, self._auto_sleep)
                self._sleep_timer.daemon = True
                self._sleep_timer.start()

    def _auto_sleep(self):
        """Re-mute after grace period so user must say 'hey jarvis' again."""
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
                )
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

    async def _send_realtime(self):
        while True:
            msg = await self.out_queue.get()
            await self.session.send_realtime_input(media=msg)

    async def _listen_audio(self):
        print("[JARVIS] 🎤 Mic started")
        loop = asyncio.get_event_loop()

        def callback(indata, frames, time_info, status):
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
                # Noise gate: reject background noise and brief transients
                arr = np.frombuffer(indata, dtype=np.int16)
                rms = float(np.sqrt(np.mean(arr.astype(np.float32) ** 2)))

                # Feed RMS level to UI waveform
                try:
                    self.ui._win.hud.set_audio_level(rms)
                except Exception:
                    pass

                if rms >= _GATE_OPEN_RMS:
                    self._gate_attack_count += 1
                    if self._gate_attack_count >= _GATE_ATTACK:
                        self._gate_open = True
                    self._gate_hold_count = _GATE_HOLD
                else:
                    self._gate_attack_count = 0
                    if self._gate_hold_count > 0:
                        self._gate_hold_count -= 1
                    else:
                        self._gate_open = False

                if self._gate_open:
                    loop.call_soon_threadsafe(
                        self.out_queue.put_nowait,
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
            if self._wake_detector:
                if hasattr(self, "_sleep_timer") and self._sleep_timer:
                    self._sleep_timer.cancel()
                self._sleep_timer = threading.Timer(8.0, self._auto_sleep)
                self._sleep_timer.daemon = True
                self._sleep_timer.start()

    def _auto_sleep(self):
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
            )
            text = tx.text.strip()
            print(f"[Whisper] → {text[:80]}")
            if text:
                self._process(text)
            else:
                if not self.ui.muted:
                    self.ui.set_state("LISTENING")
        except Exception as e:
            print(f"[Whisper] Error: {e}")
            if not self.ui.muted:
                self.ui.set_state("LISTENING")

    # ── Mic loop ──────────────────────────────────────────────────────

    def run(self):
        print("[JARVIS] ✅ GPT-4o pipeline ready.")
        self.ui.set_state("LISTENING")
        self.ui.write_log("SYS: JARVIS online (GPT-4o).")
        self.ui.push_notification("JARVIS systems online")
        self.speak("J.A.R.V.I.S systems online. GPT-4 ready.")

        audio_buffer: list = []
        gate_open         = False
        attack_count      = 0
        hold_count        = 0

        def callback(indata, frames, time_info, status):
            nonlocal gate_open, attack_count, hold_count, audio_buffer

            with self._speaking_lock:
                jarvis_speaking = self._is_speaking

            if self._wake_detector and self.ui.muted and not jarvis_speaking:
                try:
                    self._wake_detector.feed(indata)
                except Exception:
                    pass

            if jarvis_speaking or self.ui.muted or self._processing:
                return

            arr = np.frombuffer(indata, dtype=np.int16)
            rms = float(np.sqrt(np.mean(arr.astype(np.float32) ** 2)))

            try:
                self.ui._win.hud.set_audio_level(rms)
            except Exception:
                pass

            if rms >= _GATE_OPEN_RMS:
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


def main():
    if not _ensure_single_instance():
        print("[JARVIS] Already running — focused existing window.")
        return

    ui = JarvisUI("face.png")

    def _on_double_clap():
        """Toggle JARVIS mute on double clap."""
        ui.muted = not ui.muted
        state = "MUTED" if ui.muted else "LISTENING"
        try:
            ui.set_state(state)
        except Exception:
            pass
        ui.write_log(f"SYS: Double clap — JARVIS {'muted' if ui.muted else 'active'}.")
        print(f"[ClapDetector] 👏👏 Double clap → {'MUTED' if ui.muted else 'ACTIVE'}")

    def _start_clap():
        import time as _t
        _t.sleep(3)
        try:
            detector = ClapDetector(_on_double_clap)
            detector.start()
        except Exception as e:
            print(f"[ClapDetector] ⚠️ Failed to start: {e}")

    threading.Thread(target=_start_clap, daemon=True).start()

    def runner():
        ui.wait_for_api_key()
        # Use GPT-4o pipeline if openai_api_key is set AND has quota, else Gemini Live
        if _get_openai_api_key() and _openai_quota_ok():
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