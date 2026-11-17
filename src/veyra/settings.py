"""Persistent Veyra recording settings."""

import json
import os
from pathlib import Path

CONFIG_DIR = (
    Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    / "veyra"
)
CONFIG_FILE = CONFIG_DIR / "settings.json"

DEFAULTS = {
    "fps": 30,
    "resolution": "1280x720",
    "quality": "high",
    "system_audio": True,
    "microphone": True,
    "output_dir": str(Path.home() / "Videos" / "Veyra"),
}


def load_settings():
    settings = DEFAULTS.copy()

    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                settings.update({
                    key: value
                    for key, value in data.items()
                    if key in DEFAULTS
                })
        except (OSError, ValueError):
            pass

    return settings


def save_settings(settings):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)

    data = {
        key: settings.get(key, default)
        for key, default in DEFAULTS.items()
    }

    temporary = CONFIG_FILE.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(data, indent=2),
        encoding="utf-8",
    )
    temporary.replace(CONFIG_FILE)
