"""network_tools.py — ping, IP info, DNS lookup, port scan."""
import json
import socket
import subprocess
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed


def _ping(host: str, count: int = 4) -> str:
    try:
        r = subprocess.run(
            ["ping", "-c", str(count), "-W", "2", host],
            capture_output=True, text=True, timeout=count * 3 + 2,
        )
        if r.returncode == 0:
            lines = [l for l in r.stdout.splitlines() if "rtt" in l or "packets" in l]
            return "\n".join(lines) if lines else r.stdout.strip()[-300:]
        return f"Host erishib bo'lmadi: {host}"
    except subprocess.TimeoutExpired:
        return f"Ping vaqti tugadi: {host}"
    except Exception as e:
        return str(e)


def _my_ip() -> dict:
    try:
        req = urllib.request.Request(
            "https://ipinfo.io/json",
            headers={"User-Agent": "JarvisNetwork/1.0"},
        )
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"error": str(e)}


def _ip_info(ip: str) -> dict:
    try:
        req = urllib.request.Request(
            f"https://ipinfo.io/{ip}/json",
            headers={"User-Agent": "JarvisNetwork/1.0"},
        )
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"error": str(e)}


def _dns_lookup(host: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, None)
        return list({i[4][0] for i in infos})
    except socket.gaierror as e:
        return [f"DNS xatosi: {e}"]


def _scan_ports(host: str, ports: list[int], timeout: float = 1.0) -> dict[int, bool]:
    results = {}

    def _check(port: int) -> tuple[int, bool]:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return port, True
        except Exception:
            return port, False

    with ThreadPoolExecutor(max_workers=min(len(ports), 50)) as ex:
        futs = {ex.submit(_check, p): p for p in ports}
        for f in as_completed(futs):
            port, open_ = f.result()
            results[port] = open_
    return results


_COMMON_PORTS = [21, 22, 23, 25, 53, 80, 110, 143, 443, 445, 3306, 3389, 5432, 6379, 8080, 8443]


def network_tools(parameters=None, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    action = (params.get("action") or "myip").lower().strip()

    # ── MY IP ─────────────────────────────────────────────────────────────────
    if action in ("myip", "ip", "mening_ip"):
        data = _my_ip()
        if "error" in data:
            return f"IP ma'lumot olishda xato: {data['error']}"
        lines = [
            f"IP:       {data.get('ip', '?')}",
            f"Shahar:   {data.get('city', '?')}",
            f"Mintaqa:  {data.get('region', '?')}",
            f"Mamlakat: {data.get('country', '?')}",
            f"ISP:      {data.get('org', '?')}",
        ]
        return "\n".join(lines)

    # ── IP LOOKUP ─────────────────────────────────────────────────────────────
    if action in ("lookup", "ipinfo", "qidirish"):
        target = params.get("host") or params.get("ip") or ""
        if not target:
            return "IP manzil yoki domen ko'rsating."
        data = _ip_info(target)
        if "error" in data:
            return f"IP ma'lumot olishda xato: {data['error']}"
        lines = [
            f"IP:       {data.get('ip', '?')}",
            f"Shahar:   {data.get('city', '?')}",
            f"Mintaqa:  {data.get('region', '?')}",
            f"Mamlakat: {data.get('country', '?')}",
            f"ISP:      {data.get('org', '?')}",
            f"Timezone: {data.get('timezone', '?')}",
        ]
        return "\n".join(lines)

    # ── PING ──────────────────────────────────────────────────────────────────
    if action in ("ping", "tekshir"):
        host = params.get("host") or ""
        if not host:
            return "Ping uchun host ko'rsating."
        count = int(params.get("count", 4))
        if player: player.write_log(f"[Net] Ping {host} x{count}")
        return _ping(host, count)

    # ── DNS ───────────────────────────────────────────────────────────────────
    if action in ("dns", "nslookup", "resolve"):
        host = params.get("host") or ""
        if not host:
            return "DNS uchun domen ko'rsating."
        ips = _dns_lookup(host)
        return f"{host} → {', '.join(ips)}"

    # ── PORT SCAN ─────────────────────────────────────────────────────────────
    if action in ("scan", "portscan", "port"):
        host = params.get("host") or ""
        if not host:
            return "Port skan uchun host ko'rsating."
        raw_ports = params.get("ports")
        if raw_ports:
            if isinstance(raw_ports, list):
                ports = [int(p) for p in raw_ports]
            else:
                ports = [int(p.strip()) for p in str(raw_ports).split(",")]
        else:
            ports = _COMMON_PORTS

        if player: player.write_log(f"[Net] Scan {host} ({len(ports)} ports)")
        results = _scan_ports(host, ports)
        open_ports  = sorted(p for p, o in results.items() if o)
        closed_ports = sorted(p for p, o in results.items() if not o)

        lines = [f"Host: {host}"]
        if open_ports:
            lines.append(f"Ochiq portlar ({len(open_ports)}): {', '.join(map(str, open_ports))}")
        else:
            lines.append("Ochiq port topilmadi.")
        if closed_ports and len(closed_ports) <= 5:
            lines.append(f"Yopiq: {', '.join(map(str, closed_ports))}")
        return "\n".join(lines)

    return "Amallar: myip | lookup | ping | dns | scan"
