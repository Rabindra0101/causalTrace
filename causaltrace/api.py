"""Local CausalTrace API with per-run reports and a connected investigation."""
import json
import logging
import re
import shutil
import subprocess
import threading
from pathlib import Path, PurePosixPath
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from causaltrace.build_api import router as build_router
from causaltrace.demo_setup import DEMO_IDS, demo_catalog, ensure_demo
from causaltrace.public_demos import PUBLIC_IDS, ensure_public_demo
from causaltrace import upstream_projects
from causaltrace.nemotron_client import configuration
from causaltrace.pipeline import run_investigation
from causaltrace.test_runner import docker_status
from causaltrace.language_runner import committed_runner, MULTILANG_IMAGE

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORTS_ROOT = PROJECT_ROOT / "reports"
investigation_lock = threading.Lock()
log = logging.getLogger("causaltrace")
app = FastAPI(title="CausalTrace API", version="0.4.0")
app.include_router(build_router)


class InvestigationRequest(BaseModel):
    repository_id: str = "config"
    repository_path: str | None = None
    test_directory: str = "."
    investigation_type: Literal["full", "diagnose", "release", "regression", "reproduce"] = "full"
    test_runner: Literal["auto", "pytest", "node", "vitest", "jest", "maven", "go"] = "auto"
    runner_image: str | None = Field(default=None, min_length=1, max_length=200, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._/:@-]*$")
    good_ref: str | None = Field(default=None, min_length=1, max_length=200)
    bad_ref: str = Field(default="HEAD", min_length=1, max_length=200)
    max_repair_attempts: int = Field(default=3, ge=1, le=5)
    share_with_nebius: bool = False
    install_dependencies: bool = False
    build_frontend: bool = False
    frontend_directory: str = Field(default="frontend", min_length=1, max_length=200, pattern=r"^[a-zA-Z0-9_./-]+$")


@app.get("/api/health")
def health():
    key, model = configuration()
    return {"application": "CausalTrace", "git_available": bool(shutil.which("git")),
            "nebius_configured": bool(key), "model": model, "docker": docker_status()}


def report_file(report_id=None):
    if report_id is not None and not re.fullmatch(r"[a-f0-9]{32}", report_id):
        raise HTTPException(400, "Invalid investigation ID.")
    path = REPORTS_ROOT / (f"{report_id}.json" if report_id else "latest_investigation.json")
    if not path.is_file():
        raise HTTPException(404, "No report found. Run an investigation first.")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise HTTPException(500, "Unable to read the investigation report.") from error


@app.get("/api/investigation")
def get_investigation(report_id: str | None = None):
    return report_file(report_id)


@app.get("/api/investigation/{report_id}/repair.patch")
def repair_patch(report_id: str):
    report = report_file(report_id)
    path = REPORTS_ROOT / (report_id + ".patch")
    if not report.get("repair_patch_url") or not path.is_file():
        raise HTTPException(404, "No accepted repair patch exists for this report.")
    return FileResponse(path, media_type="text/x-diff", filename="causaltrace-repair-"+report_id[:8]+".patch")


@app.get("/api/graph")
def graph(report_id: str | None = None):
    report = report_file(report_id)
    if "evidence_graph" not in report:
        raise HTTPException(404, "This investigation has no causal graph. Review its status and test output.")
    return report["evidence_graph"]


@app.get("/api/repositories")
def repositories():
    return {"repositories": demo_catalog()}


