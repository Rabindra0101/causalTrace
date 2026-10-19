"""One workflow: reproduce -> locate -> explain -> reverse -> repair -> test."""
import json
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path

from causaltrace.build_doctor import BuildRequest, investigate, verify
from causaltrace.evidence_graph import build_investigation_graph
from causaltrace.nemotron_client import configuration
from causaltrace.test_runner import is_failure, setup_issues
from causaltrace.language_runner import RUNNER, IMAGE, PREPARATION, committed_runner, is_test_path
from causaltrace.verifier import classify_test_result, run_command, test_commit, verify_by_reversal
from causaltrace.repository_snapshot import independent_snapshot


MODEL_CONSENT = ContextVar("share_with_nebius", default=False)

def git(repo, *args):
    return run_command(["git", *args], repo).stdout.strip()


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
    text = ("### Diagnosis and suggestions\n" + diagnosis["summary"]
            + "\n\n### Evidence\n" + "\n".join("- " + item for item in diagnosis["evidence"])
            + "\n\n### Recommended next steps\n" + "\n".join("- " + item for item in diagnosis["recommended_steps"]))
    for key, title in (("suggested_tests", "Suggested tests"), ("improvements", "Optional improvements")):
        if diagnosis.get(key):
            text += "\n\n### " + title + "\n" + "\n".join("- " + item for item in diagnosis[key])
    if diagnosis.get("confidence") not in (None, "unspecified"):
        text += "\n\nModel confidence (self-reported): " + diagnosis["confidence"]
    return text


def add_ai_suggestions(report, repo, directory, diff=""):
    """No source/log export or model call without explicit per-run sharing consent."""
    explanation = "AI suggestions require permission to share selected evidence with Nebius."
    if not MODEL_CONSENT.get():
        report["ai_analysis"] = {"status": "consent_required", "reason": explanation}
        return explanation
    from causaltrace.diagnostic_context import evidence, bounded_text
    explanation = "AI suggestions could not be completed. Review the recorded test evidence."
    try:
        baseline = report["baseline"]
        files, scope = evidence(repo, directory, baseline["output"], diff)
        report["source_context"] = scope
        context = ("Observed baseline status: " + baseline["status"]
                   + ". Historical regression boundary confirmed: "
                   + str(report.get("regression", {}).get("confirmed", False))
                   + ". Advice is a hypothesis, not verification.\n")
        request = BuildRequest(log=bounded_text(context + baseline["output"], 40000),
                               files=files, diff=bounded_text(diff, 20000))
        report["model_request_attempted"] = True
        repair = investigate(request)
        report["repair"] = repair
        report["source_evidence"] = [file.model_dump() for file in files]
        explanation = hypothesis_text(repair["diagnosis"])
        report["ai_analysis"] = {"status": "completed", "provider": repair["provider"],
            "model": repair["model"], "hypothesis": explanation,
            "scope": "AI suggestions; Git causality and repair verification are separate."}
        if repair["patch"] and is_failure(baseline):
            try:
                repair["verification"] = verify(repair["id"], repository=repo, directory=directory)
            except Exception:
                repair["verification"] = {"status": "inconclusive", "reason": "Patch testing could not be completed. Check runner setup and server logs."}
        elif repair["patch"]:
            repair["verification"] = {"status": "not_run", "reason": "No reproduced failing baseline exists; this remains an unverified suggestion."}
    except Exception:
        key, model = configuration()
        report["ai_analysis"] = {"status": "unavailable", "provider": "Nebius Token Factory",
            "model": model, "hypothesis": "AI suggestions could not be completed.",
            "reason": "Set NEBIUS_API_KEY and retry." if not key else "Check model access and server logs."}
    return explanation


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
                      test_runner="auto", runner_image=None, install_dependencies=False,
                      build_frontend=False, frontend_directory="frontend", share_with_nebius=False, good_ref=None, bad_ref="HEAD", max_repair_attempts=3):
    release_selection = None
    if investigation_type == "release":
        from causaltrace.release_investigation import resolve_releases
        release_selection = resolve_releases(repo, good_ref, bad_ref)
    selected_runner = committed_runner(repo, directory, test_runner, revision=release_selection[1] if release_selection else "HEAD")
    consent_token = MODEL_CONSENT.set(share_with_nebius)
    runner_token = RUNNER.set(selected_runner)
    image_token = IMAGE.set(runner_image)
    preparation_token = PREPARATION.set({"install_dependencies": install_dependencies,
                                        "build_frontend": build_frontend, "frontend_directory": frontend_directory}
                                       if install_dependencies or build_frontend else None)
    try:
        if investigation_type == "release":
            from causaltrace.release_investigation import resolve_releases, run_release
            if Path(reports_root).resolve().is_relative_to(Path(repo).resolve()):
                raise ValueError("Reports must be outside the investigated repository.")
            if not 1 <= max_repair_attempts <= 5:
                raise ValueError("Choose between 1 and 5 repair attempts.")
            good, bad, revisions = release_selection
            with independent_snapshot(repo, revision=bad) as snapshot:
                selected_directory = (snapshot / directory).resolve()
                if not selected_directory.is_relative_to(snapshot.resolve()) or not selected_directory.is_dir():
                    raise ValueError("Test directory must exist inside the selected broken release.")
                normalized_directory = selected_directory.relative_to(snapshot.resolve()).as_posix()
                return run_release(snapshot, normalized_directory, repository_id, reports_root, good_ref, bad_ref,
                    good, bad, revisions, max_repair_attempts, MODEL_CONSENT.get())
        if repository_id == "local":
            if Path(reports_root).resolve().is_relative_to(Path(repo).resolve()):
                raise ValueError("Reports must be saved outside the investigated repository.")
            with independent_snapshot(repo) as snapshot:
                return _run_investigation(snapshot, directory, repository_id, reports_root, investigation_type)
        return _run_investigation(repo, directory, repository_id, reports_root, investigation_type)
    finally:
        MODEL_CONSENT.reset(consent_token)
        PREPARATION.reset(preparation_token)
        IMAGE.reset(image_token)
        RUNNER.reset(runner_token)


