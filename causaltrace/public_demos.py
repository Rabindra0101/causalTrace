"""Offline, attributed historical bug replays, isolated from upstream repositories."""
import json
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_IDS = ('humanize', 'pysnooper', 'cookiecutter', 'commons_csv')
JAVA_IMAGE = 'causaltrace-framework-fixtures:local'

def metadata(name):
    return json.loads((ROOT / 'public_demos' / name / 'replay.json').read_text(encoding='utf-8'))

def catalog():
    from causaltrace.upstream_projects import profile
    return [{'id': name, 'name': profile(name)['name'] + ' (full upstream repository)'} for name in PUBLIC_IDS]

def ensure_public_demo(name):
    from causaltrace.demo_setup import git, _setup_lock
    target = ROOT / '.causaltrace' / 'demos' / ('public-' + name)
    with _setup_lock:
        if target.exists():
            if not (target / '.git').is_dir():
                raise RuntimeError('Incomplete public demo folder; move it aside and retry.')
            return target
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=target.parent) as folder:
            repo = Path(folder) / 'repo'
            shutil.copytree(ROOT / 'public_demos' / name, repo, ignore=shutil.ignore_patterns('__pycache__', '.pytest_cache', 'target'))
            info = metadata(name)
            source = repo / info['path']
            fixed = source.read_text(encoding='utf-8')
            if fixed.count(info['fixed']) != 1:
                raise ValueError('Public replay source no longer matches its pinned mutation.')
            git(repo, 'init', '-q', '--template=', '--initial-branch=main')
            git(repo, 'add', '.')
            git(repo, 'commit', '-qm', 'Replay: passing extracted upstream source and regression test')
            source.write_text(fixed.replace(info['fixed'], info['broken']), encoding='utf-8')
            git(repo, 'add', '.')
            git(repo, 'commit', '-qm', 'Replay historical bug: ' + info['name'])
            (repo / 'notes.txt').write_text('Reconstructed history; see replay.json for upstream source and license.\n', encoding='utf-8')
            git(repo, 'add', '.')
            git(repo, 'commit', '-qm', 'Document replay (unrelated control)')
            repo.rename(target)
    return target
