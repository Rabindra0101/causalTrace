"""Execute project tests only in a restricted, disposable Docker container."""
import json
import shutil
import subprocess
import uuid
from pathlib import Path
from causaltrace.language_runner import DRIVER, PREPARE_DRIVER, PREPARATION, RUNNER, IMAGE, MULTILANG_IMAGE

DOCKER_IMAGE = "causaltrace-test-runner:local"
TEST_TIMEOUT = 60
SUMMARY_MARKER = "CAUSALTRACE_TEST_SUMMARY="
PREPARATION_TIMEOUT = 300


def setup_issues(result):
    """Explain infrastructure output without treating it as a tested regression."""
    if not result.get("execution_error"):
        return []
    output = result.get("output", "").lower()
    issues = []
    if any(value in output for value in ("goproxy=off", "cannot find module", "cannot find package", "could not resolve dependencies", "offline mode", "no such file or directory: './node_modules")):
        issues.append({"code": "missing_dependencies", "message": "Required project dependencies are missing from the runner.",
                       "action": "Enable dependency downloads during preparation, or select a dependency image prepared for this project."})
    if "no matching files found" in output and ("frontend/dist" in output or "pattern " in output):
        issues.append({"code": "missing_build_assets", "message": "Required embedded build assets are missing.",
                       "action": "Enable frontend build preparation and set the frontend directory containing package.json."})
    if any(value in output for value in ("pkg-config", "webkit2gtk", "gtk+-3.0", "c compiler", "gcc: executable file not found")):
        issues.append({"code": "native_dependencies", "message": "The project needs native compiler or desktop libraries.",
                       "action": "Select a prepared runner image with the required Linux native libraries. Windows-only tests need a compatible test target."})
    if result.get("return_code") == 5 or (not result.get("test_ids") and any(value in output for value in ("[no test files]", "no tests found", "no tests ran", 'tests="0"'))):
        issues.append({"code": "no_tests", "message": "No runnable tests were collected.",
                       "action": "Choose a directory with committed tests for the selected runner. Preparation does not create tests."})
    if result.get("preparation", {}).get("status") == "failed":
        issues.insert(0, {"code": "preparation_failed", "message": "Project preparation failed before tests started.",
                          "action": "Expand the preparation output to identify the failed dependency or build step."})
    return issues

