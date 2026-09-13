import pytest
from tests.integration.test_form_regressions import form
from applypilot.cli.main import _canonical_job_id_from_url
from applypilot.modules.profile.resolver import ValueResolver
from applypilot.modules.apply.mapper import FieldMapper
from applypilot.domain.profile import CandidateProfile
from applypilot.domain.job import ApplicationStatus


def test_hash_routes_distinct():
    assert _canonical_job_id_from_url('https://a.test/#/job/1') != _canonical_job_id_from_url('https://a.test/#/job/2')


def test_transcript_directory_not_resume():
    p = CandidateProfile(profile_id='x', assets=[dict(asset_id='t', asset_type='transcript', title='成绩单', file_path='/tmp/resumes/transcript.pdf')])
    assert ValueResolver.resolve(p,None,'assets[asset_resume_pdf].file_path') is None


def test_doctor_not_master():
    assert FieldMapper.map_field('s','博士研究生毕业院校').profile_path == 'education[doctor].school_name'


@pytest.mark.asyncio
@pytest.mark.parametrize('html,data,expected,status',[
 ('<input aria-label="姓名"><button type="button">下一步</button>',{'identity':{'name':'甲'}},'甲',ApplicationStatus.PAUSED),
 ('<fieldset><legend>家庭成员</legend><label for="n">姓名</label><input id="n" required></fieldset><button>提交申请</button>',{'identity':{'name':'甲'}},'',ApplicationStatus.PAUSED),
 ('<select aria-label="性别" required><option value="">请选择</option><option value="1">女</option><option value="2">男</option></select><button>提交申请</button>',{'identity':{'gender':'male'}},'2',ApplicationStatus.READY_REVIEW),
 ('<input aria-label="出生日期" type="date" required><button>提交申请</button>',{'identity':{'birth_date':'2000-05'}},'',ApplicationStatus.PAUSED),
])
async def test_actual_page_regressions(form,html,data,expected,status):
    page,run,_=form
    await page.set_content(html)
    result,_=await run(data,provider='beisen' if '下一步' in html else 'generic')
    assert await page.locator('input,select').input_value()==expected
    assert result==status


@pytest.mark.asyncio
async def test_cycles_are_distinct_and_retries_reuse(tmp_path):
    from unittest.mock import AsyncMock
    from applypilot.storage.database import init_db
    from applypilot.modules.apply.engine import ApplyEngine
    from tests.unit.modules.test_engine import _create_sample_target
    db=tmp_path/'cycles.db'
    await init_db(db)
    backend=AsyncMock()
    backend.open_page.return_value.find_all.return_value=[]
    backend.open_page.return_value.execute_unsafe_script.return_value=False
    engine=ApplyEngine(db,backend,interactive_readiness=False)
    target=_create_sample_target()
    for cycle in ['2026','2027','2027']:
        target.job.recruitment_cycle=cycle
        await engine.run_application_target(target,CandidateProfile(profile_id='fixture'))
    apps=await engine.app_repo.list_applications()
    assert len(apps)==2
    for row in apps:
        runs=await engine.app_repo.list_runs_by_application(row['id'])
        assert len(runs)==(2 if row['recruitment_cycle']=='2027' else 1)


@pytest.mark.asyncio
async def test_checkpoint_tracks_current_url(form):
    page,run,_=form
    await page.route('https://fixture.test/**',lambda route:route.fulfill(body='<input aria-label="手机号" required>'))
    await page.goto('https://fixture.test/apply/step2')
    status,engine=await run()
    row=(await engine.app_repo.list_applications())[0]
    checkpoint=await engine.chk_repo.get_latest_checkpoint(row['id'])
    assert status==ApplicationStatus.PAUSED
    assert checkpoint['page_url']=='https://fixture.test/apply/step2'


def test_multiple_resumes_require_explicit_selection():
    p=CandidateProfile(profile_id='x',assets=[dict(asset_id=x,asset_type='resume_pdf',title=x,file_path='/tmp/'+x+'.pdf') for x in ['resume_a','resume_b']])
    assert ValueResolver.resolve(p,None,'assets[asset_resume_pdf].file_path') is None
    assert ValueResolver.resolve(p,None,'assets[resume_b].file_path')=='/tmp/resume_b.pdf'


