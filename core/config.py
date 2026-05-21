"""
Settings dataclass for Post Pulse. All user-facing config lives here.
Paths are derived from data_dir so nothing is hardcoded elsewhere.
"""
import json
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_DATA_DIR = Path.home() / ".post-pulse"
CONFIG_FILENAME = "config.json"


@dataclass
class Settings:
    anthropic_api_key: str = ""
    scrape_limit: int = 10
    ai_feedback_enabled: bool = False
    data_dir: Path = field(default_factory=lambda: DEFAULT_DATA_DIR)

    @property
    def config_path(self) -> Path:
        return self.data_dir / CONFIG_FILENAME

    @property
    def db_path(self) -> Path:
        return self.data_dir / "tracker.db"

    @property
    def cookies_path(self) -> Path:
        return self.data_dir / "linkedin_cookies.json"

    @property
    def pipeline_state_path(self) -> Path:
        return self.data_dir / "pipeline_state.json"


def load(data_dir: Path | None = None) -> Settings:
    """
    Load settings from config.json in data_dir (default: ~/.post-pulse).
    Returns defaults if the file is missing or unreadable.
    """
    base = data_dir or DEFAULT_DATA_DIR
    config_path = base / CONFIG_FILENAME

    if not config_path.exists():
        return Settings(data_dir=base)

    try:
        with open(config_path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return Settings(data_dir=base)

    return Settings(
        anthropic_api_key=data.get("anthropic_api_key", ""),
        scrape_limit=data.get("scrape_limit", 10),
        ai_feedback_enabled=data.get("ai_feedback_enabled", False),
        data_dir=base,
    )


def save(settings: Settings) -> None:
    """Write settings to config.json, creating the data directory if needed."""
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "anthropic_api_key": settings.anthropic_api_key,
        "scrape_limit": settings.scrape_limit,
        "ai_feedback_enabled": settings.ai_feedback_enabled,
    }
    with open(settings.config_path, "w") as f:
        json.dump(data, f, indent=2)
