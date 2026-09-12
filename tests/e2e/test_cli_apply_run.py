import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from typer.testing import CliRunner
import yaml

from applypilot.cli.main import app
from applypilot.domain.job import ApplicationStatus

runner = CliRunner()


@pytest.fixture
def sample_profile_file(tmp_path: Path) -> Path:
    profile_data = {
        "profile_id": "cand_cli_01",
        "identity": {
            "name": "张三",
            "gender": "male",
            "birth_date": "2000-01-01",
        },
        "contact": {
            "mobile": "13800000000",
            "email": "zhangsan@example.com",
            "current_city": "北京",
        },
    }
    p_file = tmp_path / "profile.yaml"
    p_file.write_text(yaml.safe_dump(profile_data, allow_unicode=True), encoding="utf-8")
    return p_file


def test_apply_run_missing_profile_exits_with_error(tmp_path: Path):
    non_existent = tmp_path / "non_existent.yaml"
    res = runner.invoke(
        app,
        ["apply", "run", "-u", "https://jobs.example.com/apply/1", "-p", str(non_existent)],
    )
    assert res.exit_code == 1
    assert "Profile file not found at" in res.stdout
    assert "applypilot profile import" in res.stdout


def test_apply_run_default_profile_missing_exits_with_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APPLYPILOT_HOME", str(tmp_path))
    res = runner.invoke(
        app,
        ["apply", "run", "-u", "https://jobs.example.com/apply/1"],
    )
    assert res.exit_code == 1
    assert "Profile file not found at" in res.stdout


