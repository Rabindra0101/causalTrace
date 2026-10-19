# Test runners beyond Python

Choose **Local Git repository**, the project directory relative to its Git root,
and **Test runner**. Automatic detection reads committed manifests, in this order:
`go.mod`, `pom.xml`, `package.json` (Vitest, Jest, otherwise Node), then pytest.
Choose a runner explicitly for mixed projects. The same selection is used at
every revision, before/after reversal, and before/after repair.

| Language | Runner | Evidence |
|---|---|---|
| Python | pytest | Collection and per-test plugin events |
| JavaScript | Node built-in `node --test` | JUnit XML |
| JavaScript / TypeScript | Vitest | JUnit XML |
| JavaScript / TypeScript | Jest | JSON assertion results |
| Java | Maven / Surefire | `target/surefire-reports/TEST-*.xml` |
| Go | `go test -json -count=1 ./...` | Per-test JSON events |

The Node runner does not transpile TypeScript. Use a configured Vitest or Jest
project for TypeScript. Gradle, browser/E2E tools, other npm scripts, desktop GUI
tests and arbitrary custom test commands are not supported by these adapters.
Java uses JDK 21; Go uses 1.26; Node uses 24. Use a custom image if the project
requires a different compatible version or native libraries.

## Build the base image once

From the CausalTrace folder, with Docker Desktop running Linux containers:

```powershell
docker build -f Dockerfile.multilang-runner -t causaltrace-multilang-runner:local .
```

The existing Python image remains separate. Non-Python runners default to the
new multilingual image. Leave **Prepared runner image** blank to use the default.
Readiness checks the default Python image; submitting a run additionally checks
the image selected for that run and reports its name if missing.

## Project dependencies

Test containers run without network, with a read-only repository mount, a
non-root user, resource limits and a disposable writable copy in `/tmp/project`.
They do not read the host's `node_modules`, Maven cache, Go module cache or `.env`.
Install dependencies into a project-specific image **before** investigating.
The image cache must include dependencies needed by all tested revisions.
Missing dependencies, compiler failures without test evidence, skipped-only
suites and zero-test suites cannot verify a repair.

Example Node dependency image, saved as `Dockerfile.causaltrace` in the target
project directory containing `package-lock.json`:

```dockerfile
FROM causaltrace-multilang-runner:local
USER root
WORKDIR /opt
COPY package.json package-lock.json ./
RUN npm ci
USER runner
WORKDIR /workspace
```

Build from that project directory and enter `myproject-test-runner:local` in
**Prepared runner image**:

```powershell
docker build -f Dockerfile.causaltrace -t myproject-test-runner:local .
```

The runner copies `/opt/node_modules` into the disposable project. Vitest/Jest
configuration and any required TypeScript transformer must be committed. The
project, dependency copy, build caches and output must fit the 512 MiB temporary
filesystem; each run has a 60-second timeout and a 1 GiB memory limit.

For Go, prepare `/opt/go-mod` with the project's modules in the image:

```dockerfile
FROM causaltrace-multilang-runner:local
USER root
WORKDIR /opt/dependencies
COPY go.mod go.sum ./
RUN GOMODCACHE=/opt/go-mod go mod download
USER runner
WORKDIR /workspace
```

For Maven, prepare `/opt/maven-repository` with the dependencies and plugins
needed by the actual test phase. A conventional single-module project can use:

```dockerfile
FROM causaltrace-multilang-runner:local
USER root
WORKDIR /opt/dependencies
COPY pom.xml ./
COPY src ./src
RUN mvn -B -Dmaven.repo.local=/opt/maven-repository -Dmaven.test.failure.ignore=true test
RUN chmod -R a+rX /opt/maven-repository
USER runner
WORKDIR /workspace
```

Multi-module projects must also copy their module POMs/source during image
preparation. Maven runs offline; its dependency cache is copied to temporary
writable storage for each test run. Source under `/opt/dependencies` is not used
for the experiment: the committed worktree source is used.

## CLI

```powershell
.\.venv\Scripts\python.exe -m causaltrace.main --repo 'C:\projects\app' --test-dir '.' --test-runner go --runner-image myproject-test-runner:local
```

Full investigations send supported committed source to Nebius and permit patches
only to implementation files. Tests and manifests remain unchanged. Non-Python
repairs are verified in an isolated full committed worktree, preserving project
configuration. Evidence has the same current limits as Python: up to 12 supplied
source files and bounded context. Larger projects may retain Git evidence but
report model analysis unavailable; that is not a verified repair.

FileSync is a Go/Wails application with a TypeScript frontend. At the time this
support was added it had no committed Go test files and no frontend test script.
Choose Go for its backend, but add actual tests to FileSync before expecting
regression evidence. Wails/native desktop dependencies require a prepared image
with the appropriate Linux libraries; selecting Go does not create those tests
or make a Windows desktop build compatible with a Linux container.

## Validation

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
$env:CAUSALTRACE_DOCKER_TESTS = '1'
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_language_runner.py -v
Remove-Item Env:CAUSALTRACE_DOCKER_TESTS
docker build -t causaltrace-framework-fixtures:local tests/fixtures/multilang
$env:CAUSALTRACE_FRAMEWORK_TESTS = '1'
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_language_runner.py -v
Remove-Item Env:CAUSALTRACE_FRAMEWORK_TESTS
```

Adapter tests use structured fixture reports for every supported framework. The
opt-in Docker tests run real dependency-free Node and Go suites and a complete
Node history/reversal/repair workflow with a mocked model. The optional framework
image tests actual TypeScript/Vitest, Jest and Maven/JUnit passing and failing
suites offline. These do not substitute for testing each project's prepared image.

Reporter references: [Vitest](https://main.vitest.dev/guide/reporters),
[Jest](https://jestjs.io/docs/configuration),
[Maven Surefire](https://maven.apache.org/surefire/maven-surefire-plugin/),
[Go test JSON](https://go.dev/cmd/test2json/).
