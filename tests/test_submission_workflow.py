"""Real Git/pytest integration on trusted demo fixtures; model calls are mocked.

Production code always uses Docker. The host runner below exists only in tests.
"""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

from causaltrace import build_doctor, demo_setup, pipeline, test_runner, verifier
from causaltrace.api import app


def trusted_fixture_runner(path):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
    result = subprocess.run([sys.executable, "-c", test_runner.PYTEST_SCRIPT], cwd=path,
                            env=env, capture_output=True, text=True, timeout=20)
    return test_runner.parse_result(result.returncode, result.stdout, result.stderr)


def model_response(messages, **kwargs):
    """Simulate a structured model reply; never used by the application."""
    payload = json.loads(messages[1]["content"])
    files = payload["files"]
    source = next(file for file in files if not Path(file["path"]).name.startswith("test_"))
    code = source["content"]
    if source["path"] == "users.py":
        old, new = "normalize_username", "normalize_user"
    elif source["path"] == "config.py":
        old, new = "os.getenv('APP_PORT', '8000')", "int(os.getenv('APP_PORT', '8000'))"
    elif source["path"] == "catalog.py":
        old, new = "    if not items:\n        return {'error': 'not found'}, 404\n", ""
    elif source["path"] == "inventory.py":
        old, new = "- returned", "+ returned"
    elif "calculate_discount" in code:
        old, new = "price +", "price -"
    else:
        old, new = "a - b", "a + b"
    assert old in code
    return json.dumps({
        "category": "Test model response", "summary": "Repair the breaking implementation change.",
        "evidence": [source["path"] + ": implementation disagrees with the unchanged test."],
        "recommended_steps": ["Apply the source repair and rerun tests."],
        "replacements": [{"path": source["path"], "old": old, "new": new}],
    }), "nvidia/nemotron-test-mock"


