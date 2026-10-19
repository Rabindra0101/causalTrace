"""Execute project tests only in a restricted, disposable Docker container."""
import json
import shutil
import subprocess
import uuid
from pathlib import Path

DOCKER_IMAGE = "causaltrace-test-runner:local"
TEST_TIMEOUT = 60
SUMMARY_MARKER = "CAUSALTRACE_TEST_SUMMARY="

# This plugin reports collection/outcomes so Docker errors cannot masquerade as tests.
PYTEST_SCRIPT = """
import json
import pytest

class Evidence:
    def __init__(self):
        self.ids = []
        self.passed = []
        self.failed = []
        self.skipped = []
        self.collection_errors = []

    def pytest_collection_finish(self, session):
        self.ids = [item.nodeid for item in session.items]

    def pytest_collectreport(self, report):
        if report.failed:
            self.collection_errors.append(report.nodeid)

    def pytest_runtest_logreport(self, report):
        if report.failed:
            self.failed.append(report.nodeid)
        elif report.when == 'call' and report.passed:
            self.passed.append(report.nodeid)
        elif report.skipped:
            self.skipped.append(report.nodeid)

    def pytest_sessionfinish(self, session, exitstatus):
        print('\\nCAUSALTRACE_TEST_SUMMARY=' + json.dumps({
            'test_ids': self.ids, 'passed_ids': self.passed,
            'failed_ids': self.failed, 'skipped_ids': self.skipped,
            'collection_errors': self.collection_errors,
        }))

raise SystemExit(pytest.main(
    ['-v', '-p', 'no:cacheprovider', '--import-mode=importlib'],
    plugins=[Evidence()]
))
"""


def execution_error(message, return_code=-1):
    return {
        "passed": False, "test_failed": False, "execution_error": True,
        "status": "error", "return_code": return_code,
        "stdout": "", "stderr": message, "output": message,
        "test_ids": [], "passed_ids": [], "failed_ids": [],
        "skipped_ids": [], "collection_errors": [],
    }


def parse_result(return_code, stdout, stderr):
    output = stdout + "\n" + stderr
    summary = None
    for line in stdout.splitlines():
        if line.startswith(SUMMARY_MARKER):
            try:
                summary = json.loads(line[len(SUMMARY_MARKER):])
            except (ValueError, TypeError):
                pass
    if not isinstance(summary, dict):
        return execution_error(output.strip() or "No pytest evidence was returned.", return_code)
    required = ("test_ids", "passed_ids", "failed_ids", "skipped_ids", "collection_errors")
    if any(not isinstance(summary.get(key), list) for key in required):
        return execution_error("Malformed test-runner evidence.", return_code)
    passed = (
        return_code == 0 and bool(summary["test_ids"])
        and set(summary["passed_ids"]) == set(summary["test_ids"])
        and not summary["failed_ids"] and not summary["collection_errors"]
        and not summary["skipped_ids"]
    )
    failed = return_code == 1 and bool(summary["failed_ids"])
    collection_error = return_code == 2 and bool(summary["collection_errors"])
    status = "pass" if passed else "fail" if failed else "collection_error" if collection_error else "error"
    visible = "\n".join(line for line in output.splitlines() if not line.startswith(SUMMARY_MARKER))
    return {
        "passed": passed, "test_failed": failed or collection_error,
        "execution_error": status == "error", "status": status,
        "return_code": return_code, "stdout": stdout,
        "stderr": stderr, "output": visible, **summary,
    }


def is_failure(result):
    return result.get("status") in {"fail", "collection_error"}


def same_tests(before, after):
    """Collection failures have no complete ID set; require actual passing tests afterward."""
    return (
        bool(after.get("test_ids"))
        and (before.get("status") == "collection_error"
             or set(before.get("test_ids", [])) == set(after.get("test_ids", [])))
    )


def cleanup_container(name):
    try:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=10, check=False)
    except (subprocess.SubprocessError, OSError):
        pass


def docker_status():
    if not shutil.which("docker"):
        return {"ready": False, "reason": "Docker is not installed or is not on PATH."}
    try:
        daemon = subprocess.run(["docker", "info", "--format", "{{.ServerVersion}}"],
                                capture_output=True, text=True, timeout=5)
        if daemon.returncode:
            return {"ready": False, "reason": "Start Docker Desktop using Linux containers."}
        image = subprocess.run(["docker", "image", "inspect", DOCKER_IMAGE],
                               capture_output=True, timeout=5)
        return {
            "ready": image.returncode == 0,
            "reason": "Runner ready." if image.returncode == 0 else
                "Build the runner: docker build -f Dockerfile.test-runner -t causaltrace-test-runner:local .",
        }
    except (OSError, subprocess.SubprocessError):
        return {"ready": False, "reason": "Docker did not respond. Check Docker Desktop."}


def run_pytest(repo_path: Path) -> dict:
    repo_path = Path(repo_path).resolve()
    if not repo_path.is_dir():
        return execution_error("The test directory does not exist at this revision.")
    if not shutil.which("docker"):
        return execution_error("Docker is unavailable. Install/start Docker Desktop and build the runner.")
    name = f"causaltrace-test-{uuid.uuid4().hex[:12]}"
    command = [
        "docker", "run", "--rm", "--name", name, "--network", "none",
        "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--memory", "256m", "--cpus", "1", "--pids-limit", "64",
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=32m",
        "-e", "PYTHONDONTWRITEBYTECODE=1",
        "-e", "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1",
        "--mount", f"type=bind,source={repo_path},target=/workspace,readonly",
        "-w", "/workspace", DOCKER_IMAGE, "python", "-c", PYTEST_SCRIPT,
    ]
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=TEST_TIMEOUT, check=False,
        )
        return parse_result(result.returncode, result.stdout, result.stderr)
    except subprocess.TimeoutExpired:
        return execution_error(f"Test execution exceeded {TEST_TIMEOUT} seconds.")
    except OSError:
        return execution_error("Unable to launch Docker. Check Docker Desktop.")
    finally:
        cleanup_container(name)
