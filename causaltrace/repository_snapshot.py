"""Investigate committed history without registering worktrees in the source repo."""
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def independent_snapshot(source):
    source = Path(source).resolve()
    def git(*args, cwd=source):
        return subprocess.run(["git", "-c", "core.fsmonitor=false", *args], cwd=cwd,
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", check=True, timeout=120).stdout.strip()
    if Path(git("rev-parse", "--show-toplevel")).resolve() != source:
        raise ValueError("The configured path must be a Git repository root.")
    revision = git("rev-parse", "HEAD")
    with tempfile.TemporaryDirectory(prefix="causaltrace-snapshot-") as folder:
        root = Path(folder)
        bundle = root / "history.bundle"
        # The bundle is written outside source. No index/status/worktree operation
        # runs against source, and the resulting repository shares no object store.
        git("bundle", "create", str(bundle), revision, "HEAD")
        snapshot = root / "repo"
        git("clone", "--no-local", "--no-hardlinks", "--no-checkout", "--template=",
            str(bundle), str(snapshot), cwd=root)
        hooks = root / "empty-hooks"
        hooks.mkdir()
        git("config", "core.hooksPath", str(hooks), cwd=snapshot)
        git("config", "core.autocrlf", "false", cwd=snapshot)
        git("checkout", "--detach", revision, cwd=snapshot)
        yield snapshot
