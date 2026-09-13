import pytest
from pathlib import Path
from unittest.mock import AsyncMock
from applypilot.domain.job import Job, ApplicationTarget
from applypilot.domain.profile import CandidateProfile, IdentityInfo, ContactInfo
from applypilot.modules.apply.engine import ApplyEngine
from applypilot.storage.database import init_db
from applypilot.storage.repositories import ApplicationRepository, CheckpointRepository


@pytest.mark.asyncio
async def test_application_isolation_between_candidates(tmp_path: Path):
    db_file = tmp_path / "test_isolation.db"
    await init_db(db_file)

    mock_browser = AsyncMock()
    mock_page = AsyncMock()
    mock_page.url = AsyncMock(return_value="https://example.test/form")
    mock_browser.open_page.return_value = mock_page
    mock_browser.wait_for_user = AsyncMock()

    # Form with 1 field
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

    # Shared target job
    job = Job(
        job_id="job_same_target",
        title="后端工程师",
        company_name="某大厂",
        description_raw="desc",
        source_channel="url",
        source_url="https://example.com/jobs/100",
        apply_url="https://example.com/jobs/100",
    )
    target = ApplicationTarget(target_id="tgt_same_100", job=job)

    # Candidate A
    profile_A = CandidateProfile(
        profile_id="candidate_A",
        identity=IdentityInfo(name="张三"),
        contact=ContactInfo(mobile="13800000001"),
    )
    # Candidate B
    profile_B = CandidateProfile(
        profile_id="candidate_B",
        identity=IdentityInfo(name="李四"),
        contact=ContactInfo(mobile="13800000002"),
    )

    # Run for Candidate A
    status_A = await engine.run_application_target(target, profile_A)

    # Run for Candidate B on same target
    status_B = await engine.run_application_target(target, profile_B)

    app_repo = ApplicationRepository(db_file)
    apps = await app_repo.list_applications()

    # Must produce TWO distinct applications, not one shared record!
    assert len(apps) == 2, f"Expected 2 applications, found {len(apps)}: {apps}"

    candidate_ids = {app["candidate_id"] for app in apps}
    assert candidate_ids == {"candidate_A", "candidate_B"}

    app_A = next(app for app in apps if app["candidate_id"] == "candidate_A")
    app_B = next(app for app in apps if app["candidate_id"] == "candidate_B")
    assert app_A["id"] != app_B["id"]
    assert app_A["application_key"] != app_B["application_key"]

    # Runs must belong to their respective applications
    runs_A = await app_repo.list_runs_by_application(app_A["id"])
    runs_B = await app_repo.list_runs_by_application(app_B["id"])
    assert len(runs_A) == 1
    assert len(runs_B) == 1
    assert runs_A[0]["id"] != runs_B[0]["id"]
