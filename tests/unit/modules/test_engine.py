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
    async def script_result(reason, script, *args):
        return "final submission" in reason.lower()
    mock_page.execute_unsafe_script = AsyncMock(side_effect=script_result)
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
    mock_beisen = AsyncMock()
    mock_beisen.detect_stage.return_value = "beisen_stage"
    mock_beisen.is_final_review.return_value = True
    mock_beisen.advance.return_value = False

    engine = ApplyEngine(
        db_path=db_file,
        browser_backend=mock_browser,
        platform_detector=mock_detector,
        adapters={"beisen": mock_beisen},
    )
    profile = _create_sample_profile()
    target = _create_sample_target(provider=None)  # Provider None -> relies on detector

    status = await engine.run_application_target(target, profile)
    assert status == ApplicationStatus.READY_REVIEW
    mock_detector.detect.assert_awaited_once_with(mock_page)
    mock_beisen.detect_stage.assert_awaited_once()



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


@pytest.mark.asyncio
async def test_exception_handling_marks_run_failed(tmp_path: Path):
    db_file = tmp_path / "test.db"
    await init_db(db_file)
    mock_browser, mock_page = _create_mock_browser_and_page()
    mock_page.find_all.side_effect = RuntimeError("Browser crashed during scanning")

    engine = ApplyEngine(db_path=db_file, browser_backend=mock_browser)
    profile = _create_sample_profile()
    target = _create_sample_target(provider="generic")

    with pytest.raises(RuntimeError, match="Browser crashed during scanning"):
        await engine.run_application_target(target, profile)

    app_repo = ApplicationRepository(db_file)
    runs = await app_repo.list_runs_by_application(f"app_{target.job.job_id}")
    assert len(runs) == 1
    assert runs[0]["status"] == "failed"
    assert "Browser crashed during scanning" in (runs[0]["end_reason"] or "")

    event_repo = EventRepository(db_file)
    events = await event_repo.list_events_by_run(runs[0]["id"])
    event_types = [e["event_type"] for e in events]
    assert "RUN_FAILED" in event_types


@pytest.mark.asyncio
async def test_loop_exhaustion_triggers_max_stages_exceeded(tmp_path: Path):
    db_file = tmp_path / "test.db"
    await init_db(db_file)
    mock_browser, mock_page = _create_mock_browser_and_page()
    mock_page.find_all = AsyncMock(return_value=[])

    infinite_adapter = AsyncMock()
    infinite_adapter.detect_stage.return_value = "endless_stage"
    infinite_adapter.is_final_review.return_value = False
    infinite_adapter.advance.return_value = True

    engine = ApplyEngine(
        db_path=db_file,
        browser_backend=mock_browser,
        adapters={"infinite": infinite_adapter},
    )
    profile = _create_sample_profile()
    target = _create_sample_target(provider="infinite")

    with pytest.raises(RuntimeError, match="Exceeded maximum stage transitions"):
        await engine.run_application_target(target, profile)

    app_repo = ApplicationRepository(db_file)
    runs = await app_repo.list_runs_by_application(f"app_{target.job.job_id}")
    assert len(runs) == 1
    assert runs[0]["status"] == "failed"
    assert runs[0]["end_reason"] == "MAX_STAGES_EXCEEDED"

    event_repo = EventRepository(db_file)
    events = await event_repo.list_events_by_run(runs[0]["id"])
    assert any(e["event_type"] == "RUN_FAILED" for e in events)


@pytest.mark.asyncio
async def test_field_mappings_table_populated(tmp_path: Path):
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

    engine = ApplyEngine(db_path=db_file, browser_backend=mock_browser)
    profile = _create_sample_profile()
    target = _create_sample_target(provider="generic")

    await engine.run_application_target(target, profile)

    import aiosqlite

    async with aiosqlite.connect(db_file) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM field_mappings") as cursor:
            rows = await cursor.fetchall()
            assert len(rows) == 1
            assert rows[0]["profile_path"] == "identity.name"
            assert rows[0]["method"] == "exact_rule"
            assert rows[0]["disclosure_allowed"] == 1


