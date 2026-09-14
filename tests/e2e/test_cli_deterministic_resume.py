import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from typer.testing import CliRunner

from applypilot.cli.main import app, _canonical_job_id_from_url, _normalize_job_url
from applypilot.storage.database import init_db
from applypilot.storage.repositories import ApplicationRepository, CheckpointRepository
from applypilot.domain.job import ApplicationStatus


def test_canonical_job_id_is_deterministic_for_same_url():
    url1 = "https://app.mokahr.com/campus-recruitment/bytedance/10001#/job/detail"
    url2 = "https://app.mokahr.com/campus-recruitment/bytedance/10001#/job/detail"
    url3 = "https://app.mokahr.com/campus-recruitment/bytedance/10002#/job/detail"

    id1 = _canonical_job_id_from_url(url1)
    id2 = _canonical_job_id_from_url(url2)
    id3 = _canonical_job_id_from_url(url3)

    assert id1 == id2, "Canonical job ID must be identical for the same URL"
    assert id1 != id3, "Different URLs must produce different job IDs"
    assert id1.startswith("job_")


def test_canonical_job_id_ignores_volatile_application_parameters():
    base = "https://iflytek.zhiye.com/form?jobAdId=abc123&fromPage=job&userId=200540681"
    changed = "https://iflytek.zhiye.com/form?userId=999999&jobAdId=abc123&fromPage=detail"
    assert _canonical_job_id_from_url(base) == _canonical_job_id_from_url(changed)


def test_normalize_job_url_accepts_markdown_and_escaped_ampersands():
    value = "[job](https://example.com/form?jobAdId=abc\\&seqid=0)"
    assert _normalize_job_url(value) == "https://example.com/form?jobAdId=abc&seqid=0"


def test_cli_apply_resume_command_resumes_application(tmp_path: Path, monkeypatch):
    import asyncio
    runner = CliRunner()
    db_file = tmp_path / "applypilot.db"

    # Set home dir to tmp_path
    monkeypatch.setenv("APPLYPILOT_HOME", str(tmp_path))

    # Create profile.yaml in tmp_path
    prof_file = tmp_path / "profile.yaml"
    prof_file.write_text(
        """schema_version: "1.1.0"
profile_id: cand_resume_test
identity:
  name: "测试者"
  gender: "male"
contact:
  mobile: "13800138000"
  email: "tester@example.com"
"""
    )

    app_id = "app_cand_resume_test_job_12345"
    canon_job_id = "job_12345"
    app_key = "cand_resume_test:job_12345:default"

    async def _setup():
        await init_db(db_file)
        app_repo = ApplicationRepository(db_file)
        chk_repo = CheckpointRepository(db_file)
        await app_repo.create_application(
            app_id=app_id,
            application_key=app_key,
            candidate_id="cand_resume_test",
            canonical_job_id=canon_job_id,
            company_name="测试公司",
            job_title="测试工程师",
            status=ApplicationStatus.PAUSED,
        )
        from applypilot.storage.repositories import RevisionRepository
        rev_repo = RevisionRepository(db_file)
        await rev_repo.save_profile_revision("rev_test_001", "cand_resume_test", "h1", {})
        await app_repo.create_run("run_test_001", app_id, 1, "rev_test_001", "generic", "1.0", "1.0", "cfg")

        await chk_repo.save_checkpoint(
            checkpoint_id="chk_test_001",
            application_id=app_id,
            run_id="run_test_001",
            page_url="https://example.com/apply/page2",
            stage_key="stage_2",
            snapshot_id="snap_001",
            completed_fields_json=[],
            status="paused",
        )

    asyncio.run(_setup())

    # Mock PlaywrightBackend and ApplyEngine to avoid real browser launch in test
    with patch("applypilot.cli.main.PlaywrightBackend") as mock_backend_cls, \
         patch("applypilot.cli.main.ApplyEngine") as mock_engine_cls:

        mock_backend = AsyncMock()
        mock_backend_cls.return_value = mock_backend

        mock_engine = AsyncMock()
        mock_engine.run_application_target.return_value = ApplicationStatus.READY_REVIEW
        mock_engine_cls.return_value = mock_engine

        result = runner.invoke(app, ["apply", "resume", app_id])
        assert result.exit_code == 0, f"Error: {result.stdout}"
        assert "Resuming application" in result.stdout or "Ready for Review" in result.stdout
        mock_engine.run_application_target.assert_awaited_once()
