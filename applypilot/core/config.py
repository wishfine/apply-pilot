import os
from pathlib import Path
from platformdirs import user_data_dir
from pydantic import BaseModel
import yaml

from applypilot.core.exceptions import ConfigurationError

def get_app_home_dir() -> Path:
    env_home = os.getenv("APPLYPILOT_HOME")
    base = Path(env_home) if env_home else Path(user_data_dir("ApplyPilot", "ApplyPilot"))
    base.mkdir(parents=True, exist_ok=True)
    try:
        base.chmod(0o700)
    except OSError:
        pass
    return base

def get_db_path() -> Path:
    return get_app_home_dir() / "applypilot.db"

def get_browser_dir() -> Path:
    browser_dir = get_app_home_dir() / "browser_profile"
    browser_dir.mkdir(parents=True, exist_ok=True)
    try:
        browser_dir.chmod(0o700)
    except OSError:
        pass
    return browser_dir

def get_config_path() -> Path:
    """Return the optional user configuration file path."""
    return get_app_home_dir() / "config.yaml"

class ApplyPilotConfig(BaseModel):
    llm_provider: str = "openai_compatible"
    llm_api_base: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-chat"
    action_timeout_ms: int = 10000
    min_action_interval_ms: int = 150
    debug_screenshots: bool = False
    job_url: str | None = None


def load_config(path: Path | str | None = None) -> ApplyPilotConfig:
    """Load optional YAML configuration, using defaults when it is absent."""
    config_path = Path(path) if path is not None else get_config_path()
    if not config_path.exists():
        return ApplyPilotConfig()
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise ValueError("configuration root must be a YAML mapping")
        # Accept the natural nested form as well as the concise top-level key.
        apply_section = raw.get("apply")
        if isinstance(apply_section, dict) and "job_url" not in raw:
            raw["job_url"] = apply_section.get("job_url") or apply_section.get("url")
        return ApplyPilotConfig.model_validate(raw)
    except Exception as exc:
        raise ConfigurationError(f"Failed to load config {config_path}: {exc}") from exc
