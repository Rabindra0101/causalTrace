"""Command line entry point for the same workflow used by the dashboard."""
import argparse
import json
import sys
from pathlib import Path

from causaltrace.demo_setup import DEMO_IDS, ensure_demo
from causaltrace.pipeline import run_investigation
from causaltrace.test_runner import docker_status
from causaltrace.language_runner import RUNNERS, committed_runner, MULTILANG_IMAGE


def main():
    parser = argparse.ArgumentParser(description="CausalTrace regression investigation and tested repair")
    parser.add_argument("--repository", choices=DEMO_IDS, default="config", help="Bundled demo")
    parser.add_argument("--repo", type=Path, help="Explicit local repository root (CLI only)")
    parser.add_argument("--test-dir", default=".", help="Test directory relative to --repo")
    parser.add_argument("--test-runner", choices=RUNNERS, default="auto")
    parser.add_argument("--runner-image", help="Prepared Docker image containing project test dependencies")
    parser.add_argument("--install-dependencies", action="store_true", help="Allow dependency downloads in a preparation container")
    parser.add_argument("--build-frontend", action="store_true", help="Build frontend assets before offline tests")
    parser.add_argument("--frontend-directory", default="frontend", help="Relative frontend directory, or . for project root")
    args = parser.parse_args()
    repo = args.repo.resolve() if args.repo else ensure_demo(args.repository)
    directory = args.test_dir if args.repo else "."
    runner = committed_runner(repo, directory, args.test_runner)
    docker = docker_status(args.runner_image or MULTILANG_IMAGE) if runner != "pytest" or args.runner_image else docker_status()
    if not docker["ready"]:
        print(docker["reason"])
        return 2
    report = run_investigation(
        repo, args.test_dir if args.repo else ".",
        "local" if args.repo else args.repository,
        Path(__file__).resolve().parent.parent / "reports",
        test_runner=runner, runner_image=args.runner_image,
        install_dependencies=args.install_dependencies, build_frontend=args.build_frontend,
        frontend_directory=args.frontend_directory,
    )
    print(json.dumps({"id": report["id"], "status": report["status"],
                      "reason": report.get("reason"),
                      "report": f"reports/{report['id']}.json"}, indent=2))
    return 0 if report["status"] == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())