def _run_investigation(repo, directory, repository_id, reports_root, investigation_type):
    if investigation_type not in {"full", "diagnose", "regression", "reproduce"}:
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
        "model_sharing_consent": MODEL_CONSENT.get(),
        "preparation_options": PREPARATION.get(),
    }
    from causaltrace.public_demos import PUBLIC_IDS, metadata
    if repository_id in PUBLIC_IDS:
        from causaltrace.upstream_projects import provenance, profile
        if git(repo, "remote").splitlines() and git(repo, "remote", "get-url", "origin") == profile(repository_id)["url"]:
            report["provenance"] = provenance(repository_id)
        else:
            info = metadata(repository_id)
            report["provenance"] = {key: info[key] for key in ("name", "source", "upstream_fixed", "note")}
    # Test a committed worktree, not untracked/edited local files.
    baseline = test_commit(repo, "HEAD", directory)
    report["baseline"] = baseline
    if investigation_type == "diagnose":
        report["reason"] = "AI suggestions from baseline evidence; no Git regression boundary was requested or proven."
        add_ai_suggestions(report, repo, directory)
        report["status"] = "completed" if report["ai_analysis"]["status"] == "completed" else "partial"
        return persist(report, reports_root)
    if not is_failure(baseline):
        if baseline.get("status") == "pass_with_skips":
            report["status"] = "no_failure"
            report["reason"] = f"No failure reproduced among executed upstream tests. Skipped tests: {len(baseline.get('skipped_ids', []))}; coverage is incomplete and no repair is verified."
            return persist(report, reports_root)
        report["setup_issues"] = setup_issues(baseline)
        report["status"] = "no_failure" if baseline.get("passed") else "execution_error"
        report["reason"] = ("Committed tests pass." if baseline.get("passed") else
                            "No tests were collected. Choose a directory containing committed tests for the selected runner."
                            if baseline.get("return_code") in (0, 5) and not baseline.get("test_ids") else
                            "The baseline produced no valid test outcome. Expand test output for missing dependencies, build errors or runner setup details.")
        if report["setup_issues"]:
            report["reason"] = " ".join(issue["message"] for issue in report["setup_issues"])
        if investigation_type == "full" and not baseline.get("passed"):
            add_ai_suggestions(report, repo, directory)
        return persist(report, reports_root)
    if investigation_type == "reproduce":
        report["status"] = "completed"
        report["reason"] = "Committed HEAD failure reproduced. History, model analysis and repair were not requested."
        return persist(report, reports_root)
    boundary = locate_boundary(repo, directory)
    report["regression"] = boundary
    if not boundary["confirmed"]:
        report["reason"] = boundary["reason"]
        if investigation_type == "full":
            add_ai_suggestions(report, repo, directory)
            report["status"] = "partial"
        return persist(report, reports_root)
    suspect = boundary["suspected_commit"]
    diff = git(repo, "show", "--format=", suspect, "--", directory)
    report["candidate_diff"] = diff
    # A test edit can change expected behavior; do not present that as an implementation cause.
    changed = git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", suspect).splitlines()
    if any(is_test_path(p) for p in changed):
        report["reason"] = "The boundary changes tests. Implementation causality requires review."
        report["regression"]["confirmed"] = False
        if investigation_type == "full":
            add_ai_suggestions(report, repo, directory, diff)
            report["status"] = "partial"
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
    explanation = add_ai_suggestions(report, repo, directory, diff)
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
