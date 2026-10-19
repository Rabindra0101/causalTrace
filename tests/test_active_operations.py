"""Freeze real operations, resume without restarting, and cancel blocked requests."""
import asyncio
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch
import uuid
import pytest
from causaltrace.controlled_process import run
from causaltrace.investigation_control import Control, ACTIVE_CONTROL, InvestigationStopped
from causaltrace import nemotron_client


def until(predicate, timeout=8):
    deadline = time.monotonic()+timeout
    while time.monotonic()<deadline:
        if predicate():
            return
        time.sleep(.02)
    raise AssertionError('Operation did not reach expected state')


def worker(control, function):
    values, errors = [], []
    def target():
        token = ACTIVE_CONTROL.set(control)
        try:
            values.append(function())
        except BaseException as error:
            errors.append(error)
        finally:
            ACTIVE_CONTROL.reset(token)
    thread = threading.Thread(target=target)
    thread.start()
    return thread, values, errors


def test_process_freezes_resumes_same_pid_and_stop_kills_while_paused(tmp_path):
    path = tmp_path/'ticks.txt'
    script = "import os,time,pathlib,sys\np=pathlib.Path(sys.argv[1])\nfor i in range(10000):\n p.write_text(str(os.getpid())+':'+str(i))\n time.sleep(.03)"
    control = Control()
    thread, values, errors = worker(control,lambda:run([sys.executable,'-u','-c',script,str(path)],capture_output=True,text=True,timeout=2))
    try:
        until(lambda:path.exists() and ':' in path.read_text())
        control.command('pause')
        until(lambda:control.pause_effect=='paused')
        before = path.read_text()
        time.sleep(2.2)  # Longer than the active-time timeout.
        assert thread.is_alive()
        assert path.read_text()==before
        control.command('resume')
        until(lambda:path.read_text()!=before)
        assert path.read_text().split(':')[0]==before.split(':')[0]
        control.command('pause')
        until(lambda:control.pause_effect=='paused')
        control.command('stop')
        thread.join(3)
        assert not thread.is_alive()
        after = path.read_text()
        time.sleep(.15)
        assert path.read_text()==after
        assert not values
        assert len(errors)==1 and isinstance(errors[0],InvestigationStopped)
    finally:
        control.command('stop')
        thread.join(5)


@pytest.mark.parametrize('action',['stop','resume'])
def test_nebius_stop_cancels_connection_or_pause_holds_one_response(action):
    started, release, cancelled, closed = [threading.Event() for _ in range(4)]
    calls=[]
    async def create(**kwargs):
        calls.append(kwargs)
        started.set()
        try:
            while not release.is_set():
                await asyncio.sleep(.01)
            return SimpleNamespace(usage=None, choices=[SimpleNamespace(finish_reason='stop',message=SimpleNamespace(content='mocked response'))])
        finally:
            cancelled.set()
    class Client:
        async def __aenter__(self):
            return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        async def __aexit__(self,*args):
            closed.set()
    control=Control()
    with patch.object(nemotron_client,'configuration',return_value=('test-placeholder','mock-model')), \
         patch.object(nemotron_client,'AsyncOpenAI',return_value=Client()):
        thread, values, errors = worker(control,lambda:nemotron_client.complete([{'role':'user','content':'Mock only'}]))
        try:
            assert started.wait(5)
            control.command('pause')
            until(lambda:control.pause_effect=='provider_not_pausable')
            if action=='resume':
                release.set()
                assert cancelled.wait(3)
                time.sleep(.1)
                assert thread.is_alive() and not values
                control.command('resume')
            else:
                control.command('stop')
            thread.join(3)
            assert not thread.is_alive()
            assert closed.is_set() and cancelled.is_set()
            assert len(calls)==1
            if action=='resume':
                assert values==[('mocked response','mock-model')] and not errors
            else:
                assert not values and len(errors)==1 and isinstance(errors[0],InvestigationStopped)
        finally:
            control.command('stop')
            release.set()
            thread.join(5)


