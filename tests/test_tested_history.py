"""Persist all actually tested history, including local snapshots and long ranges."""
from pathlib import Path
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from causaltrace import pipeline, api
from causaltrace.demo_setup import git

@pytest.fixture
def project(tmp_path):
    repo=tmp_path/'repo'
    repo.mkdir()
    (repo/'state.txt').write_text('pass')
    git(repo,'init','--template=','--initial-branch=main')
    git(repo,'add','.')
    git(repo,'commit','-qm','Last working version')
    passing=git(repo,'rev-parse','HEAD')
    for i in range(20):
        (repo/'state.txt').write_text('fail')
        (repo/'notes.txt').write_text(str(i))
        git(repo,'add','.')
        git(repo,'commit','-qm',f'Broken history {i}')
    return repo,passing


def runner(repo,revision,directory):
    status=git(repo,'show',revision+':state.txt')
    return {'status':status,'passed':status=='pass','return_code':0 if status=='pass' else 1,
            'execution_error':False,'output':'Test output for '+revision,
            'test_ids':['test_contract'],'passed_ids':['test_contract'] if status=='pass' else [],
            'failed_ids':['test_contract'] if status=='fail' else [],'collection_errors':[],'skipped_ids':[]}


@pytest.mark.parametrize('mode', ['full','diagnose','release','regression','reproduce'])
def test_every_mode_stops_at_most_recent_transition(project,tmp_path,mode):
    from causaltrace import release_investigation as release
    repo,passing = project
    # Stop at the newest failure; do not retest the nineteen still older failures.
    (repo/'state.txt').write_text('pass')
    git(repo,'add','.')
    git(repo,'commit','-qm','Recovery')
    before = git(repo,'rev-parse','HEAD')
    with patch.object(pipeline,'test_commit',side_effect=runner) as diagnosis_runs, \
         patch.object(release,'test_commit',side_effect=runner) as release_runs:
        report = pipeline.run_investigation(repo,'.','local',tmp_path/'reports',mode,
            test_runner='pytest',history_limit=2,good_ref=passing)
    rows = report['tested_history']['commits']
    assert len(rows) == (3 if mode=='release' else 2)
    assert sum(row['test_status']=='fail' for row in rows) == 1
    assert [row['test_status'] for row in rows[:2]] == ['pass','fail']
    assert report['tested_history']['complete']
    assert diagnosis_runs.call_count + release_runs.call_count == (3 if mode=='release' else 2)
    assert git(repo,'rev-parse','HEAD') == before
    assert git(repo,'status','--porcelain') == ''


def test_reproduce_saves_every_commit_through_success_and_serves_local_history(project,tmp_path):
    repo,passing=project
    reports=tmp_path/'reports'
    with patch.object(pipeline,'test_commit',side_effect=runner) as runs, patch.object(pipeline,'investigate') as model,patch.object(pipeline,'verify_by_reversal') as reversal:
        report=pipeline.run_investigation(repo,'.','local',reports,'reproduce',test_runner='pytest',history_limit=64)
    history=report['tested_history']
    assert len(history['commits'])==21
    assert runs.call_count==21  # HEAD is reused, not tested twice.
    assert history['latest_pass']==passing
    assert history['latest_fail']==report['baseline_revision']
    assert history['complete']
    assert [c['test_status'] for c in history['commits']]==['fail']*20+['pass']
    assert all(c['message'] and c['date'] and c['result']['output'] for c in history['commits'])
    model.assert_not_called()
    reversal.assert_not_called()
    with patch.object(api,'REPORTS_ROOT',reports),patch.object(api,'ensure_demo',side_effect=AssertionError('Saved local history must not reopen source')):
        response=TestClient(api.app).get('/api/repositories/local/timeline?report_id='+report['id'])
        assert response.status_code==200
        assert response.json()['commits']==history['commits']
        assert response.json()['history_type']=='local'
    assert git(repo,'status','--porcelain')==''