class WorkflowTests(unittest.TestCase):
    def test_all_six_git_demos_have_verified_boundary_reversal_and_repair(self):
        for repository_id in demo_setup.DEMO_IDS:
            with self.subTest(repository=repository_id), tempfile.TemporaryDirectory() as folder:
                repo = demo_setup.ensure_demo(repository_id)
                original = pipeline.git(repo, "rev-parse", "HEAD")
                with patch.object(verifier, "run_pytest", side_effect=trusted_fixture_runner), \
                     patch.object(build_doctor, "run_pytest", side_effect=trusted_fixture_runner), \
                     patch.object(build_doctor, "complete", side_effect=model_response), \
                     contextlib.redirect_stdout(io.StringIO()):
                    report = pipeline.run_investigation(repo, ".", repository_id, folder)
                self.assertEqual(report["status"], "completed")
                self.assertTrue(report["regression"]["confirmed"])
                self.assertEqual(report["experiments"]["commit_reversal"]["outcome"], "verified")
                self.assertEqual(report["experiments"]["alternative_reversal"]["outcome"], "not_supported")
                self.assertEqual(report["repair"]["verification"]["status"], "verified")
                self.assertEqual(pipeline.git(repo, "rev-parse", "HEAD"), original)
                self.assertEqual(pipeline.git(repo, "status", "--porcelain", "--untracked-files=no"), "")
                self.assertEqual(len(pipeline.git(repo, "worktree", "list", "--porcelain").split("worktree ")) - 1, 1)
                saved = json.loads((Path(folder) / (report["id"] + ".json")).read_text())
                self.assertEqual(saved["repair"]["verification"]["status"], "verified")
                self.assertEqual(saved["repository_id"], repository_id)

    def test_unavailable_model_preserves_causal_evidence(self):
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(verifier, "run_pytest", side_effect=trusted_fixture_runner), \
             patch.object(build_doctor, "complete", side_effect=RuntimeError("No key")), \
             contextlib.redirect_stdout(io.StringIO()):
            report = pipeline.run_investigation(demo_setup.ensure_demo("config"), ".", "config", folder)
        self.assertEqual(report["status"], "partial")
        self.assertEqual(report["ai_analysis"]["status"], "unavailable")
        self.assertEqual(report["experiments"]["commit_reversal"]["outcome"], "verified")
        self.assertIsNone(report["repair"])

    def test_docker_errors_empty_and_skipped_runs_never_verify(self):
        for code, text in [(125, "docker error FAILED"), (0, "0 passed"), (1, "FAILED")]:
            result = test_runner.parse_result(code, text, "")
            self.assertFalse(result["passed"])
            self.assertTrue(result["execution_error"])
        summary = dict(test_ids=["test_x"], passed_ids=[], failed_ids=[],
                       skipped_ids=["test_x"], collection_errors=[])
        result = test_runner.parse_result(0, test_runner.SUMMARY_MARKER + json.dumps(summary), "")
        self.assertFalse(result["passed"])

    def test_paths_and_protected_test_patches(self):
        for path in ["../app.py", "/app.py", ".env", "a//b.py", "a/../b.py", "C:/a.py"]:
            with self.subTest(path=path), self.assertRaises(ValidationError):
                build_doctor.SourceFile(path=path, content="")
        with self.assertRaises(ValidationError):
            build_doctor.BuildRequest(log="error!", files=[{"path": "a.py", "content": ""},
                                                          {"path": "a.py/b.py", "content": ""}])
        for path in ["test_config.py", "conftest.py", "tests/helper.py", "pyproject.toml"]:
            with self.assertRaises(ValueError):
                build_doctor.validate_edits([build_doctor.Replacement(path=path, old="x", new="y")])
        with self.assertRaises(ValueError):
            build_doctor.apply_replacements([build_doctor.SourceFile(path="a.py", content="xx")],
                                            [build_doctor.Replacement(path="a.py", old="x", new="y")])

    def test_api_readiness_and_report_identity(self):
        with TestClient(app) as client, tempfile.TemporaryDirectory() as folder, \
             patch("causaltrace.api.REPORTS_ROOT", Path(folder)):
            self.assertEqual(client.get("/api/health").status_code, 200)
            self.assertEqual(len(client.get("/api/repositories").json()["repositories"]), 6)
            self.assertEqual(client.get("/api/investigation?report_id=../../bad").status_code, 400)
            self.assertEqual(client.get("/api/investigation?report_id=" + "f" * 32).status_code, 404)
            self.assertEqual(client.post("/api/run-investigation", json={"repository_id": "unknown"}).status_code, 400)
            self.assertEqual(client.post("/api/build/analyze", json={"log": "x", "files": []}).status_code, 422)
            with patch("causaltrace.api.docker_status", return_value={"ready": False, "reason": "Docker missing"}):
                self.assertEqual(client.post("/api/run-investigation", json={"repository_id": "config"}).status_code, 503)
            for index, repo in [("a" * 32, "config"), ("b" * 32, "imports")]:
                pipeline.persist({"id": index, "repository_id": repo, "regression": {}}, folder)
            self.assertEqual(client.get("/api/investigation?report_id=" + "a" * 32).json()["repository_id"], "config")
            self.assertEqual(client.get("/api/repositories/imports/timeline?report_id=" + "a" * 32).status_code, 400)

    def test_passing_baseline_is_reported_without_model_or_repair(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(pipeline, "test_commit", return_value={
            "status": "pass", "passed": True, "return_code": 0, "output": "1 passed",
        }), patch.object(pipeline, "investigate") as model:
            report = pipeline.run_investigation(demo_setup.ensure_demo("config"), ".", "config", folder)
            self.assertEqual(report["status"], "no_failure")
            self.assertIsNone(report["repair"])
            model.assert_not_called()

    def test_complete_api_run_returns_its_own_report_graph_and_timeline(self):
        with TestClient(app) as client, tempfile.TemporaryDirectory() as folder, \
             patch("causaltrace.api.REPORTS_ROOT", Path(folder)), \
             patch("causaltrace.api.docker_status", return_value={"ready": True, "reason": "Test override"}), \
             patch.object(verifier, "run_pytest", side_effect=trusted_fixture_runner), \
             patch.object(build_doctor, "run_pytest", side_effect=trusted_fixture_runner), \
             patch.object(build_doctor, "complete", side_effect=model_response), \
             contextlib.redirect_stdout(io.StringIO()):
            response = client.post("/api/run-investigation", json={"repository_id": "config"})
            self.assertEqual(response.status_code, 200, response.text)
            report = response.json()["report"]
            self.assertEqual(report["repair"]["verification"]["status"], "verified")
            report_id = report["id"]
            saved = client.get("/api/investigation?report_id=" + report_id)
            self.assertEqual(saved.json()["id"], report_id)
            graph = client.get("/api/graph?report_id=" + report_id)
            self.assertTrue(any(node["type"] == "repair" for node in graph.json()["nodes"]))
            timeline = client.get("/api/repositories/config/timeline?report_id=" + report_id)
            self.assertEqual([item["test_status"] for item in timeline.json()["commits"]], ["fail", "fail", "pass"])
            self.assertEqual(client.get("/").status_code, 200)


if __name__ == "__main__":
    unittest.main()
