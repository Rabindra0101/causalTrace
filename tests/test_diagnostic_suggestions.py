"""General diagnosis control flow and consent: every model response is mocked."""
import json
from pathlib import Path
from unittest.mock import patch
import pytest
from causaltrace import pipeline, build_doctor, diagnostic_context
from causaltrace.demo_setup import git
from causaltrace.test_runner import execution_error

@pytest.fixture
def project(tmp_path):
    repo = tmp_path / 'project'
    repo.mkdir()
    (repo / 'service.py').write_text("def name(data):\n    return data['name']\n")
    (repo / 'test_service.py').write_text("from service import name\ndef test_empty():\n    assert name({}) == ''\n")
    (repo / 'package.json').write_text('{"scripts":{"test":"node --test"}}')
    git(repo, 'init', '--template=', '--initial-branch=main')
    git(repo, 'add', '.')
    git(repo, 'commit', '-qm', 'Only original revision; no known passing parent')
    return repo


def model_reply(category):
    return json.dumps({'category': category, 'summary': 'Evidence supports a possible ' + category + ' issue.',
        'evidence': ['The supplied baseline log records this error.'],
        'recommended_steps': ['Check the failing code path and environment; rerun the committed tests.'],
        'suggested_tests': ['Add a regression test for the observed failure.'],
        'improvements': ['Document the relevant input contract.'], 'confidence': 'medium', 'replacements': []}), 'mock-nemotron'

@pytest.mark.parametrize('category,baseline', [
    ('dependency', execution_error("ModuleNotFoundError: No module named 'requests'")),
    ('compiler', execution_error('javac: error: cannot find symbol UserRepository')),
    ('configuration', {'status':'fail', 'passed':False, 'output':'ValueError: invalid configuration PORT=abc', 'return_code':1}),
    ('API contract', {'status':'fail', 'passed':False, 'output':'test_empty_response: expected HTTP 200 for [], received 404', 'return_code':1}),
])
def test_full_mode_provides_general_suggestions_without_proven_history(project, tmp_path, category, baseline):
    with patch.object(pipeline, 'test_commit', return_value=baseline), \
         patch.object(build_doctor, 'complete', return_value=model_reply(category)) as model, \
         patch.object(pipeline, 'verify') as verify:
        report = pipeline.run_investigation(project, '.', 'local', tmp_path/'reports', share_with_nebius=True, test_runner='pytest')
    assert report['ai_analysis']['status'] == 'completed'
    assert report['repair']['diagnosis']['category'] == category
    assert report['repair']['verification']['status'] == 'not_run'
    assert not report.get('regression', {}).get('confirmed')
    assert not report['experiments']
    assert 'Suggested tests' in report['ai_analysis']['hypothesis']
    assert 'Optional improvements' in report['ai_analysis']['hypothesis']
    model.assert_called_once()
    verify.assert_not_called()
    assert git(project, 'status', '--porcelain') == ''


def test_explicit_consent_is_required_before_evidence_selection_or_model_call(project, tmp_path):
    with patch.object(pipeline, 'test_commit', return_value=execution_error('Build failed: missing dependencies')), \
         patch.object(diagnostic_context, 'evidence') as select, patch.object(pipeline, 'investigate') as model:
        report = pipeline.run_investigation(project, '.', 'local', tmp_path/'reports', investigation_type='diagnose', test_runner='pytest')
    assert report['ai_analysis']['status'] == 'consent_required'
    select.assert_not_called()
    model.assert_not_called()
    assert pipeline.MODEL_CONSENT.get() is False


def test_passing_project_can_get_optional_review_without_a_verified_bug(project, tmp_path):
    baseline = {'status':'pass', 'passed':True, 'output':'1 passed', 'return_code':0}
    with patch.object(pipeline, 'test_commit', return_value=baseline), \
         patch.object(build_doctor, 'complete', return_value=model_reply('optional review')), \
         patch.object(pipeline, 'verify') as verify:
        report = pipeline.run_investigation(project, '.', 'local', tmp_path/'reports', investigation_type='diagnose', test_runner='pytest', share_with_nebius=True)
    assert report['status'] == 'completed'
    assert 'regression' not in report
    assert 'pass' in report['baseline']['status']
    verify.assert_not_called()


