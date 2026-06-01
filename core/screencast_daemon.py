#!/usr/bin/env python3
"""screencast_daemon.py — Silent (flash-free) screen frame provider for Wayland.

Run with SYSTEM python3 (needs python-dbus + PyGObject/GStreamer, which the venv
lacks). Uses the XDG ScreenCast portal (PipeWire) so capture produces NO flash —
unlike gnome-screenshot. With persist_mode the "Share screen" dialog appears only
the FIRST time ever; afterwards it streams silently.

Continuously writes the latest frame as JPEG to data/_live_frame.jpg. The JARVIS
Time Machine / vision tools read that file instead of flashing the screen.
"""
import os
import sys
import json
import signal
from pathlib import Path

import gi
gi.require_version("Gst", "1.0")
from gi.repository import Gst, GLib

import dbus
import dbus.mainloop.glib
dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

BASE       = Path(__file__).resolve().parent.parent
OUT        = BASE / "data" / "_live_frame.jpg"
TOKEN_FILE = Path.home() / ".config" / "jarvis" / "screencast_token.txt"
OUT.parent.mkdir(parents=True, exist_ok=True)
TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)

Gst.init(None)
_loop = GLib.MainLoop()
_bus = dbus.SessionBus()
_portal = _bus.get_object("org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop")
_screencast = dbus.Interface(_portal, "org.freedesktop.portal.ScreenCast")

_sender = _bus.get_unique_name()[1:].replace(".", "_")
_req_counter = [0]


def _request_path(token):
    return f"/org/freedesktop/portal/desktop/request/{_sender}/{token}"


def _new_token(prefix):
    _req_counter[0] += 1
    return f"{prefix}{_req_counter[0]}"


def _do(make_call, on_response, extra_opts=None):
    """Run a portal call whose options' handle_token matches the Request path."""
    token = _new_token("jv")
    path = _request_path(token)
    holder = {"sig": None}

    def _handler(code, results):
        try:
            if holder["sig"]:
                holder["sig"].remove()
        except Exception:
            pass
        on_response(code, results)

    holder["sig"] = _bus.add_signal_receiver(
        _handler, signal_name="Response",
        dbus_interface="org.freedesktop.portal.Request", path=path,
    )
    opts = {"handle_token": token}
    if extra_opts:
        opts.update(extra_opts)
    make_call(opts)


_session = {"handle": None, "node": None, "pipeline": None}


def _start_pipeline(fd, node_id):
    desc = (
        f"pipewiresrc fd={fd} path={node_id} do-timestamp=true keepalive-time=1000 ! "
        "videoconvert ! videorate ! video/x-raw,framerate=2/1 ! "
        "jpegenc quality=72 ! appsink name=sink max-buffers=1 drop=true emit-signals=false"
    )
    pipeline = Gst.parse_launch(desc)
    sink = pipeline.get_by_name("sink")
    pipeline.set_state(Gst.State.PLAYING)
    _session["pipeline"] = pipeline

    def _pull():
        try:
            sample = sink.emit("try-pull-sample", 200 * Gst.MSECOND) if hasattr(sink, "emit") else None
            if sample is None:
                sample = sink.try_pull_sample(200 * Gst.MSECOND)
        except Exception:
            try:
                sample = sink.try_pull_sample(200 * Gst.MSECOND)
            except Exception:
                sample = None
        if sample:
            buf = sample.get_buffer()
            ok, minfo = buf.map(Gst.MapFlags.READ)
            if ok:
                try:
                    tmp = str(OUT) + ".tmp"
                    with open(tmp, "wb") as f:
                        f.write(minfo.data)
                    os.replace(tmp, str(OUT))
                finally:
                    buf.unmap(minfo)
        return True  # keep timer

    GLib.timeout_add(2000, _pull)   # write latest frame every 2s
    print("[ScreencastDaemon] streaming (silent, no flash).", flush=True)


def _on_pipewire_fd(node_id):
    def _handler():
        try:
            fd_obj = _screencast.OpenPipeWireRemote(_session["handle"], {},
                                                    dbus_interface="org.freedesktop.portal.ScreenCast")
            fd = fd_obj.take()
            _start_pipeline(fd, node_id)
        except Exception as e:
            print(f"[ScreencastDaemon] OpenPipeWireRemote error: {e}", flush=True)
            _loop.quit()
        return False
    GLib.idle_add(_handler)


def _on_started(code, results):
    if code != 0:
        print(f"[ScreencastDaemon] Start denied/cancelled (code {code}).", flush=True)
        _loop.quit(); return
    streams = results.get("streams")
    if not streams:
        print("[ScreencastDaemon] No streams.", flush=True)
        _loop.quit(); return
    node_id = streams[0][0]
    if "restore_token" in results:
        try: TOKEN_FILE.write_text(str(results["restore_token"]), encoding="utf-8")
        except Exception: pass
    _on_pipewire_fd(node_id)


def _on_sources_selected(code, results):
    if code != 0:
        print(f"[ScreencastDaemon] SelectSources failed (code {code}).", flush=True)
        _loop.quit(); return
    _do(lambda o: _screencast.Start(_session["handle"], "", o,
            dbus_interface="org.freedesktop.portal.ScreenCast"),
        _on_started)


def _on_session_created(code, results):
    if code != 0:
        print(f"[ScreencastDaemon] CreateSession failed (code {code}).", flush=True)
        _loop.quit(); return
    _session["handle"] = results["session_handle"]
    extra = {
        "types": dbus.UInt32(1),         # 1 = MONITOR
        "multiple": False,
        "cursor_mode": dbus.UInt32(2),   # 2 = embedded
        "persist_mode": dbus.UInt32(2),  # 2 = persistent (one dialog ever)
    }
    if TOKEN_FILE.exists():
        try:
            rt = TOKEN_FILE.read_text(encoding="utf-8").strip()
            if rt:
                extra["restore_token"] = rt
        except Exception:
            pass
    _do(lambda o: _screencast.SelectSources(_session["handle"], o,
            dbus_interface="org.freedesktop.portal.ScreenCast"),
        _on_sources_selected, extra_opts=extra)


def main():
    ssess = _new_token("sess")
    _do(lambda o: _screencast.CreateSession(o,
            dbus_interface="org.freedesktop.portal.ScreenCast"),
        _on_session_created, extra_opts={"session_handle_token": ssess})

    for s in (signal.SIGINT, signal.SIGTERM):
        signal.signal(s, lambda *a: _loop.quit())
    try:
        _loop.run()
    finally:
        if _session["pipeline"]:
            _session["pipeline"].set_state(Gst.State.NULL)


if __name__ == "__main__":
    main()