@app.post("/api/run-investigation")
def run(request: InvestigationRequest):
    if request.repository_id not in (*DEMO_IDS, *PUBLIC_IDS, "local"):
        raise HTTPException(400, "Repository is not configured.")
    if request.repository_id == "local":
        if not request.repository_path or not Path(request.repository_path).is_absolute():
            raise HTTPException(400, "Enter an absolute local Git repository path.")
        repository = Path(request.repository_path).resolve()
        if not repository.is_dir():
            raise HTTPException(400, "Local repository directory does not exist.")
        directory = request.test_directory
        if Path(directory).is_absolute() or not (repository / directory).resolve().is_relative_to(repository):
            raise HTTPException(400, "Test directory must be relative and inside the repository.")
    else:
        repository = None
        directory = "."
    if not investigation_lock.acquire(blocking=False):
        raise HTTPException(409, "An investigation is already running.")
    try:
        repository = repository if repository is not None else ensure_demo(request.repository_id)
        runner = upstream_projects.profile(request.repository_id)["runner"] if request.repository_id in PUBLIC_IDS else request.test_runner
        image = request.runner_image or (upstream_projects.profile(request.repository_id)["image"] if request.repository_id in PUBLIC_IDS else None)
        selected_revision = "HEAD"
        if request.investigation_type == "release":
            from causaltrace.release_investigation import resolve_releases
            _, selected_revision, _ = resolve_releases(repository, request.good_ref, request.bad_ref)
        selected_runner = committed_runner(repository, directory, runner, revision=selected_revision)
        if request.install_dependencies or request.build_frontend:
            if selected_runner == "pytest":
                raise HTTPException(400, "Automatic project preparation currently supports non-Python runners. Use a prepared image for Python.")
            if ".." in PurePosixPath(request.frontend_directory).parts or PurePosixPath(request.frontend_directory).is_absolute():
                raise HTTPException(400, "Frontend directory must be relative and inside the project.")
        docker = (docker_status(image or MULTILANG_IMAGE) if selected_runner != "pytest" or image
                  else docker_status())
        if not docker["ready"]:
            raise HTTPException(503, docker["reason"])
        report = run_investigation(repository, directory, request.repository_id, REPORTS_ROOT,
                                   investigation_type=request.investigation_type,
                                   test_runner=selected_runner, runner_image=image,
                                   share_with_nebius=request.share_with_nebius,
                                   good_ref=request.good_ref, bad_ref=request.bad_ref, max_repair_attempts=request.max_repair_attempts,
                                   install_dependencies=request.install_dependencies,
                                   build_frontend=request.build_frontend, frontend_directory=request.frontend_directory)
        return {"status": report["status"], "report": report}
    except HTTPException:
        raise
    except (ValueError, RuntimeError) as error:
        raise HTTPException(400, str(error)) from error
    except (OSError, subprocess.SubprocessError) as error:
        log.exception("Git investigation failed")
        raise HTTPException(500, "Git investigation failed. Check Git installation and server logs.") from error
    finally:
        investigation_lock.release()


@app.get("/api/repositories/{repository_id}/timeline")
def timeline(repository_id: str, report_id: str | None = None):
    if repository_id not in (*DEMO_IDS, *PUBLIC_IDS):
        raise HTTPException(404, "Repository is not configured.")
    report = report_file(report_id) if report_id else None
    if report and report["repository_id"] != repository_id:
        raise HTTPException(400, "Report belongs to a different repository.")
    tested = {row["commit"]: row["status"] for row in (report or {}).get("regression", {}).get("history", [])}
    try:
        legacy_replay = report and repository_id in PUBLIC_IDS and report.get("provenance", {}).get("history_type") != "upstream"
        repo = ensure_public_demo(repository_id) if legacy_replay else ensure_demo(repository_id)
        revision = report["baseline_revision"] if report else "HEAD"
        result = subprocess.run(
            ["git", "log", "--first-parent", "-16", "--format=%H%x1f%h%x1f%s%x1f%aI", revision],
            cwd=repo, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=15, check=True,
        )
    except (RuntimeError, OSError, subprocess.SubprocessError) as error:
        raise HTTPException(500, "Unable to load demo Git history.") from error
    commits = []
    for line in result.stdout.splitlines():
        fields = line.split("\x1f", 3)
        if len(fields) == 4:
            commit, short, message, date = fields
            commits.append({"hash": commit, "short_hash": short, "message": message,
                            "date": date, "test_status": tested.get(commit, "not_tested")})
    history_type = ("upstream" if repository_id in PUBLIC_IDS and not (report and report.get("provenance", {}).get("history_type") != "upstream") else "synthetic")
    return {"repository_id": repository_id, "history_type": history_type, "commits": commits}


# After npm run build, one backend process can serve the production frontend too.
dist = PROJECT_ROOT / "frontend" / "dist"
if dist.is_dir():
    app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
else:
    @app.get("/")
    def home():
        return {"application": "CausalTrace", "status": "running",
                "frontend": "Run npm run dev in frontend, or npm run build and restart this API."}
