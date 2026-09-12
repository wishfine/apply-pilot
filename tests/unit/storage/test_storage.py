import pytest
import sqlite3
import aiosqlite
from pathlib import Path

from applypilot.storage.database import init_db
from applypilot.storage.repositories import (
    ApplicationRepository,
    CheckpointRepository,
    EventRepository,
    SnapshotRepository,
    CorrectionRepository,
    RevisionRepository,
)


@pytest.mark.asyncio
async def test_init_db_and_foreign_keys(tmp_path: Path):
    db_file = tmp_path / "test.db"
    await init_db(db_file)

    async with aiosqlite.connect(db_file) as db:
        async with db.execute("PRAGMA foreign_keys;") as cursor:
            row = await cursor.fetchone()
            assert row[0] == 1

        async with db.execute("PRAGMA journal_mode;") as cursor:
            row = await cursor.fetchone()
            assert row[0].lower() == "wal"

        async with db.execute("SELECT name FROM sqlite_master WHERE type='table';") as cursor:
            tables = [r[0] for r in await cursor.fetchall()]
            expected = [
                "profile_revisions",
                "resume_variant_revisions",
                "applications",
                "application_runs",
                "application_checkpoints",
                "application_events",
                "form_snapshots",
                "field_mappings",
                "field_actions",
                "correction_memories",
            ]
            for t in expected:
                assert t in tables


@pytest.mark.asyncio
async def test_schema_indexes_exist(tmp_path: Path):
    db_file = tmp_path / "test.db"
    await init_db(db_file)

    async with aiosqlite.connect(db_file) as db:
        async with db.execute("SELECT name FROM sqlite_master WHERE type='index';") as cursor:
            indexes = [r[0] for r in await cursor.fetchall()]
            assert "idx_events_run_time" in indexes
            assert "idx_corr_lookup" in indexes


@pytest.mark.asyncio
async def test_foreign_key_enforcement(tmp_path: Path):
    db_file = tmp_path / "test.db"
    await init_db(db_file)

    # Attempt to insert into application_runs without existing application should fail FK check
    app_repo = ApplicationRepository(db_file)
    with pytest.raises(sqlite3.IntegrityError):
        await app_repo.create_run(
            run_id="run_nonexistent",
            application_id="app_does_not_exist",
            run_index=1,
            profile_revision_id="rev_does_not_exist",
            adapter_name="italent",
            adapter_version="1.0",
            mapper_version="1.0",
            config_hash="hash_01",
        )


@pytest.mark.asyncio
async def test_checkpoint_materialization(tmp_path: Path):
    db_file = tmp_path / "test.db"
    await init_db(db_file)

    app_repo = ApplicationRepository(db_file)
    chk_repo = CheckpointRepository(db_file)

    app_id = "app_test_01"
    await app_repo.create_application(
        app_id=app_id,
        application_key="cand_1:job_1:2027",
        candidate_id="cand_1",
        canonical_job_id="job_1",
        company_name="中国移动",
        job_title="算法工程师",
        recruitment_cycle="2027-campus",
    )

    await chk_repo.save_checkpoint(
        checkpoint_id="chk_01",
        application_id=app_id,
        run_id="run_01",
        page_url="https://italent.cn/apply/step2",
        stage_key="education",
        snapshot_id="snap_01",
        last_completed_field_sig="sig_school",
        status="paused",
    )

    chk = await chk_repo.get_latest_checkpoint(app_id)
    assert chk is not None
    assert chk["stage_key"] == "education"
    assert chk["page_url"] == "https://italent.cn/apply/step2"
    assert chk["status"] == "paused"


