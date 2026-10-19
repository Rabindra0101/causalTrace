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
from causaltrace.analysis_policy import ACTIVE_PROFILE, MODEL_USAGE, PROFILES, settings, usage_summary
from causaltrace.investigation_control import ACTIVE_CONTROL, InvestigationStopped, checkpoint


MODEL_CONSENT = ContextVar("share_with_nebius", default=False)
HISTORY_LIMIT = ContextVar("history_limit", default=64)

def git(repo, *args):
    return run_command(["git", *args], repo).stdout.strip()


def locate_boundary(repo, directory, limit=16, baseline=None):
    """Test every first-parent commit through the newest passing/failing transition."""
    log = git(repo, "log", "--first-parent", "--max-count="+str(limit),
              "--format=%H%x1f%h%x1f%s%x1f%aI", "HEAD")
    commits = [line.split("\x1f", 3) for line in log.splitlines() if len(line.split("\x1f", 3)) == 4]
    rows, latest_pass, latest_fail = [], None, None
    latest_partial, latest_error, initial = None, None, None
    previous_observed = None
    def result(confirmed, reason, **extra):
        return {"confirmed":confirmed, "reason":reason, "history":rows,
                "latest_pass":latest_pass, "latest_fail":latest_fail,
                "latest_pass_with_skips":latest_partial, "latest_error":latest_error,
                "limit":limit, "complete":False, **extra}
    for index, (commit, short, message, date) in enumerate(commits):
        run = baseline if index == 0 and baseline is not None else test_commit(repo, commit, directory)
        state = classify_test_result(run)
        partial = run.get("status") == "pass_with_skips"
        rows.append({"commit":commit, "short_hash":short, "message":message, "date":date,
                     "status":run.get("status", state), "result":run})
        if partial:
            latest_partial = latest_partial or commit
            state = "pass"
        elif state == "error":
            latest_error = latest_error or commit
            continue  # Keep the error visible; do not hide older failures.
        elif state == "pass":
            latest_pass = latest_pass or commit
        elif state == "fail":
            latest_fail = latest_fail or commit
        initial = initial or state
        if state != initial:
            reliable = all(row["status"] in {"pass", "fail", "collection_error"} for row in rows)
            if initial == "fail":
                if reliable:
                    return result(True, "Every commit from HEAD through the adjacent passing/failing boundary was tested.",
                        suspected_commit=previous_observed, parent_revision=commit,
                        transition="regression", complete=True, stop_reason="transition_found")
                return result(False, "Passing/failing results were found. Skipped or unavailable runs remain visible and prevent a verified regression boundary.",
                    observed_failing_revision=latest_fail, observed_passing_revision=latest_pass or latest_partial,
                    transition="uncertain", complete=True, stop_reason="transition_with_gaps")
            reason = ("HEAD passes. The most recent older failing commit and every intervening commit were tested." if reliable else
                      "An older failing commit was found after passing/partially passing results. Skips and runner errors remain visible; no regression boundary is verified.")
            return result(False, reason, transition="recovery" if reliable else "uncertain",
                passing_revision=previous_observed, failing_revision=commit,
                complete=True, stop_reason="transition_found" if reliable else "transition_with_gaps")
        previous_observed = commit
    exhausted = len(commits) < limit or (commits and not git(repo, "rev-list", "--parents", "-n", "1", commits[-1][0]).split()[1:])
    return result(False, "All attempted results, including skips and errors, are shown. No passing/failing transition was found before " + ("the repository root." if exhausted else f"the {limit}-commit search limit."),
        stop_reason="repository_root" if exhausted else "search_limit")


