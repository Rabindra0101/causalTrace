"""Release-agent integration with real Git history and mocked model/provider calls."""
import json
import os
from pathlib import Path
from unittest.mock import patch
import pytest
from causaltrace import pipeline, verifier, build_doctor, release_investigation as release
from causaltrace.demo_setup import git
from causaltrace.test_runner import parse_result, SUMMARY_MARKER

IDS = ['test_service.py::test_normalize', 'test_service.py::test_empty', 'test_service.py::test_stable']
GOOD = "def normalize(value):\n    return value.strip().lower()\n\ndef response(items):\n    return items\n\ndef stable():\n    return True\n"

def fake_runner(path):
    code = (Path(path)/'service.py').read_text(encoding='utf-8')
    failed = []
    if 'return value.strip()\n' in code:
        failed.append(IDS[0])
    if 'return items or None' in code:
        failed.append(IDS[1])
    if 'return False' in code:
        failed.append(IDS[2])
    summary = {'test_ids':IDS, 'passed_ids':[i for i in IDS if i not in failed], 'failed_ids':failed, 'skipped_ids':[], 'collection_errors':[]}
    return parse_result(1 if failed else 0, 'service.py: failing API/string contract\n'+SUMMARY_MARKER+json.dumps(summary), '')

@pytest.fixture
def history(tmp_path):
    repo = tmp_path/'app'
    repo.mkdir()
    (repo/'service.py').write_text(GOOD)
    (repo/'test_service.py').write_text('''from service import normalize, response, stable

def test_normalize():
    assert normalize(' Alice ') == 'alice'

def test_empty():
    assert response([]) == []

def test_stable():
    assert stable() is True
''')
    git(repo,'init','--template=','--initial-branch=main')
    git(repo,'add','.')
    git(repo,'commit','-qm','Working release')
    git(repo,'tag','v1.0.0')
    commits = {}
    for n in range(1,13):
        if n == 4:
            code = (repo/'service.py').read_text().replace('return value.strip().lower()', 'return value.strip()')
            (repo/'service.py').write_text(code)
        elif n == 9:
            code = (repo/'service.py').read_text().replace('return items\n', 'return items or None\n')
            (repo/'service.py').write_text(code)
        else:
            (repo/'notes.txt').write_text('Unrelated release note '+str(n))
        git(repo,'add','.')
        git(repo,'commit','-qm',f'Update {n}')
        commits[n] = git(repo,'rev-parse','HEAD')
    git(repo,'tag','v2.0.0')
    return repo, commits


def answer(messages, **kwargs):
    payload = json.loads(messages[1]['content'])
    source = next(f for f in payload['files'] if f['path']=='service.py')
    old,new = ('return value.strip()','return value.strip().lower()') if 'return value.strip()\n' in source['content'] else ('return items or None','return items')
    return json.dumps({'category':'API/string contract','summary':'Repair the observed contract failure.',
        'evidence':['service.py disagrees with the unchanged regression test.'],
        'recommended_steps':['Apply the source patch and run the full suite.'],
        'replacements':[{'path':'service.py','old':old,'new':new}]}),'mock-nemotron-agent'


def test_two_independent_bugs_are_bisected_reversed_and_fixed_iteratively(history,tmp_path):
    repo, commits = history
    original = (repo/'service.py').read_bytes()
    with patch.object(verifier,'run_pytest',side_effect=fake_runner), patch.object(release,'run_pytest',side_effect=fake_runner), \
         patch.object(build_doctor,'run_pytest',side_effect=fake_runner), patch.object(build_doctor,'complete',side_effect=answer) as model:
        report = pipeline.run_investigation(repo,'.','local',tmp_path/'reports',investigation_type='release',
            test_runner='pytest',good_ref='v1.0.0',bad_ref='v2.0.0',share_with_nebius=True)
    assert report['status']=='completed'
    groups = {g['test_id']:g for g in report['failure_groups']}
    assert groups[IDS[0]]['suspected_commit']==commits[4]
    assert groups[IDS[1]]['suspected_commit']==commits[9]
    assert all(g['confirmed'] and g['reversal']['outcome']=='verified' for g in groups.values())
    session=report['repair_session']
    assert session['status']=='verified'
    assert [a['accepted'] for a in session['attempts']]==[True,True]
    assert session['attempts'][0]['verification']['status']=='not_verified'
    assert session['final_tests']['passed']
    assert model.call_count==2
    assert len(report['regression']['history']) < 13
    assert (tmp_path/'reports'/(report['id']+'.patch')).is_file()
    assert 'service.py' in session['patch'] and 'test_service.py' not in session['patch']
    assert (repo/'service.py').read_bytes()==original
    assert git(repo,'rev-parse','HEAD')==commits[12]


def test_no_consent_still_finds_boundaries_but_never_calls_model(history,tmp_path):
    repo,_=history
    with patch.object(verifier,'run_pytest',side_effect=fake_runner), patch.object(release,'run_pytest',side_effect=fake_runner), \
         patch.object(build_doctor,'complete') as model:
        report=pipeline.run_investigation(repo,'.','local',tmp_path/'reports',investigation_type='release',test_runner='pytest',good_ref='v1.0.0')
    assert len(report['failure_groups'])==2
    assert report['repair_session']['status']=='not_run'
    assert 'repair_patch_url' not in report
    model.assert_not_called()


