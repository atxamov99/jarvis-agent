import subprocess
import sys
import json
import re
import time
from pathlib import Path


def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

BASE_DIR           = get_base_dir()
API_CONFIG_PATH    = BASE_DIR / "config" / "api_keys.json"
DESKTOP            = Path.home() / "Desktop"
MAX_BUILD_ATTEMPTS = 3
GEMINI_MODEL       = "gemini-2.5-flash"


def _get_api_key() -> str:
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]


def _gemini_client():
    from google import genai
    return genai.Client(api_key=_get_api_key())


def _generate(prompt: str, model: str = GEMINI_MODEL) -> str:
    return _gemini_client().models.generate_content(
        model=model,
        contents=prompt,
    ).text


def _generate_openai(prompt: str, model: str = "gpt-4o") -> str:
    from actions.openai_client import get_client
    client = get_client()
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    return resp.choices[0].message.content or ""


def _generate_with_fallback(prompt: str) -> str:
    """Try Gemini first; fall back to GPT-4o on any error."""
    try:
        result = _generate(prompt)
        if result and result.strip():
            return result
    except Exception as e:
        print(f"[Code] ⚠️ Gemini failed ({e}), switching to GPT-4o...")
    return _generate_openai(prompt)


def _clean_code(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    return text.strip()


_LANG_EXT_MAP = {
    "python": ".py", "py": ".py",
    "javascript": ".js", "js": ".js",
    "typescript": ".ts", "ts": ".ts",
    "react": ".jsx", "jsx": ".jsx", "react.js": ".jsx", "reactjs": ".jsx",
    "react-ts": ".tsx", "tsx": ".tsx", "react-typescript": ".tsx",
    "vue": ".vue", "svelte": ".svelte",
    "html": ".html", "css": ".css", "scss": ".scss", "sass": ".sass",
    "java": ".java", "cpp": ".cpp", "c": ".c",
    "bash": ".sh", "shell": ".sh", "powershell": ".ps1",
    "sql": ".sql", "json": ".json", "rust": ".rs", "go": ".go",
    "php": ".php", "ruby": ".rb", "kotlin": ".kt", "swift": ".swift",
}


def _normalize_language(raw: str) -> str:
    """Normalize 'reactda', 'react js', 'React.js' etc. to a canonical key."""
    key = (raw or "python").lower().strip()
    key = re.sub(r"\.?(js|ts)$", lambda m: "." + m.group(1), key)
    if "react" in key and ("ts" in key or "typescript" in key):
        return "react-ts"
    if "react" in key or "jsx" in key:
        return "react"
    if "vue" in key:
        return "vue"
    if "svelte" in key:
        return "svelte"
    return key


def _resolve_save_path(output_path: str, language: str) -> Path:
    if output_path:
        p = Path(output_path)
        return p if p.is_absolute() else DESKTOP / p
    norm = _normalize_language(language)
    ext = _LANG_EXT_MAP.get(norm, ".py")
    # React components get a PascalCase file name by default
    stem = "JarvisComponent" if norm in ("react", "react-ts") else "jarvis_code"
    return DESKTOP / f"{stem}{ext}"


_REACT_PROMPT_RULES = """
React-specific rules:
- Functional components only (no class components).
- Use React hooks (useState, useEffect, useMemo, useCallback) where appropriate.
- Component name must be PascalCase and exported as default.
- Use modern JSX — no React.createElement calls.
- Props are destructured in the function signature.
- For TypeScript variants (.tsx): define proper Props interface or type.
- Keep styling minimal and inline-friendly (Tailwind utility classes are fine if requested).
- No `import React from 'react'` line — the new JSX transform handles it.
- No CSS-in-JS unless explicitly asked.
"""

_HTML_PROMPT_RULES = """
HTML-specific rules:
- Use semantic HTML5 elements (header, nav, main, section, article, footer).
- Always include <!DOCTYPE html>, <html lang="...">, <meta charset="UTF-8">, and a viewport meta.
- Add a meaningful <title>.
- Use proper accessibility: alt for images, label for form inputs, ARIA only when needed.
- Inline <style> and <script> are OK for a single self-contained file.
- For a standalone deliverable, embed CSS/JS in the file so it works by double-clicking.
"""

_CSS_PROMPT_RULES = """
CSS-specific rules:
- Use modern CSS: custom properties (--var), flexbox, grid, clamp(), :has(), :is().
- Mobile-first with min-width media queries.
- Prefer logical properties (margin-inline, padding-block) where applicable.
- No vendor prefixes unless the user explicitly asks (autoprefixer handles them).
- Group related rules; keep specificity low.
"""

_JS_PROMPT_RULES = """
JavaScript-specific rules:
- ES2022+ syntax. Use const/let, arrow functions, optional chaining, nullish coalescing.
- Prefer async/await over .then() chains.
- Use template literals over string concatenation.
- Use early returns to flatten nested conditionals.
- For DOM code: document.querySelector and addEventListener, not inline handlers.
- No `var`. No callback-hell.
"""

_TS_PROMPT_RULES = """
TypeScript-specific rules:
- Strict types. Avoid `any`; use `unknown` then narrow.
- Prefer `interface` for object shapes, `type` for unions/aliases.
- Use const assertions and readonly where appropriate.
- Discriminated unions for state modeling.
- All function signatures explicitly typed.
"""


def _language_specific_rules(norm_lang: str) -> str:
    if norm_lang in ("react", "react-ts"):
        return _REACT_PROMPT_RULES + (_TS_PROMPT_RULES if norm_lang == "react-ts" else "")
    if norm_lang == "html":
        return _HTML_PROMPT_RULES
    if norm_lang in ("css", "scss", "sass"):
        return _CSS_PROMPT_RULES
    if norm_lang in ("javascript", "js"):
        return _JS_PROMPT_RULES
    if norm_lang in ("typescript", "ts"):
        return _TS_PROMPT_RULES
    return ""


def _read_file(file_path: str) -> tuple[str, str]:
    if not file_path:
        return "", "No file path provided."
    p = Path(file_path)
    if not p.exists():
        return "", f"File not found: {file_path}"
    try:
        return p.read_text(encoding="utf-8"), ""
    except Exception as e:
        return "", f"Could not read file: {e}"


def _save_file(path: Path, content: str) -> str:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return f"Saved to: {path}"
    except Exception as e:
        return f"Could not save: {e}"


def _preview(code: str, lines: int = 10) -> str:
    all_lines = code.splitlines()
    preview   = "\n".join(all_lines[:lines])
    suffix    = f"\n... ({len(all_lines) - lines} more lines)" if len(all_lines) > lines else ""
    return preview + suffix


def _has_error(output: str) -> bool:
    error_signals = ["error", "exception", "traceback", "syntaxerror",
                     "nameerror", "typeerror", "stderr", "failed", "crash"]
    return any(s in output.lower() for s in error_signals)


def _take_screenshot() -> Path | None:
    try:
        import pyautogui
        screenshot_path = Path.home() / "Desktop" / f"jarvis_debug_{int(time.time())}.png"
        screenshot = pyautogui.screenshot()
        screenshot.save(str(screenshot_path))
        print(f"[Code] 📸 Screenshot: {screenshot_path}")
        return screenshot_path
    except Exception as e:
        print(f"[Code] ⚠️ Screenshot failed: {e}")
        return None


def _image_to_base64(path: Path) -> str:
    import base64
    return base64.b64encode(path.read_bytes()).decode("utf-8")


def _detect_intent(description: str, file_path: str, code: str) -> str:
    desc = (description or "").lower()

    screen_kw = ["ekrandaki", "screen", "ekranda", "bu hatayı", "why am i getting",
                 "neden hata", "what's wrong", "ne yanlış", "screenshot", "görüntü"]
    if any(k in desc for k in screen_kw):
        return "screen_debug"

    optimize_kw = ["optimize", "refactor", "clean up", "improve", "temizle",
                   "iyileştir", "daha iyi", "make it better", "hızlandır"]
    if any(k in desc for k in optimize_kw) and (code or file_path):
        return "optimize"

    if file_path:
        p = Path(file_path)
        edit_kw  = ["edit", "update", "modify", "change", "add", "remove",
                    "refactor", "fix", "rename", "replace", "düzenle", "değiştir"]
        run_kw   = ["run", "execute", "launch", "start", "çalıştır"]
        build_kw = ["build", "make it work", "try", "attempt"]

        if p.exists() and any(k in desc for k in edit_kw):
            return "edit"
        if p.exists() and any(k in desc for k in run_kw):
            return "run"
        if any(k in desc for k in build_kw):
            return "build"
        if p.exists():
            return "explain"

    explain_kw = ["explain", "what does", "describe", "analyze", "açıkla", "ne yapıyor"]
    if any(k in desc for k in explain_kw) and (code or file_path):
        return "explain"

    build_kw = ["build", "make it work", "try and", "attempt"]
    if any(k in desc for k in build_kw):
        return "build"

    return "write"

def _detect_language_from_description(description: str, fallback: str) -> str:
    """If user said 'reactda funksiya yoz' but didn't pass language='react', detect it."""
    if fallback and fallback.lower() not in ("python", "py", ""):
        return fallback
    desc_low = description.lower()
    if re.search(r"\breact(\s*js|\.js)?(\b|\s+da)?", desc_low) or "jsx" in desc_low:
        return "react-ts" if "typescript" in desc_low or " ts " in desc_low else "react"
    if "vue" in desc_low:
        return "vue"
    if "svelte" in desc_low:
        return "svelte"
    if re.search(r"\btypescript\b", desc_low):
        return "typescript"
    if re.search(r"\bjavascript\b|\bjs\b", desc_low):
        return "javascript"
    if re.search(r"\bhtml\b|\bweb\s*sahifa\b|\bveb\s*sahifa\b|landing\s*page", desc_low):
        return "html"
    if re.search(r"\bcss\b|\bstyles?\b|\btailwind\b|\bscss\b", desc_low):
        return "css"
    if re.search(r"\bbash\b|\bshell\b|\.sh\b", desc_low):
        return "bash"
    if re.search(r"\bsql\b|\bquery\b", desc_low) and "select" in desc_low:
        return "sql"
    return fallback or "python"


def _write(description: str, language: str, output_path: str, player=None) -> tuple[str, Path]:
    lang       = _detect_language_from_description(description, language)
    norm       = _normalize_language(lang)
    extra_rules = _language_specific_rules(norm)
    display    = "React (JSX)" if norm == "react" else "React + TypeScript (TSX)" if norm == "react-ts" else lang

    prompt = f"""You are an expert {display} developer.
Write clean, working, well-commented {display} code for the description below.

Rules:
- Output ONLY the code. No explanation, no markdown, no backticks.
- Add helpful inline comments only where the WHY isn't obvious.
- Handle errors and edge cases properly.
- Use modern best practices.
{extra_rules}
Description: {description}

Code:"""

    code = _clean_code(_generate_with_fallback(prompt))
    path = _resolve_save_path(output_path, lang)
    _save_file(path, code)
    return code, path


def _fix_code(code: str, error_output: str, description: str) -> str:
    prompt = f"""You are an expert debugger.
The code below failed with the following error. Fix it.
Return ONLY the corrected code — no explanation, no markdown, no backticks.

Original goal: {description}

Error:
{error_output[:2000]}

Broken code:
{code}

Fixed code:"""

    return _clean_code(_generate_with_fallback(prompt))


def _run_file(path: Path, args: list, timeout: int) -> str:
    interpreters = {
        ".py":  [sys.executable],
        ".js":  ["node"],
        ".ts":  ["ts-node"],
        ".sh":  ["bash"],
        ".ps1": ["powershell", "-File"],
        ".rb":  ["ruby"],
        ".php": ["php"],
    }
    interp = interpreters.get(path.suffix.lower())
    if not interp:
        return f"No interpreter for {path.suffix}."

    try:
        result = subprocess.run(
            interp + [str(path)] + (args or []),
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=timeout, cwd=str(path.parent)
        )
        output = result.stdout.strip()
        error  = result.stderr.strip()
        parts  = []
        if output: parts.append(f"Output:\n{output}")
        if error:  parts.append(f"Stderr:\n{error}")
        return "\n\n".join(parts) if parts else "Executed with no output."

    except subprocess.TimeoutExpired:
        return f"Timed out after {timeout}s."
    except FileNotFoundError:
        return f"Interpreter not found: {interp[0]}."
    except Exception as e:
        return f"Execution error: {e}"


def _build(description, language, output_path, args, timeout, speak=None, player=None) -> str:
    if not description:
        return "Please describe what you want me to build, sir."

    if player:
        player.write_log("[Code] Build started...")

    lang = language or "python"

    try:
        code, path = _write(description, lang, output_path, player)
        print(f"[Code] ✅ Written: {path}")
    except Exception as e:
        msg = f"Could not write initial code: {e}"
        if speak: speak(msg)
        return msg

    last_output = ""
    for attempt in range(1, MAX_BUILD_ATTEMPTS + 1):
        print(f"[Code] 🔄 Attempt {attempt}/{MAX_BUILD_ATTEMPTS}")
        if player:
            player.write_log(f"[Code] Attempt {attempt}...")

        last_output = _run_file(path, args, timeout)

        if not _has_error(last_output):
            msg = (
                f"Build complete, sir. "
                f"The code is working after {attempt} attempt{'s' if attempt > 1 else ''}. "
                f"Saved to {path}."
            )
            if speak: speak(msg)
            return f"{msg}\n\nOutput:\n{last_output}"

        print(f"[Code] ⚠️ Error on attempt {attempt}, fixing...")
        if player:
            player.write_log(f"[Code] Fixing (attempt {attempt})...")

        try:
            code = _fix_code(code, last_output, description)
            _save_file(path, code)
        except Exception as e:
            msg = f"Could not fix code on attempt {attempt}: {e}"
            if speak: speak(msg)
            return msg

    msg = (
        f"I was unable to build a working version after {MAX_BUILD_ATTEMPTS} attempts, sir. "
        f"The last error was: {last_output[:200]}"
    )
    if speak: speak(msg)
    return f"{msg}\n\nLast code saved to: {path}"

def _write_action(description, language, output_path, player) -> str:
    if not description:
        return "Please describe what you want me to write, sir."
    if player:
        player.write_log("[Code] Writing code...")
    try:
        code, path = _write(description, language, output_path, player)
        print(f"[Code] ✅ Written: {path}")
        return f"Code written. Saved to: {path}\n\nPreview:\n{_preview(code)}"
    except Exception as e:
        return f"Could not generate code: {e}"


def _edit_action(file_path, instruction, player) -> str:
    if not file_path:
        return "Please provide a file path to edit, sir."
    if not instruction:
        return "Please describe what change to make, sir."

    content, err = _read_file(file_path)
    if err:
        return err

    if player:
        player.write_log("[Code] Editing file...")

    prompt = f"""You are an expert code editor.
Apply the following change to the code below.
Return ONLY the complete updated code — no explanation, no markdown, no backticks.

Change: {instruction}

Original code:
{content}

Updated code:"""

    try:
        edited = _clean_code(_generate_with_fallback(prompt))
    except Exception as e:
        return f"Could not edit code: {e}"

    status = _save_file(Path(file_path), edited)
    print(f"[Code] ✅ Edited: {file_path}")
    return f"File edited. {status}\n\nPreview:\n{_preview(edited)}"


def _explain_action(file_path, code, player) -> str:
    if file_path and not code:
        code, err = _read_file(file_path)
        if err:
            return err
    if not code:
        return "Please provide code or a file path to explain, sir."

    if player:
        player.write_log("[Code] Analyzing code...")

    prompt = f"""Explain what this code does in simple, clear language.
Focus on: what it does, how it works, and any important details.
Be concise — 3 to 6 sentences maximum.

Code:
{code[:4000]}

Explanation:"""

    try:
        return _generate_with_fallback(prompt).strip()
    except Exception as e:
        return f"Could not explain code: {e}"


def _run_action(file_path, args, timeout, player) -> str:
    if not file_path:
        return "Please provide a file path to run, sir."
    p = Path(file_path)
    if not p.exists():
        return f"File not found: {file_path}"
    if player:
        player.write_log(f"[Code] Running {p.name}...")
    return _run_file(p, args, timeout)


def _optimize_action(file_path, code, language, output_path, player) -> str:

    if file_path and not code:
        code, err = _read_file(file_path)
        if err:
            return err
    if not code:
        return "Please provide code or a file path to optimize, sir."

    if player:
        player.write_log("[Code] Optimizing code...")

    lang = language or "python"

    prompt = f"""You are an expert {lang} developer and code reviewer.
Optimize the following code for:
1. Performance — eliminate unnecessary operations, use efficient data structures
2. Readability — clear variable names, proper formatting, logical structure
3. Best practices — modern {lang} patterns, error handling, type hints if applicable
4. Remove dead code, redundant comments, and unnecessary complexity

Return ONLY the optimized code — no explanation, no markdown, no backticks.

Original code:
{code[:6000]}

Optimized code:"""

    try:
        optimized = _clean_code(_generate_with_fallback(prompt))
    except Exception as e:
        return f"Could not optimize code: {e}"

    # Kaydet
    if file_path:
        save_path = Path(file_path)
    else:
        save_path = _resolve_save_path(output_path, lang)

    status = _save_file(save_path, optimized)
    print(f"[Code] ✅ Optimized: {save_path}")

    original_lines  = len(code.splitlines())
    optimized_lines = len(optimized.splitlines())
    diff = original_lines - optimized_lines

    return (
        f"Code optimized. {status}\n"
        f"Lines: {original_lines} → {optimized_lines} "
        f"({'−' if diff > 0 else '+'}{abs(diff)} lines)\n\n"
        f"Preview:\n{_preview(optimized)}"
    )


def _screen_debug_action(description, file_path, player, speak=None) -> str:

    if player:
        player.write_log("[Code] Taking screenshot for analysis...")

    print("[Code] 📸 Capturing screen for debug...")


    screenshot_path = _take_screenshot()
    if not screenshot_path:
        return "Could not take screenshot, sir. Please make sure PyAutoGUI is installed."


    file_content = ""
    if file_path:
        file_content, err = _read_file(file_path)
        if err:
            print(f"[Code] ⚠️ Could not read file: {err}")

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=_get_api_key())

        image_bytes  = screenshot_path.read_bytes()
        image_base64 = _image_to_base64(screenshot_path)

        user_question = description or "What error or problem do you see on the screen? How can it be fixed?"

        context = ""
        if file_content:
            context = f"\n\nAdditionally, here is the related file content:\n```\n{file_content[:4000]}\n```"

        analysis_prompt = f"""You are an expert programmer and debugger analyzing a screenshot.

User's question: {user_question}{context}

Please:
1. Identify any errors, exceptions, or problems visible on the screen
2. Explain what is causing the problem in simple terms
3. Provide a concrete fix or solution
4. If there's code visible, show the corrected version

Be specific and actionable. If you see an error message, quote it exactly."""

        contents = [
            types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
            analysis_prompt,
        ]

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents,
        )

        analysis = response.text.strip()
        print(f"[Code] ✅ Screen analysis complete")

        try:
            screenshot_path.unlink()
        except Exception:
            pass

        if file_path and file_content:

            code_match = re.search(r"```[a-zA-Z]*\n(.*?)```", analysis, re.DOTALL)
            if code_match:
                fixed_code = code_match.group(1).strip()
                save_path  = Path(file_path)
                _save_file(save_path, fixed_code)
                analysis += f"\n\n✅ Fixed code has been saved to: {file_path}"
                print(f"[Code] ✅ Fixed code saved: {file_path}")

        return analysis

    except Exception as e:

        try:
            screenshot_path.unlink()
        except Exception:
            pass
        return f"Screen analysis failed: {e}"


