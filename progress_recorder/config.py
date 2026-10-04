from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path

APP_DIR = Path.home() / ".progress_recorder"
CONFIG_PATH = APP_DIR / "config.json"
DB_PATH = APP_DIR / "progress.db"
EXPORT_DIR = APP_DIR / "exports"


@dataclass
class AppConfig:
    poll_seconds: int = 5
    watched_folders: list[str] = field(default_factory=list)
    watched_extensions: list[str] = field(
        default_factory=lambda: [
            ".pptx", ".ppt", ".pdf", ".docx", ".xlsx",
            ".py", ".m", ".lsf", ".txt", ".md",
        ]
    )


def ensure_app_dirs() -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> AppConfig:
    ensure_app_dirs()
    if not CONFIG_PATH.exists():
        config = AppConfig()
        save_config(config)
        return config

    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return AppConfig(**data)
    except (json.JSONDecodeError, TypeError):
        # If the config is broken after manual editing, keep the app usable.
        return AppConfig()


def save_config(config: AppConfig) -> None:
    ensure_app_dirs()
    CONFIG_PATH.write_text(
        json.dumps(asdict(config), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
