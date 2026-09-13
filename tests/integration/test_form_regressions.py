"""Exercise the real browser wrapper and engine on local, synthetic forms."""
import json
import os
from typing import get_type_hints
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from playwright.async_api import async_playwright, Error

from applypilot.browser.base import InteractionPolicy
from applypilot.browser.playwright_backend import PlaywrightPage
from applypilot.domain.job import ApplicationTarget, ApplicationStatus, Job
from applypilot.domain.profile import CandidateProfile
from applypilot.domain.variant import DisclosurePolicy
from applypilot.modules.apply.engine import ApplyEngine
from applypilot.modules.apply.readiness import ProfileWritebackSynchronizer, ReadinessAuditor
from applypilot.storage.database import init_db
from applypilot.storage.repositories import BaseRepository, SnapshotRepository


def test_repository_annotations_resolve():
    assert get_type_hints(BaseRepository.get_connection)['return'] is not None


def test_json_writeback_remains_json(tmp_path):
    path = tmp_path / 'profile.json'
    path.write_text(json.dumps({'profile_id': 'fixture'}))
    ProfileWritebackSynchronizer.sync_field(path, 'contact.current_city', '北京')
    assert CandidateProfile.model_validate_json(path.read_text()).contact.current_city == '北京'


def test_profile_value_does_not_prove_dom_readiness():
    profile = CandidateProfile(profile_id='fixture', identity={'name': '测试甲'})
    report = ReadinessAuditor.audit_fields([
        {'field_sig': 'name', 'label': '姓名', 'is_required': True,
         'mapped_path': 'identity.name', 'observed_value': ''}
    ], profile)
    assert not report.is_ready


@pytest_asyncio.fixture
async def form(tmp_path, monkeypatch):
    monkeypatch.setenv('APPLYPILOT_HOME', str(tmp_path))
    async with async_playwright() as pw:
        try:
            browser = await pw.chromium.launch(headless=True)
        except Error:
            try:
                browser = await pw.chromium.launch(channel='chrome', headless=True)
            except Error:
                if os.getenv('APPLYPILOT_REQUIRE_BROWSER_TESTS'):
                    raise
                pytest.skip('Install Playwright Chromium to run browser integration tests')
        page = await browser.new_page()
        wrapped = PlaywrightPage(page, InteractionPolicy(action_timeout_ms=500, min_action_interval_ms=0))
        backend = AsyncMock()
        backend.open_page.return_value = wrapped
        db = tmp_path / 'test.db'
        await init_db(db)

        async def run(data=None, provider='generic', sensitive=False, resolver=None):
            target = ApplicationTarget(target_id='fixture', provider=provider,
                disclosure_policy=DisclosurePolicy(allow_sensitive=sensitive),
                job=Job(job_id='fixture', title='Fixture', company_name='Fixture',
                    description_raw='', source_channel='url', source_url='about:blank', apply_url='about:blank'))
            engine = ApplyEngine(db, backend, interactive_readiness=resolver is not None, readiness_resolver=resolver)
            result = await engine.run_application_target(target, CandidateProfile.model_validate({'profile_id': 'fixture', **(data or {})}))
            return result, engine

        yield page, run, db
        await browser.close()


@pytest.mark.asyncio
async def test_native_select_uses_selection(form):
    page, run, _ = form
    await page.set_content('<select aria-label="性别" required><option value="">请选择</option><option value="male">男</option></select>')
    await page.evaluate("document.body.insertAdjacentHTML('beforeend', '<button>提交申请</button>')")
    status, _ = await run({'identity': {'gender': 'male'}})
    assert await page.locator('select').input_value() == 'male'
    assert status == ApplicationStatus.READY_REVIEW


@pytest.mark.asyncio
async def test_radio_checks_matching_option(form):
    page, run, _ = form
    await page.set_content('<input name="性别" type="radio" value="male" required><input name="性别" type="radio" value="female" required>')
    await page.evaluate("document.body.insertAdjacentHTML('beforeend', '<button>提交申请</button>')")
    status, _ = await run({'identity': {'gender': 'male'}})
    assert await page.locator('[value=male]').is_checked()
    assert not await page.locator('[value=female]').is_checked()
    assert status == ApplicationStatus.READY_REVIEW


@pytest.mark.asyncio
async def test_reads_live_input_value(form):
    page, run, _ = form
    await page.set_content('<input aria-label="姓名" value="测试甲">')
    await page.locator('input').fill('测试乙')
    await run({'identity': {'name': '测试甲'}})
    assert await page.locator('input').input_value() == '测试甲'


@pytest.mark.asyncio
async def test_native_label_maps_field(form):
    page, run, _ = form
    await page.set_content('<label for="f_123">* 手机号</label><input id="f_123">')
    await run({'contact': {'mobile': '13800138000'}})
    assert await page.locator('input').input_value() == '13800138000'


