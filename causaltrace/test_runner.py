
import subprocess
import sys
from pathlib import Path


TEST_TIMEOUT_SECONDS = 30


def run_pytest(repo_path: Path) -> dict:
    """Run pytest with a timeout and structured error handling."""

    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-v"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=TEST_TIMEOUT_SECONDS,
            check=False,
        )

    except subprocess.TimeoutExpired:
        message = (
            f"Pytest exceeded the {TEST_TIMEOUT_SECONDS}-second "
            "timeout. Investigation stopped."
        )

        return {
            "passed": False,
            "test_failed": False,
            "execution_error": True,
            "return_code": None,
            "stdout": "",
            "stderr": message,
            "output": message,
        }

    except OSError as error:
        message = f"Unable to execute pytest: {error}"

        return {
            "passed": False,
            "test_failed": False,
            "execution_error": True,
            "return_code": None,
            "stdout": "",
            "stderr": message,
            "output": message,
        }

    output = result.stdout + "\n" + result.stderr

    return {
        "passed": result.returncode == 0,
        "test_failed": result.returncode == 1,
        "execution_error": result.returncode not in (0, 1),
        "return_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "output": output,
    }
