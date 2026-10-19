"""Upstream clone integrity and original timestamps, without network dependencies."""
import os
import subprocess
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from causaltrace import upstream_projects as upstream


def git(repo, *args, date=None):
    env = dict(os.environ)
    if date:
        env.update(GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
    return subprocess.run(['git', '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', '-c', 'commit.gpgsign=false', *args], cwd=repo, env=env, capture_output=True, check=True, text=True).stdout.strip()

@pytest.fixture
def original_history(tmp_path, monkeypatch):
    original = tmp_path / 'original'
    original.mkdir()
    git(original, 'init', '--template=', '--initial-branch=main')
    (original / 'test_original.py').write_text('def test_original():\n    assert True\n')
    git(original, 'add', '.')
    git(original, 'commit', '-m', 'Original first commit', date='2012-03-26T12:15:00+00:00')
    (original / 'notes.txt').write_text('upstream notes')
    git(original, 'add', '.')
    git(original, 'commit', '-m', 'Original second commit', date='2012-03-27T13:45:00+00:00')
    spec = {'name': 'CSV fixture', 'url': str(original), 'revision': git(original, 'rev-parse', 'HEAD'), 'runner': 'pytest', 'image': 'fixture:local'}
    monkeypatch.setattr(upstream, 'ROOT', tmp_path / 'app')
    monkeypatch.setattr(upstream, 'profile', lambda name: spec)
    return original, spec


def test_full_clone_preserves_original_objects_tests_and_dates(original_history):
    original, spec = original_history
    clone = upstream.ensure_upstream('commons_csv')
    assert git(clone, 'log', '--format=%H %aI %s') == git(original, 'log', '--format=%H %aI %s')
    assert git(clone, 'rev-parse', '--is-shallow-repository') == 'false'
    assert git(clone, 'ls-tree', '-r', 'HEAD') == git(original, 'ls-tree', '-r', 'HEAD')
    assert git(clone, 'rev-parse', 'HEAD') == spec['revision']
    assert upstream.ensure_upstream('commons_csv') == clone


def test_dirty_upstream_work_is_preserved_and_rejected(original_history):
    clone = upstream.ensure_upstream('commons_csv')
    path = clone / 'test_original.py'
    path.write_text('local work\n')
    with pytest.raises(ValueError, match='local changes'):
        upstream.ensure_upstream('commons_csv')
    assert path.read_text() == 'local work\n'


def test_timeline_uses_original_dates_and_report_revision(original_history, monkeypatch):
    from causaltrace import api
    clone = upstream.ensure_upstream('commons_csv')
    monkeypatch.setattr(api, 'ensure_demo', lambda name: clone)
    response = TestClient(api.app).get('/api/repositories/commons_csv/timeline')
    assert response.status_code == 200
    commits = response.json()['commits']
    assert [c['date'] for c in commits] == ['2012-03-27T13:45:00Z', '2012-03-26T12:15:00Z']
    first = git(clone, 'rev-parse', 'HEAD~1')
    monkeypatch.setattr(api, 'report_file', lambda report_id: {'repository_id': 'commons_csv', 'baseline_revision': first, 'provenance': {'history_type': 'upstream'}})
    response = TestClient(api.app).get('/api/repositories/commons_csv/timeline?report_id=' + 'a'*32)
    assert [c['hash'] for c in response.json()['commits']] == [first]


def test_old_replay_report_keeps_replay_timeline(original_history, monkeypatch):
    from causaltrace import api
    clone = upstream.ensure_upstream('commons_csv')
    monkeypatch.setattr(api, 'ensure_demo', lambda name: pytest.fail('Old reports must not switch to upstream history'))
    monkeypatch.setattr(api, 'ensure_public_demo', lambda name: clone)
    monkeypatch.setattr(api, 'report_file', lambda report_id: {'repository_id': 'commons_csv', 'baseline_revision': git(clone, 'rev-parse', 'HEAD'), 'provenance': {'note': 'historical replay'}})
    response = TestClient(api.app).get('/api/repositories/commons_csv/timeline?report_id=' + 'a'*32)
    assert response.status_code == 200

@pytest.mark.skipif(os.environ.get('CAUSALTRACE_UPSTREAM_TESTS') != '1', reason='Opt in to full upstream Docker suites')
@pytest.mark.parametrize('name', upstream.PUBLIC_IDS)
def test_real_upstream_baseline_runs_original_tests(name, tmp_path):
    from causaltrace.pipeline import run_investigation
    spec = upstream.profile(name)
    repo = upstream.ensure_upstream(name)
    report = run_investigation(repo, '.', name, tmp_path, investigation_type='reproduce', test_runner=spec['runner'], runner_image=spec['image'])
    assert report['provenance']['history_type'] == 'upstream'
    assert report['baseline_revision'] == spec['revision']
    assert report['baseline']['test_ids'], report['baseline']['output'][-12000:]
    assert not report['baseline']['collection_errors'], report['baseline']['output'][-12000:]
    assert upstream.command(repo, 'status', '--porcelain', '--untracked-files=all') == ''

def test_mixed_skips_are_reported_without_verifying_a_repair():
    import json
    from causaltrace.test_runner import parse_result, SUMMARY_MARKER
    summary = {'test_ids': ['executed', 'optional'], 'passed_ids': ['executed'], 'skipped_ids': ['optional'], 'failed_ids': [], 'collection_errors': []}
    result = parse_result(0, SUMMARY_MARKER + json.dumps(summary), '')
    assert result['status'] == 'pass_with_skips'
    assert not result['passed']
    assert not result['execution_error']


def test_container_worktree_uses_lf_without_rewriting_original(original_history):
    from unittest.mock import patch
    from causaltrace.verifier import test_commit
    original, _ = original_history
    git(original, 'config', 'core.autocrlf', 'true')
    with patch('causaltrace.verifier.run_pytest', return_value={'passed': True, 'return_code': 0, 'output': ''}) as runner:
        test_commit(original, 'HEAD', '.')
        # Worktree is removed by test_commit; the source repository stays clean.
        assert runner.call_count == 1
    assert git(original, 'status', '--porcelain') == ''
