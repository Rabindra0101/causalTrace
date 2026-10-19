"""Language selection and isolated container driver for non-Python test suites."""
import json
import subprocess
from contextvars import ContextVar
from pathlib import Path

RUNNER = ContextVar("test_runner", default="pytest")
IMAGE = ContextVar("runner_image", default=None)
RUNNERS = ("auto", "pytest", "node", "vitest", "jest", "maven", "go")
MULTILANG_IMAGE = "causaltrace-multilang-runner:local"


def committed_runner(repo, directory, requested):
    if requested not in RUNNERS:
        raise ValueError("Unknown test runner.")
    if requested != "auto":
        return requested
    prefix = Path(directory).as_posix().strip("/")
    prefix = "" if prefix == "." else prefix + "/"
    def content(name):
        result = subprocess.run(["git", "show", "HEAD:" + prefix + name], cwd=repo,
                                capture_output=True, text=True, encoding="utf-8", timeout=15)
        return result.stdout if result.returncode == 0 else None
    if content("go.mod") is not None:
        return "go"
    if content("pom.xml") is not None:
        return "maven"
    package = content("package.json")
    if package is not None:
        data = json.loads(package)
        dependencies = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
        return "vitest" if "vitest" in dependencies else "jest" if "jest" in dependencies else "node"
    return "pytest"


def is_test_path(path):
    path = Path(path)
    name = path.name.lower()
    return (bool({"test", "tests", "__tests__", "__mocks__"} & set(p.lower() for p in path.parts))
            or name.startswith(("test_", "test-", "test.")) or name.endswith(("_test.py", "_test.go", "test.java", "tests.java", "it.java"))
            or any(token in name for token in (".test.", ".spec.")) or name == "conftest.py")


# Executed by Python inside the multilingual image, never on the host.
DRIVER = r'''
import glob, json, os, pathlib, shutil, subprocess, sys, xml.etree.ElementTree as ET
root = pathlib.Path('/tmp/project')
shutil.copytree('/workspace', root, ignore=shutil.ignore_patterns('.git', 'node_modules', 'target', 'dist', '.env', '.env.*'))
os.chdir(root)
runner = sys.argv[1]
env = dict(os.environ, HOME='/tmp', GOCACHE='/tmp/go-build', GOPATH='/tmp/go', GOTOOLCHAIN='local', GOPROXY='off', GOSUMDB='off')
summary = dict(test_ids=[], passed_ids=[], failed_ids=[], skipped_ids=[], collection_errors=[])
def record(identity, outcome):
    summary['test_ids'].append(identity)
    summary[outcome + '_ids'].append(identity)
try:
    if pathlib.Path('/opt/node_modules').is_dir():
        shutil.copytree('/opt/node_modules', root / 'node_modules', symlinks=True)
    if pathlib.Path('/opt/go-mod').is_dir():
        env['GOMODCACHE'] = '/opt/go-mod'
    if runner == 'node':
        command = ['node', '--test', '--test-reporter=junit']
    elif runner == 'vitest':
        command = ['./node_modules/.bin/vitest', 'run', '--reporter=junit', '--outputFile=/tmp/results.xml']
    elif runner == 'jest':
        command = ['./node_modules/.bin/jest', '--runInBand', '--json', '--outputFile=/tmp/results.json']
    elif runner == 'maven':
        if pathlib.Path('/opt/maven-repository').is_dir():
            shutil.copytree('/opt/maven-repository', '/tmp/m2')
        command = ['mvn', '-o', '-B', '-Dmaven.repo.local=/tmp/m2', 'test']
    else:
        command = ['go', 'test', '-json', '-count=1', './...']
    result = subprocess.run(command, env=env, capture_output=True, text=True, errors='replace')
    print(result.stdout)
    print(result.stderr, file=sys.stderr)
    if runner == 'go':
        for line in result.stdout.splitlines():
            try: event = json.loads(line)
            except ValueError: continue
            if event.get('Test') and event.get('Action') in ('pass', 'fail', 'skip'):
                record(event.get('Package', '') + '::' + event['Test'], {'pass':'passed', 'fail':'failed', 'skip':'skipped'}[event['Action']])
    elif runner == 'jest':
        data = json.loads(pathlib.Path('/tmp/results.json').read_text())
        for suite in data.get('testResults', []):
            for test in suite.get('assertionResults', []):
                record(suite['name'].replace(str(root), '') + '::' + test['fullName'], {'passed':'passed', 'failed':'failed'}.get(test['status'], 'skipped'))
    else:
        documents = ([result.stdout] if runner == 'node' else
                     [pathlib.Path('/tmp/results.xml').read_text()] if runner == 'vitest' else
                     [pathlib.Path(p).read_text() for p in glob.glob('**/target/surefire-reports/TEST-*.xml', recursive=True)])
        for document in documents:
            tree = ET.fromstring(document)
            for test in tree.iter('testcase'):
                # Node's JUnit reporter represents suite containers as testcases too.
                if test.find('testsuite') is not None: continue
                identity = test.get('file', '') + '::' + test.get('classname', '') + '::' + test.get('name', '')
                outcome = 'skipped' if test.find('skipped') is not None else 'failed' if test.find('failure') is not None or test.find('error') is not None else 'passed'
                record(identity, outcome)
    print('CAUSALTRACE_TEST_SUMMARY=' + json.dumps(summary))
    sys.exit(result.returncode)
except (OSError, ValueError, ET.ParseError) as error:
    print('Test runner could not produce structured evidence: ' + str(error), file=sys.stderr)
    sys.exit(125)
'''
