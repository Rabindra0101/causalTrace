
import subprocess
import tempfile
import shutil
from pathlib import Path

from causaltrace.test_runner import run_pytest, is_failure, same_tests


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


def classify_test_result(result: dict) -> str:
    """
    Distinguish a genuine pytest failure from an execution error.
    """
    if is_failure(result):
        return "fail"
    if result.get("execution_error"):
        return "error"

    return_code = result.get("return_code")
    output = result.get("output", "")

    if return_code == 0 and result.get("passed"):
        return "pass"

    if return_code == 1 and "FAILED" in output:
        return "fail"

    return "error"


def test_commit(
    repo_path: Path,
    commit: str,
    test_directory: str,
):
    """Run pytest at a commit in an isolated Git worktree."""

    with tempfile.TemporaryDirectory(prefix="causaltrace-") as temp:
        worktree = Path(temp) / "repo"

        run_command(
            [
                "git",
                "worktree",
                "add",
                "--detach",
                str(worktree),
                commit,
            ],
            repo_path,
        )

        try:
            result = run_pytest(worktree / test_directory)

            return {
                **result,
                "commit": commit,
                "passed": result["passed"],
                "return_code": result["return_code"],
                "output": result["output"],
                "execution_error": result.get(
                    "execution_error", False
                ),
            }

        finally:
            run_command(
                [
                    "git",
                    "worktree",
                    "remove",
                    "--force",
                    str(worktree),
                ],
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

    before = test_commit(
        repo_path,
        parent_commit,
        test_directory,
    )

    after = test_commit(
        repo_path,
        suspect_commit,
        test_directory,
    )

    before_status = classify_test_result(before)
    after_status = classify_test_result(after)

    print(f"Parent commit: {parent_commit}")
    print(f"Result: {before_status.upper()}")

    print(f"\nSuspect commit: {suspect_commit}")
    print(f"Result: {after_status.upper()}")

    verified = (
        before_status == "pass"
        and after_status == "fail"
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


def find_regression_commit(
    repo_path: Path,
    test_directory: str = "demo/sample_repo",
):
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
        result = test_commit(
            repo_path,
            commit,
            test_directory,
        )

        status = classify_test_result(result)

        print(f"{commit[:7]}: {status.upper()}")

        if status == "error":
            print(
                "Investigation stopped: "
                "test execution was inconclusive."
            )
            print(result["output"])
            return None

        if status == "pass":
            if previous_failing_commit is not None:
                print("\n" + "=" * 60)
                print("REGRESSION BOUNDARY FOUND")
                print(f"Last passing commit: {commit[:7]}")
                print(
                    "First failing commit: "
                    f"{previous_failing_commit[:7]}"
                )
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
    Reverse a candidate commit in an isolated worktree based on
    HEAD and determine whether the observed failure disappears.

    Outcomes:
        verified:
            Tests fail before reversal and pass afterward.

        not_supported:
            Tests fail before and after a successful reversal.

        inconclusive:
            The experiment cannot be evaluated reliably.
    """

    print("\n[6] Running reversal experiment...\n")

    def result_payload(
        outcome: str,
        reason: str,
        before: dict | None = None,
        after: dict | None = None,
    ) -> dict:
        return {
            "verified": outcome == "verified",
            "outcome": outcome,
            "reason": reason,
            "before_return_code": (
                before.get("return_code")
                if before is not None
                else None
            ),
            "after_return_code": (
                after.get("return_code")
                if after is not None
                else None
            ),
            "before": before,
            "after": after,
        }

    with tempfile.TemporaryDirectory(
        prefix="causaltrace-reversal-"
    ) as temp:
        worktree = Path(temp) / "repo"

        try:
            run_command(
                [
                    "git",
                    "worktree",
                    "add",
                    "--detach",
                    str(worktree),
                    "HEAD",
                ],
                repo_path,
            )
        except (subprocess.SubprocessError, OSError) as error:
            print(f"Unable to create experiment worktree: {error}")

            return result_payload(
                "inconclusive",
                "Unable to create the experiment worktree.",
            )

        try:
            # 1. Run tests at HEAD before reversal.
            before = run_pytest(worktree / test_directory)
            before_status = classify_test_result(before)

            print(f"Candidate commit: {suspect_commit[:7]}")
            print("Experiment baseline: HEAD")
            print(f"Before reversal: {before_status.upper()}")

            if before_status != "fail":
                return result_payload(
                    "inconclusive",
                    "Baseline tests did not produce a valid test failure.",
                    before=before,
                )

            # 2. Reverse the candidate commit on HEAD.
            try:
                reversal = subprocess.run(
                    [
                        "git",
                        "revert",
                        "--no-commit",
                        suspect_commit,
                    ],
                    cwd=worktree,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=30,
                    check=False,
                )
            except (subprocess.SubprocessError, OSError) as error:
                print(f"Git reversal execution error: {error}")

                return result_payload(
                    "inconclusive",
                    "Git reversal could not be executed.",
                    before=before,
                )

            if reversal.returncode != 0:
                print("Reversal could not be applied.")
                print(reversal.stdout + reversal.stderr)

                return result_payload(
                    "inconclusive",
                    "Git reversal failed or encountered a conflict.",
                    before=before,
                )

            # 3. Remove cached Python bytecode.
            test_path = worktree / test_directory

            for cache_directory in test_path.rglob("__pycache__"):
                shutil.rmtree(
                    cache_directory,
                    ignore_errors=True,
                )

            pytest_cache = test_path / ".pytest_cache"

            if pytest_cache.exists():
                shutil.rmtree(
                    pytest_cache,
                    ignore_errors=True,
                )

            # 4. Run tests after reversal.
            after = run_pytest(worktree / test_directory)
            after_status = classify_test_result(after)

            print(f"After reversal: {after_status.upper()}")
            print(
                "After reversal exit code: "
                f"{after.get('return_code')}"
            )

            print("\nAfter reversal test output:")
            print(after.get("stdout", after.get("output", "")))

            if after.get("stderr"):
                print("\nAfter reversal errors:")
                print(after["stderr"])

            # 5. Classify the experiment.
            if after_status == "pass" and same_tests(before, after):
                outcome = "verified"
                reason = (
                    "Tests failed before reversal and passed afterward. "
                    "This supports the candidate as a cause of the "
                    "observed failure."
                )

            elif after_status == "fail":
                outcome = "not_supported"
                reason = (
                    "Tests failed before and after reversal. "
                    "Undoing this commit did not resolve the "
                    "observed failure."
                )

            else:
                outcome = "inconclusive"
                reason = (
                    "Tests could not be evaluated reliably "
                    "after reversal."
                )

            print("\n" + "=" * 60)
            print(f"REVERSAL OUTCOME: {outcome.upper()}")
            print(reason)

            return result_payload(
                outcome,
                reason,
                before=before,
                after=after,
            )

        finally:
            run_command(
                [
                    "git",
                    "worktree",
                    "remove",
                    "--force",
                    str(worktree),
                ],
                repo_path,
            )
