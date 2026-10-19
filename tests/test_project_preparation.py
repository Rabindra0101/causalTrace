import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from causaltrace.api import app

from causaltrace import language_runner, test_runner


class PreparationTests(unittest.TestCase):
    def test_api_forwards_preparation_and_rejects_outside_build_directory(self):
        with tempfile.TemporaryDirectory() as folder, TestClient(app) as client, \
             patch('causaltrace.api.committed_runner', return_value='go'), \
             patch('causaltrace.api.docker_status', return_value={'ready': True}), \
             patch('causaltrace.api.run_investigation', return_value={'status': 'completed'}) as run:
            request = dict(repository_id='local', repository_path=folder, test_runner='go',
                           install_dependencies=True, build_frontend=True, frontend_directory='frontend')
            self.assertEqual(client.post('/api/run-investigation', json=request).status_code, 200)
            self.assertTrue(run.call_args.kwargs['install_dependencies'])
            self.assertTrue(run.call_args.kwargs['build_frontend'])
            for directory in ('../outside', '/outside', 'C:/outside'):
                response = client.post('/api/run-investigation', json={**request, 'frontend_directory': directory})
                self.assertIn(response.status_code, (400, 422))

    @unittest.skipUnless(os.getenv('CAUSALTRACE_WAILS_TESTS') == '1', 'Opt-in native GTK/WebKit compilation fixture')
    def test_native_gtk_webkit_runner_compiles_without_a_desktop(self):
        runner_token = language_runner.RUNNER.set('go')
        image_token = language_runner.IMAGE.set('causaltrace-wails-runner:local')
        try:
            with tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                (root / 'go.mod').write_text('module fixture\n\ngo 1.26\n')
                (root / 'native.go').write_text('package fixture\n/*\n#cgo pkg-config: gtk+-3.0 webkit2gtk-4.1\n#include <gtk/gtk.h>\n#include <webkit2/webkit2.h>\n*/\nimport "C"\nfunc Linked() bool {return C.gtk_get_major_version()>=3 && C.webkit_get_major_version()>=2}\n')
                (root / 'native_test.go').write_text('package fixture\nimport "testing"\nfunc TestLinked(t *testing.T) {if !Linked() {t.Fatal("native library unavailable")}}\n')
                result = test_runner.run_pytest(root)
                self.assertTrue(result['passed'], result['output'])
        finally:
            language_runner.IMAGE.reset(image_token)
            language_runner.RUNNER.reset(runner_token)

    def test_go_setup_errors_have_distinct_actions(self):
        result = test_runner.execution_error('module lookup disabled by GOPROXY=off\npattern all:frontend/dist: no matching files found\n[no test files]', 1)
        codes = {issue['code'] for issue in test_runner.setup_issues(result)}
        self.assertEqual(codes, {'missing_dependencies', 'missing_build_assets', 'no_tests'})
        self.assertEqual(test_runner.setup_issues({'status': 'fail', 'execution_error': False}), [])

    def test_preparation_network_is_opt_in_tests_are_offline_and_volume_is_cleaned(self):
        for allow_network in (False, True):
            with self.subTest(allow_network=allow_network), tempfile.TemporaryDirectory() as folder:
                runner_token = language_runner.RUNNER.set('go')
                preparation_token = language_runner.PREPARATION.set({'install_dependencies': allow_network,
                    'build_frontend': True, 'frontend_directory': 'frontend'})
                calls = []
                def execute(command, **kwargs):
                    calls.append(command)
                    if language_runner.PREPARE_DRIVER in command:
                        return subprocess.CompletedProcess(command, 0, 'Prepared assets', '')
                    if language_runner.DRIVER in command:
                        summary = dict(test_ids=['TestAdd'], passed_ids=['TestAdd'], failed_ids=[], skipped_ids=[], collection_errors=[])
                        return subprocess.CompletedProcess(command, 0, test_runner.SUMMARY_MARKER + json.dumps(summary), '')
                    return subprocess.CompletedProcess(command, 0, '', '')
                try:
                    with patch('shutil.which', return_value='docker'), patch('subprocess.run', side_effect=execute):
                        result = test_runner.run_pytest(Path(folder))
                    self.assertTrue(result['passed'])
                    prep = next(c for c in calls if language_runner.PREPARE_DRIVER in c)
                    tests = next(c for c in calls if language_runner.DRIVER in c)
                    self.assertEqual(prep[prep.index('--network') + 1], 'bridge' if allow_network else 'none')
                    self.assertEqual(tests[tests.index('--network') + 1], 'none')
                    self.assertIn('--prepared', tests)
                    self.assertTrue(any(c[:3] == ['docker', 'volume', 'rm'] for c in calls))
                finally:
                    language_runner.PREPARATION.reset(preparation_token)
                    language_runner.RUNNER.reset(runner_token)

    def test_failed_preparation_never_starts_tests(self):
        with tempfile.TemporaryDirectory() as folder:
            runner_token = language_runner.RUNNER.set('go')
            preparation_token = language_runner.PREPARATION.set({'install_dependencies': True, 'build_frontend': False, 'frontend_directory': 'frontend'})
            calls = []
            def execute(command, **kwargs):
                calls.append(command)
                return subprocess.CompletedProcess(command, 1 if language_runner.PREPARE_DRIVER in command else 0, '', 'download failed')
            try:
                with patch('shutil.which', return_value='docker'), patch('subprocess.run', side_effect=execute):
                    result = test_runner.run_pytest(Path(folder))
                self.assertTrue(result['execution_error'])
                self.assertEqual(result['preparation']['status'], 'failed')
                self.assertFalse(any(language_runner.DRIVER in c for c in calls))
                self.assertEqual(test_runner.setup_issues(result)[0]['code'], 'preparation_failed')
            finally:
                language_runner.PREPARATION.reset(preparation_token)
                language_runner.RUNNER.reset(runner_token)

    @unittest.skipUnless(os.getenv('CAUSALTRACE_PREPARATION_TESTS') == '1', 'Opt-in live Docker project preparation')
    def test_real_go_embedded_assets_built_in_copy_and_tested_offline(self):
        runner_token = language_runner.RUNNER.set('go')
        preparation_token = language_runner.PREPARATION.set({'install_dependencies': True, 'build_frontend': True, 'frontend_directory': 'frontend'})
        try:
            with tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                (root / 'frontend').mkdir()
                files = {
                    'go.mod': 'module fixture\n\ngo 1.26\n',
                    'assets.go': 'package fixture\nimport "embed"\n//go:embed all:frontend/dist\nvar Assets embed.FS\n',
                    'assets_test.go': 'package fixture\nimport "testing"\nfunc TestAssets(t *testing.T) { b,e:=Assets.ReadFile("frontend/dist/index.html"); if e!=nil || string(b)!="built" {t.Fatal("assets missing")} }\n',
                    'frontend/package.json': '{"name":"fixture","version":"1.0.0","scripts":{"build":"node build.cjs"}}',
                    'frontend/package-lock.json': '{"name":"fixture","version":"1.0.0","lockfileVersion":3,"packages":{"":{"name":"fixture","version":"1.0.0"}}}',
                    'frontend/build.cjs': "const fs=require('node:fs'); if(fs.existsSync('../.env')) throw Error('Environment file copied'); fs.mkdirSync('dist',{recursive:true}); fs.writeFileSync('dist/index.html','built');\n",
                    '.env': 'PRIVATE_FIXTURE=must-not-be-copied\n',
                }
                for name, content in files.items():
                    (root / name).write_text(content, encoding='utf-8')
                result = test_runner.run_pytest(root)
                self.assertTrue(result['passed'], result['output'])
                self.assertEqual(result['preparation']['status'], 'completed')
                self.assertFalse((root / 'frontend/dist').exists())
                for name, content in files.items():
                    self.assertEqual((root / name).read_text(), content)
                (root / 'frontend/build.cjs').write_text("require('node:fs').writeFileSync('../assets_test.go','package fixture');\n")
                failed = test_runner.run_pytest(root)
                self.assertTrue(failed['execution_error'])
                self.assertIn('changed committed source', failed['output'])
                self.assertEqual((root / 'assets_test.go').read_text(), files['assets_test.go'])
        finally:
            language_runner.PREPARATION.reset(preparation_token)
            language_runner.RUNNER.reset(runner_token)

    @unittest.skipUnless(os.getenv('CAUSALTRACE_PREPARATION_TESTS') == '1', 'Opt-in dependency download fixture')
    def test_real_go_download_then_offline_test_and_failure_cleanup(self):
        runner_token = language_runner.RUNNER.set('go')
        preparation_token = language_runner.PREPARATION.set({'install_dependencies': True, 'build_frontend': False, 'frontend_directory': 'frontend'})
        try:
            with tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                (root / 'go.mod').write_text('module fixture\n\ngo 1.26\n\nrequire github.com/google/uuid v1.6.0\n')
                (root / 'id.go').write_text('package fixture\nimport "github.com/google/uuid"\nfunc ID() string {return uuid.NewString()}\n')
                (root / 'id_test.go').write_text('package fixture\nimport ("testing"; "net")\nfunc TestOffline(t *testing.T) {if len(ID())!=36 {t.Fatal("uuid")}; interfaces,_:=net.Interfaces(); for _,i:=range interfaces {if i.Flags&net.FlagLoopback==0 {t.Fatal("test network enabled")}}}\n')
                result = test_runner.run_pytest(root)
                self.assertTrue(result['passed'], result.get('preparation', {}).get('output', '') + result['output'])
                self.assertFalse((root / 'go.sum').exists())
                (root / 'go.mod').write_text('invalid manifest\n')
                failed = test_runner.run_pytest(root)
                self.assertTrue(failed['execution_error'])
                self.assertEqual(failed['preparation']['status'], 'failed')
                volumes = subprocess.run(['docker','volume','ls','--filter','label=causaltrace.temporary=true','--format','{{.Name}}'], capture_output=True, text=True, timeout=15)
                self.assertEqual(volumes.stdout.strip(), '')
        finally:
            language_runner.PREPARATION.reset(preparation_token)
            language_runner.RUNNER.reset(runner_token)
