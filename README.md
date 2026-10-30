# CausalTrace

Find the release change that broke your application, explain the evidence with
NVIDIA Nemotron on Nebius Token Factory, and test proposed code repairs.

CausalTrace combines Git history, isolated Docker tests, reversal experiments and
a bounded coding-agent loop. It keeps the original repository unchanged and
produces a report and a cumulative repair patch for review.

## Quick start - Windows PowerShell

Run from the CausalTrace repository root. Requirements: Python 3.11+, Git 2.28+,
Node.js 22.12+ and Docker Desktop using Linux containers.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path -LiteralPath .env)) { Copy-Item .env.example .env }
```

Edit `.env` to set your Nebius Token Factory API key. Preserve existing values.
The default model is `nvidia/nemotron-3-super-120b-a12b`; access depends on your
account. Never commit or share your `.env` file.

Prepare the default Python runner and frontend:

```powershell
docker build -f Dockerfile.test-runner -t causaltrace-test-runner:local .
if ($LASTEXITCODE -ne 0) { throw 'Docker runner build failed' }
Push-Location frontend
npm.cmd ci
npm.cmd run build
Pop-Location
.\.venv\Scripts\python.exe -m uvicorn causaltrace.api:app --host 127.0.0.1 --port 8000 --no-access-log
```

While an investigation runs, **Pause**, **Resume** and **Stop** appear beside
the Run button. Pause freezes active child processes and Docker containers;
Resume continues the same operation without restarting it. Paused time does not
consume the subprocess timeout. Stop terminates active work, cleans up temporary
resources and saves completed commit results in a partial report.
Nebius generation cannot be frozen remotely: while paused, its response is held
locally until Resume. Stop cancels the local request and closes its connection;
provider computation or billing may continue. No subsequent analysis or repair
starts while paused or stopped. A stopped run does not claim a completed diagnosis
or verified repair. Process termination and resource cleanup can take a few seconds.
These controls require the same running backend process; restarting it ends the run.
Refreshing or reopening the page reconnects to an active investigation and restores
its controls. The page loads the saved report when that investigation finishes.
Only one investigation runs at a time; additional run requests return HTTP 409.
Readiness cards show a check mark for available checks and a cross for missing or failed components.
If the backend is unreachable, all three checks show unavailable rather than stale
green results. Git readiness checks installation; a repository-operation failure
is shown separately on the Git card.

All repository investigations use independent temporary snapshots, including
bundled and public upstream repositories. Git worktree registration and cleanup
stay outside the source cache, avoiding writes to OneDrive-hosted Git metadata.

Open **http://127.0.0.1:8000**. The backend serves `frontend/dist` after a build;
restart it when that build changes. For frontend development, run `npm.cmd run dev`
from `frontend` in a second terminal. Vite forwards API requests to port 8000.
PowerShell commands above are separate lines; do not append a backslash to the port.

For macOS/Linux, create/activate a Python virtual environment, use its `python`,
and use `npm` instead of `npm.cmd`.

For a single-command Windows setup and launch, use:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1 -Setup
# Subsequent launches:
.\scripts\start.ps1
```

The launcher preserves existing environment files. Configure your key locally
before a model-assisted run. Dependency installation requires network access.
Routine HTTP access logs are disabled by default, so status polling does not
fill the terminal. Application errors remain visible. Use
`.\scripts\start.ps1 -AccessLog` to enable request logs for debugging.
Restart an already-running backend to apply this launcher change.

## Try a measured demo

Choose **Broken package import** or **Configuration type mismatch**, select
**Find the breaking change**, and enable **Share selected evidence with
Nebius for this run**. The app should reproduce the failure, test an adjacent
passing/failing boundary, compare suspected and unrelated reversals, and request
a proposed repair. A repair is verified only after unchanged tests pass.