@pytest.mark.asyncio
async def test_checkpoint_ordering_and_lookup(tmp_path: Path):
    db_file = tmp_path / "test.db"
    await init_db(db_file)

    app_repo = ApplicationRepository(db_file)
    chk_repo = CheckpointRepository(db_file)

    app_id = "app_test_order"
    await app_repo.create_application(
        app_id=app_id,
        application_key="cand_1:job_order:2027",
        candidate_id="cand_1",
        canonical_job_id="job_order",
        company_name="测试公司",
        job_title="工程师",
    )

    # Save multiple checkpoints with explicit created_at
    await chk_repo.save_checkpoint(
        checkpoint_id="chk_first",
        application_id=app_id,
        run_id="run_01",
        page_url="https://example.com/step1",
        stage_key="basic",
        created_at="2026-09-12T10:00:00Z",
    )
    await chk_repo.save_checkpoint(
        checkpoint_id="chk_second",
        application_id=app_id,
        run_id="run_01",
        page_url="https://example.com/step2",
        stage_key="education",
        created_at="2026-09-12T10:05:00Z",
    )

    latest = await chk_repo.get_latest_checkpoint(app_id)
    assert latest is not None
    assert latest["id"] == "chk_second"
    assert latest["stage_key"] == "education"

    chk_by_id = await chk_repo.get_checkpoint("chk_first")
    assert chk_by_id is not None
    assert chk_by_id["stage_key"] == "basic"

    missing = await chk_repo.get_checkpoint("chk_nonexistent")
    assert missing is None


@pytest.mark.asyncio
async def test_application_repository_lifecycle(tmp_path: Path):
    db_file = tmp_path / "test.db"
    await init_db(db_file)

    app_repo = ApplicationRepository(db_file)
    app_id = "app_lifecycle_01"
    await app_repo.create_application(
        app_id=app_id,
        application_key="cand_2:job_2:2027",
        candidate_id="cand_2",
        canonical_job_id="job_2",
        company_name="腾讯",
        job_title="后端开发",
    )

    app = await app_repo.get_application(app_id)
    assert app is not None
    assert app["company_name"] == "腾讯"
    assert app["status"] == "created"
    assert app["current_stage"] is None

    await app_repo.update_status(app_id, status="in_progress", current_stage="basic_info")
    app_updated = await app_repo.get_application(app_id)
    assert app_updated["status"] == "in_progress"
    assert app_updated["current_stage"] == "basic_info"


@pytest.mark.asyncio
async def test_application_runs_lifecycle(tmp_path: Path):
    db_file = tmp_path / "test.db"
    await init_db(db_file)

    rev_repo = RevisionRepository(db_file)
    app_repo = ApplicationRepository(db_file)

    # 1. Create profile revision
    await rev_repo.save_profile_revision(
        revision_id="rev_prof_run",
        profile_id="cand_run",
        content_hash="hash_run_p",
        content_json={"name": "李四"},
    )

    # 2. Create application
    app_id = "app_runs_test"
    await app_repo.create_application(
        app_id=app_id,
        application_key="cand_run:job_run:2027",
        candidate_id="cand_run",
        canonical_job_id="job_run",
        company_name="阿里巴巴",
        job_title="架构师",
    )

    # 3. Create run
    run_id = "run_test_01"
    await app_repo.create_run(
        run_id=run_id,
        application_id=app_id,
        run_index=1,
        profile_revision_id="rev_prof_run",
        adapter_name="italent",
        adapter_version="1.0.0",
        mapper_version="1.0.0",
        config_hash="cfg_hash_01",
    )

    run = await app_repo.get_run(run_id)
    assert run is not None
    assert run["status"] == "running"
    assert run["adapter_name"] == "italent"
    assert run["application_id"] == app_id

    # 4. List runs
    runs = await app_repo.list_runs_by_application(app_id)
    assert len(runs) == 1
    assert runs[0]["id"] == run_id

    # 5. Update run status
    await app_repo.update_run_status(run_id, status="completed", end_reason="submitted_successfully")
    run_updated = await app_repo.get_run(run_id)
    assert run_updated["status"] == "completed"
    assert run_updated["end_reason"] == "submitted_successfully"


@pytest.mark.asyncio
async def test_event_repository(tmp_path: Path):
    db_file = tmp_path / "test.db"
    await init_db(db_file)

    event_repo = EventRepository(db_file)
    await event_repo.append_event(
        event_id="evt_01",
        run_id="run_01",
        event_type="FIELD_FILLED",
        payload_json={"field": "mobile", "status": "success"},
    )
    await event_repo.append_event(
        event_id="evt_02",
        run_id="run_01",
        event_type="NAVIGATED",
        payload_json='{"url": "https://example.com/step2"}',
    )

    events = await event_repo.list_events_by_run("run_01")
    assert len(events) == 2
    assert events[0]["id"] == "evt_01"
    assert events[0]["event_type"] == "FIELD_FILLED"
    assert '"mobile"' in events[0]["payload_json"]
    assert events[1]["id"] == "evt_02"


