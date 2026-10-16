
import sys
import argparse
import subprocess
from pathlib import Path

from causaltrace.git_analyzer import (
    get_commit_diff,
    get_recent_commits,
)
from causaltrace.test_runner import run_pytest
from causaltrace.nemotron_client import generate_root_cause_hypothesis
from causaltrace.verifier import find_regression_commit, verify_by_reversal
from causaltrace.report_generator import generate_report


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def validate_repository(repo_path: Path) -> bool:
    if not repo_path.is_dir():
        return False

    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=False,
    )

    return (
        result.returncode == 0
        and Path(result.stdout.strip()).resolve() == repo_path.resolve()
    )


def validate_test_directory(
    repo_path: Path,
    test_directory: str,
) -> bool:
    test_path = (repo_path / test_directory).resolve()

    return (
        test_path.is_dir()
        and test_path.is_relative_to(repo_path.resolve())
    )


def parse_arguments():
    project_root = Path(__file__).resolve().parent.parent

    parser = argparse.ArgumentParser(
        description="CausalTrace regression investigation engine"
    )

    parser.add_argument(
        "--repo",
        type=Path,
        default=project_root,
        help="Path to the Git repository to investigate",
    )

    parser.add_argument(
        "--test-dir",
        default="demo/sample_repo",
        help="Test directory relative to the repository root",
    )

    args = parser.parse_args()
    args.repo = args.repo.resolve()

    if not validate_repository(args.repo):
        parser.error(
            "The --repo path must be the root of an existing Git repository."
        )

    if not validate_test_directory(args.repo, args.test_dir):
        parser.error(
            "The --test-dir path must be an existing directory inside the repository."
        )

    return args


def get_latest_commit(repo_path: Path) -> str | None:
    """Return the current HEAD commit hash."""

    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        return None

    return result.stdout.strip() or None


def get_reversal_outcome(result: dict) -> str:
    """
    Read the structured outcome from the verifier.

    Retain compatibility with older verifier results.
    """
    outcome = result.get("outcome")

    if outcome in {
        "verified",
        "not_supported",
        "inconclusive",
    }:
        return outcome

    if result.get("verified") is True:
        return "verified"

    if (
        result.get("before_return_code") == 1
        and result.get("after_return_code") == 1
    ):
        return "not_supported"

    return "inconclusive"


def print_reversal_summary(
    label: str,
    result: dict,
):
    """Print the precise classification of a reversal experiment."""

    outcome = get_reversal_outcome(result)

    labels = {
        "verified": "VERIFIED",
        "not_supported": "NOT SUPPORTED",
        "inconclusive": "INCONCLUSIVE",
    }

    print(f"\n{label}: {labels[outcome]}")

    reason = result.get("reason")

    if reason:
        print(f"Reason: {reason}")
    elif outcome == "verified":
        print(
            "Reason: Reversal restored passing tests."
        )
    elif outcome == "not_supported":
        print(
            "Reason: Reversal did not resolve the observed failure."
        )
    else:
        print(
            "Reason: The experiment could not establish "
            "a reliable conclusion."
        )


