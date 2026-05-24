"""terminal_control — run shell commands, git operations, system tasks by voice."""
import subprocess
import shlex
import os
from pathlib import Path


_BLOCKED = [
    "rm -rf /", "rm -rf ~", "mkfs", "dd if=", ":(){:|:&};:",
    "chmod -R 777 /", "> /dev/sda",
]

def _is_blocked(cmd: str) -> bool:
    cl = cmd.lower()
    return any(b in cl for b in _BLOCKED)


def terminal_control(action: str, command: str = "", path: str = "", message: str = "") -> str:
    home = str(Path.home())
    work_dir = path if (path and os.path.isdir(path)) else home

    if action == "run":
        if not command:
            return "No command specified."
        if _is_blocked(command):
            return "Blocked: destructive command refused."
        try:
            result = subprocess.run(
                command, shell=True, capture_output=True, text=True,
                timeout=15, cwd=work_dir
            )
            out = (result.stdout or "").strip()
            err = (result.stderr or "").strip()
            if result.returncode != 0:
                return f"Error (code {result.returncode}): {err or out or 'no output'}"
            return out or "Done."
        except subprocess.TimeoutExpired:
            return "Command timed out (15s limit)."
        except Exception as e:
            return f"Failed: {e}"

    elif action == "git_status":
        try:
            r = subprocess.run(["git", "status", "--short"], capture_output=True, text=True,
                               timeout=5, cwd=work_dir)
            out = r.stdout.strip()
            if not out:
                return "Git: working tree clean."
            lines = out.split("\n")
            return f"Git status: {len(lines)} changed file(s). " + "; ".join(lines[:5])
        except Exception as e:
            return f"Git error: {e}"

    elif action == "git_commit":
        if not message:
            return "Commit message required."
        try:
            subprocess.run(["git", "add", "-A"], cwd=work_dir, timeout=5, check=True,
                           capture_output=True)
            r = subprocess.run(["git", "commit", "-m", message], cwd=work_dir,
                               capture_output=True, text=True, timeout=10)
            out = (r.stdout + r.stderr).strip()
            return out[:200] if out else "Committed."
        except subprocess.CalledProcessError as e:
            return f"Git error: {e.stderr.decode() if e.stderr else e}"
        except Exception as e:
            return f"Failed: {e}"

    elif action == "git_push":
        try:
            r = subprocess.run(["git", "push"], cwd=work_dir, capture_output=True,
                               text=True, timeout=30)
            out = (r.stdout + r.stderr).strip()
            return out[:200] if out else "Pushed."
        except Exception as e:
            return f"Push failed: {e}"

    elif action == "git_pull":
        try:
            r = subprocess.run(["git", "pull"], cwd=work_dir, capture_output=True,
                               text=True, timeout=30)
            out = (r.stdout + r.stderr).strip()
            return out[:200] if out else "Pulled."
        except Exception as e:
            return f"Pull failed: {e}"

    elif action == "git_log":
        try:
            r = subprocess.run(
                ["git", "log", "--oneline", "-8"],
                cwd=work_dir, capture_output=True, text=True, timeout=5
            )
            return r.stdout.strip() or "No commits yet."
        except Exception as e:
            return f"Git log error: {e}"

    elif action == "list_dir":
        try:
            entries = sorted(os.listdir(work_dir))
            dirs  = [e for e in entries if os.path.isdir(os.path.join(work_dir, e))]
            files = [e for e in entries if os.path.isfile(os.path.join(work_dir, e))]
            return f"Dir: {work_dir} — {len(dirs)} folders, {len(files)} files. " + \
                   ", ".join((dirs + files)[:10])
        except Exception as e:
            return f"Error: {e}"

    elif action == "processes":
        try:
            r = subprocess.run(["ps", "aux", "--sort=-%cpu"], capture_output=True,
                               text=True, timeout=5)
            lines = r.stdout.strip().split("\n")[1:6]
            return "Top processes: " + " | ".join(
                " ".join(l.split()[10:12]) + f" cpu:{l.split()[2]}%"
                for l in lines if l
            )
        except Exception as e:
            return f"Error: {e}"

    else:
        return f"Unknown action: {action}. Use run/git_status/git_commit/git_push/git_pull/git_log/list_dir/processes."
