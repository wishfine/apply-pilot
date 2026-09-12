from pathlib import Path
from platformdirs import user_data_dir
from pydantic import BaseModel, Field

def get_app_home_dir() -> Path:
    base = Path(user_data_dir("ApplyPilot", "ApplyPilot"))
    base.mkdir(parents=True, exist_ok=True)
    return base

def get_db_path() -> Path:
    return get_app_home_dir() / "applypilot.db"

def get_browser_dir() -> Path:
    browser_dir = get_app_home_dir() / "browser_profile"
    browser_dir.mkdir(parents=True, exist_ok=True)
    return browser_dir

class ApplyPilotConfig(BaseModel):
    llm_provider: str = "openai_compatible"
    llm_api_base: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-chat"
    action_timeout_ms: int = 10000
    min_action_interval_ms: int = 150
    debug_screenshots: bool = False
