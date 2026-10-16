
import subprocess
import uuid
from pathlib import Path

DOCKER_IMAGE = "causaltrace-test-runner:local"
TEST_TIMEOUT = 60


def cleanup_container(container_name: str) -> None:
    """Force-remove a test container if it still exists."""
    try:
        subprocess.run(
            ["docker", "rm", "-f", container_name],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        pass


def run_pytest(repo_path: Path) -> dict:
    """Run pytest inside a restricted Docker container."""

    repo_path = Path(repo_path).resolve()
    container_name = f"causaltrace-test-{uuid.uuid4().hex[:12]}"

    command = [
        "docker", "run",
        "--rm",
        "--name", container_name,
        "--network", "none",
        "--read-only",
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--memory", "256m",
        "--cpus", "1",
        "--pids-limit", "64",
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=32m",
        "--mount",
        f"type=bind,source={repo_path},target=/workspace,readonly",
        DOCKER_IMAGE,
        "python", "-m", "pytest", "-v",
        "-p", "no:cacheprovider",
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=TEST_TIMEOUT,
            check=False,
        )

        output = result.stdout + "\n" + result.stderr

        # Pytest exit code 1 is a test failure only when
        # pytest actually reports failed tests.
        test_failed = (
            result.returncode == 1
            and "FAILED" in output
        )

        return {
            "passed": result.returncode == 0,
            "test_failed": test_failed,
            "execution_error": (
                result.returncode != 0 and not test_failed
            ),
            "return_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "output": output,
        }

    except subprocess.TimeoutExpired:
        return {
            "passed": False,
            "test_failed": False,
            "execution_error": True,
            "return_code": -1,
            "stdout": "",
            "stderr": "Docker test execution timed out.",
            "output": (
                f"Test execution exceeded {TEST_TIMEOUT} seconds."
            ),
        }

    except OSError as error:
        return {
            "passed": False,
            "test_failed": False,
            "execution_error": True,
            "return_code": -1,
            "stdout": "",
            "stderr": str(error),
            "output": str(error),
        }

    finally:
        cleanup_container(container_name)