@pytest.mark.asyncio
async def test_snapshot_repository(tmp_path: Path):
    db_file = tmp_path / "test.db"
    await init_db(db_file)

    snap_repo = SnapshotRepository(db_file)
    await snap_repo.save_snapshot(
        snapshot_id="snap_01",
        run_id="run_01",
        page_url="https://example.com/form",
        dom_fingerprint="fingerprint_abc",
        fields_meta_json=[{"id": "name", "type": "text"}],
        stage_key="basic",
    )

    snap = await snap_repo.get_snapshot("snap_01")
    assert snap is not None
    assert snap["dom_fingerprint"] == "fingerprint_abc"
    assert snap["stage_key"] == "basic"
    assert '"name"' in snap["fields_meta_json"]

    # Test field mappings
    await snap_repo.save_field_mapping(
        mapping_id="map_01",
        snapshot_id="snap_01",
        field_signature="sig_name",
        profile_path="identity.name",
        method="semantic",
        confidence=0.98,
        disclosure_allowed=True,
    )
    mappings = await snap_repo.get_field_mappings("snap_01")
    assert len(mappings) == 1
    assert mappings[0]["profile_path"] == "identity.name"
    assert mappings[0]["confidence"] == 0.98

    # Test field actions
    await snap_repo.save_field_action(
        action_id="act_01",
        run_id="run_01",
        snapshot_id="snap_01",
        field_signature="sig_name",
        mapping_id="map_01",
        action_type="type_text",
        status="success",
        duration_ms=45,
        expected_hash="h1",
        observed_hash="h1",
        value_preview="李四",
    )
    actions = await snap_repo.list_field_actions("run_01")
    assert len(actions) == 1
    assert actions[0]["id"] == "act_01"
    assert actions[0]["status"] == "success"
    assert actions[0]["value_preview"] == "李四"


@pytest.mark.asyncio
async def test_correction_repository(tmp_path: Path):
    db_file = tmp_path / "test.db"
    await init_db(db_file)

    corr_repo = CorrectionRepository(db_file)
    await corr_repo.save_correction(
        correction_id="corr_01",
        provider="italent",
        normalized_label="最高学历",
        field_type="select",
        corrected_semantic_path="education[__HIGHEST__].education_level",
        confidence=0.95,
        section_signature="sec_edu",
    )
    await corr_repo.save_correction(
        correction_id="corr_02",
        provider="italent",
        normalized_label="手机号",
        field_type="text",
        corrected_semantic_path="contact.mobile",
        confidence=1.0,
    )

    results = await corr_repo.lookup_corrections(
        provider="italent",
        normalized_label="最高学历",
        section_signature="sec_edu",
    )
    assert len(results) >= 1
    assert results[0]["corrected_semantic_path"] == "education[__HIGHEST__].education_level"

    # Non-existent lookup returns empty list
    empty = await corr_repo.lookup_corrections(
        provider="italent",
        normalized_label="不存在的字段",
    )
    assert len(empty) == 0


@pytest.mark.asyncio
async def test_revision_repository(tmp_path: Path):
    db_file = tmp_path / "test.db"
    await init_db(db_file)

    rev_repo = RevisionRepository(db_file)
    await rev_repo.save_profile_revision(
        revision_id="rev_prof_01",
        profile_id="cand_1",
        content_hash="hash_p1",
        content_json={"name": "张三", "mobile": "13800000000"},
    )
    prof_rev = await rev_repo.get_profile_revision("rev_prof_01")
    assert prof_rev is not None
    assert prof_rev["profile_id"] == "cand_1"
    assert prof_rev["content_hash"] == "hash_p1"
    assert '"张三"' in prof_rev["content_json"]

    await rev_repo.save_variant_revision(
        revision_id="rev_var_01",
        variant_id="var_1",
        content_hash="hash_v1",
        content_json={"summary": "前端专家"},
    )
    var_rev = await rev_repo.get_variant_revision("rev_var_01")
    assert var_rev is not None
    assert var_rev["variant_id"] == "var_1"
    assert '"前端专家"' in var_rev["content_json"]

    # Nonexistent revisions return None
    assert await rev_repo.get_profile_revision("nonexistent") is None
    assert await rev_repo.get_variant_revision("nonexistent") is None
