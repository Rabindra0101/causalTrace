"""Control real investigation threads; runners are mocked, never Nebius."""
import threading
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from causaltrace import api, pipeline, verifier
from causaltrace.demo_setup import git
from causaltrace.investigation_control import Control, ACTIVE_CONTROL


@pytest.mark.parametrize('mode', ['diagnose','release'])
def test_pause_resume_and_stop_keep_completed_results_and_original_repo(mode,tmp_path):
    repo = tmp_path/'repo'
    repo.mkdir()
    git(repo,'init','--template=','--initial-branch=main')
    for number in range(3):
        (repo/'module.py').write_text('number = '+str(number))
        git(repo,'add','.')
        git(repo,'commit','-qm','Revision '+str(number))
    original = git(repo,'rev-parse','HEAD')
    control = Control()
    first, second, release_first, release_second = [threading.Event() for _ in range(4)]
    report, errors = [], []
    calls = []
    def runner(path):
        calls.append(str(path))
        event, gate = (first,release_first) if len(calls)==1 else (second,release_second)
        event.set()
        assert gate.wait(10)
        return {'status':'fail','passed':False,'return_code':1,'output':'FAILED test_contract',
                'test_ids':['test_contract'],'failed_ids':['test_contract'],'passed_ids':[],
                'skipped_ids':[],'collection_errors':[],'execution_error':False}
    def work():
        token = ACTIVE_CONTROL.set(control)
        try:
            report.append(pipeline.run_investigation(repo,'.','local',tmp_path/'reports',mode,
                test_runner='pytest',good_ref='HEAD~2'))
        except BaseException as error:
            errors.append(error)
        finally:
            ACTIVE_CONTROL.reset(token)
    with patch.object(verifier,'run_pytest',side_effect=runner):
        thread = threading.Thread(target=work)
        thread.start()
        try:
            assert first.wait(10)
            assert control.command('pause') == 'paused'
            release_first.set()
            assert not second.wait(.3), 'Pause must prevent the next test from starting'
            assert control.command('resume') == 'running'
            assert second.wait(10)
            control.command('pause')
            control.command('stop')  # Stop must also wake a paused investigation.
            assert control.command('resume') == 'stopping'
        finally:
            release_first.set()
            release_second.set()
            control.command('stop')
            thread.join(15)
    assert not thread.is_alive()
    assert not errors
    assert len(calls)==2
    assert report[0]['status']=='stopped'
    assert len(report[0]['tested_history']['commits'])==2
    assert report[0]['tested_history']['complete'] is False
    assert report[0]['regression']['confirmed'] is False
    assert git(repo,'rev-parse','HEAD')==original
    assert git(repo,'status','--porcelain')==''
    assert len(git(repo,'worktree','list','--porcelain').split('worktree '))==2


def test_control_api_is_scoped_to_active_id_and_validates_actions():
    client = TestClient(api.app)
    control = Control()
    run_id = 'b'*32
    with patch.dict(api.controls,{run_id:control},clear=True):
        url = '/api/investigation-control/'+run_id
        assert client.post(url,json={'action':'pause'}).json()['state']=='paused'
        assert client.post(url,json={'action':'resume'}).json()['state']=='running'
        assert client.post(url,json={'action':'stop'}).json()['state']=='stopping'
        assert client.post(url,json={'action':'resume'}).json()['state']=='stopping'
        assert client.post(url,json={'action':'invalid'}).status_code==422
        assert client.post('/api/investigation-control/'+('c'*32),json={'action':'stop'}).status_code==404