@pytest.mark.asyncio
async def test_label_required_marker_halts(form):
    page, run, _ = form
    await page.set_content('<label for="f_123">* 手机号</label><input id="f_123">')
    status, _ = await run()
    assert status == ApplicationStatus.PAUSED


@pytest.mark.asyncio
async def test_failed_required_upload_halts(form, tmp_path):
    page, run, _ = form
    await page.set_content('<input aria-label="上传简历" type="file" required>')
    status, _ = await run({'assets': [{'asset_id': 'asset_resume_pdf', 'asset_type': 'resume_pdf', 'file_path': str(tmp_path / 'missing.pdf'), 'title': 'Fixture'}]})
    assert status == ApplicationStatus.PAUSED


@pytest.mark.asyncio
async def test_audit_does_not_store_sensitive_plaintext(form):
    page, run, db = form
    await page.set_content('<input aria-label="身份证号">')
    value = '110101200001011234'
    _, engine = await run({'identity': {'id_number': value}}, sensitive=True)
    runs = await engine.app_repo.list_runs_by_application('app_fixture')
    actions = await SnapshotRepository(db).list_field_actions(runs[0]['id'])
    assert actions and value not in json.dumps(actions)
    assert actions[0]['expected_hash'].startswith('hmac-sha256:')
    assert actions[0]['observed_hash'] == actions[0]['expected_hash']


@pytest.mark.asyncio
async def test_beisen_advances_without_submitting(form):
    page, run, _ = form
    await page.set_content('''<div id="stage"><input aria-label="姓名"><button type="button" onclick="document.getElementById('stage').innerHTML = '<h2>确认信息</h2><button onclick=window.submitted=true>提交申请</button>'">下一步</button></div>''')
    status, _ = await run({'identity': {'name': '测试甲'}}, provider='beisen')
    assert status == ApplicationStatus.READY_REVIEW
    assert await page.get_by_text('提交申请', exact=True).count() == 1
    assert not await page.evaluate('Boolean(window.submitted)')


@pytest.mark.asyncio
async def test_beisen_unknown_stage_pauses(form):
    page, run, _ = form
    await page.set_content('<h2>无法识别的阶段</h2>')
    status, _ = await run(provider='beisen')
    assert status == ApplicationStatus.PAUSED


@pytest.mark.asyncio
async def test_manual_resolution_is_rechecked(form):
    page, run, _ = form
    await page.set_content('<input aria-label="手机号" required>')
    status, _ = await run(resolver=lambda *args: True)
    assert status == ApplicationStatus.PAUSED


@pytest.mark.asyncio
async def test_manual_resolution_filled_page_proceeds(form):
    page, run, _ = form
    await page.set_content('<input aria-label="手机号" required>')
    await page.evaluate("document.body.insertAdjacentHTML('beforeend', '<button>提交申请</button>')")
    async def resolve(*args):
        await page.locator('input').fill('13800138000')
        return True
    status, _ = await run(resolver=resolve)
    assert status == ApplicationStatus.READY_REVIEW


@pytest.mark.asyncio
async def test_beisen_blocked_next_does_not_claim_review(form):
    page, run, _ = form
    await page.set_content('<button type="button">下一步</button>')
    status, _ = await run(provider='beisen')
    assert status == ApplicationStatus.PAUSED


@pytest.mark.asyncio
async def test_existing_checked_checkbox_is_not_toggled_off(form):
    page, run, _ = form
    await page.set_content('''<fieldset><legend>姓名</legend><input type="checkbox" aria-label="姓名" value="测试甲"></fieldset><button onclick="document.querySelector('h2').textContent='第二阶段'; this.remove()">下一步</button><h2>第一阶段</h2>''')
    # A value set through JS is live state, without a checked HTML attribute.
    await page.locator('input').check()
    await run({'identity': {'name': '测试甲'}}, provider='beisen')
    assert await page.locator('input').is_checked()


@pytest.mark.asyncio
async def test_textarea_uses_text_filler(form):
    page, run, _ = form
    await page.set_content('<textarea aria-label="姓名" required></textarea>')
    await page.evaluate("document.body.insertAdjacentHTML('beforeend', '<button>提交申请</button>')")
    status, _ = await run({'identity': {'name': '测试甲'}})
    assert await page.locator('textarea').input_value() == '测试甲'
    assert status == ApplicationStatus.READY_REVIEW


@pytest.mark.asyncio
async def test_beisen_only_fills_visible_stage(form):
    page, run, _ = form
    await page.set_content('''
      <section id="first"><input aria-label="姓名" required>
        <button onclick="document.getElementById('first').hidden=true;document.getElementById('second').hidden=false">下一步</button>
      </section>
      <section id="second" hidden><input aria-label="手机号" required><button>提交申请</button></section>
    ''')
    status, _ = await run({'identity': {'name': '测试甲'}, 'contact': {'mobile': '13800138000'}}, provider='beisen')
    assert status == ApplicationStatus.READY_REVIEW
    assert await page.locator('#second input').input_value() == '13800138000'


