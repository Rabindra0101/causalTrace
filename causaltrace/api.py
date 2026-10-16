
import json
import subprocess
import sys
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


app = FastAPI(
    title="CausalTrace API",
    description="Evidence-driven software regression investigation API",
    version="0.2.0",
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORT_PATH = PROJECT_ROOT / "reports" / "latest_investigation.json"

# Only explicitly configured repositories may be investigated.
ALLOWED_REPOSITORIES = {
    "calculator": {
        "name": "Calculator Demo",
        "repo": PROJECT_ROOT,
        "test_dir": "demo/sample_repo",
    },
    "inventory": {
        "name": "Inventory Demo",
        "repo": PROJECT_ROOT.parent / "inventory-regression-demo",
        "test_dir": ".",
    },
}


class InvestigationRequest(BaseModel):
    repository_id: str = "calculator"


# Prevent simultaneous investigations.
investigation_lock = threading.Lock()


@app.get("/")
def home():
    return {
        "application": "CausalTrace",
        "status": "running",
    }


@app.get("/api/investigation")
def get_investigation():
    """Return the latest saved investigation report."""

    if not REPORT_PATH.is_file():
        raise HTTPException(
            status_code=404,
            detail="No investigation report found. Run CausalTrace first.",
        )

    try:
        with REPORT_PATH.open("r", encoding="utf-8") as file:
            report = json.load(file)

    except (OSError, json.JSONDecodeError) as error:
        raise HTTPException(
            status_code=500,
            detail="Unable to read the investigation report.",
        ) from error

    return report


@app.get("/api/graph")
def get_evidence_graph():
    """Return the Evidence Graph from the latest report."""

    report = get_investigation()

    if "evidence_graph" not in report:
        raise HTTPException(
            status_code=404,
            detail="Evidence Graph is missing from the report.",
        )

    return report["evidence_graph"]


@app.get("/api/repositories")
def get_repositories():
    """Return repositories available for investigation."""

    return {
        "repositories": [
            {
                "id": repository_id,
                "name": config["name"],
            }
            for repository_id, config in ALLOWED_REPOSITORIES.items()
        ]
    }


@app.post("/api/run-investigation")
def run_investigation(request: InvestigationRequest | None = None):
    """
    Run an allowlisted investigation.

    The API does not accept arbitrary repository paths
    or shell commands.
    """

    repository_id = (
        request.repository_id if request is not None else "calculator"
    )

    if repository_id not in ALLOWED_REPOSITORIES:
        raise HTTPException(
            status_code=400,
            detail="Repository is not in the allowed list.",
        )

    repository = ALLOWED_REPOSITORIES[repository_id]

    if not investigation_lock.acquire(blocking=False):
        raise HTTPException(
            status_code=409,
            detail="An investigation is already running.",
        )

    try:
        # Track the previous report to detect stale results.
        previous_report_time = (
            REPORT_PATH.stat().st_mtime_ns
            if REPORT_PATH.is_file()
            else None
        )

        result = subprocess.run(
            [
                sys.executable,
                "-X",
                "utf8",
                "-m",
                "causaltrace.main",
                "--repo",
                str(repository["repo"]),
                "--test-dir",
                repository["test_dir"],
            ],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
            check=False,
        )

        if result.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail="Investigation failed. Check server logs for details.",
            )

        if not REPORT_PATH.is_file():
            raise HTTPException(
                status_code=500,
                detail="Investigation finished without generating a report.",
            )

        # Ensure this investigation generated a fresh report.
        current_report_time = REPORT_PATH.stat().st_mtime_ns

        if (
            previous_report_time is not None
            and current_report_time == previous_report_time
        ):
            raise HTTPException(
                status_code=500,
                detail="Investigation did not generate a fresh report.",
            )

        return {
            "status": "completed",
            "message": "Investigation process finished.",
            "return_code": result.returncode,
        }

    except subprocess.TimeoutExpired as error:
        raise HTTPException(
            status_code=504,
            detail="Investigation exceeded the 180-second timeout.",
        ) from error

    except OSError as error:
        raise HTTPException(
            status_code=500,
            detail="Unable to start the investigation process.",
        ) from error

    finally:
        investigation_lock.release()
