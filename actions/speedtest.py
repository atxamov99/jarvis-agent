"""speedtest.py — Measure internet download/upload/ping via speedtest-cli Python module."""
import shutil
import subprocess
import sys


def _run_python_speedtest() -> str | None:
    try:
        import speedtest as st
        s = st.Speedtest(secure=True)
        s.get_best_server()
        down = s.download() / 1_000_000
        up   = s.upload()   / 1_000_000
        ping = s.results.ping
        return (
            f"Ping:     {ping:.1f} ms\n"
            f"Download: {down:.2f} Mbps\n"
            f"Upload:   {up:.2f} Mbps"
        )
    except Exception as e:
        return None


def _run_curl_download() -> str:
    """Rough download speed via curl against a 10 MB test file."""
    url = "http://speedtest.tele2.net/10MB.zip"
    try:
        r = subprocess.run(
            ["curl", "-o", "/dev/null", "--max-time", "20", "-w",
             "%{speed_download}", "-s", url],
            capture_output=True, text=True, timeout=25,
        )
        if r.returncode == 0 and r.stdout.strip():
            bps  = float(r.stdout.strip())
            mbps = bps / 1_000_000 * 8
            return f"Download: {mbps:.2f} Mbps (curl taxminiy)"
    except Exception:
        pass
    return "O'lchab bo'lmadi. speedtest-cli yoki curl kerak."


def speedtest(parameters=None, response=None, player=None, session_memory=None) -> str:
    if player:
        player.write_log("[Speedtest] Running…")

    result = _run_python_speedtest()
    if result:
        if player:
            player.write_log(f"[Speedtest] {result.splitlines()[0]}")
        return f"Internet tezligi:\n{result}"

    result = _run_curl_download()
    if player:
        player.write_log(f"[Speedtest] {result[:80]}")
    return result