def code_helper(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
    speak=None
) -> str:
    """
    Called from main.py.

    parameters:
        action      : write | edit | explain | run | build | screen_debug | optimize | auto
        description : What the code should do / what change to make / what problem to analyze
        language    : Programming language (default: python)
        output_path : Where to save — user specifies full path or filename
        file_path   : Path to existing file (edit / explain / run / build / optimize)
        code        : Raw code string (explain/optimize without a file)
        args        : CLI argument list for run/build
        timeout     : Execution timeout in seconds (default: 30)
    """
    p           = parameters or {}
    action      = p.get("action", "auto").lower().strip()
    description = p.get("description", "").strip()
    language    = p.get("language", "python").strip()
    output_path = p.get("output_path", "").strip()
    file_path   = p.get("file_path", "").strip()
    code        = p.get("code", "").strip()
    args        = p.get("args", [])
    timeout     = int(p.get("timeout", 30))

    if action == "auto":
        action = _detect_intent(description, file_path, code)
        print(f"[Code] 🤖 Auto-detected: {action}")

    if action == "write":
        return _write_action(description, language, output_path, player)

    elif action == "edit":
        return _edit_action(
            file_path,
            description or p.get("instruction", ""),
            player
        )

    elif action == "explain":
        return _explain_action(file_path, code, player)

    elif action == "run":
        return _run_action(file_path, args, timeout, player)

    elif action == "build":
        return _build(description, language, output_path, args, timeout, speak, player)

    elif action == "optimize":
        return _optimize_action(file_path, code, language, output_path, player)

    elif action == "screen_debug":
        return _screen_debug_action(description, file_path, player, speak)

    else:
        return f"Unknown action: '{action}'. Use write, edit, explain, run, build, optimize, or screen_debug."