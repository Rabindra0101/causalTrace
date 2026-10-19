"""Pinned full upstream checkouts. Original Git objects and dates are preserved."""
import json
import subprocess
import tempfile
from pathlib import Path
from causaltrace.public_demos import ROOT, PUBLIC_IDS, metadata

URLS = {
    'humanize': 'https://github.com/python-humanize/humanize.git',
    'pysnooper': 'https://github.com/cool-RR/PySnooper.git',
    'cookiecutter': 'https://github.com/cookiecutter/cookiecutter.git',
    'commons_csv': 'https://github.com/apache/commons-csv.git',
}

def profile(name):
    info = metadata(name)
    return {'name': info['name'].split(' — ')[0], 'url': URLS[name],
            'revision': info['upstream_buggy'],
            'runner': 'maven' if name == 'commons_csv' else 'pytest',
            'image': 'causaltrace-upstream-' + name.replace('_', '-') + ':local'}

def command(repo, *args):
    return subprocess.run(['git', *args], cwd=repo,
        check=True, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=180).stdout.strip()

def ensure_upstream(name):
    from causaltrace.demo_setup import _setup_lock
    if name not in PUBLIC_IDS:
        raise ValueError('Unknown upstream project.')
    spec = profile(name)
    parent = ROOT / '.causaltrace' / 'upstream'
    target = parent / ('commons-csv' if name == 'commons_csv' else name)
    with _setup_lock:
        parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            with tempfile.TemporaryDirectory(dir=parent, prefix='clone-') as folder:
                clone = Path(folder) / 'repo'
                command(parent, 'clone', '-c', 'core.autocrlf=false', '--no-checkout', '--', spec['url'], str(clone))
                command(clone, 'switch', '--detach', spec['revision'])
                clone.rename(target)
        if command(target, 'remote', 'get-url', 'origin') != spec['url']:
            raise ValueError('Upstream checkout origin does not match the configured project.')
        if command(target, 'rev-parse', 'HEAD') != spec['revision']:
            raise ValueError('Upstream checkout revision changed. Preserve local work and restore the configured revision before investigating.')
        if command(target, 'status', '--porcelain', '--untracked-files=all'):
            raise ValueError('Upstream checkout contains local changes. Preserve them before investigating.')
        if command(target, 'rev-parse', '--is-shallow-repository') != 'false':
            raise ValueError('Upstream investigation requires the full Git history.')
    return target

def provenance(name):
    spec = profile(name)
    return {'name': spec['name'], 'source': spec['url'].removesuffix('.git'),
            'upstream_revision': spec['revision'], 'history_type': 'upstream',
            'note': 'Full upstream repository at a pinned historical revision, with original committed tests, Git IDs and author dates. No replay commits or tests are injected.'}

def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project', choices=[*PUBLIC_IDS, 'all'], default='all', nargs='?')
    args = parser.parse_args()
    for name in PUBLIC_IDS if args.project == 'all' else [args.project]:
        repo = ensure_upstream(name)
        print(json.dumps({'project': name, 'path': str(repo), **profile(name)}))

if __name__ == '__main__':
    main()
