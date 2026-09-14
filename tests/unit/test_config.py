from pathlib import Path
from applypilot.core.config import (
    ApplyPilotConfig,
    get_app_home_dir,
    get_browser_dir,
    get_config_path,
    get_db_path,
    load_config,
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
    assert home.stat().st_mode & 0o777 == 0o700


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
    assert cfg.job_url is None


def test_load_config_reads_job_url_from_app_home(monkeypatch, tmp_path):
    monkeypatch.setenv("APPLYPILOT_HOME", str(tmp_path))
    config_path = get_config_path()
    config_path.write_text(
        "job_url: 'https://example.com/apply?id=123'\n", encoding="utf-8"
    )
    config = load_config()
    assert config.job_url == "https://example.com/apply?id=123"


def test_load_config_missing_file_returns_defaults(tmp_path):
    config = load_config(tmp_path / "missing.yaml")
    assert config.job_url is None


def test_exceptions_hierarchy():
    assert issubclass(ConfigurationError, ApplyPilotError)
    assert issubclass(DomainValidationError, ApplyPilotError)
    assert issubclass(StorageError, ApplyPilotError)
    assert issubclass(BrowserDriverError, ApplyPilotError)
    assert issubclass(AdapterError, ApplyPilotError)