@pytest.mark.asyncio
async def test_inferred_value_kind_avoids_redundant_fill(tmp_path: Path):
    db_file = tmp_path / "test.db"
    await init_db(db_file)
    mock_browser, mock_page = _create_mock_browser_and_page()

    # Form field already has "北京市", profile has "北京"
    mock_el = AsyncMock()
    mock_el.get_attribute = AsyncMock(
        side_effect=lambda attr: {
            "name": "现居城市",
            "type": "text",
            "id": "city_field",
            "value": "北京市",
        }.get(attr)
    )
    mock_el.get_text = AsyncMock(return_value="北京市")
    mock_page.find_all = AsyncMock(return_value=[mock_el])

    engine = ApplyEngine(db_path=db_file, browser_backend=mock_browser)
    profile = _create_sample_profile()
    target = _create_sample_target(provider="generic")

    await engine.run_application_target(target, profile)

    # Because ValueKind.CITY treats "北京市" == "北京", clear/type should not be called
    mock_el.type_text.assert_not_called()


@pytest.mark.asyncio
async def test_correction_memory_wiring(tmp_path: Path):
    db_file = tmp_path / "test.db"
    await init_db(db_file)
    mock_browser, mock_page = _create_mock_browser_and_page()

    # Pre-seed correction memory for custom label
    from applypilot.storage.repositories import CorrectionRepository

    corr_repo = CorrectionRepository(db_file)
    await corr_repo.save_correction(
        correction_id="corr_01",
        provider="generic",
        normalized_label="自定义姓名标签",
        field_type="text",
        corrected_semantic_path="identity.name",
        confidence=0.99,
    )

    mock_el = AsyncMock()
    mock_el.get_attribute = AsyncMock(
        side_effect=lambda attr: {
            "name": "自定义姓名标签",
            "type": "text",
            "id": "custom_name_field",
        }.get(attr)
    )
    mock_el.get_text = AsyncMock(return_value="")
    mock_page.find_all = AsyncMock(return_value=[mock_el])

    engine = ApplyEngine(db_path=db_file, browser_backend=mock_browser)
    profile = _create_sample_profile()
    target = _create_sample_target(provider="generic")

    await engine.run_application_target(target, profile)

    # Element typed with "张三" via memory
    mock_el.type_text.assert_awaited_once_with("张三")

    import aiosqlite

    async with aiosqlite.connect(db_file) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM field_mappings") as cursor:
            rows = await cursor.fetchall()
            assert len(rows) == 1
            assert rows[0]["method"] == "memory"
            assert rows[0]["confidence"] == 0.99


@pytest.mark.asyncio
async def test_correction_memory_does_not_cross_target_tenant(tmp_path: Path):
    db_file = tmp_path / "tenant_scope.db"
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

    from applypilot.storage.repositories import CorrectionRepository

    await CorrectionRepository(db_file).save_correction(
        correction_id="company_a_name",
        provider="generic",
        tenant_hint="company-a.example",
        normalized_label="姓名",
        field_type="text",
        corrected_semantic_path="contact.email",
    )

    target = _create_sample_target(provider="generic")
    target.job.apply_url = "https://company-b.example/apply"
    engine = ApplyEngine(db_path=db_file, browser_backend=mock_browser)
    status = await engine.run_application_target(target, _create_sample_profile())

    assert status == ApplicationStatus.READY_REVIEW
    mock_el.type_text.assert_awaited_once_with("张三")


@pytest.mark.asyncio
async def test_engine_persists_target_context_for_later_resume(tmp_path: Path):
    db_file = tmp_path / "target_context.db"
    await init_db(db_file)
    mock_browser, mock_page = _create_mock_browser_and_page()
    mock_page.find_all = AsyncMock(return_value=[])

    from applypilot.domain.variant import DisclosurePolicy

    target = _create_sample_target(provider="generic")
    target.platform_type = "company"
    target.assigned_variant_id = "variant-1"
    target.disclosure_policy = DisclosurePolicy(blocked_field_paths={"contact.email"})
    engine = ApplyEngine(db_path=db_file, browser_backend=mock_browser)

    await engine.run_application_target(target, _create_sample_profile())

    app = await engine.app_repo.get_application_by_key(
        f"cand_test_001:{target.job.job_id}:default"
    )
    context = __import__("json").loads(app["target_context_json"])
    assert context["provider"] == "generic"
    assert context["platform_type"] == "company"
    assert context["assigned_variant_id"] == "variant-1"
    assert context["disclosure_policy"]["blocked_field_paths"] == ["contact.email"]

    target.disclosure_policy = DisclosurePolicy(allow_sensitive=False)
    await engine.run_application_target(target, _create_sample_profile())
    app = await engine.app_repo.get_application_by_key(
        f"cand_test_001:{target.job.job_id}:default"
    )
    refreshed = __import__("json").loads(app["target_context_json"])
    assert refreshed["disclosure_policy"]["allow_sensitive"] is False


