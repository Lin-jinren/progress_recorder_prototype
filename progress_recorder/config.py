from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict, fields
from pathlib import Path

APP_DIR = Path.home() / ".progress_recorder"
CONFIG_PATH = APP_DIR / "config.json"
DB_PATH = APP_DIR / "progress.db"
EXPORT_DIR = APP_DIR / "exports"


@dataclass
class AppConfig:
    poll_seconds: int = 5
    # No keyboard/mouse input for this long counts as idle (not work).
    idle_threshold_seconds: int = 300
    watched_folders: list[str] = field(default_factory=list)
    watched_extensions: list[str] = field(
        default_factory=lambda: [
            ".pptx", ".ppt", ".pdf", ".docx", ".xlsx",
            ".py", ".m", ".lsf", ".txt", ".md",
        ]
    )
    # Checked before the built-in rules; see classifier.py for the format.
    classification_rules: list[dict] = field(default_factory=list)


def ensure_app_dirs() -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> AppConfig:
    ensure_app_dirs()
    if not CONFIG_PATH.exists():
        config = AppConfig()
        save_config(config)
        return config

    known = {f.name for f in fields(AppConfig)}
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        config = AppConfig(**{k: v for k, v in data.items() if k in known})
        config.poll_seconds = max(1, int(config.poll_seconds))
        config.idle_threshold_seconds = max(30, int(config.idle_threshold_seconds))
    except (json.JSONDecodeError, TypeError, ValueError, AttributeError):
        # Broken after manual editing: keep a copy instead of silently overwriting
        # it the next time the app saves its settings.
        try:
            CONFIG_PATH.replace(CONFIG_PATH.with_name("config.broken.json"))
        except OSError:
            pass
        return AppConfig()

    if not known.issubset(data):
        # Write newly added options so users can see and edit them.
        save_config(config)
    return config


def save_config(config: AppConfig) -> None:
    ensure_app_dirs()
    CONFIG_PATH.write_text(
        json.dumps(asdict(config), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