def test_complete_history(repo, directory, baseline=None):
    """Execute every commit reachable from the selected HEAD, including merge parents."""
    rows = []
    latest_pass = latest_fail = None
    for line in git(repo, 'log', '--topo-order', '--format=%H%x1f%h%x1f%s%x1f%aI', 'HEAD').splitlines():
        commit, short, message, date = line.split('\x1f', 3)
        run = baseline if not rows and baseline is not None else test_commit(repo, commit, directory)
        rows.append({'commit':commit, 'short_hash':short, 'message':message, 'date':date,
                     'status':run['status'], 'result':run})
        if run.get('passed'):
            latest_pass = latest_pass or commit
        if is_failure(run):
            latest_fail = latest_fail or commit
    return {'confirmed':False, 'history':rows, 'latest_pass':latest_pass, 'latest_fail':latest_fail,
            'complete':True, 'stop_reason':'repository_root', 'limit':len(rows),
            'reason':'Every commit reachable from the selected revision was tested, including merge parents. All failures, skips and runner errors remain visible. Timeline ordering alone does not prove causality.'}


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
        limits = settings()
        request = BuildRequest(log=bounded_text(context + baseline["output"], limits["log_chars"]),
                               files=files, diff=bounded_text(diff, limits["diff_chars"]))
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
    report["analysis_profile"] = ACTIVE_PROFILE.get()
    report["model_usage"] = usage_summary()
    boundary = report.get("regression", {})
    rows = boundary.get("history", [])
    if rows and all("date" in row for row in rows):
        report["tested_history"] = {
            "history_type": "local" if report["repository_id"] == "local" else report.get("provenance", {}).get("history_type", "synthetic"),
            "latest_pass": boundary.get("latest_pass") or next((r["commit"] for r in rows if r["status"] == "pass"), None),
            "latest_fail": boundary.get("latest_fail") or next((r["commit"] for r in rows if r["status"] in {"fail", "collection_error"}), None),
            "latest_pass_with_skips": boundary.get("latest_pass_with_skips") or next((r["commit"] for r in rows if r["status"] == "pass_with_skips"), None),
            "latest_error": boundary.get("latest_error") or next((r["commit"] for r in rows if r["status"] == "error"), None),
            "complete": boundary.get("complete", False), "reason": boundary.get("reason", ""),
            "stop_reason": boundary.get("stop_reason"), "limit": boundary.get("limit"),
            "commits": [{"hash":row["commit"], "short_hash":row["short_hash"], "message":row["message"],
                "date":row["date"], "test_status":row["status"],
                "result":{**{key:row["result"].get(key) for key in ("status", "return_code", "output")},
                          "counts":{key:len(row["result"].get(key+"_ids", [])) for key in ("test", "passed", "failed", "skipped")}}} for row in rows]}
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
                      build_frontend=False, frontend_directory="frontend", share_with_nebius=False, good_ref=None, bad_ref="HEAD", max_repair_attempts=3, history_limit=64, analysis_profile="standard"):
    if analysis_profile not in PROFILES:
        raise ValueError("Choose standard or deep analysis.")
    release_selection = None
    if investigation_type == "release":
        from causaltrace.release_investigation import resolve_releases
        release_selection = resolve_releases(repo, good_ref, bad_ref)
    if not 2 <= history_limit <= 2048:
        raise ValueError("History limit must be between 2 and 2048 commits.")
    selected_runner = committed_runner(repo, directory, test_runner, revision=release_selection[1] if release_selection else "HEAD")
    profile_token = ACTIVE_PROFILE.set(analysis_profile)
    usage_token = MODEL_USAGE.set([])
    history_token = HISTORY_LIMIT.set(history_limit)
    consent_token = MODEL_CONSENT.set(share_with_nebius)
    runner_token = RUNNER.set(selected_runner)
    image_token = IMAGE.set(runner_image)
    preparation_token = PREPARATION.set({"install_dependencies": install_dependencies,
                                        "build_frontend": build_frontend, "frontend_directory": frontend_directory}
                                       if install_dependencies or build_frontend else None)
    try:
        checkpoint()
        if investigation_type == "release":
            from causaltrace.release_investigation import resolve_releases, run_release
            if Path(reports_root).resolve().is_relative_to(Path(repo).resolve()):
                raise ValueError("Reports must be outside the investigated repository.")
            if not 1 <= max_repair_attempts <= settings()["repair_attempts"]:
                raise ValueError("Repair attempts exceed the selected analysis profile limit.")
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
    except InvestigationStopped:
        control = ACTIVE_CONTROL.get()
        by_commit = {row['commit']:row for row in control.results}
        selected = release_selection[1] if release_selection else git(repo, 'rev-parse', 'HEAD')
        rows = [by_commit[commit] for commit in git(repo,'rev-list','--topo-order',selected).splitlines() if commit in by_commit]
        report = {'id':uuid.uuid4().hex, 'project':'CausalTrace', 'repository_id':repository_id,
                  'generated_at':datetime.now(timezone.utc).isoformat(), 'status':'stopped',
                  'reason':'Stopped by you after the active operation finished. Completed commit results are preserved; remaining history and repairs were not completed.',
                  'investigation_type':investigation_type, 'test_runner':selected_runner,
                  'baseline_revision':selected,
                  'baseline':by_commit[selected]['result'] if selected in by_commit else {'status':'not_run','return_code':None,'output':'Stopped before baseline tests completed.'},
                  'experiments':{}, 'repair':None, 'ai_analysis':{'status':'not_run','reason':'Run stopped; no completed AI diagnosis is claimed.'},
                  'regression':{'confirmed':False,'history':rows,'complete':False,'stop_reason':'user_stopped','reason':'Investigation stopped by user. Untested commits remain unclassified.'}}
        from causaltrace.public_demos import PUBLIC_IDS
        if repository_id in PUBLIC_IDS:
            from causaltrace.upstream_projects import provenance
            report['provenance'] = {**provenance(repository_id), 'upstream_revision':selected}
        return persist(report, reports_root)
    finally:
        ACTIVE_PROFILE.reset(profile_token)
        MODEL_USAGE.reset(usage_token)
        HISTORY_LIMIT.reset(history_token)
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
    if investigation_type in {"full", "reproduce", "regression"}:
        history = locate_boundary(repo, directory, limit=HISTORY_LIMIT.get(), baseline=baseline)
        report["regression"] = history
        if investigation_type == "reproduce" or (investigation_type == "regression" and not history["confirmed"]):
            report["status"] = ("execution_error" if baseline.get("execution_error") else
                                "no_failure" if baseline.get("passed") else
                                "completed" if history["complete"] else "inconclusive")
            report["reason"] = history["reason"]
            return persist(report, reports_root)
    if investigation_type == "diagnose":
        report['regression'] = test_complete_history(repo, directory, baseline)
        report["reason"] = "All reachable commits were tested. AI suggestions explain the selected revision; historical results alone do not prove causality."
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
    boundary = report.get("regression") or locate_boundary(repo, directory)
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
