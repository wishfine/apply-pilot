import pytest
from pathlib import Path
from unittest.mock import AsyncMock
from applypilot.adapters.applications.generic import GenericApplicationAdapter
from applypilot.adapters.applications.moka import MokaApplicationAdapter
from applypilot.domain.job import Job, ApplicationTarget, ApplicationStatus
from applypilot.domain.profile import CandidateProfile, IdentityInfo, ContactInfo
from applypilot.modules.apply.engine import ApplyEngine
from applypilot.storage.database import init_db
from applypilot.storage.repositories import ApplicationRepository, CheckpointRepository, EventRepository


@pytest.mark.asyncio
async def test_generic_and_moka_is_final_review_rejects_empty_page():
    mock_page = AsyncMock()
    mock_page.url = AsyncMock(return_value="https://example.test/form")
    # Mock execute_unsafe_script returning False (no submit buttons found)
    mock_page.execute_unsafe_script = AsyncMock(return_value=False)

    gen_adapter = GenericApplicationAdapter()
    assert await gen_adapter.is_final_review(mock_page) is False

    moka_adapter = MokaApplicationAdapter()
    assert await moka_adapter.is_final_review(mock_page) is False


@pytest.mark.asyncio
async def test_generic_is_final_review_detects_submit_button():
    mock_page = AsyncMock()
    mock_page.url = AsyncMock(return_value="https://example.test/form")
    # Mock execute_unsafe_script returning True when submit button exists
    mock_page.execute_unsafe_script = AsyncMock(return_value=True)

    gen_adapter = GenericApplicationAdapter()
    assert await gen_adapter.is_final_review(mock_page) is True


@pytest.mark.asyncio
async def test_engine_pauses_on_login_page_without_false_ready_review(tmp_path: Path):
    db_file = tmp_path / "test_pages.db"
    await init_db(db_file)

    mock_browser = AsyncMock()
    mock_page = AsyncMock()
    mock_page.url = AsyncMock(return_value="https://example.test/form")
    mock_browser.open_page.return_value = mock_page
    mock_browser.wait_for_user = AsyncMock()

    # Simulate login page: script finds login text, but 0 form fields
    async def fake_script(name, script):
        if "login" in name.lower() or "login" in script.lower() or "登录" in script:
            return True
        if "final submission" in name.lower():
            return False
        return False

    mock_page.execute_unsafe_script = AsyncMock(side_effect=fake_script)

    engine = ApplyEngine(db_path=db_file, browser_backend=mock_browser)

    profile = CandidateProfile(
        profile_id="cand_test_login",
        identity=IdentityInfo(name="测试员"),
        contact=ContactInfo(mobile="13800000000"),
    )
    job = Job(
        job_id="job_login_test",
        title="测试岗位",
        company_name="测试公司",
        description_raw="desc",
        source_channel="url",
        source_url="https://example.com/login",
        apply_url="https://example.com/login",
    )
    target = ApplicationTarget(target_id="tgt_login_test", job=job)

    status = await engine.run_application_target(target, profile)
    # Must NOT be READY_REVIEW! Must pause safely
    assert status == ApplicationStatus.PAUSED


@pytest.mark.asyncio
async def test_navigation_failure_is_paused_with_resumable_checkpoint(tmp_path: Path):
    db_file = tmp_path / "navigation_failure.db"
    await init_db(db_file)
    browser = AsyncMock()
    browser.open_page.side_effect = RuntimeError("browser unavailable")
    profile = CandidateProfile(profile_id="cand_nav", identity=IdentityInfo(name="测试员"))
    job = Job(job_id="job_nav", title="岗位", company_name="公司", description_raw="desc",
              source_channel="url", source_url="https://example.com/apply", apply_url="https://example.com/apply")
    target = ApplicationTarget(target_id="target_nav", job=job)
    engine = ApplyEngine(db_path=db_file, browser_backend=browser)
    with pytest.raises(RuntimeError, match="browser unavailable"):
        await engine.run_application_target(target, profile)
    app = await engine.app_repo.get_application_by_key("cand_nav:job_nav:default")
    assert app["status"] == ApplicationStatus.PAUSED
    checkpoint = await engine.chk_repo.get_latest_checkpoint(app["id"])
    assert checkpoint["page_url"] == job.apply_url


@pytest.mark.asyncio
async def test_engine_uses_latest_checkpoint_url_when_resuming(tmp_path: Path):
    db_file = tmp_path / "resume_url.db"
    await init_db(db_file)
    browser = AsyncMock()
    page = AsyncMock()
    page.url = AsyncMock(return_value="https://example.com/apply/step1")
    page.find_all = AsyncMock(return_value=[])
    page.execute_unsafe_script = AsyncMock(return_value=False)
    browser.open_page.return_value = page

    profile = CandidateProfile(profile_id="cand_resume_url", identity=IdentityInfo(name="测试员"))
    job = Job(job_id="job_resume_url", title="岗位", company_name="公司", description_raw="desc",
              source_channel="url", source_url="https://example.com/apply/step1",
              apply_url="https://example.com/apply/step1")
    target = ApplicationTarget(target_id="target_resume_url", job=job)
    app_id = "app_resume_url"
    app_repo = ApplicationRepository(db_file)
    await app_repo.create_application(
        app_id=app_id,
        application_key=f"{profile.profile_id}:{job.job_id}:default",
        candidate_id=profile.profile_id,
        canonical_job_id=job.job_id,
        company_name=job.company_name,
        job_title=job.title,
        status=ApplicationStatus.PAUSED,
    )
    from applypilot.storage.repositories import RevisionRepository
    await RevisionRepository(db_file).save_profile_revision("rev_resume_url", profile.profile_id, "hash", {})
    await app_repo.create_run("run_resume_url", app_id, 1, "rev_resume_url", "generic", "1", "1", "cfg")
    await CheckpointRepository(db_file).save_checkpoint(
        "chk_resume_url", app_id, "run_resume_url", page_url="https://example.com/apply/step2", status="paused"
    )

    engine = ApplyEngine(db_file, browser, interactive_readiness=False)
    await engine.run_application_target(target, profile)
    browser.open_page.assert_awaited_once_with("https://example.com/apply/step2")


@pytest.mark.asyncio
async def test_failure_event_does_not_store_exception_details(tmp_path: Path):
    db_file = tmp_path / "failure_event.db"
    await init_db(db_file)
    browser = AsyncMock()
    browser.open_page = AsyncMock(side_effect=RuntimeError("candidate secret 110101200001011234"))
    engine = ApplyEngine(db_file, browser)
    profile = CandidateProfile(profile_id="cand_failure_event", identity=IdentityInfo(name="测试员"))
    job = Job(job_id="job_failure_event", title="岗位", company_name="公司", description_raw="desc",
              source_channel="url", source_url="https://example.com/apply",
              apply_url="https://example.com/apply")
    with pytest.raises(RuntimeError, match="candidate secret"):
        await engine.run_application_target(ApplicationTarget(target_id="target_failure_event", job=job), profile)
    app = await engine.app_repo.get_application_by_key("cand_failure_event:job_failure_event:default")
    run = (await engine.app_repo.list_runs_by_application(app["id"]))[0]
    events = await EventRepository(db_file).list_events_by_run(run["id"])
    failed = [event for event in events if event["event_type"] == "RUN_FAILED"]
    assert failed
    assert "110101200001011234" not in failed[0]["payload_json"]
