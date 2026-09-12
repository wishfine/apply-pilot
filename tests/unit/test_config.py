from pathlib import Path
from applypilot.core.config import (
    ApplyPilotConfig,
    get_app_home_dir,
    get_browser_dir,
    get_db_path,
)
from applypilot.core.exceptions import (
    AdapterError,
    ApplyPilotError,
    BrowserDriverError,
    ConfigurationError,
    DomainValidationError,
    StorageError,
)


def test_app_home_dir_resolution():
    home = get_app_home_dir()
    assert isinstance(home, Path)
    assert "ApplyPilot" in str(home) or "applypilot" in str(home)

def test_app_home_dir_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("APPLYPILOT_HOME", str(tmp_path / "custom_home"))
    home = get_app_home_dir()
    assert home == tmp_path / "custom_home"
    assert home.exists()
    assert home.is_dir()


def test_db_path_under_home():
    db_path = get_db_path()
    assert db_path.name == "applypilot.db"
    assert db_path.parent == get_app_home_dir()


def test_browser_dir_under_home():
    browser_dir = get_browser_dir()
    assert browser_dir.name == "browser_profile"
    assert browser_dir.parent == get_app_home_dir()
    assert browser_dir.is_dir()


def test_default_config_instantiation():
    cfg = ApplyPilotConfig()
    assert cfg.llm_provider == "openai_compatible"
    assert cfg.action_timeout_ms == 10000
    assert cfg.min_action_interval_ms == 150
    assert cfg.llm_api_base == "https://api.deepseek.com/v1"
    assert cfg.llm_model == "deepseek-chat"
    assert cfg.debug_screenshots is False


def test_exceptions_hierarchy():
    assert issubclass(ConfigurationError, ApplyPilotError)
    assert issubclass(DomainValidationError, ApplyPilotError)
    assert issubclass(StorageError, ApplyPilotError)
    assert issubclass(BrowserDriverError, ApplyPilotError)
    assert issubclass(AdapterError, ApplyPilotError)
