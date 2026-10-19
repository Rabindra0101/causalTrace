"""Local CausalTrace API with per-run reports and a connected investigation."""
import json
import logging
import re
import shutil
import subprocess
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from causaltrace.build_api import router as build_router
from causaltrace.demo_setup import DEMO_IDS, demo_catalog, ensure_demo
from causaltrace.nemotron_client import configuration
from causaltrace.pipeline import run_investigation
from causaltrace.test_runner import docker_status

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORTS_ROOT = PROJECT_ROOT / "reports"
investigation_lock = threading.Lock()
log = logging.getLogger("causaltrace")
app = FastAPI(title="CausalTrace API", version="0.4.0")
app.include_router(build_router)


class InvestigationRequest(BaseModel):
    repository_id: str = "config"


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
    if request.repository_id not in DEMO_IDS:
        raise HTTPException(400, "Repository is not configured.")
    if not investigation_lock.acquire(blocking=False):
        raise HTTPException(409, "An investigation is already running.")
    try:
        docker = docker_status()
        if not docker["ready"]:
            raise HTTPException(503, docker["reason"])
        repository = ensure_demo(request.repository_id)
        report = run_investigation(repository, ".", request.repository_id, REPORTS_ROOT)
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
    if repository_id not in DEMO_IDS:
        raise HTTPException(404, "Repository is not configured.")
    report = report_file(report_id) if report_id else None
    if report and report["repository_id"] != repository_id:
        raise HTTPException(400, "Report belongs to a different repository.")
    tested = {row["commit"]: row["status"] for row in (report or {}).get("regression", {}).get("history", [])}
    try:
        repo = ensure_demo(repository_id)
        result = subprocess.run(
            ["git", "log", "-16", "--format=%H%x1f%h%x1f%s%x1f%aI"],
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
    return {"repository_id": repository_id, "commits": commits}


# After npm run build, one backend process can serve the production frontend too.
dist = PROJECT_ROOT / "frontend" / "dist"
if dist.is_dir():
    app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
else:
    @app.get("/")
    def home():
        return {"application": "CausalTrace", "status": "running",
                "frontend": "Run npm run dev in frontend, or npm run build and restart this API."}