def test_father_section_not_candidate():
    assert FieldMapper.map_field('name','姓名',section_title='父亲').profile_path=='soe_extended.family_members[father].name'


def test_grandfather_is_not_father():
    p=CandidateProfile(profile_id='x',soe_extended={'family_members':[dict(id='grandfather',relation='祖父',name='祖父甲')]})
    assert ValueResolver.resolve(p,None,'soe_extended.family_members[father].name') is None


def test_explicit_education_label_wins_over_section():
    assert FieldMapper.map_field('s','本科毕业院校',section_title='博士教育').profile_path=='education[bachelor].school_name'


@pytest.mark.asyncio
async def test_ambiguous_legacy_job_alias_does_not_mix_candidates(tmp_path):
    from applypilot.storage.database import init_db
    from applypilot.storage.repositories import ApplicationRepository,CheckpointRepository
    db=tmp_path/'aliases.db'
    await init_db(db)
    repo=ApplicationRepository(db)
    for owner in ['a','b']:
        await repo.create_application('app_'+owner,owner+':job:default',owner,'job','company','title')
    assert await repo.get_application('app_job') is None
    assert await repo.list_runs_by_application('app_job')==[]
    assert await CheckpointRepository(db).get_latest_checkpoint('app_job') is None
    assert (await repo.get_application('app_a'))['candidate_id']=='a'


@pytest.mark.asyncio
async def test_dynamic_required_field_is_discovered_before_final_review(form):
    page, run, _ = form
    await page.set_content('''
        <input aria-label="姓名" required
          oninput="if (!document.querySelector('#email')) {
            const email = document.createElement('input');
            email.id = 'email'; email.required = true; email.setAttribute('aria-label', '邮箱');
            document.body.appendChild(email);
          }">
        <button>提交申请</button>
    ''')
    status, _ = await run({'identity': {'name': '候选人甲'}})
    assert await page.locator('#email').input_value() == ''
    assert status == ApplicationStatus.PAUSED


@pytest.mark.asyncio
async def test_required_value_that_cannot_be_overwritten_halts_for_review(form):
    page, run, _ = form
    await page.set_content('<input aria-label="姓名" value="其他人乙" readonly required><button>提交申请</button>')
    status, _ = await run({'identity': {'name': '候选人甲'}})
    assert await page.locator('input').input_value() == '其他人乙'
    assert status == ApplicationStatus.PAUSED


@pytest.mark.asyncio
async def test_nested_family_section_is_not_mapped_to_candidate_name(form):
    page, run, _ = form
    await page.set_content('''
        <section><h2>家庭成员</h2>
          <fieldset><label for="family-name">姓名</label><input id="family-name" required></fieldset>
        </section>
        <button>提交申请</button>
    ''')
    status, _ = await run({'identity': {'name': '候选人甲'}})
    assert await page.locator('#family-name').input_value() == ''
    assert status == ApplicationStatus.PAUSED


@pytest.mark.asyncio
async def test_concrete_academic_degree_does_not_fall_back_to_another_degree(form):
    page, run, _ = form
    await page.set_content('''
        <select aria-label="学位" required>
          <option value="">请选择</option><option value="science">理学硕士</option>
          <option value="engineering">工程硕士</option>
        </select><button>提交申请</button>
    ''')
    status, _ = await run({'education': [{
        'id': 'edu-master', 'school_name': '测试大学', 'education_level': 'master',
        'academic_degree': '工学硕士', 'major': '计算机科学',
        'start_date': '2022-09', 'end_date': '2025-06',
    }]})
    assert await page.locator('select').input_value() == ''
    assert status == ApplicationStatus.PAUSED


@pytest.mark.asyncio
async def test_login_page_with_phone_input_pauses_before_filling(form):
    page, run, _ = form
    await page.set_content('<h1>请先登录</h1><input aria-label="手机号"><button>提交</button>')
    status, _ = await run({'contact': {'mobile': '13800138000'}})
    assert await page.locator('input').input_value() == ''
    assert status == ApplicationStatus.PAUSED