def test_candidate_that_breaks_a_passing_test_is_rejected(history,tmp_path):
    repo,_=history
    def harmful(messages,**kwargs):
        content, model=answer(messages,**kwargs)
        data=json.loads(content)
        data['replacements'].append({'path':'service.py','old':'return True','new':'return False'})
        return json.dumps(data),model
    with patch.object(verifier,'run_pytest',side_effect=fake_runner), patch.object(release,'run_pytest',side_effect=fake_runner), \
         patch.object(build_doctor,'run_pytest',side_effect=fake_runner), patch.object(build_doctor,'complete',side_effect=harmful):
        report=pipeline.run_investigation(repo,'.','local',tmp_path/'reports',investigation_type='release',test_runner='pytest',good_ref='v1.0.0',share_with_nebius=True,max_repair_attempts=1)
    assert report['repair_session']['status']=='not_verified'
    assert not report['repair_session']['attempts'][0]['accepted']
    assert 'repair_patch_url' not in report


def test_invalid_or_reversed_release_range_is_rejected(history):
    repo,_=history
    for good,bad in [('v2.0.0','v1.0.0'),('v1.0.0','v1.0.0'),('--help','HEAD')]:
        with pytest.raises(ValueError):
            release.resolve_releases(repo,good,bad)


def test_missing_test_evidence_never_becomes_a_confirmed_boundary(history):
    repo,_=history
    good,bad,revisions=release.resolve_releases(repo,'v1.0.0','v2.0.0')
    cache={good:parse_result(0,SUMMARY_MARKER+json.dumps({'test_ids':IDS,'passed_ids':IDS,'failed_ids':[],'skipped_ids':[],'collection_errors':[]}),''),bad:fake_runner(repo)}
    with patch.object(release,'test_commit',return_value={'status':'error','execution_error':True}):
        groups,_,_=release.regression_search(repo,'.',revisions,cache)
    assert all(not g['confirmed'] for g in groups)

@pytest.mark.skipif(os.environ.get('CAUSALTRACE_RELEASE_DOCKER_TESTS')!='1',reason='Opt in to real Docker release repair experiments')
def test_real_docker_release_agent_repairs_two_bugs_with_mocked_nemotron(history,tmp_path):
    repo,_=history
    with patch.object(build_doctor,'complete',side_effect=answer):
        report=pipeline.run_investigation(repo,'.','local',tmp_path/'reports',investigation_type='release',test_runner='pytest',good_ref='v1.0.0',bad_ref='v2.0.0',share_with_nebius=True)
    assert report['repair_session']['status']=='verified',report['repair_session']
    assert len(report['repair_session']['attempts'])==2
    assert all(g['reversal']['outcome']=='verified' for g in report['failure_groups'])
    assert git(repo,'status','--porcelain')==''


def test_selected_broken_release_need_not_be_current_head(history,tmp_path):
    repo,commits=history
    git(repo,'checkout','--detach','v1.0.0')
    original=git(repo,'rev-parse','HEAD')
    with patch.object(verifier,'run_pytest',side_effect=fake_runner), patch.object(release,'run_pytest',side_effect=fake_runner):
        report=pipeline.run_investigation(repo,'.','local',tmp_path/'reports',investigation_type='release',test_runner='pytest',good_ref='v1.0.0',bad_ref='v2.0.0')
    assert report['baseline_revision']==commits[12]
    assert len(report['failure_groups'])==2
    assert git(repo,'rev-parse','HEAD')==original


def test_patch_download_is_report_scoped_and_rejects_invalid_ids(history,tmp_path):
    from fastapi.testclient import TestClient
    from causaltrace import api
    repo,_=history
    reports=tmp_path/'reports'
    with patch.object(verifier,'run_pytest',side_effect=fake_runner), patch.object(release,'run_pytest',side_effect=fake_runner), \
         patch.object(build_doctor,'run_pytest',side_effect=fake_runner), patch.object(build_doctor,'complete',side_effect=answer):
        report=pipeline.run_investigation(repo,'.','local',reports,investigation_type='release',test_runner='pytest',good_ref='v1.0.0',share_with_nebius=True)
    from causaltrace.repository_snapshot import independent_snapshot
    with independent_snapshot(repo) as check:
        git(check,'apply','--check',str(reports/(report['id']+'.patch')))
    with patch.object(api,'REPORTS_ROOT',reports):
        client=TestClient(api.app)
        response=client.get(report['repair_patch_url'])
        assert response.status_code==200
        assert response.text==report['repair_session']['patch']
        assert client.get('/api/investigation/not-an-id/repair.patch').status_code==400
        assert client.get('/api/investigation/'+('a'*32)+'/repair.patch').status_code==404


def test_collection_failure_is_bisected_without_fabricating_test_ids(history,tmp_path):
    repo,_=history
    git(repo,'checkout','--detach','v1.0.0')
    (repo/'service.py').write_text('def broken(:\n')
    git(repo,'add','.')
    git(repo,'commit','-qm','Break module syntax')
    bad=git(repo,'rev-parse','HEAD')
    def collect(path):
        if 'def broken' in (Path(path)/'service.py').read_text():
            return parse_result(2,'SyntaxError in service.py\n'+SUMMARY_MARKER+json.dumps({'test_ids':[], 'passed_ids':[], 'failed_ids':[], 'skipped_ids':[], 'collection_errors':['test_service.py']}),'')
        return fake_runner(path)
    with patch.object(verifier,'run_pytest',side_effect=collect),patch.object(release,'run_pytest',side_effect=collect):
        report=pipeline.run_investigation(repo,'.','local',tmp_path/'reports',investigation_type='release',test_runner='pytest',good_ref='v1.0.0')
    group=report['failure_groups'][0]
    assert group['test_id']=='collection::test_service.py'
    assert group['confirmed']
    assert group['suspected_commit']==bad
    assert group['reversal']['outcome']=='verified'
