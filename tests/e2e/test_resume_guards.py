import asyncio
from unittest.mock import patch
from typer.testing import CliRunner
import pytest
from applypilot.cli.main import app
from applypilot.storage.database import init_db
from applypilot.storage.repositories import ApplicationRepository,CheckpointRepository,RevisionRepository
from applypilot.domain.variant import DisclosurePolicy


@pytest.mark.parametrize('candidate,has_checkpoint,expected', [('owner',True,0),('other',True,1),('owner',False,1)])
def test_resume_identity_cycle_and_checkpoint(tmp_path,monkeypatch,candidate,has_checkpoint,expected):
    monkeypatch.setenv('APPLYPILOT_HOME',str(tmp_path))
    (tmp_path/'profile.yaml').write_text(f'profile_id: {candidate}\n')
    db=tmp_path/'applypilot.db'
    async def setup():
        await init_db(db)
        repo=ApplicationRepository(db)
        await repo.create_application('original','owner:job:2027','owner','job','company','title',recruitment_cycle='2027',status='paused')
        await RevisionRepository(db).save_profile_revision('rev','owner','hash',{})
        await repo.create_run('run','original',profile_revision_id='rev')
        if has_checkpoint:
            await CheckpointRepository(db).save_checkpoint('check','original','run',page_url='https://fixture.test/step2')
    asyncio.run(setup())
    with patch('applypilot.cli.main._execute_apply_session') as execute:
        result=CliRunner().invoke(app,['apply','resume','original'])
        assert result.exit_code==expected,result.output
        if expected:
            execute.assert_not_called()
        else:
            target=execute.call_args.kwargs['target']
            assert target.job.recruitment_cycle=='2027'
            assert target.final_form_url=='https://fixture.test/step2'


def test_resume_restores_original_disclosure_policy(tmp_path, monkeypatch):
    monkeypatch.setenv('APPLYPILOT_HOME', str(tmp_path))
    (tmp_path / 'profile.yaml').write_text('profile_id: owner\n')
    db = tmp_path / 'applypilot.db'

    async def setup():
        await init_db(db)
        repo = ApplicationRepository(db)
        await repo.create_application(
            'original', 'owner:job:2027', 'owner', 'job', 'company', 'title',
            recruitment_cycle='2027', status='paused',
            target_context={
                'provider': 'generic',
                'platform_type': 'company',
                'assigned_variant_id': 'variant-1',
                'disclosure_policy': DisclosurePolicy(blocked_field_paths={'contact.email'}).model_dump(mode='json'),
            },
        )
        await RevisionRepository(db).save_profile_revision('rev', 'owner', 'hash', {})
        await repo.create_run('run', 'original', profile_revision_id='rev')
        await CheckpointRepository(db).save_checkpoint('check', 'original', 'run', page_url='https://fixture.test/step2')

    asyncio.run(setup())
    with patch('applypilot.cli.main._execute_apply_session') as execute:
        result = CliRunner().invoke(app, ['apply', 'resume', 'original'])
        assert result.exit_code == 0, result.output
        target = execute.call_args.kwargs['target']
        assert target.provider == 'generic'
        assert target.platform_type == 'company'
        assert target.assigned_variant_id == 'variant-1'
        assert target.disclosure_policy.blocked_field_paths == {'contact.email'}


def test_legacy_resume_disables_automatic_disclosure_without_saved_context(tmp_path, monkeypatch):
    monkeypatch.setenv('APPLYPILOT_HOME', str(tmp_path))
    (tmp_path / 'profile.yaml').write_text('profile_id: owner\n')
    db = tmp_path / 'applypilot.db'

    async def setup():
        await init_db(db)
        repo = ApplicationRepository(db)
        await repo.create_application('original', 'owner:job:2027', 'owner', 'job', 'company', 'title', status='paused')
        await RevisionRepository(db).save_profile_revision('rev', 'owner', 'hash', {})
        await repo.create_run('run', 'original', profile_revision_id='rev')
        await CheckpointRepository(db).save_checkpoint('check', 'original', 'run', page_url='https://fixture.test/step2')

    asyncio.run(setup())
    with patch('applypilot.cli.main._execute_apply_session') as execute:
        result = CliRunner().invoke(app, ['apply', 'resume', 'original'])
        assert result.exit_code == 0, result.output
        target = execute.call_args.kwargs['target']
        assert target.disclosure_policy.blocked_field_paths == {'*'}
