#!/usr/bin/env python3
"""Albion Lite Recorder: GNOME/Wayland shortcut-triggered recording.

Bind a GNOME custom shortcut to:
    bash -lc 'python3 "$HOME/albion_lite_recorder.py"'

Requires GPU Screen Recorder, installed natively or as its official Flatpak.
Each invocation starts or gracefully stops one recording. No resident Python loop.
"""

import fcntl
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# --- Change these settings if needed ---
OUTPUT_DIR = Path.home() / "Videos" / "Veyra"
FPS = 30
MAX_RESOLUTION = "1280x720"
RECORD_GAME_AUDIO = True     # Captures default system output (game + other audio).
QUALITY = "high"
# ---------------------------------------

APP_ID = "com.dec05eba.gpu_screen_recorder"
RUNTIME_DIR = Path(os.environ.get("XDG_RUNTIME_DIR", str(Path.home() / ".cache")))
STATE_DIR = RUNTIME_DIR / "veyra-recorder"
STATE_FILE = STATE_DIR / "active.json"
LOCK_FILE = STATE_DIR / "lock"
LOG_DIR = Path.home() / ".local" / "state" / "albion-lite-recorder"
LOG_FILE = LOG_DIR / "recorder.log"


def notify(title, body):
    print(f"{title}: {body}")
    if shutil.which("notify-send"):
        try:
            subprocess.Popen(
                ["notify-send", "-a", "Albion Lite Recorder", title, body],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError:
            pass



def play_recording_sound(name):
    sound = Path.home() / ".local/share/albion-lite-recorder" / (name + ".wav")
    if sound.is_file() and shutil.which("pw-play"):
        try:
            subprocess.Popen(
                ["pw-play", str(sound)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError:
            pass


def read_state():
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write_state(state):
    temp_file = STATE_FILE.with_suffix(".tmp")
    temp_file.write_text(json.dumps(state), encoding="utf-8")
    os.replace(temp_file, STATE_FILE)


def recorder_pids(output_filename):
    """Find *our* recorder by its unique -o path, never kill unrelated jobs."""
    matches = []
    proc = Path("/proc")
    for entry in proc.iterdir():
        if not entry.name.isdecimal():
            continue
        try:
            if entry.stat().st_uid != os.getuid():
                continue
            argv = [x.decode(errors="replace") for x in
                    (entry / "cmdline").read_bytes().split(b"\x00") if x]
            if not argv or Path(argv[0]).name != "gpu-screen-recorder":
                continue
            if "-o" not in argv:
                continue
            pos = argv.index("-o")
            if pos + 1 < len(argv) and argv[pos + 1] == output_filename:
                matches.append(int(entry.name))
        except (OSError, ValueError, IndexError):
            continue
    return matches


def is_running(pid):
    try:
        os.kill(pid, 0)
        return True
    except (OSError, TypeError):
        return False


def backend_command():
    executable = shutil.which("gpu-screen-recorder")
    if executable:
        return [executable]
    if shutil.which("flatpak"):
        check = subprocess.run(
            ["flatpak", "info", APP_ID],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=8,
            check=False,
        )
        if check.returncode == 0:
            return ["flatpak", "run", "--command=gpu-screen-recorder", APP_ID]
    return None


def main():
    if os.environ.get("XDG_SESSION_TYPE") != "wayland":
        notify("Unsupported session", "This version is configured for GNOME Wayland.")
        return 1

    STATE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with LOCK_FILE.open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = read_state()
        mode = sys.argv[1] if len(sys.argv) > 1 else "toggle"
        if mode not in ("toggle", "start", "stop", "status"):
            print("Usage: albion_lite_recorder.py [toggle|start|stop|status]", file=sys.stderr)
            return 2

        pids = recorder_pids(state["file"]) if state and "file" in state else []
        if mode == "status":
            print("Recorder status: Recording" if pids else "Recorder status: Not recording")
            return 0

        if pids:
            if mode == "start":
                notify("Already recording", state["file"])
                return 0
            if state.get("stopping"):
                notify("Saving video", "Recording is already stopping.")
                return 0
            try:
                for pid in pids:
                    os.kill(pid, signal.SIGINT)  # Graceful stop AND save MKV.
            except ProcessLookupError:
                pass
            state["stopping"] = True
            write_state(state)
            play_recording_sound("stop")
            notify("Recording stopped", "Saving video to: " + state["file"])
            return 0

        if state:
            elapsed = time.time() - float(state.get("started", 0))
            launcher = int(state.get("launcher_pid", -1))
            if elapsed < 20 and is_running(launcher):
                notify("Recorder starting", "Approve the screen-sharing dialog if shown.")
                return 0
            STATE_FILE.unlink(missing_ok=True)
        if mode == "stop":
            notify("Not recording", "Nothing to stop.")
            return 0

        backend = backend_command()
        if backend is None:
            notify("Recorder not installed", "Install GPU Screen Recorder (official Flatpak).")
            return 1

        import sys as _sys
        _sys.path.insert(
            0, str(Path(__file__).resolve().parents[3])
        )
        from veyra.settings import load_settings

        settings = load_settings()
        fps = settings["fps"]
        resolution = settings["resolution"]
        quality = settings["quality"]

        output_dir = Path(settings["output_dir"]).expanduser()
        output_dir.mkdir(parents=True, exist_ok=True)
        filename = str(output_dir / ("Veyra_" + datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + ".mkv"))
        cmd = backend + [
            "-w", "portal", "-restore-portal-session", "yes",
            "-f", str(fps), "-fm", "content", "-s", resolution,
            "-k", "h264", "-encoder", "gpu",
            "-fallback-cpu-encoding", "no", "-q", quality,
            "-cursor", "yes", "-v", "no",
        ]
        system_audio = settings["system_audio"]
        microphone = settings["microphone"]

        if system_audio and microphone:
            audio_source = "default_output|default_input"
        elif system_audio:
            audio_source = "default_output"
        elif microphone:
            audio_source = "default_input"
        else:
            audio_source = None

        if audio_source:
            cmd += ["-a", audio_source, "-ac", "opus"]
        cmd += ["-o", filename]

        with LOG_FILE.open("a", encoding="utf-8") as log:
            log.write("\n--- " + datetime.now().isoformat() + " ---\n")
            log.flush()
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        write_state({"file": filename, "started": time.time(),
                     "launcher_pid": process.pid, "stopping": False})
        play_recording_sound("start")
        notify("Recording requested", f"{fps} FPS, {resolution} max. First use: select the full screen.")
        return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        notify("Recorder error", str(exc))
        raise
