"""Command line entry point for the same workflow used by the dashboard."""
import argparse
import json
import sys
from pathlib import Path

from causaltrace.demo_setup import DEMO_IDS, ensure_demo
from causaltrace.pipeline import run_investigation
from causaltrace.test_runner import docker_status


def main():
    parser = argparse.ArgumentParser(description="CausalTrace regression investigation and tested repair")
    parser.add_argument("--repository", choices=DEMO_IDS, default="config", help="Bundled demo")
    parser.add_argument("--repo", type=Path, help="Explicit local repository root (CLI only)")
    parser.add_argument("--test-dir", default=".", help="Test directory relative to --repo")
    args = parser.parse_args()
    docker = docker_status()
    if not docker["ready"]:
        print(docker["reason"])
        return 2
    repo = args.repo.resolve() if args.repo else ensure_demo(args.repository)
    report = run_investigation(
        repo, args.test_dir if args.repo else ".",
        "local" if args.repo else args.repository,
        Path(__file__).resolve().parent.parent / "reports",
    )
    print(json.dumps({"id": report["id"], "status": report["status"],
                      "reason": report.get("reason"),
                      "report": f"reports/{report['id']}.json"}, indent=2))
    return 0 if report["status"] == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())
