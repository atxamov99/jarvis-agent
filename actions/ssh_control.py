"""ssh_control.py — Execute commands on remote hosts via SSH."""
import json
import shutil
import subprocess
from pathlib import Path

_HOSTS_FILE = Path.home() / ".config" / "jarvis" / "ssh_hosts.json"


def _load_hosts() -> dict:
    try:
        return json.loads(_HOSTS_FILE.read_text())
    except Exception:
        return {}


def _save_hosts(data: dict):
    _HOSTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _HOSTS_FILE.write_text(json.dumps(data, indent=2))
    _HOSTS_FILE.chmod(0o600)


def _ssh_run(host: str, user: str, port: int, command: str,
             key: str = "", timeout: int = 30) -> tuple[int, str, str]:
    if not shutil.which("ssh"):
        return -1, "", "ssh topilmadi. OpenSSH o'rnatilgan bo'lsin."

    cmd = ["ssh", "-o", "StrictHostKeyChecking=no",
           "-o", "ConnectTimeout=10",
           "-o", "BatchMode=yes",
           "-p", str(port)]
    if key:
        cmd += ["-i", str(Path(key).expanduser())]
    cmd += [f"{user}@{host}", command]

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "Ulanish vaqti tugadi."
    except Exception as e:
        return -1, "", str(e)


def ssh_control(parameters=None, response=None, player=None, session_memory=None) -> str:
    params  = parameters or {}
    action  = (params.get("action") or "run").lower().strip()
    name    = (params.get("name") or "").strip()
    command = (params.get("command") or "").strip()

    # ── ADD HOST ──────────────────────────────────────────────────────────────
    if action in ("add", "qo'sh", "saqlash"):
        host = (params.get("host") or "").strip()
        user = (params.get("user") or "").strip()
        port = int(params.get("port", 22))
        key  = (params.get("key") or "").strip()
        if not name or not host or not user:
            return "name, host, user kerak. Masalan: name='server1', host='192.168.1.10', user='ubuntu'"
        hosts = _load_hosts()
        hosts[name.lower()] = {"host": host, "user": user, "port": port, "key": key}
        _save_hosts(hosts)
        if player: player.write_log(f"[SSH] Added host: {name}")
        return f"SSH host qo'shildi: {name} ({user}@{host}:{port})"

    # ── LIST HOSTS ────────────────────────────────────────────────────────────
    if action in ("list", "hosts", "ro'yxat"):
        hosts = _load_hosts()
        if not hosts:
            return "Saqlangan SSH hostlar yo'q. 'add' orqali qo'shing."
        lines = [f"• {n}: {v['user']}@{v['host']}:{v['port']}"
                 for n, v in hosts.items()]
        return f"SSH hostlar ({len(hosts)}):\n" + "\n".join(lines)

    # ── RUN COMMAND ───────────────────────────────────────────────────────────
    if action in ("run", "exec", "bajar", "ishla"):
        if not command:
            return "Buyruq ko'rsatilmagan (command parametri)."

        hosts = _load_hosts()
        if name:
            entry = hosts.get(name.lower())
            if not entry:
                available = ", ".join(hosts.keys()) if hosts else "yo'q"
                return f"'{name}' topilmadi. Mavjud: {available}"
        elif hosts:
            name, entry = next(iter(hosts.items()))
        else:
            # Direct connection via parameters
            host = (params.get("host") or "").strip()
            user = (params.get("user") or "root").strip()
            port = int(params.get("port", 22))
            key  = (params.get("key") or "").strip()
            if not host:
                return "host yoki name ko'rsatilmagan."
            entry = {"host": host, "user": user, "port": port, "key": key}

        if player: player.write_log(f"[SSH] {name}: {command[:50]}")
        rc, out, err = _ssh_run(
            entry["host"], entry["user"], entry["port"],
            command, entry.get("key", ""),
        )
        if rc == 0:
            result = out if out else "(chiqish yo'q)"
            return f"✓ {name} [{entry['user']}@{entry['host']}]:\n{result}"
        return f"✗ Xato (rc={rc}):\n{err or out}"

    # ── DELETE HOST ───────────────────────────────────────────────────────────
    if action in ("delete", "o'chir", "remove"):
        if not name:
            return "O'chirish uchun nom ko'rsating."
        hosts = _load_hosts()
        key   = next((k for k in hosts if name.lower() in k.lower()), None)
        if not key:
            return f"'{name}' topilmadi."
        del hosts[key]
        _save_hosts(hosts)
        return f"O'chirildi: {key}"

    return "Amallar: run | add | list | delete"