Six small bundled demos are synthetic Git histories created from source recipes;
their commits are labeled generated. Four additional selections use complete
original public repositories with authentic Git IDs/dates. Their original suites
currently reproduce no failure at the pinned revisions; the app reports that
honestly. See [PUBLIC_DEMOS.md](PUBLIC_DEMOS.md) for upstream profiles, historical
runner images and measured outcomes.

## Investigate your application

Select **Local Git repository**, enter its absolute path, and choose the directory
containing its committed manifest, source and tests. Uncommitted work is ignored;
no stash or commit is required to run. The original checkout, `.env`, index and
Git worktree metadata are preserved by independent temporary snapshots.

Supported runners: Python/pytest; JavaScript/TypeScript with Node, Vitest or Jest;
Java/Maven; and Go. Dependencies must be available in the chosen Docker image.
Optional non-Python preparation can download dependencies and build frontend assets
in disposable containers before network-disabled tests. Preparation failures stay
separate from test failures. See [MULTILANGUAGE.md](MULTILANGUAGE.md).

Choose the investigation type:

| Mode | Behavior |
| --- | --- |
| Repair a broken update | Test good/bad releases, bisect failures, reverse candidates and iterate on source repairs. |
| Find the breaking change | Reproduce HEAD, search recent history, run reversals and request a tested repair. |
| Explain an error | Explain baseline errors or suggest optional improvements without requiring a historical boundary. |
| Check Git causes | Test the same history, then run reversal experiments when an implementation regression is confirmed. |
| Explore test history | Test HEAD and every first-parent commit through the newest passing/failing transition, without reversals or AI. |

Model-assisted modes require explicit sharing opt-in. It starts disabled and
resets when changing repositories/paths. The selected source/config files, logs
and diffs are sent to **Nebius Token Factory** at runtime. Environment files,
hidden paths, credential/secret paths and symbolic links are excluded; this is
not a general secret scanner. Review committed code before sharing it.

The standard profile bounds context to 12 files, 100,000 source characters, 40,000 log characters
and 20,000 diff characters. Files mentioned in errors/diffs and manifests receive
priority. Reports disclose selected and omitted files. Nemotron returns likely
causes, evidence, next steps, suggested tests and optional improvements. Advice
is a hypothesis until independently verified.

API clients can select `analysis_profile: "deep"` for larger bounded context
(24 files and 200,000 source characters), longer model requests and up to ten
repair attempts. The dashboard uses the standard profile. More context does not
replace reproducible tests or establish that a model suggestion is correct.

## Release repair agent

Enter the last working tag/commit and the broken tag/commit. The broken release
can differ from current HEAD. Select 1 to 5 repair attempts and opt into AI sharing.

1. Verify the working release passes and the broken release actually fails.
2. Group failing tests or collection errors and analyze their recent tested Git interval.
3. Reverse candidate commits to test whether individual failures disappear.
4. Ask Nemotron for implementation edits; test them in a disposable workspace.
5. Retain an edit only when it reduces failures without losing test identities,
   passing outcomes or introducing skipped tests. Feed remaining failures into
   the next attempt.
6. Stop when the complete unchanged selected suite passes, the attempt budget is
   exhausted, or a proposal cannot be applied/tested. Download accepted changes
   as a cumulative Git patch for review.

Private checkpoint commits exist only inside the disposable snapshot. Original
source/branches and remote repositories are not changed. Partial patches can
leave failures unresolved and are labeled accordingly. The workflow does not
auto-deploy, create a PR, or execute arbitrary shell instructions from the model.
Dependency/configuration changes remain recommendations; source patches cannot
change tests/configuration or weaken assertions.

