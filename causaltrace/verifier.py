
import subprocess
import sys
import tempfile
import shutil
from pathlib import Path
from causaltrace.test_runner import run_pytest


def run_command(args, cwd):
    return subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
        timeout=30,
    )


def test_commit(repo_path: Path, commit: str, test_directory: str):
    """Run pytest at a commit in an isolated Git worktree."""

    with tempfile.TemporaryDirectory(prefix="causaltrace-") as temp:
        worktree = Path(temp) / "repo"

        run_command(
            ["git", "worktree", "add", "--detach",
             str(worktree), commit],
            repo_path,
        )

        try:
            result = run_pytest(worktree / test_directory)


            return {
                "commit": commit,
                "passed": result["passed"],
                "return_code": result["return_code"],
                "output": result["output"],
            }

        finally:
            run_command(
                ["git", "worktree", "remove", "--force",
                 str(worktree)],
                repo_path,
            )


def verify_regression(
    repo_path: Path,
    suspect_commit: str,
    test_directory: str = "demo/sample_repo",
):
    """Compare a suspected regression commit with its parent."""

    parent_commit = f"{suspect_commit}^"

    print("\n[5] Running counterfactual verification...\n")

    before = test_commit(repo_path, parent_commit, test_directory)
    after = test_commit(repo_path, suspect_commit, test_directory)

    print(f"Parent commit: {parent_commit}")
    print(f"Result: {'PASS' if before['passed'] else 'NOT PASS'}")

    print(f"\nSuspect commit: {suspect_commit}")
    print(f"Result: {'PASS' if after['passed'] else 'NOT PASS'}")

    verified = (
        before["return_code"] == 0
        and after["return_code"] == 1
        and "FAILED" in after["output"]
    )

    print("\n" + "=" * 60)

    if verified:
        print("COUNTERFACTUAL EVIDENCE FOUND")
        print("Parent version: PASS")
        print("Suspected version: FAIL")
        print("Regression introduced between these revisions.")
    else:
        print("REGRESSION NOT VERIFIED")
        print("Inspect test output and execution errors.")

    return verified



def find_regression_commit(repo_path: Path, test_directory: str = "demo/sample_repo"):
    """
    Search backward through first-parent Git history to find
    the first passing revision before the current failure.
    """
    history = run_command(
        ["git", "rev-list", "--first-parent", "HEAD"],
        repo_path,
    ).stdout.splitlines()

    print("\n[5] Searching Git history for regression...\n")

    previous_failing_commit = None

    for commit in history:
        result = test_commit(repo_path, commit, test_directory)

        if result["return_code"] == 0:
            status = "PASS"
        elif result["return_code"] == 1 and "FAILED" in result["output"]:
            status = "FAIL"
        else:
            status = "ERROR"

        print(f"{commit[:7]}: {status}")

        if status == "ERROR":
            print("Investigation stopped: test execution was inconclusive.")
            print(result["output"])
            return None

        if status == "PASS":
            if previous_failing_commit is not None:
                print("\n" + "=" * 60)
                print("REGRESSION BOUNDARY FOUND")
                print(f"Last passing commit: {commit[:7]}")
                print(f"First failing commit: {previous_failing_commit[:7]}")
                return previous_failing_commit

            print("The newest revision passes. No current regression.")
            return None

        previous_failing_commit = commit

    print("\nNo passing baseline was found in the tested history.")
    return None


def verify_by_reversal(
    repo_path: Path,
    suspect_commit: str,
    test_directory: str = "demo/sample_repo",
) -> dict:
    """
    Test whether reverting the suspect commit restores
    passing tests in an isolated worktree.
    """
    print("\n[6] Running reversal experiment...\n")

    with tempfile.TemporaryDirectory(prefix="causaltrace-reversal-") as temp:
        worktree = Path(temp) / "repo"

        run_command(
            ["git", "worktree", "add", "--detach",
             str(worktree), suspect_commit],
            repo_path,
        )

        try:
            # Run tests before the reversal
            before = run_pytest(worktree / test_directory)

            print(f"Original revision: {suspect_commit[:7]}")
            print(f"Before reversal: {'PASS' if before['passed'] else 'NOT PASS'}")

            # Reverse the suspect commit inside the temporary worktree
            reversal = subprocess.run(
                ["git", "revert", "--no-commit", suspect_commit],
                cwd=worktree,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if reversal.returncode != 0:
                print("Reversal could not be applied.")
                print(reversal.stdout + reversal.stderr)
                return {
                    "verified": False,
                    "reason": "Git reversal failed",
                }

            # Remove cached Python bytecode before retesting.
            test_path = worktree / test_directory

            for cache_directory in test_path.rglob("__pycache__"):
                shutil.rmtree(cache_directory, ignore_errors=True)

            pytest_cache = test_path / ".pytest_cache"
            if pytest_cache.exists():
                shutil.rmtree(pytest_cache, ignore_errors=True)

            # Run tests after the reversal
            after = run_pytest(worktree / test_directory)

            print(f"After reversal: {'PASS' if after['passed'] else 'NOT PASS'}")
            print(f"\nAfter reversal exit code: {after['return_code']}")
            print("\nAfter reversal pytest output:")
            print(after["stdout"])

            if after["stderr"]:
                print("\nAfter reversal errors:")
                print(after["stderr"])

            verified = (
                before["return_code"] == 1
                and "FAILED" in before["output"]
                and after["return_code"] == 0
            )

            if verified:
                print("\nREVERSAL EXPERIMENT SUCCESSFUL")
                print("The original revision failed.")
                print("Reverting the suspected commit restored passing tests.")
            else:
                print("\nREVERSAL EXPERIMENT INCONCLUSIVE")
                print("The expected fail-to-pass transition was not observed.")

            return {
                "verified": verified,
                "before_return_code": before["return_code"],
                "after_return_code": after["return_code"],
            }

        finally:
            run_command(
                ["git", "worktree", "remove", "--force", str(worktree)],
                repo_path,
            )