@pytest.mark.asyncio
async def test_hidden_upload_with_visible_label_is_filled(form, tmp_path):
    page, run, _ = form
    await page.set_content('<label for="resume">* 上传简历</label><input id="resume" type="file" style="display:none" required>')
    await page.evaluate("document.body.insertAdjacentHTML('beforeend', '<button>提交申请</button>')")
    asset = tmp_path / 'resume.pdf'
    asset.write_bytes(b'%PDF-1.4\n% synthetic upload fixture\n')
    status, _ = await run({'assets': [{'asset_id': 'asset_resume_pdf', 'asset_type': 'resume_pdf', 'file_path': str(asset), 'title': 'Fixture'}]})
    assert status == ApplicationStatus.READY_REVIEW
    assert await page.locator('input').evaluate('el => el.files[0].name') == 'resume.pdf'


@pytest.mark.asyncio
async def test_snapshot_does_not_store_candidate_values(form):
    page, run, db = form
    secret_name = '审查候选人敏感姓名'
    await page.set_content('<input aria-label="姓名"><button>提交申请</button>')
    status, _ = await run({'identity': {'name': secret_name}})
    assert status == ApplicationStatus.READY_REVIEW
    import aiosqlite
    async with aiosqlite.connect(db) as conn:
        row = await (await conn.execute(
            'SELECT fields_meta_json FROM form_snapshots ORDER BY rowid DESC LIMIT 1'
        )).fetchone()
    assert secret_name not in row[0]
    assert 'expected_value' not in row[0]
    assert 'observed_value' not in row[0]
    assert 'outer_html' not in row[0]


@pytest.mark.asyncio
async def test_prefilled_blocked_sensitive_field_pauses(form):
    page, run, _ = form
    value = '110101200001011234'
    await page.set_content(f'<input aria-label="身份证号" value="{value}"><button>提交申请</button>')
    status, _ = await run({'identity': {'id_number': value}}, sensitive=False)
    assert status == ApplicationStatus.PAUSED


@pytest.mark.asyncio
async def test_optional_radio_without_matching_option_pauses(form):
    page, run, _ = form
    await page.set_content('''
        <fieldset><legend>性别</legend>
          <label><input name="gender" type="radio" value="x">未知一</label>
          <label><input name="gender" type="radio" value="y">未知二</label>
        </fieldset><button>提交申请</button>
    ''')
    status, _ = await run({'identity': {'gender': 'male'}})
    assert status == ApplicationStatus.PAUSED


@pytest.mark.asyncio
async def test_disabled_submit_does_not_claim_final_review(form):
    page, run, _ = form
    await page.set_content('<input aria-label="姓名"><button disabled>提交申请</button>')
    status, _ = await run({'identity': {'name': '测试甲'}})
    assert status == ApplicationStatus.PAUSED


@pytest.mark.asyncio
async def test_moka_login_text_in_header_does_not_block_form(form):
    page, run, _ = form
    await page.set_content('<nav>立即登录</nav><input aria-label="姓名"><button>提交申请</button>')
    status, _ = await run({'identity': {'name': '测试甲'}}, provider='moka')
    assert status == ApplicationStatus.READY_REVIEW
    assert await page.locator('input').input_value() == '测试甲'


@pytest.mark.asyncio
async def test_secret_asset_is_not_uploaded_when_sensitive_disclosure_disabled(form, tmp_path):
    page, run, _ = form
    secret_file = tmp_path / 'secret-resume.pdf'
    secret_file.write_bytes(b'%PDF-1.4 audit fixture')
    await page.set_content('<input aria-label="上传简历" type="file" required><button>提交申请</button>')
    status, _ = await run({'assets': [{
        'asset_id': 'asset_resume_pdf', 'asset_type': 'resume_pdf',
        'file_path': str(secret_file), 'title': 'secret', 'sensitivity': 'secret',
    }]}, sensitive=False)
    assert status == ApplicationStatus.PAUSED
    assert await page.locator('input').evaluate('el => el.files.length') == 0


@pytest.mark.asyncio
async def test_moka_search_widget_selects_and_verifies_option(form):
    page, run, _ = form
    await page.set_content('''
        <input aria-label="毕业院校" data-widget="search_select">
        <div role="option" onclick="const i=document.querySelector('input');i.value=this.textContent.trim();i.dispatchEvent(new Event('input',{bubbles:true}));i.dispatchEvent(new Event('change',{bubbles:true}))">清华大学</div>
        <button>提交申请</button>
    ''')
    status, _ = await run({'education': [{
        'id': 'edu-master', 'school_name': '清华大学', 'education_level': 'master',
        'major': '计算机科学', 'start_date': '2022-09', 'end_date': '2025-06',
    }]}, provider='moka')
    assert status == ApplicationStatus.READY_REVIEW
    assert await page.locator('input').input_value() == '清华大学'
