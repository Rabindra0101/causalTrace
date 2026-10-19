"""Adapter evidence tests plus opt-in real, network-isolated Docker checks."""
import contextlib
import io
import json
import os
import subprocess
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from causaltrace import build_doctor, demo_setup, language_runner, pipeline, test_runner


class LanguageRunnerTests(unittest.TestCase):
    def run_driver(self, runner, code, stdout="", artifact=None):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "source"
            source.mkdir()
            project = Path(folder) / "project"
            script = language_runner.DRIVER.replace("'/tmp/project'", repr(str(project)))
            script = script.replace("'/workspace'", repr(str(source)))
            script = script.replace("'/tmp/results", repr(str(Path(folder) / "results"))[:-1])
            if artifact is not None:
                suffix = ".json" if runner == "jest" else ".xml"
                (Path(folder) / ("results" + suffix)).write_text(artifact, encoding="utf-8")
            if runner == "maven" and artifact is not None:
                # Driver copies this into the disposable project before executing Maven.
                report = source / "module" / "target" / "surefire-reports"
                report.mkdir(parents=True)
                (report / "TEST-example.xml").write_text(artifact, encoding="utf-8")
                # Real runner excludes target to prevent stale reports; inject fresh output at execution.
                def execute(*args, **kwargs):
                    target = project / "target" / "surefire-reports"
                    target.mkdir(parents=True)
                    (target / "TEST-example.xml").write_text(artifact, encoding="utf-8")
                    return subprocess.CompletedProcess([], code, stdout, "")
            else:
                execute = lambda *a, **kw: subprocess.CompletedProcess([], code, stdout, "")
            previous = Path.cwd()
            output = io.StringIO()
            try:
                with patch("sys.argv", ["driver", runner]), patch("subprocess.run", side_effect=execute), \
                     contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as stopped:
                        exec(compile(script, "driver", "exec"), {})
                return test_runner.parse_result(stopped.exception.code, output.getvalue(), "")
            finally:
                os.chdir(previous)

    def test_junit_adapters_require_real_testcases_and_preserve_failures(self):
        for runner in ("node", "vitest", "maven"):
            for code, body, status in [(0, "", "pass"), (1, "<failure/>", "fail"),
                                       (0, "<skipped/>", "error")]:
                with self.subTest(runner=runner, status=status):
                    xml = '<testsuites><testsuite><testcase classname="Example" name="adds">' + body + '</testcase></testsuite></testsuites>'
                    result = self.run_driver(runner, code, xml if runner == "node" else "", xml)
                    self.assertEqual(result["status"], status)
            empty = '<testsuites><testsuite tests="0"/></testsuites>'
            self.assertFalse(self.run_driver(runner, 0, empty if runner == "node" else "", empty)["passed"])

    def test_go_and_jest_evidence_and_build_errors(self):
        for action, code, status in [("pass", 0, "pass"), ("fail", 1, "fail"), ("skip", 0, "error")]:
            result = self.run_driver("go", code, json.dumps({"Package": "example", "Test": "TestAdd", "Action": action}))
            self.assertEqual(result["status"], status)
        self.assertTrue(self.run_driver("go", 1, json.dumps({"Package": "example", "Action": "fail"}))["execution_error"])
        for state, code, status in [("passed", 0, "pass"), ("failed", 1, "fail"), ("pending", 0, "error")]:
            data = json.dumps({"testResults": [{"name": "add.test.ts", "assertionResults": [{"fullName": "adds", "status": state}]}]})
            self.assertEqual(self.run_driver("jest", code, artifact=data)["status"], status)

    def test_source_repairs_cannot_change_tests_or_manifests(self):
        for path in ("add.test.ts", "add.spec.js", "src/test/java/Add.java", "AddTest.java", "add_test.go", "pom.xml", "go.mod", "package.json"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                build_doctor.validate_edits([build_doctor.Replacement(path=path, old="a", new="b")])
        for path in ("src/add.ts", "add.js", "Add.java", "add.go"):
            build_doctor.SourceFile(path=path, content="source")
            build_doctor.validate_edits([build_doctor.Replacement(path=path, old="a", new="b")])

    def test_auto_detection_reads_committed_manifest_and_context_is_restored(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            demo_setup.git(root, "init", "-q")
            (root / "package.json").write_text('{"devDependencies":{"vitest":"*"}}')
            demo_setup.git(root, "add", ".")
            demo_setup.git(root, "commit", "-qm", "Manifest")
            (root / "package.json").write_text('{"devDependencies":{"jest":"*"}}')
            self.assertEqual(language_runner.committed_runner(root, ".", "auto"), "vitest")
            self.assertEqual(language_runner.committed_runner(root, ".", "go"), "go")
            with patch.object(pipeline, "_run_investigation", side_effect=ValueError("failure")):
                with self.assertRaises(ValueError):
                    pipeline.run_investigation(root, ".", "local", root, test_runner="go")
            self.assertEqual(language_runner.RUNNER.get(), "pytest")
            self.assertIsNone(language_runner.IMAGE.get())

    @unittest.skipUnless(os.getenv("CAUSALTRACE_DOCKER_TESTS") == "1", "Opt-in real multilingual Docker checks")
    def test_real_node_git_history_reversal_and_full_worktree_repair(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "repo"
            root.mkdir()
            demo_setup.git(root, "init", "-q")
            (root / "package.json").write_text('{"name":"example","version":"1.0.0"}')
            (root / "add.cjs").write_text("exports.add = (a,b) => a + b;\n")
            (root / "add.test.cjs").write_text("const {test}=require('node:test'); const assert=require('node:assert/strict'); const {add}=require('./add.cjs'); test('adds',()=>assert.equal(add(2,3),5));\n")
            demo_setup.git(root, "add", ".")
            demo_setup.git(root, "commit", "-qm", "Passing tests")
            (root / "add.cjs").write_text("exports.add = (a,b) => a - b;\n")
            demo_setup.git(root, "add", ".")
            demo_setup.git(root, "commit", "-qm", "Break addition")
            (root / "notes.txt").write_text("Unrelated documentation")
            demo_setup.git(root, "add", ".")
            demo_setup.git(root, "commit", "-qm", "Documentation")
            original_head = demo_setup.git(root, "rev-parse", "HEAD")
            reply = json.dumps({"category":"Arithmetic", "summary":"Subtraction replaced addition.",
                "evidence":["add.cjs: subtracts operands"], "recommended_steps":["Restore addition"],
                "replacements":[{"path":"add.cjs", "old":"a - b", "new":"a + b"}]})
            with patch.object(build_doctor, "complete", return_value=(reply, "mock-model")), \
                 contextlib.redirect_stdout(io.StringIO()):
                report = pipeline.run_investigation(root, ".", "local", Path(folder) / "reports", share_with_nebius=True)
            self.assertEqual(report["test_runner"], "node")
            self.assertEqual(report["experiments"]["commit_reversal"]["outcome"], "verified")
            self.assertEqual(report["experiments"]["alternative_reversal"]["outcome"], "not_supported")
            self.assertEqual(report["repair"]["verification"]["status"], "verified", report)
            self.assertEqual(demo_setup.git(root, "rev-parse", "HEAD"), original_head)
            self.assertEqual(demo_setup.git(root, "status", "--porcelain"), "")
            self.assertIn("a - b", (root / "add.cjs").read_text())

    @unittest.skipUnless(os.getenv("CAUSALTRACE_DOCKER_TESTS") == "1", "Opt-in real multilingual Docker checks")
    def test_real_node_and_go_pass_fail_no_tests_and_readonly_source(self):
        fixtures = {
            "node": {"add.cjs": "exports.add = (a,b) => a + b;\n", "add.test.cjs": "const {test}=require('node:test'); const assert=require('node:assert/strict'); const {add}=require('./add.cjs'); test('adds',()=>assert.equal(add(2,3),5));\n"},
            "go": {"go.mod": "module example\n\ngo 1.26\n", "add.go": "package example\nfunc Add(a,b int) int { return a + b }\n", "add_test.go": 'package example\nimport "testing"\nfunc TestAdd(t *testing.T) { if Add(2,3)!=5 {t.Fatal("wrong sum")} }\n'},
        }
        for runner, files in fixtures.items():
            token = language_runner.RUNNER.set(runner)
            try:
                with tempfile.TemporaryDirectory() as folder:
                    root = Path(folder)
                    for path, content in files.items():
                        (root / path).write_text(content, encoding="utf-8")
                    passing = test_runner.run_pytest(root)
                    self.assertTrue(passing["passed"], passing["output"])
                    source = root / ("add.cjs" if runner == "node" else "add.go")
                    source.write_text(source.read_text().replace("a + b", "a - b"))
                    failing = test_runner.run_pytest(root)
                    self.assertTrue(test_runner.is_failure(failing), failing["output"])
                    self.assertTrue(test_runner.same_tests(failing, passing))
                    self.assertIn("a - b", source.read_text())
                    (root / ("add.test.cjs" if runner == "node" else "add_test.go")).unlink()
                    self.assertFalse(test_runner.run_pytest(root)["passed"])
            finally:
                language_runner.RUNNER.reset(token)

    @unittest.skipUnless(os.getenv("CAUSALTRACE_FRAMEWORK_TESTS") == "1", "Requires prepared framework fixture image")
    def test_real_vitest_jest_and_maven_pass_fail_and_unchanged_tests(self):
        image_token = language_runner.IMAGE.set("causaltrace-framework-fixtures:local")
        try:
            for runner in ("vitest", "jest", "maven"):
                token = language_runner.RUNNER.set(runner)
                try:
                    with tempfile.TemporaryDirectory() as folder:
                        root = Path(folder)
                        if runner == "maven":
                            shutil.copytree(Path(__file__).parent / "fixtures" / "multilang", root, dirs_exist_ok=True)
                            source = root / "src/main/java/Add.java"
                        else:
                            (root / "package.json").write_text('{"name":"fixture","version":"1.0.0"}')
                            if runner == "vitest":
                                (root / "add.test.ts").write_text("import {test, expect} from 'vitest'; import {add} from './add'; test('adds',()=>expect(add(2,3)).toBe(5));\n")
                                source = root / "add.ts"
                                source.write_text("export const add = (a:number,b:number) => a + b;\n")
                            else:
                                (root / "add.test.js").write_text("const {add}=require('./add'); test('adds',()=>expect(add(2,3)).toBe(5));\n")
                                source = root / "add.js"
                                source.write_text("exports.add = (a,b) => a + b;\n")
                        passing = test_runner.run_pytest(root)
                        self.assertTrue(passing["passed"], passing["output"])
                        source.write_text(source.read_text().replace("a + b", "a - b"))
                        failing = test_runner.run_pytest(root)
                        self.assertTrue(test_runner.is_failure(failing), failing["output"])
                        self.assertTrue(test_runner.same_tests(failing, passing))
                finally:
                    language_runner.RUNNER.reset(token)
        finally:
            language_runner.IMAGE.reset(image_token)