def test_skipped_head_does_not_stop_before_actual_failing_and_passing_results(project):
    repo,passing = project
    head = git(repo,'rev-parse','HEAD')
    def outcomes(repo,revision,directory):
        result = runner(repo,revision,directory)
        if revision == head:
            result.update(status='pass_with_skips',passed=False,skipped_ids=['test_contract'])
        return result
    with patch.object(pipeline,'test_commit',side_effect=outcomes):
        history = pipeline.locate_boundary(repo,'.',limit=64)
    assert len(history['history'])==21
    assert history['latest_pass']==passing
    assert history['latest_fail']
    assert history['confirmed'] is False
    assert history['stop_reason']=='transition_with_gaps'


def test_passing_head_shows_previous_failure_and_no_false_regression(project,tmp_path):
    repo,_=project
    last_fail=git(repo,'rev-parse','HEAD')
    (repo/'state.txt').write_text('pass')
    git(repo,'add','.')
    git(repo,'commit','-qm','Recovered release')
    with patch.object(pipeline,'test_commit',side_effect=runner),patch.object(pipeline,'verify_by_reversal') as reverse:
        report=pipeline.run_investigation(repo,'.','local',tmp_path/'reports','regression',test_runner='pytest')
    assert report['status']=='no_failure'
    assert report['regression']['transition']=='recovery'
    assert not report['regression']['confirmed']
    assert report['tested_history']['latest_fail']==last_fail
    assert report['tested_history']['latest_pass']==report['baseline_revision']
    assert len(report['tested_history']['commits'])==2
    reverse.assert_not_called()


def test_history_limit_is_explicit_and_does_not_invent_a_pass(project,tmp_path):
    repo,_=project
    with patch.object(pipeline,'test_commit',side_effect=runner):
        report=pipeline.run_investigation(repo,'.','local',tmp_path/'reports','reproduce',test_runner='pytest',history_limit=8)
    assert len(report['tested_history']['commits'])==8
    assert report['tested_history']['latest_pass'] is None
    assert report['tested_history']['stop_reason']=='search_limit'
    assert not report['tested_history']['complete']
    assert not report['regression']['confirmed']


def test_unavailable_historical_evidence_stays_visible(project,tmp_path):
    repo,_=project
    head=git(repo,'rev-parse','HEAD')
    def unavailable(repo,commit,directory):
        if commit not in ('HEAD',head):
            return {'status':'error','execution_error':True,'passed':False,'return_code':125,'output':'Docker runner error'}
        return runner(repo,commit,directory)
    with patch.object(pipeline,'test_commit',side_effect=unavailable):
        report=pipeline.run_investigation(repo,'.','local',tmp_path/'reports','reproduce',test_runner='pytest')
    assert [c['test_status'] for c in report['tested_history']['commits']]==['fail']+['error']*20
    assert report['tested_history']['stop_reason']=='repository_root'
    assert report['tested_history']['commits'][-1]['result']['output']=='Docker runner error'

@pytest.mark.skipif(__import__('os').environ.get('CAUSALTRACE_HISTORY_DOCKER_TESTS')!='1',reason='Opt in to real Docker tested-history modes')
@pytest.mark.parametrize('mode',['reproduce','regression','diagnose','release'])
def test_real_docker_modes_show_all_tests_through_last_pass(mode,tmp_path):
    from causaltrace.demo_setup import ensure_demo
    with patch.object(pipeline,'investigate') as model:
        report=pipeline.run_investigation(ensure_demo('imports'),'.','local',tmp_path/'reports',mode,test_runner='pytest',good_ref='HEAD~2')
    assert [c['test_status'] for c in report['tested_history']['commits']]==['collection_error','collection_error','pass']
    assert all(c['result']['output'] for c in report['tested_history']['commits'])
    assert report['tested_history']['latest_pass']
    assert report['tested_history']['latest_fail']
    assert report['tested_history']['complete']
    if mode=='regression':
        assert report['experiments']['commit_reversal']['outcome']=='verified'
    else:
        assert report['experiments']=={}
    model.assert_not_called()