Every investigation uses the same first-parent search: start at the selected
revision (HEAD by default, or the broken release) and test backward through the
most recent passing/failing transition. It stops there, at the repository root,
or at the selected history limit. Skips and errors remain visible while the
search continues. Repair mode additionally checks the chosen working release
as a separate endpoint; it does not resume a full-repository scan.
The 12-file AI source-context limit is separate from history execution.
Release boundary analysis uses the recent tested interval, using
the cached suite results, up to 20 failure groups and three distinct candidate
reversals in the standard profile. It assumes one passing-to-failing transition per test and
confirms an adjacent boundary, not the absence of earlier transient failures.
Missing/skipped historical evidence remains visible; changed tests prevent a
claim of implementation causality. Multiple failing tests may share one bug.
All modes test consecutively through the newest passing/failing
transition, with a selectable limit of 16 to 2,048 commits (default 64). Every tested
commit is saved with its original date, message, status and output. The timeline
marks the most recent pass and fail and supports local repositories from persisted
report evidence, without reopening the source. Search limits or unavailable test
evidence are shown explicitly; unknown outcomes never become passing results.
If HEAD already passes, the previous failing commit is shown as a recovery
transition rather than a current regression.

Production-only bugs still need reproducible tests/logs and compatible service,
data and runtime setup. Passing tests establish correctness only for the tested
behavior. CausalTrace does not promise a bug-free app or universal framework support.

## Reports and validation

Reports live in ignored `reports/<id>.json`; the download belongs to that specific
run. Accepted release patches are downloadable alongside reports. Existing saved
reports and cached histories are preserved. Investigation time is distinct from
original upstream commit dates.

- `completed`: the requested workflow finished; inspect individual outcomes.
- `partial`: some evidence or repairs exist, but work remains unresolved.
- `no_failure`: executed tests did not reproduce a failure; skips stay visible.
- `execution_error`: the runner could not produce a valid test outcome.
- `inconclusive`: no reliable boundary or verification was established.
- `verified` repair: a reproduced failure became a passing unchanged test suite.

Run the automated checks:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
Push-Location frontend
npm.cmd run build
npm.cmd run lint
Pop-Location
```

The standard suite uses mocked model responses. Opt-in Docker checks measure
real container results:

```powershell
$env:CAUSALTRACE_RELEASE_DOCKER_TESTS = '1'
.\.venv\Scripts\python.exe -m pytest tests/test_release_investigation.py -q
```

GitHub Actions repeats backend, frontend and Docker checks and packages a test
build after they pass. See the [workflow runs](https://github.com/Rabindra0101/causalTrace/actions/workflows/ci.yml).

## CLI and project map

```powershell
.\.venv\Scripts\python.exe -m causaltrace.main --repository imports --share-with-nebius
```

Use `--repo 'C:\projects\app'`, `--test-dir`, `--test-runner` and `--runner-image`
for a local project. Omitting `--share-with-nebius` preserves Git/test evidence
without a model request. The dashboard provides release comparison and diagnosis.

- `causaltrace/api.py`: local API, reports, patch downloads and timelines.
- `causaltrace/pipeline.py`: connected investigation and consent controls.
- `causaltrace/release_investigation.py`: bisection and iterative repair agent.
- `causaltrace/repository_snapshot.py`: independent Git snapshots.
- `causaltrace/verifier.py`, `test_runner.py`, `language_runner.py`: experiments and isolated execution.
- `causaltrace/build_doctor.py`, `diagnostic_context.py`, `nemotron_client.py`: diagnosis, protected patches and provider requests.
- `causaltrace/demo_setup.py`, `upstream_projects.py`: synthetic and original upstream repositories.
- `frontend/src/InvestigationDashboard.tsx`: submission dashboard.
- `tests/`: safety, agent, runner and workflow regression checks.

## Packaged builds and operating scope

The packaged test build includes the compiled frontend. From its extracted
causalTrace directory, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1 -Setup -UsePrebuiltFrontend
```

It needs Python, Git and Docker Desktop; Node is only needed when building from
source. To create a package from a clean committed checkout after a frontend
build, run `.\.venv\Scripts\python.exe -m scripts.package_submission`. The ZIP
contains a source-commit manifest and file hashes, plus a SHA256 sidecar.

The private judge key must be provided separately; it is never part of a build.
MIT license. Use one API worker bound to localhost: this prototype has no
multi-tenant authentication and is intended for trusted local repositories.
