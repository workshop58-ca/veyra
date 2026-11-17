#!/usr/bin/env python3
"""Veyra — lightweight recording control interface."""

import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk

import os

sys.path.insert(
    0, str(Path(__file__).resolve().parents[2])
)
from veyra.settings import load_settings, save_settings

RECORDER = (
    Path(__file__).resolve().parents[1]
    / "backends"
    / "linux"
    / "legacy_recorder.py"
)


class VeyraApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Veyra — Workshop58")
        self.root.geometry("400x340")
        self.root.resizable(False, False)

        self.status = tk.StringVar(value="Checking...")
        self.busy = False
        self.recording = False
        self.request_id = 0
        self.status_check_running = False

        frame = ttk.Frame(root, padding=24)
        frame.pack(fill="both", expand=True)

        ttk.Label(
            frame,
            text="VEYRA",
            font=("Sans", 22, "bold"),
        ).pack(pady=(0, 4))

        ttk.Label(
            frame,
            text="Lightweight Screen Recorder",
        ).pack()

        ttk.Label(
            frame,
            textvariable=self.status,
            font=("Sans", 11),
        ).pack(pady=20)

        self.start_button = ttk.Button(
            frame,
            text="Start Recording",
            command=lambda: self.run_recorder("start"),
        )
        self.start_button.pack(fill="x", pady=4)

        self.stop_button = ttk.Button(
            frame,
            text="Stop Recording",
            command=lambda: self.run_recorder("stop"),
        )
        self.stop_button.pack(fill="x", pady=4)

        ttk.Button(
            frame,
            text="⚙ Settings",
            command=self.open_settings,
        ).pack(fill="x", pady=(12, 4))

        ttk.Label(
            frame,
            text="Powered by Workshop58",
            font=("Sans", 9),
        ).pack(pady=(14, 0))

        self.refresh_buttons()
        self.refresh_status()

    def open_settings(self):
        existing = getattr(self, "settings_window", None)
        if existing is not None and existing.winfo_exists():
            existing.lift()
            existing.focus_set()
            return

        window = tk.Toplevel(self.root)
        self.settings_window = window
        window.title("Veyra — Settings")
        window.geometry("420x620")
        window.resizable(False, False)
        window.transient(self.root)

        frame = ttk.Frame(window, padding=20)
        frame.pack(fill="both", expand=True)

        ttk.Label(
            frame,
            text="Recording Settings",
            font=("Sans", 16, "bold"),
        ).pack(anchor="w", pady=(0, 16))

        current = load_settings()

        fps = tk.StringVar(value=str(current["fps"]))
        resolution = tk.StringVar(value=current["resolution"])
        quality = tk.StringVar(value=current["quality"])

        fields = (
            ("Frame Rate", fps, ("30", "60")),
            ("Resolution", resolution, ("1280x720", "1920x1080")),
            ("Video Quality", quality, ("medium", "high", "very_high")),
        )

        for label, variable, options in fields:
            ttk.Label(
                frame,
                text=label,
                font=("Sans", 10, "bold"),
            ).pack(anchor="w", pady=(10, 3))

            ttk.Combobox(
                frame,
                textvariable=variable,
                values=options,
                state="readonly",
            ).pack(fill="x")

        ttk.Label(
            frame,
            text="Audio Sources",
            font=("Sans", 10, "bold"),
        ).pack(anchor="w", pady=(12, 4))

        system_audio = tk.BooleanVar(
            value=current["system_audio"]
        )
        microphone = tk.BooleanVar(
            value=current["microphone"]
        )

        ttk.Checkbutton(
            frame,
            text="System Audio",
            variable=system_audio,
        ).pack(anchor="w", pady=2)

        ttk.Checkbutton(
            frame,
            text="Microphone",
            variable=microphone,
        ).pack(anchor="w", pady=2)

        ttk.Label(
            frame,
            text="Output Folder",
            font=("Sans", 10, "bold"),
        ).pack(anchor="w", pady=(12, 4))

        output_dir = tk.StringVar(
            value=current["output_dir"]
        )

        output_row = ttk.Frame(frame)
        output_row.pack(fill="x")

        ttk.Entry(
            output_row,
            textvariable=output_dir,
            state="readonly",
        ).pack(side="left", fill="x", expand=True)

        def browse_output():
            from tkinter import filedialog
            selected = filedialog.askdirectory(
                parent=window,
                title="Select Recording Folder",
                initialdir=output_dir.get(),
            )
            if selected:
                output_dir.set(selected)

        ttk.Button(
            output_row,
            text="Browse",
            command=browse_output,
        ).pack(side="left", padx=(8, 0))

        def save():
            settings = load_settings()
            settings["fps"] = int(fps.get())
            settings["resolution"] = resolution.get()
            settings["quality"] = quality.get()
            settings["system_audio"] = system_audio.get()
            settings["microphone"] = microphone.get()
            settings["output_dir"] = output_dir.get()
            save_settings(settings)
            window.destroy()

        ttk.Button(
            frame,
            text="Save Settings",
            command=save,
        ).pack(fill="x", pady=(18, 4))

        ttk.Button(
            frame,
            text="Cancel",
            command=window.destroy,
        ).pack(fill="x", pady=4)



    def refresh_buttons(self):
        if self.busy:
            self.start_button.configure(state="disabled")
            self.stop_button.configure(state="disabled")
        else:
            self.start_button.configure(
                state="disabled" if self.recording else "normal"
            )
            self.stop_button.configure(
                state="normal" if self.recording else "disabled"
            )

    def refresh_status(self):
        if not self.busy and not self.status_check_running:
            self.status_check_running = True
            generation = self.request_id
            threading.Thread(
                target=self.check_status,
                args=(generation,),
                daemon=True,
            ).start()

        self.root.after(1000, self.refresh_status)

    def check_status(self, generation):
        try:
            result = subprocess.run(
                [sys.executable, str(RECORDER), "status"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            output = result.stdout.strip()
            if result.returncode != 0:
                message = (
                    result.stderr.strip()
                    or output
                    or "Status unavailable"
                )
                self.root.after(
                    0, lambda: self.finish_status_check(
                        generation, error=message
                    )
                )
                return

            recording = "Not recording" not in output
            if "Recorder status:" not in output:
                raise ValueError("Unexpected recorder status")

            self.root.after(
                0,
                lambda: self.finish_status_check(
                    generation, recording=recording
                ),
            )

        except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
            message = str(exc)
            self.root.after(
                0, lambda: self.finish_status_check(
                    generation, error=message
                )
            )

    def finish_status_check(
        self, generation, recording=None, error=None
    ):
        self.status_check_running = False

        if self.busy or generation != self.request_id:
            return

        if error is not None:
            self.status.set("Error: " + error[:80])
            return

        self.recording = recording
        self.status.set(
            "Recording..." if recording else "Ready"
        )
        self.refresh_buttons()

    def run_recorder(self, action):
        if self.busy:
            return

        self.busy = True
        self.request_id += 1
        request_id = self.request_id

        self.status.set(
            "Starting..." if action == "start"
            else "Stopping..."
        )
        self.refresh_buttons()

        threading.Thread(
            target=self.execute_command,
            args=(action, request_id),
            daemon=True,
        ).start()

    def execute_command(self, action, request_id):
        try:
            result = subprocess.run(
                [sys.executable, str(RECORDER), action],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )

            error = None
            if result.returncode != 0:
                error = (
                    result.stderr.strip()
                    or result.stdout.strip()
                    or "Recorder command failed"
                )

        except (OSError, subprocess.TimeoutExpired) as exc:
            error = str(exc)

        self.root.after(
            0,
            lambda: self.command_finished(
                action, request_id, error
            ),
        )

    def command_finished(self, action, request_id, error):
        if request_id != self.request_id:
            return

        self.busy = False

        if error:
            self.status.set("Error: " + error[:80])
        else:
            self.recording = action == "start"
            self.status.set(
                "Recording..." if self.recording
                else "Ready"
            )

        self.refresh_buttons()


if __name__ == "__main__":
    root = tk.Tk()
    VeyraApp(root)
    root.mainloop()