def test_apply_run_success_flow(sample_profile_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APPLYPILOT_HOME", str(tmp_path))

    mock_browser = AsyncMock()
    mock_browser.close = AsyncMock()
    mock_browser.wait_for_user = AsyncMock()

    with (
        patch("applypilot.cli.main.PlaywrightBackend", return_value=mock_browser),
        patch(
            "applypilot.cli.main.ApplyEngine.run_application_target",
            new_callable=AsyncMock,
            return_value=ApplicationStatus.READY_REVIEW,
        ) as mock_run_target,
    ):
        res = runner.invoke(
            app,
            [
                "apply",
                "run",
                "-u",
                "https://jobs.bytedance.com/campus/position/123",
                "-p",
                str(sample_profile_file),
                "--headless",
            ],
        )
        assert res.exit_code == 0
        assert "READY_REVIEW" in res.stdout
        assert "终审" in res.stdout
        mock_run_target.assert_awaited_once()
        mock_browser.close.assert_awaited_once()


def test_apply_run_paused_flow(sample_profile_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APPLYPILOT_HOME", str(tmp_path))

    mock_browser = AsyncMock()
    mock_browser.close = AsyncMock()

    with (
        patch("applypilot.cli.main.PlaywrightBackend", return_value=mock_browser),
        patch(
            "applypilot.cli.main.ApplyEngine.run_application_target",
            new_callable=AsyncMock,
            return_value=ApplicationStatus.PAUSED,
        ) as mock_run_target,
    ):
        res = runner.invoke(
            app,
            [
                "apply",
                "run",
                "-u",
                "https://jobs.bytedance.com/campus/position/123",
                "-p",
                str(sample_profile_file),
                "--headless",
            ],
        )
        assert res.exit_code == 0
        assert "PAUSED" in res.stdout
        assert "网申已暂停" in res.stdout
        mock_run_target.assert_awaited_once()
        mock_browser.close.assert_awaited_once()


def test_apply_run_no_interactive_flag(
    sample_profile_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("APPLYPILOT_HOME", str(tmp_path))

    mock_browser = AsyncMock()
    mock_browser.close = AsyncMock()

    with (
        patch("applypilot.cli.main.PlaywrightBackend", return_value=mock_browser),
        patch("applypilot.cli.main.ApplyEngine") as mock_engine_cls,
    ):
        mock_engine = mock_engine_cls.return_value
        mock_engine.run_application_target = AsyncMock(
            return_value=ApplicationStatus.READY_REVIEW
        )

        res = runner.invoke(
            app,
            [
                "apply",
                "run",
                "-u",
                "https://jobs.bytedance.com/campus/position/123",
                "-p",
                str(sample_profile_file),
                "--no-interactive-readiness",
                "--headless",
            ],
        )
        assert res.exit_code == 0
        mock_engine_cls.assert_called_once()
        _, kwargs = mock_engine_cls.call_args
        assert kwargs.get("interactive_readiness") is False


def test_apply_run_interactive_readiness_pause_choice(
    sample_profile_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("APPLYPILOT_HOME", str(tmp_path))
    mock_browser = AsyncMock()

    async def fake_run_target(target, profile):
        from applypilot.modules.apply.readiness import (
            FieldReadinessItem,
            FieldReadinessStatus,
            ReadinessReport,
        )

        report = ReadinessReport(
            is_ready=False,
            missing_required=[
                FieldReadinessItem(
                    field_sig="sig_mobile",
                    label="手机号",
                    section_title="基本信息",
                    is_required=True,
                    status=FieldReadinessStatus.REQUIRED_MISSING,
                    profile_path="contact.mobile",
                    suggested_fix="请填写手机号",
                )
            ],
            total_fields=1,
            filled_fields=0,
            optional_empty_fields=0,
            all_items=[],
        )
        return await fake_engine.readiness_resolver(None, report, profile, None)

    fake_engine = None

    with (
        patch("applypilot.cli.main.PlaywrightBackend", return_value=mock_browser),
        patch("applypilot.cli.main.ApplyEngine") as mock_engine_cls,
    ):
        mock_instance = MagicMock()
        mock_instance.run_application_target = AsyncMock(side_effect=fake_run_target)

        def capture_init(*args, **kwargs):
            nonlocal fake_engine
            fake_engine = mock_instance
            fake_engine.readiness_resolver = kwargs.get("readiness_resolver")
            return mock_instance

        mock_engine_cls.side_effect = capture_init

        res = runner.invoke(
            app,
            [
                "apply",
                "run",
                "-u",
                "https://jobs.bytedance.com/campus/123",
                "-p",
                str(sample_profile_file),
                "--headless",
            ],
            input="3\n",
        )
        assert res.exit_code == 0
        assert "PAUSED" in res.stdout


def test_apply_run_interactive_readiness_writeback_choice(
    sample_profile_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("APPLYPILOT_HOME", str(tmp_path))
    mock_browser = AsyncMock()

    async def fake_run_target(target, profile):
        from applypilot.modules.apply.readiness import (
            FieldReadinessItem,
            FieldReadinessStatus,
            ReadinessReport,
        )

        report = ReadinessReport(
            is_ready=False,
            missing_required=[
                FieldReadinessItem(
                    field_sig="sig_city",
                    label="现居城市",
                    section_title="基本信息",
                    is_required=True,
                    status=FieldReadinessStatus.REQUIRED_MISSING,
                    profile_path="contact.current_city",
                    suggested_fix="请填写城市",
                )
            ],
            total_fields=1,
            filled_fields=0,
            optional_empty_fields=0,
            all_items=[],
        )
        mock_el = AsyncMock()
        mock_el.clear_text = AsyncMock()
        mock_el.type_text = AsyncMock()
        mock_page = AsyncMock()
        mock_page.find = AsyncMock(return_value=mock_el)

        fake_engine.mock_el = mock_el
        fake_engine.mock_page = mock_page

        res = await fake_engine.readiness_resolver(mock_page, report, profile, None)
        if res is True:
            return ApplicationStatus.READY_REVIEW
        return ApplicationStatus.PAUSED

    fake_engine = None

    with (
        patch("applypilot.cli.main.PlaywrightBackend", return_value=mock_browser),
        patch("applypilot.cli.main.ApplyEngine") as mock_engine_cls,
    ):
        mock_instance = MagicMock()
        mock_instance.run_application_target = AsyncMock(side_effect=fake_run_target)

        def capture_init(*args, **kwargs):
            nonlocal fake_engine
            fake_engine = mock_instance
            fake_engine.readiness_resolver = kwargs.get("readiness_resolver")
            return mock_instance

        mock_engine_cls.side_effect = capture_init

        res = runner.invoke(
            app,
            [
                "apply",
                "run",
                "-u",
                "https://jobs.bytedance.com/campus/123",
                "-p",
                str(sample_profile_file),
                "--headless",
            ],
            input="2\n广州\n",
        )
        assert res.exit_code == 0
        assert "已同步回写" in res.stdout
        # Verify file content
        content = yaml.safe_load(sample_profile_file.read_text(encoding="utf-8"))
        assert content["contact"]["current_city"] == "广州"
        # Verify DOM element interaction
        fake_engine.mock_page.find.assert_awaited()
        fake_engine.mock_el.type_text.assert_awaited_with("广州")


def test_apply_run_configures_user_prompt_handler(
    sample_profile_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("APPLYPILOT_HOME", str(tmp_path))

    mock_browser = AsyncMock()
    mock_browser.close = AsyncMock()

    with (
        patch("applypilot.cli.main.PlaywrightBackend", return_value=mock_browser) as mock_backend_cls,
        patch(
            "applypilot.cli.main.ApplyEngine.run_application_target",
            new_callable=AsyncMock,
            return_value=ApplicationStatus.READY_REVIEW,
        ),
    ):
        res = runner.invoke(
            app,
            [
                "apply",
                "run",
                "-u",
                "https://jobs.bytedance.com/campus/123",
                "-p",
                str(sample_profile_file),
                "--headless",
            ],
        )
        assert res.exit_code == 0
        mock_backend_cls.assert_called_once()
        _, kwargs = mock_backend_cls.call_args
        handler = kwargs.get("user_prompt_handler")
        assert handler is not None and callable(handler)


def test_apply_run_interactive_readiness_browser_fill_choice(
    sample_profile_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("APPLYPILOT_HOME", str(tmp_path))
    mock_browser = AsyncMock()
    mock_browser.wait_for_user = AsyncMock()

    async def fake_run_target(target, profile):
        from applypilot.modules.apply.readiness import (
            FieldReadinessItem,
            FieldReadinessStatus,
            ReadinessReport,
        )

        report = ReadinessReport(
            is_ready=False,
            missing_required=[
                FieldReadinessItem(
                    field_sig="sig_city",
                    label="现居城市",
                    section_title="基本信息",
                    is_required=True,
                    status=FieldReadinessStatus.REQUIRED_MISSING,
                    profile_path="contact.current_city",
                    suggested_fix="请填写城市",
                )
            ],
            total_fields=1,
            filled_fields=0,
            optional_empty_fields=0,
            all_items=[],
        )
        res = await fake_engine.readiness_resolver(None, report, profile, None)
        if res is True:
            return ApplicationStatus.READY_REVIEW
        return ApplicationStatus.PAUSED

    fake_engine = None

    with (
        patch("applypilot.cli.main.PlaywrightBackend", return_value=mock_browser),
        patch("applypilot.cli.main.ApplyEngine") as mock_engine_cls,
    ):
        mock_instance = MagicMock()
        mock_instance.run_application_target = AsyncMock(side_effect=fake_run_target)

        def capture_init(*args, **kwargs):
            nonlocal fake_engine
            fake_engine = mock_instance
            fake_engine.readiness_resolver = kwargs.get("readiness_resolver")
            return mock_instance

        mock_engine_cls.side_effect = capture_init

        res = runner.invoke(
            app,
            [
                "apply",
                "run",
                "-u",
                "https://jobs.bytedance.com/campus/123",
                "-p",
                str(sample_profile_file),
                "--headless",
            ],
            input="1\n",
        )
        assert res.exit_code == 0
        mock_browser.wait_for_user.assert_awaited_once()


def test_update_in_memory_profile_auto_instantiates_soe_extended():
    from applypilot.cli.main import _update_in_memory_profile
    from applypilot.domain.profile import CandidateProfile, SOEExtendedInfo

    prof = CandidateProfile(profile_id="cand_test")
    assert prof.soe_extended is None

    _update_in_memory_profile(prof, "soe_extended.political_status", "中共党员")
    assert prof.soe_extended is not None
    assert isinstance(prof.soe_extended, SOEExtendedInfo)
    assert prof.soe_extended.political_status == "中共党员"

    # Subsequent update preserves existing instance
    _update_in_memory_profile(prof, "soe_extended.native_place", "广东省广州市")
    assert prof.soe_extended.political_status == "中共党员"
    assert prof.soe_extended.native_place == "广东省广州市"

    # Dict representation test
    dict_prof = {}
    _update_in_memory_profile(dict_prof, "soe_extended.political_status", "共青团员")
    assert dict_prof["soe_extended"]["political_status"] == "共青团员"


def test_apply_run_non_headless_no_duplicate_wait_for_user(
    sample_profile_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("APPLYPILOT_HOME", str(tmp_path))

    mock_browser = AsyncMock()
    mock_browser.close = AsyncMock()
    mock_browser.wait_for_user = AsyncMock()

    with (
        patch("applypilot.cli.main.PlaywrightBackend", return_value=mock_browser),
        patch(
            "applypilot.cli.main.ApplyEngine.run_application_target",
            new_callable=AsyncMock,
            return_value=ApplicationStatus.READY_REVIEW,
        ) as mock_run_target,
    ):
        res = runner.invoke(
            app,
            [
                "apply",
                "run",
                "-u",
                "https://jobs.bytedance.com/campus/position/123",
                "-p",
                str(sample_profile_file),
                # non-headless mode: no --headless flag
            ],
        )
        assert res.exit_code == 0
        assert "READY_REVIEW" in res.stdout
        assert "终审确认" in res.stdout
        mock_run_target.assert_awaited_once()
        # main.py does not make a redundant wait_for_user call
        mock_browser.wait_for_user.assert_not_called()
        mock_browser.close.assert_awaited_once()

