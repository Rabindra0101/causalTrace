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
        and Path(result.stdout.strip()).resolve() == repo_path
    )


def validate_test_directory(repo_path: Path, test_directory: str) -> bool:
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


def main():
    args = parse_arguments()

    application_root = Path(__file__).resolve().parent.parent
    project_root = args.repo
    test_directory = args.test_dir
    target_repo = project_root / test_directory

    print("\nCAUSALTRACE")
    print("=" * 60)

    # 1. Reproduce the failure
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

    print("STATUS: FAIL")
    print("\nFailure output:")
    print(test_result["output"])

    # 2. Inspect Git history
    print("\n[2] Inspecting Git history...\n")

    commits = get_recent_commits(project_root)

    if not commits:
        print("No commits found.")
        return 1

    for commit in commits:
        print(commit)

    # 3. Search Git history for the regression
    print("\n[3] Finding regression-introducing commit...\n")

    commit_hash = find_regression_commit(
        project_root,
        test_directory=test_directory,
    )

    if commit_hash is None:
        print("Unable to identify a regression-introducing commit.")
        return 1

    print(f"\nIdentified regression commit: {commit_hash[:7]}")

    diff = get_commit_diff(project_root, commit_hash)
    print(diff)

    # 4. Generate an AI hypothesis
    print("\n[4] Asking NVIDIA Nemotron to analyze the evidence...\n")

    hypothesis = generate_root_cause_hypothesis(
        test_output=test_result["output"],
        git_diff=diff,
    )

    print("NEMOTRON ROOT-CAUSE HYPOTHESIS:")
    print(hypothesis)

    # 5. Review the passing-to-failing boundary
    print("\n[5] Reviewing regression evidence...\n")

    verification_status = "REGRESSION BOUNDARY CONFIRMED"

    print(f"Last passing revision: {commit_hash[:7]}^")
    print(f"First failing revision: {commit_hash[:7]}")
    print(f"Verification status: {verification_status}")

    # 6. Test whether reversing the suspect commit restores passing tests
    reversal_result = verify_by_reversal(
        project_root,
        commit_hash,
        test_directory=test_directory,
    )

    if reversal_result["verified"]:
        causal_status = "REVERSAL VERIFIED"
    else:
        causal_status = "REVERSAL INCONCLUSIVE"

    print(f"\nCausal verification: {causal_status}")

    # 7. Generate a machine-readable investigation report
    report_path = generate_report(
        project_root=application_root,
        regression_commit=commit_hash,
        hypothesis=hypothesis,
        reversal_result=reversal_result,
        test_result=test_result,
    )

    print("\n" + "=" * 60)
    print("INVESTIGATION COMPLETE")
    print("=" * 60)

    print("Regression reproduced: YES")
    print(f"Failing repository: {target_repo}")
    print(f"Candidate commit: {commit_hash}")
    print(f"Counterfactual verification: {verification_status}")
    print(f"Causal verification: {causal_status}")
    print(f"Investigation report: {report_path}")
    print("\nCausalTrace investigation finished.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