@pytest.mark.skipif(os.environ.get('CAUSALTRACE_ACTIVE_CONTROL_DOCKER_TESTS')!='1',reason='Opt in to active Docker pause/resume/stop')
def test_real_docker_freezes_resumes_same_container_and_stop_removes_it(tmp_path):
    name='causaltrace-control-'+uuid.uuid4().hex[:12]
    script="import pathlib,time,os\nfor i in range(10000):\n pathlib.Path('/ticks/ticks').write_text(str(os.getpid())+':'+str(i))\n time.sleep(.03)"
    control=Control()
    command=['docker','run','--rm','--name',name,'--network','none','--read-only','--user','0:0','--cap-drop','ALL','--mount',f'type=bind,source={tmp_path},target=/ticks','causaltrace-test-runner:local','python','-u','-c',script]
    thread, values, errors = worker(control,lambda:run(command,capture_output=True,text=True,timeout=20))
    def docker(*args):
        return subprocess.run(['docker',*args],capture_output=True,text=True,timeout=5)
    try:
        copy=tmp_path/'ticks'
        until(lambda:copy.exists() and ':' in copy.read_text())
        identity=docker('inspect','--format','{{.Id}}',name).stdout.strip()
        control.command('pause')
        until(lambda:control.pause_effect=='paused')
        assert docker('inspect','--format','{{.State.Paused}}',name).stdout.strip()=='true'
        before=copy.read_text()
        time.sleep(.3)
        assert copy.read_text()==before
        control.command('resume')
        until(lambda:copy.read_text()!=before)
        assert docker('inspect','--format','{{.Id}}',name).stdout.strip()==identity
        control.command('pause')
        until(lambda:control.pause_effect=='paused')
        control.command('stop')
        thread.join(8)
        assert not thread.is_alive()
        assert docker('inspect',name).returncode!=0
        assert not values and len(errors)==1 and isinstance(errors[0],InvestigationStopped)
    finally:
        control.command('stop')
        thread.join(8)
        docker('rm','-f',name)


@pytest.mark.skipif(os.environ.get('CAUSALTRACE_ACTIVE_CONTROL_DOCKER_TESTS')!='1',reason='Opt in to active Docker API cancellation')
def test_real_api_stop_interrupts_running_test_and_saves_no_false_result(tmp_path):
    from fastapi.testclient import TestClient
    from causaltrace import api
    from causaltrace.demo_setup import git
    repo=tmp_path/'repo'
    repo.mkdir()
    (repo/'test_slow.py').write_text('import time\ndef test_slow():\n time.sleep(60)\n assert False\n')
    git(repo,'init','--template=','--initial-branch=main')
    git(repo,'add','.')
    git(repo,'commit','-qm','Slow test for cancellation')
    head=git(repo,'rev-parse','HEAD')
    run_id=uuid.uuid4().hex
    results, errors=[], []
    def investigate():
        try:
            results.append(api.run(api.InvestigationRequest(control_id=run_id,repository_id='local',
                repository_path=str(repo),investigation_type='reproduce',test_runner='pytest')))
        except BaseException as error:
            errors.append(error)
    client=TestClient(api.app)
    with patch.object(api,'REPORTS_ROOT',tmp_path/'reports'):
        thread=threading.Thread(target=investigate)
        thread.start()
        try:
            until(lambda:client.get('/api/investigation-status').json().get('activity')=='docker',timeout=15)
            assert client.post('/api/investigation-control/'+run_id,json={'action':'pause'}).status_code==200
            until(lambda:client.get('/api/investigation-status').json().get('pause_effect')=='paused')
            assert thread.is_alive()
            client.post('/api/investigation-control/'+run_id,json={'action':'resume'})
            time.sleep(.15)
            client.post('/api/investigation-control/'+run_id,json={'action':'stop'})
            thread.join(10)
            assert not thread.is_alive(), 'Stop must not wait for the 60-second test'
        finally:
            client.post('/api/investigation-control/'+run_id,json={'action':'stop'})
            thread.join(10)
    assert not errors
    report=results[0]['report']
    assert report['status']=='stopped'
    assert report['baseline']['status']=='not_run'
    assert (tmp_path/'reports'/(report['id']+'.json')).exists()
    assert not api.investigation_lock.locked()
    assert git(repo,'rev-parse','HEAD')==head
    assert git(repo,'status','--porcelain')==''
    assert len(git(repo,'worktree','list','--porcelain').split('worktree '))==2
