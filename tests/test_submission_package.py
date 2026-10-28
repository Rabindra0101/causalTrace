import hashlib
import json
import zipfile
import pytest
from causaltrace.demo_setup import git
from scripts.package_submission import package


@pytest.fixture
def build_root(tmp_path):
    root = tmp_path / 'project'
    root.mkdir()
    git(root, 'init', '--template=', '--initial-branch=main')
    (root / 'README.md').write_text('Committed setup instructions')
    git(root, 'add', 'README.md')
    git(root, 'commit', '-qm', 'Reviewed source')
    dist = root / 'frontend' / 'dist'
    dist.mkdir(parents=True)
    (dist / 'index.html').write_text('<main>Built dashboard</main>')
    (root / 'local-only.txt').write_text('Must stay local')
    return root


def test_test_build_contains_reviewed_source_assets_and_verifiable_manifest(build_root, tmp_path):
    destination = package(build_root, tmp_path / 'builds')
    with zipfile.ZipFile(destination) as archive:
        names = archive.namelist()
        assert 'causalTrace/frontend/dist/index.html' in names
        assert 'causalTrace/README.md' in names
        assert 'causalTrace/local-only.txt' not in names
        manifest = json.loads(archive.read('causalTrace/BUILD.json'))
        assert manifest['commit'] == git(build_root, 'rev-parse', 'HEAD')
        for name, digest in manifest['files'].items():
            assert hashlib.sha256(archive.read('causalTrace/' + name)).hexdigest() == digest
    assert destination.with_suffix('.zip.sha256').read_text().split()[0] == hashlib.sha256(destination.read_bytes()).hexdigest()
    with pytest.raises(FileExistsError):
        package(build_root, tmp_path / 'builds')


def test_dirty_source_cannot_be_mislabeled_as_a_reviewed_build(build_root, tmp_path):
    (build_root / 'README.md').write_text('Uncommitted instructions')
    with pytest.raises(ValueError, match='Commit tracked edits'):
        package(build_root, tmp_path / 'builds')


def test_tracked_credential_path_is_rejected_before_archiving(build_root, tmp_path):
    (build_root / 'credentials').mkdir()
    (build_root / 'credentials' / 'placeholder.txt').write_text('Non-secret test placeholder')
    git(build_root, 'add', 'credentials')
    git(build_root, 'commit', '-qm', 'Credential path fixture')
    with pytest.raises(ValueError, match='Credential paths'):
        package(build_root, tmp_path / 'builds')
