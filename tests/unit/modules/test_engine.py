from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
import pytest

from applypilot.adapters.detection import DetectionEvidence, DetectionReport, DetectionResult
from applypilot.domain.job import ApplicationStatus, ApplicationTarget, Job
from applypilot.domain.profile import CandidateProfile, ContactInfo, IdentityInfo
from applypilot.modules.apply import ApplicationStatus as ApplyApplicationStatus, ApplyEngine
from applypilot.storage.database import init_db
from applypilot.storage.repositories import (
    ApplicationRepository,
    CheckpointRepository,
    EventRepository,
)


def _create_sample_profile() -> CandidateProfile:
    return CandidateProfile(
        profile_id="cand_test_001",
        identity=IdentityInfo(
            name="张三",
            gender="male",
        ),
        contact=ContactInfo(
            mobile="13800138000",
            email="zhangsan@example.com",
            current_city="北京",
        ),
    )


def _create_sample_target(provider: str | None = "generic") -> ApplicationTarget:
    return ApplicationTarget(
        target_id="tgt_test_001",
        job=Job(
            job_id="job_dev_100",
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
async def test_engine_initialization(tmp_path: Path):
    db_file = tmp_path / "test.db"
    await init_db(db_file)
    mock_browser, _ = _create_mock_browser_and_page()

    engine = ApplyEngine(db_path=db_file, browser_backend=mock_browser)
    assert engine.app_repo is not None
    assert engine.chk_repo is not None
    assert engine.event_repo is not None
    assert engine.snap_repo is not None
    assert "generic" in engine.adapters
    assert "moka" in engine.adapters
    assert "beisen" in engine.adapters


@pytest.mark.asyncio
async def test_full_execution_flow_ready_review(tmp_path: Path):
    db_file = tmp_path / "test.db"
    await init_db(db_file)
    mock_browser, mock_page = _create_mock_browser_and_page()

    # Create mock form element
    mock_el = AsyncMock()
    mock_el.get_attribute = AsyncMock(
        side_effect=lambda attr: {
            "name": "姓名",
            "type": "text",
            "id": "name_field",
        }.get(attr)
    )
    mock_el.get_text = AsyncMock(return_value="")
    mock_page.find_all = AsyncMock(return_value=[mock_el])

    engine = ApplyEngine(db_path=db_file, browser_backend=mock_browser)
    profile = _create_sample_profile()
    target = _create_sample_target(provider="generic")

    status = await engine.run_application_target(target, profile)

    assert status == ApplicationStatus.READY_REVIEW
    mock_browser.open_page.assert_awaited_once_with(target.job.apply_url)
    mock_browser.wait_for_user.assert_awaited_once_with(
        "表单字段已填写完毕，请在浏览器中核对后亲自点击提交"
    )

    # Verify application persisted in database with READY_REVIEW
    app_repo = ApplicationRepository(db_file)
    app = await app_repo.get_application(f"app_{target.job.job_id}")
    assert app is not None
    assert app["status"] == ApplicationStatus.READY_REVIEW

    # Verify element was typed with candidate name
    mock_el.type_text.assert_awaited_once_with("张三")


@pytest.mark.asyncio
async def test_events_and_checkpoints_created(tmp_path: Path):
    db_file = tmp_path / "test.db"
    await init_db(db_file)
    mock_browser, mock_page = _create_mock_browser_and_page()
    mock_page.find_all = AsyncMock(return_value=[])

    engine = ApplyEngine(db_path=db_file, browser_backend=mock_browser)
    profile = _create_sample_profile()
    target = _create_sample_target(provider="generic")

    await engine.run_application_target(target, profile)

    # Check checkpoints in database
    chk_repo = CheckpointRepository(db_file)
    latest_chk = await chk_repo.get_latest_checkpoint(f"app_{target.job.job_id}")
    assert latest_chk is not None
    assert latest_chk["status"] == "ready_review"
    assert latest_chk["stage_key"] == "final_review"

    # Check events in database
    app_repo = ApplicationRepository(db_file)
    runs = await app_repo.list_runs_by_application(f"app_{target.job.job_id}")
    assert len(runs) == 1
    run_id = runs[0]["id"]

    event_repo = EventRepository(db_file)
    events = await event_repo.list_events_by_run(run_id)
    event_types = [e["event_type"] for e in events]
    assert "RUN_STARTED" in event_types
    assert "READY_REVIEW" in event_types


@pytest.mark.asyncio
async def test_platform_detection_routing(tmp_path: Path):
    db_file = tmp_path / "test.db"
    await init_db(db_file)
    mock_browser, mock_page = _create_mock_browser_and_page()
    mock_page.find_all = AsyncMock(return_value=[])
    mock_page.execute_unsafe_script = AsyncMock()

    # Mock detector returning Beisen
    mock_detector = AsyncMock()
    mock_detector.detect.return_value = DetectionReport(
        candidates=[
            DetectionResult(
                platform="beisen",
                confidence=0.95,
                evidences=[
                    DetectionEvidence(
                        signal_type="host", detail="beisen.com", weight=0.9
                    )
                ],
            )
        ]
    )

    engine = ApplyEngine(
        db_path=db_file,
        browser_backend=mock_browser,
        platform_detector=mock_detector,
    )
    profile = _create_sample_profile()
    target = _create_sample_target(provider=None)  # Provider None -> relies on detector

    status = await engine.run_application_target(target, profile)
    assert status == ApplicationStatus.READY_REVIEW
    mock_detector.detect.assert_awaited_once_with(mock_page)


@pytest.mark.asyncio
async def test_resume_from_checkpoint(tmp_path: Path):
    db_file = tmp_path / "test.db"
    await init_db(db_file)
    mock_browser, mock_page = _create_mock_browser_and_page()
    mock_page.find_all = AsyncMock(return_value=[])

    profile = _create_sample_profile()
    target = _create_sample_target(provider="generic")
    app_id = f"app_{target.job.job_id}"

    # Pre-seed existing checkpoint
    app_repo = ApplicationRepository(db_file)
    await app_repo.create_application(
        app_id=app_id,
        application_key=f"{profile.profile_id}:{target.job.job_id}:default",
        candidate_id=profile.profile_id,
        canonical_job_id=target.job.job_id,
        company_name=target.job.company_name,
        job_title=target.job.title,
        status="in_progress",
    )
    # Save dummy profile revision and run
    from applypilot.storage.repositories import RevisionRepository
    rev_repo = RevisionRepository(db_file)
    await rev_repo.save_profile_revision("rev_01", profile.profile_id, "h1", {})
    await app_repo.create_run("run_pre", app_id, 1, "rev_01", "generic", "1.0", "1.0", "cfg")

    chk_repo = CheckpointRepository(db_file)
    await chk_repo.save_checkpoint(
        checkpoint_id="chk_prev",
        application_id=app_id,
        run_id="run_pre",
        page_url="https://example.com",
        stage_key="stage_prev",
        status="paused",
    )

    engine = ApplyEngine(db_path=db_file, browser_backend=mock_browser)
    await engine.run_application_target(target, profile)

    runs = await app_repo.list_runs_by_application(app_id)
    new_run = runs[-1]
    event_repo = EventRepository(db_file)
    events = await event_repo.list_events_by_run(new_run["id"])
    event_types = [e["event_type"] for e in events]
    assert "CHECKPOINT_RESUMED" in event_types


@pytest.mark.asyncio
async def test_privacy_disclosure_gate_blocks_fields(tmp_path: Path):
    db_file = tmp_path / "test.db"
    await init_db(db_file)
    mock_browser, mock_page = _create_mock_browser_and_page()

    mock_el = AsyncMock()
    mock_el.get_attribute = AsyncMock(
        side_effect=lambda attr: {
            "name": "姓名",
            "type": "text",
            "id": "name_field",
        }.get(attr)
    )
    mock_el.get_text = AsyncMock(return_value="")
    mock_page.find_all = AsyncMock(return_value=[mock_el])

    from applypilot.domain.variant import DisclosurePolicy
    target = _create_sample_target(provider="generic")
    target.disclosure_policy = DisclosurePolicy(blocked_field_paths={"identity.name"})

    engine = ApplyEngine(db_path=db_file, browser_backend=mock_browser)
    profile = _create_sample_profile()

    status = await engine.run_application_target(target, profile)
    assert status == ApplicationStatus.READY_REVIEW

    # Type text should NOT have been called because path was blocked
    mock_el.type_text.assert_not_called()


@pytest.mark.asyncio
async def test_beisen_multistage_advance_and_fill(tmp_path: Path):
    db_file = tmp_path / "test.db"
    await init_db(db_file)
    mock_browser, mock_page = _create_mock_browser_and_page()

    from applypilot.adapters.applications.base import FillResult

    # Create mock adapter that advances once then reviews
    mock_adapter = AsyncMock()
    mock_adapter.detect_stage.side_effect = ["stage_info", "stage_review"]
    mock_adapter.is_final_review.side_effect = [False, True]
    mock_adapter.advance.return_value = True
    mock_adapter.fill_field.return_value = FillResult(
        success=True,
        action_type="beisen_fill",
        observed_value="13800138000",
    )


    mock_el = AsyncMock()
    mock_el.get_attribute = AsyncMock(
        side_effect=lambda attr: {
            "name": "手机号",
            "type": "text",
            "id": "phone_field",
        }.get(attr)
    )
    mock_el.get_text = AsyncMock(return_value="")
    mock_page.find_all = AsyncMock(return_value=[mock_el])

    engine = ApplyEngine(
        db_path=db_file,
        browser_backend=mock_browser,
        adapters={"beisen": mock_adapter},
    )
    profile = _create_sample_profile()
    target = _create_sample_target(provider="beisen")

    status = await engine.run_session(target, profile)
    assert status == ApplicationStatus.READY_REVIEW

    # Verified multi-stage advancement occurred
    assert mock_adapter.detect_stage.await_count == 2
    mock_adapter.advance.assert_awaited_once()
    mock_adapter.fill_field.assert_awaited()

