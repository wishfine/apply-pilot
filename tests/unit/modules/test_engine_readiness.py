from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
import pytest

from applypilot.domain.job import ApplicationStatus, ApplicationTarget, Job
from applypilot.domain.profile import CandidateProfile, ContactInfo, IdentityInfo
from applypilot.modules.apply import ApplyEngine
from applypilot.storage.database import init_db
from applypilot.storage.repositories import (
    ApplicationRepository,
    CheckpointRepository,
    EventRepository,
)


def _create_sample_profile(mobile: str | None = "13800138000") -> CandidateProfile:
    return CandidateProfile(
        profile_id="cand_test_readiness",
        identity=IdentityInfo(
            name="张三",
            gender="male",
        ),
        contact=ContactInfo(
            mobile=mobile,
            email="zhangsan@example.com",
            current_city="北京",
        ),
    )


def _create_sample_target(provider: str | None = "generic") -> ApplicationTarget:
    return ApplicationTarget(
        target_id="tgt_test_readiness",
        job=Job(
            job_id="job_readiness_100",
            title="Python开发工程师",
            company_name="测试科技有限公司",
            description_raw="岗位要求熟悉Python，具备良好编程能力。",
            source_channel="url",
            source_url="https://jobs.example.com/apply/100",
            apply_url="https://jobs.example.com/apply/100",
        ),
        provider=provider,
    )


def _create_mock_browser_and_page():
    mock_browser = AsyncMock()
    mock_page = AsyncMock()
    mock_browser.open_page.return_value = mock_page
    mock_browser.wait_for_user = AsyncMock()
    return mock_browser, mock_page


@pytest.mark.asyncio
async def test_readiness_audit_halts_and_prompts_user_when_required_missing(tmp_path: Path):
    db_file = tmp_path / "test.db"
    await init_db(db_file)
    mock_browser, mock_page = _create_mock_browser_and_page()

    # Create mock form element for required mobile phone, but profile has mobile=None
    mock_el = AsyncMock()
    mock_el.get_attribute = AsyncMock(
        side_effect=lambda attr: {
            "name": "手机号",
            "type": "text",
            "id": "mobile_field",
            "required": "required",
            "value": "",
        }.get(attr)
    )
    mock_el.get_text = AsyncMock(return_value="")
    mock_page.find_all = AsyncMock(return_value=[mock_el])

    engine = ApplyEngine(db_path=db_file, browser_backend=mock_browser, interactive_readiness=True)
    profile = _create_sample_profile(mobile=None)
    target = _create_sample_target(provider="generic")

    status = await engine.run_application_target(target, profile)
    assert status == ApplicationStatus.PAUSED

    # A prompt alone does not resolve the missing field; no final-review prompt.
    assert mock_browser.wait_for_user.await_count == 1
    prompt_call = mock_browser.wait_for_user.await_args_list[0][0][0]
    assert "阶段【single_page】存在 1 个必填缺失项：手机号" in prompt_call
    assert "请在浏览器中核对补填" in prompt_call


@pytest.mark.asyncio
async def test_readiness_audit_records_event_in_repository(tmp_path: Path):
    db_file = tmp_path / "test.db"
    await init_db(db_file)
    mock_browser, mock_page = _create_mock_browser_and_page()

    mock_el = AsyncMock()
    mock_el.get_attribute = AsyncMock(
        side_effect=lambda attr: {
            "name": "手机号",
            "type": "text",
            "id": "mobile_field",
            "required": "required",
            "value": "",
        }.get(attr)
    )
    mock_el.get_text = AsyncMock(return_value="")
    mock_page.find_all = AsyncMock(return_value=[mock_el])

    engine = ApplyEngine(db_path=db_file, browser_backend=mock_browser)
    profile = _create_sample_profile(mobile=None)
    target = _create_sample_target(provider="generic")

    await engine.run_application_target(target, profile)

    app_repo = ApplicationRepository(db_file)
    runs = await app_repo.list_runs_by_application(f"app_{target.job.job_id}")
    assert len(runs) == 1
    run_id = runs[0]["id"]

    event_repo = EventRepository(db_file)
    events = await event_repo.list_events_by_run(run_id)
    halt_events = [e for e in events if e["event_type"] == "READINESS_AUDIT_HALTED"]
    assert len(halt_events) == 1

    payload = halt_events[0]["payload_json"]
    import json
    if isinstance(payload, str):
        payload = json.loads(payload)
    assert payload["stage"] == "single_page"
    assert len(payload["missing_required"]) == 1
    assert payload["missing_required"][0]["label"] == "手机号"
    assert payload["missing_required"][0]["status"] == "required_missing"