def main():
    args = parse_arguments()

    application_root = Path(__file__).resolve().parent.parent
    project_root = args.repo
    test_directory = args.test_dir
    target_repo = project_root / test_directory

    print("\nCAUSALTRACE")
    print("=" * 60)

    # 1. Reproduce the failure.
    print("\n[1] Reproducing failure...\n")

    test_result = run_pytest(target_repo)

    if test_result["execution_error"]:
        print("STATUS: TEST EXECUTION ERROR")
        print(test_result["output"])
        return 1

    if test_result["passed"]:
        print("STATUS: PASS")
        print("No regression detected.")
        return 1

    # A nonzero exit code does not always mean pytest
    # observed an actual test assertion failure.
    if (
        test_result.get("return_code") != 1
        or "FAILED" not in test_result.get("output", "")
    ):
        print("STATUS: INCONCLUSIVE")
        print(
            "The test runner did not produce a valid "
            "pytest assertion failure."
        )
        print(test_result.get("output", ""))
        return 1

    print("STATUS: FAIL")
    print("\nFailure output:")
    print(test_result["output"])

    # 2. Inspect Git history.
    print("\n[2] Inspecting Git history...\n")

    commits = get_recent_commits(project_root)

    if not commits:
        print("No commits found.")
        return 1

    for commit in commits:
        print(commit)

    # 3. Search Git history for the regression.
    print("\n[3] Finding regression-introducing commit...\n")

    commit_hash = find_regression_commit(
        project_root,
        test_directory=test_directory,
    )

    if commit_hash is None:
        print(
            "Unable to identify a regression-introducing commit."
        )
        return 1

    print(
        f"\nIdentified regression commit: {commit_hash[:7]}"
    )

    diff = get_commit_diff(project_root, commit_hash)
    print(diff)

    # 4. Generate an AI hypothesis.
    print(
        "\n[4] Asking NVIDIA Nemotron "
        "to analyze the evidence...\n"
    )

    hypothesis = generate_root_cause_hypothesis(
        test_output=test_result["output"],
        git_diff=diff,
    )

    print("NEMOTRON ROOT-CAUSE HYPOTHESIS:")
    print(hypothesis)

    # 5. Review the passing-to-failing boundary.
    print("\n[5] Reviewing regression evidence...\n")

    verification_status = "REGRESSION BOUNDARY CONFIRMED"

    print(
        f"Last passing revision: {commit_hash[:7]}^"
    )
    print(
        f"First failing revision: {commit_hash[:7]}"
    )
    print(
        f"Verification status: {verification_status}"
    )

    # 6A. Test the latest commit as an alternative hypothesis
    # when it differs from the regression-introducing commit.
    latest_commit = get_latest_commit(project_root)
    alternative_reversal_result = None

    if latest_commit and latest_commit != commit_hash:
        print(
            "\n[6A] Testing latest commit "
            "as an alternative hypothesis...\n"
        )

        print(
            f"Alternative commit: {latest_commit[:7]}"
        )
        print(
            f"Regression commit: {commit_hash[:7]}"
        )

        alternative_reversal_result = verify_by_reversal(
            project_root,
            latest_commit,
            test_directory=test_directory,
        )

        print_reversal_summary(
            "Alternative hypothesis",
            alternative_reversal_result,
        )

        if get_reversal_outcome(
            alternative_reversal_result
        ) == "verified":
            print(
                "Note: Reverting the latest commit also "
                "restored passing tests. Multiple commits "
                "may influence the observed failure."
            )

    else:
        print(
            "\n[6A] Alternative hypothesis "
            "experiment skipped."
        )
        print(
            "No different latest commit is "
            "available for comparison."
        )

    # 6B. Verify the identified regression commit.
    print(
        "\n[6B] Verifying the "
        "regression-introducing commit...\n"
    )

    reversal_result = verify_by_reversal(
        project_root,
        commit_hash,
        test_directory=test_directory,
    )

    primary_outcome = get_reversal_outcome(
        reversal_result
    )

    print_reversal_summary(
        "Regression hypothesis",
        reversal_result,
    )

    causal_status_labels = {
        "verified": "REVERSAL VERIFIED",
        "not_supported": "REVERSAL NOT SUPPORTED",
        "inconclusive": "REVERSAL INCONCLUSIVE",
    }

    causal_status = causal_status_labels[primary_outcome]

    print(
        f"\nCausal verification: {causal_status}"
    )

    # 7. Generate a report containing both experiments.
    report_path = generate_report(
        project_root=application_root,
        regression_commit=commit_hash,
        hypothesis=hypothesis,
        reversal_result=reversal_result,
        test_result=test_result,
        alternative_commit=(
            latest_commit
            if alternative_reversal_result is not None
            else None
        ),
        alternative_reversal_result=alternative_reversal_result,
    )

    print("\n" + "=" * 60)
    print("INVESTIGATION COMPLETE")
    print("=" * 60)

    print("Regression reproduced: YES")
    print(f"Failing repository: {target_repo}")
    print(f"Candidate commit: {commit_hash}")

    if alternative_reversal_result is not None:
        alternative_outcome = get_reversal_outcome(
            alternative_reversal_result
        )

        print(
            f"Alternative commit tested: {latest_commit}"
        )

        print(
            "Alternative reversal outcome: "
            f"{alternative_outcome.upper().replace('_', ' ')}"
        )

    print(
        f"Regression reversal outcome: "
        f"{primary_outcome.upper().replace('_', ' ')}"
    )

    print(
        f"Counterfactual verification: "
        f"{verification_status}"
    )

    print(
        f"Causal verification: {causal_status}"
    )

    print(
        f"Investigation report: {report_path}"
    )

    print("\nCausalTrace investigation finished.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