def test_context_prioritizes_stack_trace_and_excludes_environment_and_secret_files(project):
    for i in range(18):
        (project / f'unrelated{i}.py').write_text('x = 1\n')
    (project / '.env').write_text('FAKE_TEST_VALUE=fixture\n')
    (project / 'secrets.json').write_text('{"value":"fixture"}')
    git(project, 'add', '.')
    git(project, 'commit', '-qm', 'Additional context fixtures')
    files, scope = diagnostic_context.evidence(project, log='Traceback in service.py:2')
    assert files[0].path == 'service.py'
    assert len(files) == 12
    assert scope['omitted_files']
    assert all(f.path not in ('.env','secrets.json') for f in files)
    assert len(diagnostic_context.bounded_text('x'*50000, 40000)) == 40000


def test_source_patch_verification_uses_complete_repository(project, tmp_path):
    baseline = {'status':'fail', 'passed':False, 'output':"service.py:2 KeyError: 'name'", 'return_code':1}
    response = json.loads(model_reply('missing key')[0])
    response['replacements'] = [{'path':'service.py', 'old':"return data['name']", 'new':"return data.get('name', '')"}]
    with patch.object(pipeline, 'test_commit', return_value=baseline), \
         patch.object(build_doctor, 'complete', return_value=(json.dumps(response),'mock-nemotron')), \
         patch.object(pipeline, 'verify', return_value={'status':'not_verified'}) as verify:
        report = pipeline.run_investigation(project, '.', 'local', tmp_path/'reports', investigation_type='diagnose', test_runner='pytest', share_with_nebius=True)
        assert verify.call_args.kwargs['directory'] == '.'
        assert Path(verify.call_args.kwargs['repository']).name
    assert report['repair']['verification']['status'] == 'not_verified'
    assert "return data['name']" in (project/'service.py').read_text()

@pytest.mark.skipif(__import__('os').environ.get('CAUSALTRACE_DOCKER_TESTS') != '1', reason='Opt in to real Docker repair verification')
def test_real_import_error_repair_uses_original_fixture_assets_without_history(tmp_path):
    repo = tmp_path/'original'
    repo.mkdir()
    (repo/'service.py').write_text("def normalize_username(value):\n    return value.strip().lower()\n")
    (repo/'fixtures').mkdir()
    (repo/'fixtures'/'user.json').write_text('{"name":" Alice "}')
    (repo/'test_service.py').write_text("import json\nfrom pathlib import Path\nfrom service import normalize_user\n\ndef test_fixture_user():\n    data = json.loads((Path(__file__).parent/'fixtures'/'user.json').read_text())\n    assert normalize_user(data['name']) == 'alice'\n")
    git(repo, 'init', '--template=', '--initial-branch=main')
    git(repo, 'add', '.')
    git(repo, 'commit', '-qm', 'Import contract broken at only committed revision')
    response = json.loads(model_reply('import contract')[0])
    response['replacements'] = [{'path':'service.py','old':'normalize_username','new':'normalize_user'}]
    with patch.object(build_doctor, 'complete', return_value=(json.dumps(response),'mock-nemotron')):
        report = pipeline.run_investigation(repo, '.', 'local', tmp_path/'reports', investigation_type='diagnose', test_runner='pytest', share_with_nebius=True)
    assert report['baseline']['status'] == 'collection_error'
    assert report['repair']['verification']['status'] == 'verified'
    assert report['repair']['verification']['after']['status'] == 'pass'
    assert 'regression' not in report
    assert 'normalize_username' in (repo/'service.py').read_text()
    assert git(repo, 'status', '--porcelain') == ''