@pytest.mark.asyncio
async def test_non_interactive_readiness_pauses_application(tmp_path: Path):
    db_file = tmp_path / "test.db"
    await init_db(db_file)
    mock_browser, mock_page = _create_mock_browser_and_page()

    mock_el = AsyncMock()
    mock_el.get_attribute = AsyncMock(
        side_effect=lambda attr: {
            "name": "手机号",
            "type": "text",
            "id": "mobile_field",
            "required": "required",
            "value": "",
        }.get(attr)
    )
    mock_el.get_text = AsyncMock(return_value="")
    mock_page.find_all = AsyncMock(return_value=[mock_el])

    engine = ApplyEngine(
        db_path=db_file,
        browser_backend=mock_browser,
        interactive_readiness=False,
    )
    profile = _create_sample_profile(mobile=None)
    target = _create_sample_target(provider="generic")

    status = await engine.run_application_target(target, profile)
    assert status == ApplicationStatus.PAUSED

    # In non-interactive mode, browser.wait_for_user should not be invoked
    mock_browser.wait_for_user.assert_not_called()

    # Verify application status in database
    app_repo = ApplicationRepository(db_file)
    app = await app_repo.get_application(f"app_{target.job.job_id}")
    assert app is not None
    assert app["status"] == ApplicationStatus.PAUSED

    # Verify checkpoint saved with status "paused"
    chk_repo = CheckpointRepository(db_file)
    latest_chk = await chk_repo.get_latest_checkpoint(f"app_{target.job.job_id}")
    assert latest_chk is not None
    assert latest_chk["status"] == "paused"


@pytest.mark.asyncio
async def test_custom_readiness_resolver_invoked(tmp_path: Path):
    db_file = tmp_path / "test.db"
    await init_db(db_file)
    mock_browser, mock_page = _create_mock_browser_and_page()

    mock_el = AsyncMock()
    mock_el.get_attribute = AsyncMock(
        side_effect=lambda attr: {
            "name": "手机号",
            "type": "text",
            "id": "mobile_field",
            "required": "required",
            "value": "",
        }.get(attr)
    )
    mock_el.get_text = AsyncMock(return_value="")
    mock_page.find_all = AsyncMock(return_value=[mock_el])

    custom_resolver = AsyncMock()

    engine = ApplyEngine(
        db_path=db_file,
        browser_backend=mock_browser,
        interactive_readiness=True,
        readiness_resolver=custom_resolver,
    )
    profile = _create_sample_profile(mobile=None)
    target = _create_sample_target(provider="generic")

    status = await engine.run_application_target(target, profile)
    assert status == ApplicationStatus.PAUSED

    # Custom resolver called once with (page, report, profile, variant)
    assert custom_resolver.await_count == 1
    call_args = custom_resolver.await_args[0]
    assert call_args[0] == mock_page
    report = call_args[1]
    assert report.is_ready is False
    assert len(report.missing_required) == 1
    assert call_args[2] == profile

    # The resolver did not fill the page, so neither default nor final prompts run.
    mock_browser.wait_for_user.assert_not_awaited()


@pytest.mark.asyncio
async def test_all_required_fields_present_advances_without_halting(tmp_path: Path):
    db_file = tmp_path / "test.db"
    await init_db(db_file)
    mock_browser, mock_page = _create_mock_browser_and_page()

    # Form element has required mobile, and profile has mobile="13800138000"
    mock_el = AsyncMock()
    mock_el.get_attribute = AsyncMock(
        side_effect=lambda attr: {
            "name": "手机号",
            "type": "text",
            "id": "mobile_field",
            "required": "required",
            "value": "",
        }.get(attr)
    )
    mock_el.get_text = AsyncMock(return_value="")
    mock_page.find_all = AsyncMock(return_value=[mock_el])

    engine = ApplyEngine(db_path=db_file, browser_backend=mock_browser)
    profile = _create_sample_profile(mobile="13800138000")
    target = _create_sample_target(provider="generic")

    status = await engine.run_application_target(target, profile)
    assert status == ApplicationStatus.READY_REVIEW

    # No READINESS_AUDIT_HALTED event recorded
    event_repo = EventRepository(db_file)
    app_repo = ApplicationRepository(db_file)
    runs = await app_repo.list_runs_by_application(f"app_{target.job.job_id}")
    events = await event_repo.list_events_by_run(runs[0]["id"])
    assert not any(e["event_type"] == "READINESS_AUDIT_HALTED" for e in events)

    # Only one call to wait_for_user: the final review handoff
    assert mock_browser.wait_for_user.await_count == 1
    assert "表单字段已填写完毕" in mock_browser.wait_for_user.await_args[0][0]


