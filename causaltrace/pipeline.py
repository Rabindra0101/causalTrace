"""One workflow: reproduce -> locate -> explain -> reverse -> repair -> test."""
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from causaltrace.build_doctor import BuildRequest, SourceFile, investigate, verify
from causaltrace.evidence_graph import build_investigation_graph
from causaltrace.nemotron_client import configuration
from causaltrace.test_runner import is_failure
from causaltrace.language_runner import RUNNER, IMAGE, committed_runner, is_test_path
from causaltrace.verifier import classify_test_result, run_command, test_commit, verify_by_reversal


def git(repo, *args):
    return run_command(["git", *args], repo).stdout.strip()


def tracked_sources(repo, test_directory):
    prefix = Path(test_directory).as_posix().rstrip("/")
    if prefix == ".":
        prefix = ""
    paths = git(repo, "ls-tree", "-r", "--name-only", "HEAD").splitlines()
    files = []
    for path in paths:
        if prefix and not path.startswith(prefix + "/"):
            continue
        relative = path[len(prefix) + 1:] if prefix else path
        if not relative.endswith((".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".java", ".go")):
            continue
        if (repo / path).is_symlink():
            raise ValueError("Symbolic links are not supported as repair evidence.")
        content = run_command(["git", "show", f"HEAD:{path}"], repo).stdout
        # Preserve complete source lines; the model needs exact fragments for patches.
        files.append(SourceFile(path=relative, content=content.lstrip("\ufeff")))
    if not files:
        raise ValueError("No supported source was found in the configured test directory.")
    return files


def locate_boundary(repo, directory, limit=16):
    history = git(repo, "rev-list", "--first-parent", "--max-count=" + str(limit), "HEAD").splitlines()
    rows = []
    newest_failure = None
    for commit in history:
        result = test_commit(repo, commit, directory)
        status = classify_test_result(result)
        rows.append({"commit": commit, "status": result.get("status", status), "result": result})
        if status == "error":
            return {"confirmed": False, "reason": "A historical test run could not be evaluated.", "history": rows}
        if status == "pass":
            if newest_failure:
                return {"confirmed": True, "suspected_commit": newest_failure,
                        "parent_revision": commit, "history": rows}
            return {"confirmed": False, "reason": "Committed HEAD passes; no committed regression was reproduced.", "history": rows}
        newest_failure = commit
    return {"confirmed": False, "reason": f"No passing baseline within {limit} commits.", "history": rows}


def hypothesis_text(diagnosis):
    return ("### Likely Root Cause\n" + diagnosis["summary"]
            + "\n\n### Evidence\n" + "\n".join("- " + s for s in diagnosis["evidence"])
            + "\n\n### Recommended Fix\n" + "\n".join("- " + s for s in diagnosis["recommended_steps"]))


def persist(report, reports_root):
    reports_root = Path(reports_root)
    reports_root.mkdir(parents=True, exist_ok=True)
    content = json.dumps(report, indent=2, ensure_ascii=False)
    path = reports_root / (report["id"] + ".json")
    temporary = reports_root / (report["id"] + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)
    # Legacy CLI consumers can still read the most recent completed report.
    latest = reports_root / (report["id"] + ".latest.tmp")
    latest.write_text(content, encoding="utf-8")
    latest.replace(reports_root / "latest_investigation.json")
    return report


def run_investigation(repo, directory, repository_id, reports_root, investigation_type="full",
                      test_runner="auto", runner_image=None):
    runner_token = RUNNER.set(committed_runner(repo, directory, test_runner))
    image_token = IMAGE.set(runner_image)
    try:
        return _run_investigation(repo, directory, repository_id, reports_root, investigation_type)
    finally:
        IMAGE.reset(image_token)
        RUNNER.reset(runner_token)


def _run_investigation(repo, directory, repository_id, reports_root, investigation_type):
    if investigation_type not in {"full", "regression", "reproduce"}:
        raise ValueError("Unknown investigation type.")
    repo = Path(repo).resolve()
    if git(repo, "rev-parse", "--show-toplevel") != str(repo):
        # Windows Git can return slash-normalized paths.
        if Path(git(repo, "rev-parse", "--show-toplevel")).resolve() != repo:
            raise ValueError("The configured path must be a Git repository root.")
    test_root = (repo / directory).resolve()
    if not test_root.is_relative_to(repo) or not test_root.is_dir():
        raise ValueError("Test directory must be inside the configured repository.")
    if git(repo, "status", "--porcelain", "--untracked-files=no"):
        raise ValueError("Commit or stash tracked changes before investigating Git history.")
    report = {
        "id": uuid.uuid4().hex, "project": "CausalTrace", "repository_id": repository_id,
        "generated_at": datetime.now(timezone.utc).isoformat(), "status": "inconclusive",
        "baseline_revision": git(repo, "rev-parse", "HEAD"), "experiments": {},
        "repair": None, "ai_analysis": {"status": "not_run"},
        "investigation_type": investigation_type,
        "test_runner": RUNNER.get(),
    }
    # Test a committed worktree, not untracked/edited local files.
    baseline = test_commit(repo, "HEAD", directory)
    report["baseline"] = baseline
    if not is_failure(baseline):
        report["status"] = "no_failure" if baseline.get("passed") else "execution_error"
        report["reason"] = ("Committed tests pass." if baseline.get("passed") else
                            "No tests were collected. Choose a directory containing committed tests for the selected runner."
                            if baseline.get("return_code") in (0, 5) and not baseline.get("test_ids") else
                            "The baseline produced no valid test outcome. Expand test output for missing dependencies, build errors or runner setup details.")
        return persist(report, reports_root)
    if investigation_type == "reproduce":
        report["status"] = "completed"
        report["reason"] = "Committed HEAD failure reproduced. History, model analysis and repair were not requested."
        return persist(report, reports_root)
    boundary = locate_boundary(repo, directory)
    report["regression"] = boundary
    if not boundary["confirmed"]:
        report["reason"] = boundary["reason"]
        return persist(report, reports_root)
    suspect = boundary["suspected_commit"]
    diff = git(repo, "show", "--format=", suspect, "--", directory)
    report["candidate_diff"] = diff
    # A test edit can change expected behavior; do not present that as an implementation cause.
    changed = git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", suspect).splitlines()
    if any(is_test_path(p) for p in changed):
        report["reason"] = "The boundary changes tests. Implementation causality requires review."
        report["regression"]["confirmed"] = False
        return persist(report, reports_root)
    primary = verify_by_reversal(repo, suspect, test_directory=directory)
    primary["commit"] = suspect
    report["experiments"]["commit_reversal"] = primary
    head = report["baseline_revision"]
    if head != suspect:
        alternative = verify_by_reversal(repo, head, test_directory=directory)
        alternative["commit"] = head
        report["experiments"]["alternative_reversal"] = alternative
    if investigation_type == "regression":
        report["status"] = "completed"
        report["reason"] = "Git history and reversal experiments finished. Model analysis and repair were not requested."
        report["evidence_graph"] = build_investigation_graph(
            baseline, suspect, "Model analysis was not requested.", primary)
        return persist(report, reports_root)
    explanation = "Nemotron analysis is unavailable. Review the test and reversal evidence."
    try:
        request = BuildRequest(log=baseline["output"], files=tracked_sources(repo, directory), diff=diff)
        repair = investigate(request)
        report["repair"] = repair
        report["source_evidence"] = [file.model_dump() for file in request.files]
        explanation = hypothesis_text(repair["diagnosis"])
        report["ai_analysis"] = {"status": "completed", "provider": repair["provider"],
                                 "model": repair["model"], "hypothesis": explanation}
        if repair["patch"]:
            repair["verification"] = (verify(repair["id"]) if RUNNER.get() == "pytest" else
                                      verify(repair["id"], repository=repo, directory=directory))
    except Exception:
        # Preserve experimental evidence on missing key, provider outage or malformed response.
        key, model = configuration()
        report["ai_analysis"] = {
            "status": "unavailable", "provider": "Nebius Token Factory", "model": model,
            "hypothesis": explanation,
            "reason": "Set NEBIUS_API_KEY and retry." if not key else
                "Nemotron analysis or repair verification failed. Check model access, credit and server logs.",
        }
    report["evidence_graph"] = build_investigation_graph(baseline, suspect, explanation, primary)
    for node in report["evidence_graph"]["nodes"]:
        if node["type"] == "ai_hypothesis":
            node["data"]["model"] = report["ai_analysis"].get("model", "unavailable")
    if report["repair"]:
        graph = report["evidence_graph"]
        graph["nodes"].append({"id": "proposed_repair", "type": "repair", "data": {
            "patch": report["repair"]["patch"], "verification": report["repair"]["verification"]["status"],
        }})
        graph["edges"].append({"source": "root_cause_hypothesis", "target": "proposed_repair", "relationship": "proposes"})
    report["status"] = "completed" if report["ai_analysis"]["status"] == "completed" else "partial"
    report["reason"] = "Review reversal and repair results separately; each has its own experimental outcome."
    return persist(report, reports_root)