# This plugin reports collection/outcomes so Docker errors cannot masquerade as tests.
PYTEST_SCRIPT = """
import json
import pytest
import os, pathlib, shutil, subprocess, sys

upstream = os.environ.get('CAUSALTRACE_UPSTREAM_PROJECT')
extra_args = []
if upstream:
    root = pathlib.Path('/tmp/upstream-project')
    shutil.copytree('/workspace', root, ignore=shutil.ignore_patterns('.git', '.env', '.env.*', '__pycache__', '.pytest_cache'))
    os.chdir(root)
    sys.path[:0] = [str(root), str(root / 'src')]
    os.environ['PYTHONPATH'] = str(root) + ':' + str(root / 'src')
    if upstream == 'humanize':
        os.environ['SETUPTOOLS_SCM_PRETEND_VERSION'] = '0.0.0'
        subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-index', '--no-deps', '--no-build-isolation', '--target', '/tmp/upstream-install', '.'], check=True)
        subprocess.run(['bash', 'scripts/generate-translation-binaries.sh'], check=True)
        extra_args += ['-p', 'pytest_benchmark.plugin', '--benchmark-disable']
    elif upstream == 'cookiecutter':
        extra_args += ['-p', 'pytest_cov.plugin', '-p', 'pytest_mock', '-o', 'addopts=']

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
    ['-v', '-p', 'no:cacheprovider', '--import-mode=prepend' if upstream else '--import-mode=importlib', *extra_args],
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
        return execution_error(output.strip() or "No structured test evidence was returned.", return_code)
    required = ("test_ids", "passed_ids", "failed_ids", "skipped_ids", "collection_errors")
    if any(not isinstance(summary.get(key), list) for key in required):
        return execution_error("Malformed test-runner evidence.", return_code)
    passed = (
        return_code == 0 and bool(summary["test_ids"])
        and set(summary["passed_ids"]) == set(summary["test_ids"])
        and not summary["failed_ids"] and not summary["collection_errors"]
        and not summary["skipped_ids"]
    )
    failed = return_code in (1, 2) and bool(summary["failed_ids"])
    collection_error = return_code in (1, 2) and bool(summary["collection_errors"]) and not failed
    pass_with_skips = (
        return_code == 0 and bool(summary['passed_ids']) and bool(summary['skipped_ids'])
        and not summary['failed_ids'] and not summary['collection_errors']
        and set(summary['passed_ids']) | set(summary['skipped_ids']) == set(summary['test_ids'])
    )
    status = "pass_with_skips" if pass_with_skips else "pass" if passed else "fail" if failed else "collection_error" if collection_error else "error"
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


def docker_status(image_name=None):
    image_name = image_name or IMAGE.get() or (DOCKER_IMAGE if RUNNER.get() == "pytest" else MULTILANG_IMAGE)
    if not shutil.which("docker"):
        return {"ready": False, "reason": "Docker is not installed or is not on PATH."}
    try:
        daemon = subprocess.run(["docker", "info", "--format", "{{.ServerVersion}}"],
                                capture_output=True, text=True, timeout=5)
        if daemon.returncode:
            return {"ready": False, "reason": "Start Docker Desktop using Linux containers."}
        image = subprocess.run(["docker", "image", "inspect", image_name],
                               capture_output=True, timeout=5)
        return {
            "ready": image.returncode == 0,
            "available": True,
            "reason": "Runner ready." if image.returncode == 0 else
                f"Runner image {image_name} is missing. Build the selected runner image first.",
        }
    except (OSError, subprocess.SubprocessError):
        return {"ready": False, "reason": "Docker did not respond. Check Docker Desktop."}


def run_pytest(repo_path: Path) -> dict:
    """Compatibility entry point: execute the runner selected for this investigation."""
    repo_path = Path(repo_path).resolve()
    if not repo_path.is_dir():
        return execution_error("The test directory does not exist at this revision.")
    if not shutil.which("docker"):
        return execution_error("Docker is unavailable. Install/start Docker Desktop and build the runner.")
    name = f"causaltrace-test-{uuid.uuid4().hex[:12]}"
    runner = RUNNER.get()
    image = IMAGE.get() or (DOCKER_IMAGE if runner == "pytest" else MULTILANG_IMAGE)
    upstream_image = image.startswith("causaltrace-upstream-")
    script = ["python", "-c", PYTEST_SCRIPT] if runner == "pytest" else ["python", "-c", DRIVER, runner]
    preparation = PREPARATION.get()
    volume = name + "-prepared"
    preparation_result = None
    common = [
        "docker", "run", "--rm",
        "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--memory", "256m" if runner == "pytest" and not upstream_image else "1g",
        "--cpus", "1" if runner == "pytest" and not upstream_image else "2",
        "--pids-limit", "64" if runner == "pytest" and not upstream_image else "256",
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=32m" if runner == "pytest" and not upstream_image else "/tmp:rw,exec,nosuid,size=512m",
        "-e", "PYTHONDONTWRITEBYTECODE=1",
        "-e", "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1",
        "--mount", f"type=bind,source={repo_path},target=/workspace,readonly",
        "-w", "/workspace",
    ]
    try:
        if preparation:
            if runner == "pytest":
                return execution_error("Automatic preparation is available for Node, Vitest, Jest, Maven and Go. For pytest use a prepared Python image.")
            created = subprocess.run(["docker", "volume", "create", "--label", "causaltrace.temporary=true", volume],
                                     capture_output=True, text=True, timeout=15)
            if created.returncode:
                return execution_error("Unable to create temporary project preparation storage.")
            mount = ["--mount", f"type=volume,source={volume},target=/prepared"]
            prepared = subprocess.run(
                [*common, "--name", name + "-prepare", "--network", "bridge" if preparation["install_dependencies"] else "none",
                 *mount, image, "python", "-c", PREPARE_DRIVER, runner, json.dumps(preparation)],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=PREPARATION_TIMEOUT)
            preparation_result = {"status": "completed" if prepared.returncode == 0 else "failed",
                                  "return_code": prepared.returncode, "output": prepared.stdout + "\n" + prepared.stderr}
            if prepared.returncode:
                return {**execution_error(preparation_result["output"], prepared.returncode), "preparation": preparation_result}
            script += ["--prepared"]
        else:
            mount = []
        command = [*common, "--name", name, "--network", "none", *mount, image, *script]
        result = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=180 if upstream_image else TEST_TIMEOUT, check=False,
        )
        evidence = parse_result(result.returncode, result.stdout, result.stderr)
        if preparation_result:
            evidence["preparation"] = preparation_result
        return evidence
    except subprocess.TimeoutExpired:
        preparing = preparation and preparation_result is None
        evidence = execution_error("Project preparation exceeded 300 seconds." if preparing else "Test execution exceeded its time limit.")
        if preparing:
            evidence["preparation"] = {"status": "failed", "return_code": -1, "output": evidence["output"]}
        elif preparation_result:
            evidence["preparation"] = preparation_result
        return evidence
    except OSError:
        return execution_error("Unable to launch Docker. Check Docker Desktop.")
    finally:
        cleanup_container(name)
        if preparation:
            cleanup_container(name + "-prepare")
            try:
                subprocess.run(["docker", "volume", "rm", volume], capture_output=True, timeout=15, check=False)
            except (OSError, subprocess.SubprocessError):
                pass
