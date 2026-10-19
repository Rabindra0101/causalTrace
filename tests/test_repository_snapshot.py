import contextlib
import hashlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from causaltrace import demo_setup, pipeline, verifier
from causaltrace.repository_snapshot import independent_snapshot
from test_submission_workflow import trusted_fixture_runner


def fingerprint(root):
    return {str(path.relative_to(root)): (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
            for path in root.rglob('*') if path.is_file()}


class SnapshotTests(unittest.TestCase):
    def fixture(self, root):
        demo_setup.git(root, 'init', '-q')
        (root / '.gitignore').write_text('.env\n')
        (root / 'add.py').write_text('def add(a,b):\n    return a + b\n')
        (root / 'test_add.py').write_text('from add import add\ndef test_add():\n    assert add(2,3) == 5\n')
        demo_setup.git(root, 'add', '.')
        demo_setup.git(root, 'commit', '-qm', 'Passing baseline')
        (root / 'add.py').write_text('def add(a,b):\n    return a - b\n')
        demo_setup.git(root, 'add', '.')
        demo_setup.git(root, 'commit', '-qm', 'Break implementation')
        (root / '.env').write_text('FIXTURE_ONLY=unchanged\n')
        (root / 'notes.txt').write_text('Untracked local work\n')
        (root / 'add.py').write_text('Uncommitted local edits that must remain unchanged\n')

    def test_complete_history_and_reversals_do_not_write_to_source_or_git_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'source'
            source.mkdir()
            self.fixture(source)
            before = fingerprint(source)
            with patch.object(verifier, 'run_pytest', side_effect=trusted_fixture_runner), \
                 contextlib.redirect_stdout(io.StringIO()):
                report = pipeline.run_investigation(source, '.', 'local', Path(folder) / 'reports', 'regression')
            self.assertEqual(report['status'], 'completed')
            self.assertTrue(report['regression']['confirmed'])
            self.assertEqual(report['experiments']['commit_reversal']['outcome'], 'verified')
            self.assertEqual(fingerprint(source), before)
            self.assertFalse((source / '.git/worktrees').exists())

    def test_snapshot_objects_are_independent_and_cleanup_on_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'source'
            source.mkdir()
            self.fixture(source)
            before = fingerprint(source)
            snapshot_path = None
            with self.assertRaisesRegex(RuntimeError, 'intentional'):
                with independent_snapshot(source) as snapshot:
                    snapshot_path = snapshot
                    self.assertFalse((snapshot / '.git/objects/info/alternates').exists())
                    (snapshot / 'add.py').write_text('only the copy changes')
                    raise RuntimeError('intentional')
            self.assertFalse(snapshot_path.exists())
            self.assertEqual(fingerprint(source), before)

    def test_bundled_repository_worktrees_also_stay_outside_source_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder)/'cached-demo'
            source.mkdir()
            self.fixture(source)
            before = fingerprint(source)
            original = verifier.run_command
            def guarded(args,cwd):
                if 'worktree' in args:
                    self.assertNotEqual(Path(cwd).resolve(),source.resolve())
                return original(args,cwd)
            with patch.object(verifier,'run_pytest',side_effect=trusted_fixture_runner), \
                 patch.object(verifier,'run_command',side_effect=guarded), contextlib.redirect_stdout(io.StringIO()):
                report=pipeline.run_investigation(source,'.','config',Path(folder)/'reports','regression')
            self.assertEqual(report['status'],'completed')
            self.assertEqual(fingerprint(source),before)
            self.assertFalse((source/'.git/worktrees').exists())

    def test_reports_inside_original_repository_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder)
            self.fixture(source)
            before = fingerprint(source)
            with self.assertRaisesRegex(ValueError, 'outside'):
                pipeline.run_investigation(source, '.', 'local', source / 'reports')
            self.assertEqual(fingerprint(source), before)
