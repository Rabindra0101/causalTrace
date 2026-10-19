"""Four independent upstream regressions; real Docker tests on broken and repaired source."""
import hashlib
import os
import shutil
import tempfile
from pathlib import Path
import pytest
from causaltrace import language_runner
from causaltrace.public_demos import ROOT, PUBLIC_IDS, JAVA_IMAGE, metadata, ensure_public_demo
from causaltrace.demo_setup import git
from causaltrace.test_runner import run_pytest

@pytest.mark.parametrize('name', PUBLIC_IDS)
def test_public_replay_provenance_and_three_commit_history(name):
    info = metadata(name)
    repo = ensure_public_demo(name)
    assert len(info['upstream_fixed']) == 40
    assert info['source'].startswith('https://raw.githubusercontent.com/')
    assert len(git(repo, 'rev-list', 'HEAD').splitlines()) == 3
    changed = git(repo, 'diff', '--name-only', 'HEAD~2', 'HEAD~1').splitlines()
    assert changed == [info['path']]
    assert git(repo, 'status', '--porcelain') == ''

@pytest.mark.skipif(os.environ.get('CAUSALTRACE_PUBLIC_DEMO_TESTS') != '1', reason='Opt in to real Docker regression tests')
@pytest.mark.parametrize('name', PUBLIC_IDS)
def test_public_bug_fails_and_repair_passes_with_unchanged_tests(name):
    info = metadata(name)
    with tempfile.TemporaryDirectory() as folder:
        repo = Path(folder) / 'repo'
        shutil.copytree(ROOT / 'public_demos' / name, repo)
        source = repo / info['path']
        fixed = source.read_text(encoding='utf-8')
        assert fixed.count(info['fixed']) == 1
        tests = {p.relative_to(repo): hashlib.sha256(p.read_bytes()).hexdigest() for p in repo.rglob('*') if p.is_file() and ('test' in p.name.lower())}
        assert tests
        runner = language_runner.RUNNER.set('maven' if name == 'commons_csv' else 'pytest')
        image = language_runner.IMAGE.set(JAVA_IMAGE if name == 'commons_csv' else None)
        try:
            source.write_text(fixed.replace(info['fixed'], info['broken']), encoding='utf-8')
            broken = run_pytest(repo)
            assert broken['status'] == 'fail', broken
            source.write_text(fixed, encoding='utf-8')
            repaired = run_pytest(repo)
            assert repaired['status'] == 'pass', repaired
            assert all(hashlib.sha256((repo / p).read_bytes()).hexdigest() == digest for p,digest in tests.items())
        finally:
            language_runner.IMAGE.reset(image)
            language_runner.RUNNER.reset(runner)

@pytest.mark.skipif(os.environ.get('CAUSALTRACE_PUBLIC_DEMO_TESTS') != '1', reason='Opt in to real Docker history experiments')
@pytest.mark.parametrize('name', PUBLIC_IDS)
def test_public_history_identifies_bug_and_reversal_control(name):
    from causaltrace.pipeline import run_investigation
    repo = ensure_public_demo(name)
    original = git(repo, 'rev-parse', 'HEAD')
    with tempfile.TemporaryDirectory() as reports:
        report = run_investigation(repo, '.', name, Path(reports), investigation_type='regression',
            test_runner='maven' if name == 'commons_csv' else 'pytest',
            runner_image=JAVA_IMAGE if name == 'commons_csv' else None)
    assert report['regression']['confirmed'], report
    assert report['experiments']['commit_reversal']['outcome'] == 'verified', report
    assert report['experiments']['alternative_reversal']['outcome'] == 'not_supported', report
    assert report['provenance']['upstream_fixed'] == metadata(name)['upstream_fixed']
    assert git(repo, 'rev-parse', 'HEAD') == original
    assert git(repo, 'status', '--porcelain') == ''

def test_public_java_api_selects_maven_and_prepared_image(monkeypatch):
    from fastapi.testclient import TestClient
    from causaltrace import api
    captured = {}
    def investigate(*args, **kwargs):
        captured.update(kwargs)
        return {'status': 'completed'}
    monkeypatch.setattr(api, 'docker_status', lambda *args: {'ready': True})
    monkeypatch.setattr(api, 'run_investigation', investigate)
    response = TestClient(api.app).post('/api/run-investigation', json={'repository_id': 'commons_csv', 'test_runner': 'pytest'})
    assert response.status_code == 200
    assert captured['test_runner'] == 'maven'
    assert captured['runner_image'] == JAVA_IMAGE