@pytest.mark.asyncio
async def test_field_structure_signature_includes_live_descriptor_changes(tmp_path: Path):
    engine = ApplyEngine(db_path=tmp_path / "sig.db", browser_backend=AsyncMock())

    class Element:
        def __init__(self, state):
            self.state = state

        async def inspect_field(self):
            return self.state

    state = {"field_sig": "same", "label": "姓名", "tag": "input", "type": "text",
             "section_title": "基本信息", "options": None, "is_active": True}
    page = AsyncMock()
    page.find_all = AsyncMock(return_value=[Element(state)])
    assert await engine._field_structure_changed(page, [{**state}]) is False
    state["label"] = "手机号"
    assert await engine._field_structure_changed(
        page, [{"field_sig": "same", "label": "姓名", "tag": "input", "type": "text",
                "section_title": "基本信息", "options": None}]
    ) is True


@pytest.mark.asyncio
async def test_engine_does_not_restart_submitted_application(tmp_path: Path):
    db_file = tmp_path / "terminal.db"
    await init_db(db_file)
    browser, _ = _create_mock_browser_and_page()
    profile = _create_sample_profile()
    target = _create_sample_target(provider="generic")
    engine = ApplyEngine(db_path=db_file, browser_backend=browser)
    app_id = "app_terminal"
    await engine.app_repo.create_application(
        app_id=app_id,
        application_key=f"{profile.profile_id}:{target.job.job_id}:default",
        candidate_id=profile.profile_id,
        canonical_job_id=target.job.job_id,
        company_name=target.job.company_name,
        job_title=target.job.title,
        status=ApplicationStatus.SUBMITTED,
    )
    with pytest.raises(RuntimeError, match="terminal"):
        await engine.run_application_target(target, profile)
    app = await engine.app_repo.get_application(app_id)
    assert app["status"] == ApplicationStatus.SUBMITTED


@pytest.mark.asyncio
async def test_failure_before_run_creation_pauses_application(tmp_path: Path):
    db_file = tmp_path / "early_failure.db"
    await init_db(db_file)
    engine = ApplyEngine(db_file, AsyncMock())
    engine.rev_repo.save_profile_revision = AsyncMock(side_effect=RuntimeError("revision failed"))
    profile = _create_sample_profile()
    target = _create_sample_target()
    with pytest.raises(RuntimeError, match="revision failed"):
        await engine.run_application_target(target, profile)
    app = await engine.app_repo.get_application_by_key(
        f"{profile.profile_id}:{target.job.job_id}:default"
    )
    assert app["status"] == ApplicationStatus.PAUSED


@pytest.mark.asyncio
async def test_run_creation_failure_preserves_original_error_and_pauses(tmp_path: Path):
    db_file = tmp_path / "run_creation_failure.db"
    await init_db(db_file)
    engine = ApplyEngine(db_file, AsyncMock())
    engine.app_repo.create_run = AsyncMock(side_effect=RuntimeError("create run failed"))
    profile = _create_sample_profile()
    target = _create_sample_target()
    with pytest.raises(RuntimeError, match="create run failed"):
        await engine.run_application_target(target, profile)
    app = await engine.app_repo.get_application_by_key(
        f"{profile.profile_id}:{target.job.job_id}:default"
    )
    assert app["status"] == ApplicationStatus.PAUSED


@pytest.mark.asyncio
async def test_detected_adapter_name_is_persisted(tmp_path: Path):
    db_file = tmp_path / "adapter_name.db"
    await init_db(db_file)
    browser, page = _create_mock_browser_and_page()
    page.find_all = AsyncMock(return_value=[])
    detector = AsyncMock()
    detector.detect.return_value = DetectionReport(
        candidates=[DetectionResult(platform="beisen", confidence=1.0)]
    )
    adapter = AsyncMock()
    adapter.detect_stage.return_value = "review"
    adapter.is_final_review.return_value = True
    engine = ApplyEngine(
        db_file,
        browser,
        platform_detector=detector,
        adapters={"beisen": adapter},
    )
    target = _create_sample_target(provider=None)
    await engine.run_application_target(target, _create_sample_profile())
    app = await engine.app_repo.get_application_by_key(
        f"cand_test_001:{target.job.job_id}:default"
    )
    run = (await engine.app_repo.list_runs_by_application(app["id"]))[0]
    assert run["adapter_name"] == "beisen"