@pytest.mark.asyncio
async def test_readiness_resolver_returning_paused_pauses_application(tmp_path: Path):
    db_file = tmp_path / "test.db"
    await init_db(db_file)
    mock_browser, mock_page = _create_mock_browser_and_page()

    mock_el = AsyncMock()
    mock_el.get_attribute = AsyncMock(
        side_effect=lambda attr: {
            "name": "手机号",
            "type": "text",
            "id": "mobile_field",
            "required": "required",
            "value": "",
        }.get(attr)
    )
    mock_el.get_text = AsyncMock(return_value="")
    mock_page.find_all = AsyncMock(return_value=[mock_el])

    # Custom resolver cancels / requests pause
    custom_resolver = AsyncMock(return_value=ApplicationStatus.PAUSED)

    engine = ApplyEngine(
        db_path=db_file,
        browser_backend=mock_browser,
        interactive_readiness=True,
        readiness_resolver=custom_resolver,
    )
    profile = _create_sample_profile(mobile=None)
    target = _create_sample_target(provider="generic")

    status = await engine.run_application_target(target, profile)
    assert status == ApplicationStatus.PAUSED

    # Assert application in DB has current_stage and PAUSED status
    app_repo = ApplicationRepository(db_file)
    app = await app_repo.get_application(f"app_{target.job.job_id}")
    assert app is not None
    assert app["status"] == ApplicationStatus.PAUSED
    assert app["current_stage"] == "single_page"

    # Assert checkpoint saved with status "paused"
    chk_repo = CheckpointRepository(db_file)
    latest_chk = await chk_repo.get_latest_checkpoint(f"app_{target.job.job_id}")
    assert latest_chk is not None
    assert latest_chk["status"] == "paused"
    assert latest_chk["stage_key"] == "single_page"


@pytest.mark.asyncio
async def test_readiness_resolver_returning_false_pauses_application(tmp_path: Path):
    db_file = tmp_path / "test.db"
    await init_db(db_file)
    mock_browser, mock_page = _create_mock_browser_and_page()

    mock_el = AsyncMock()
    mock_el.get_attribute = AsyncMock(
        side_effect=lambda attr: {
            "name": "手机号",
            "type": "text",
            "id": "mobile_field",
            "required": "required",
            "value": "",
        }.get(attr)
    )
    mock_el.get_text = AsyncMock(return_value="")
    mock_page.find_all = AsyncMock(return_value=[mock_el])

    custom_resolver = AsyncMock(return_value=False)

    engine = ApplyEngine(
        db_path=db_file,
        browser_backend=mock_browser,
        interactive_readiness=True,
        readiness_resolver=custom_resolver,
    )
    profile = _create_sample_profile(mobile=None)
    target = _create_sample_target(provider="generic")

    status = await engine.run_application_target(target, profile)
    assert status == ApplicationStatus.PAUSED


@pytest.mark.asyncio
async def test_sync_readiness_resolver_invoked(tmp_path: Path):
    db_file = tmp_path / "test.db"
    await init_db(db_file)
    mock_browser, mock_page = _create_mock_browser_and_page()

    mock_el = AsyncMock()
    mock_el.get_attribute = AsyncMock(
        side_effect=lambda attr: {
            "name": "手机号",
            "type": "text",
            "id": "mobile_field",
            "required": "required",
            "value": "",
        }.get(attr)
    )
    mock_el.get_text = AsyncMock(return_value="")
    mock_page.find_all = AsyncMock(return_value=[mock_el])

    sync_called = []

    def sync_resolver(page, report, profile, variant):
        sync_called.append((page, report, profile))
        return True

    engine = ApplyEngine(
        db_path=db_file,
        browser_backend=mock_browser,
        interactive_readiness=True,
        readiness_resolver=sync_resolver,
    )
    profile = _create_sample_profile(mobile=None)
    target = _create_sample_target(provider="generic")

    status = await engine.run_application_target(target, profile)
    assert status == ApplicationStatus.PAUSED
    assert len(sync_called) == 1


@pytest.mark.asyncio
async def test_detached_element_does_not_crash_engine(tmp_path: Path):
    db_file = tmp_path / "test.db"
    await init_db(db_file)
    mock_browser, mock_page = _create_mock_browser_and_page()

    # First element throws detached error
    mock_detached_el = AsyncMock()
    mock_detached_el.get_attribute = AsyncMock(side_effect=RuntimeError("Element detached from DOM"))

    # Second element is normal valid element
    mock_valid_el = AsyncMock()
    mock_valid_el.get_attribute = AsyncMock(
        side_effect=lambda attr: {
            "name": "姓名",
            "type": "text",
            "id": "name_field",
            "value": "张三",
        }.get(attr)
    )
    mock_valid_el.get_text = AsyncMock(return_value="张三")

    mock_page.find_all = AsyncMock(return_value=[mock_detached_el, mock_valid_el])

    engine = ApplyEngine(db_path=db_file, browser_backend=mock_browser)
    profile = _create_sample_profile(mobile="13800138000")
    target = _create_sample_target(provider="generic")

    # Should safely catch exception on detached element and complete successfully
    status = await engine.run_application_target(target, profile)
    assert status == ApplicationStatus.READY_REVIEW

