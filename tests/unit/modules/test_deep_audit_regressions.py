from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from applypilot.adapters.applications.base import BaseApplicationAdapter, FillResult
from applypilot.adapters.detection import DetectionReport, DetectionResult
from applypilot.domain.job import ApplicationStatus, ApplicationTarget, Job
from applypilot.domain.profile import CandidateProfile
from applypilot.modules.apply.engine import ApplyEngine
from applypilot.storage.database import init_db


def _target(provider=None):
    return ApplicationTarget(
        target_id="audit-target",
        provider=provider,
        job=Job(
            job_id="audit-job",
            title="测试岗位",
            company_name="测试公司",
            description_raw="",
            source_channel="url",
            source_url="https://example.test/job",
            apply_url="https://example.test/form",
        ),
    )


def _profile():
    return CandidateProfile.model_validate({
        "profile_id": "audit-candidate",
        "identity": {"name": "测试甲"},
    })


class _FinalPage:
    async def url(self):
        return "https://example.test/form"

    async def execute_unsafe_script(self, reason, script, arg=None):
        return "final submission" in reason.lower()


@pytest.mark.asyncio
async def test_engine_pauses_when_filler_returns_malformed_result(tmp_path: Path):
    await init_db(tmp_path / "audit.db")
    page = _FinalPage()
    element = AsyncMock()
    element.get_attribute = AsyncMock(side_effect=lambda name: {
        "name": "姓名", "type": "text", "id": "name",
    }.get(name))
    element.get_text = AsyncMock(return_value="")
    page.find_all = AsyncMock(return_value=[element])

    class BadAdapter(BaseApplicationAdapter):
        async def detect_stage(self, page):
            return "single_page"

        async def is_login_page(self, page):
            return False

        async def is_final_review(self, page):
            return True

        async def fill_field(self, page, element, field_info, value):
            return None

    engine = ApplyEngine(tmp_path / "audit.db", AsyncMock(open_page=AsyncMock(return_value=page)), adapters={"generic": BadAdapter()})
    status = await engine.run_application_target(_target("generic"), _profile())
    assert status == ApplicationStatus.PAUSED


@pytest.mark.asyncio
async def test_engine_pauses_when_all_field_inspections_fail(tmp_path: Path):
    await init_db(tmp_path / "audit.db")
    page = _FinalPage()
    element = AsyncMock()
    element.get_attribute = AsyncMock(side_effect=RuntimeError("detached"))
    page.find_all = AsyncMock(return_value=[element])

    class InspectAdapter(BaseApplicationAdapter):
        async def detect_stage(self, page):
            return "single_page"

        async def is_login_page(self, page):
            return False

        async def is_final_review(self, page):
            return True

    browser = AsyncMock()
    browser.open_page.return_value = page
    engine = ApplyEngine(tmp_path / "audit.db", browser, adapters={"generic": InspectAdapter()})
    status = await engine.run_application_target(_target("generic"), _profile())
    assert status == ApplicationStatus.PAUSED


@pytest.mark.asyncio
async def test_login_retries_do_not_consume_stage_transition_budget(tmp_path: Path):
    await init_db(tmp_path / "audit.db")
    page = _FinalPage()
    element = AsyncMock()
    element.get_attribute = AsyncMock(side_effect=lambda name: {
        "name": "姓名", "type": "text", "id": "name",
    }.get(name))
    element.get_text = AsyncMock(return_value="测试甲")
    element.inspect_field = AsyncMock(return_value={
        "label": "姓名", "field_sig": "name", "tag": "input", "type": "text",
        "element_attrs": {"name": "姓名", "type": "text", "id": "name"},
        "outer_html": '<input name="姓名">', "observed_value": "测试甲",
        "is_active": True, "is_valid": True, "section_title": "",
        "option_label": "", "options": None, "widget": "",
    })
    page.find_all = AsyncMock(return_value=[element])

    class ManyStageAdapter(BaseApplicationAdapter):
        def __init__(self):
            super().__init__([ ])
            self.login_checks = 0
            self.transitions = 0

        async def detect_stage(self, page):
            return f"stage_{self.transitions}"

        async def is_login_page(self, page):
            self.login_checks += 1
            return self.login_checks <= 3

        async def is_final_review(self, page):
            return self.transitions >= 8

        async def fill_field(self, page, element, field_info, value):
            return FillResult(success=True, action_type="type_text", observed_value=str(value), verification_status="verified_match")

        async def advance(self, page, current_stage):
            self.transitions += 1
            return self.transitions <= 8

    adapter = ManyStageAdapter()
    browser = AsyncMock()
    browser.open_page.return_value = page
    browser.current_page.return_value = page
    engine = ApplyEngine(tmp_path / "audit.db", browser, adapters={"generic": adapter})
    status = await engine.run_application_target(_target("generic"), _profile())
    assert status == ApplicationStatus.READY_REVIEW
    assert adapter.transitions == 8


@pytest.mark.asyncio
async def test_login_handoff_rebinds_popup_page_and_platform(tmp_path: Path):
    await init_db(tmp_path / "audit.db")
    old_page = _FinalPage()
    old_page.find_all = AsyncMock(return_value=[])
    new_page = _FinalPage()
    new_page.find_all = AsyncMock(return_value=[])

    class LoginAdapter(BaseApplicationAdapter):
        async def detect_stage(self, page):
            return "login" if page is old_page else "form"

        async def is_login_page(self, page):
            return page is old_page

        async def is_final_review(self, page):
            return page is new_page

    class FormAdapter(LoginAdapter):
        pass

    login_adapter = LoginAdapter()
    form_adapter = FormAdapter()
    detector = AsyncMock()
    detector.detect.side_effect = [
        DetectionReport(candidates=[DetectionResult(platform="generic", confidence=0.9)]),
        DetectionReport(candidates=[DetectionResult(platform="moka", confidence=0.9)]),
    ]
    browser = AsyncMock()
    browser.open_page.return_value = old_page
    browser.current_page.return_value = new_page
    engine = ApplyEngine(
        tmp_path / "audit.db",
        browser,
        platform_detector=detector,
        adapters={"generic": login_adapter, "moka": form_adapter},
    )
    status = await engine.run_application_target(_target(None), _profile())
    assert status == ApplicationStatus.READY_REVIEW
    assert detector.detect.await_count == 2
    assert browser.current_page.await_count == 1
