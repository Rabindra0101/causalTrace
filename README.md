# CausalTrace

Find the release change that broke your application, explain the evidence with
NVIDIA Nemotron on Nebius Token Factory, and test proposed code repairs.

CausalTrace combines Git history, isolated Docker tests, reversal experiments and
a bounded coding-agent loop. It keeps the original repository unchanged and
produces a report and a cumulative repair patch for review.

## Quick start — Windows PowerShell

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
.\.venv\Scripts\python.exe -m uvicorn causaltrace.api:app --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000**. The backend serves `frontend/dist` after a build;
restart it when that build changes. For frontend development, run `npm.cmd run dev`
from `frontend` in a second terminal. Vite forwards API requests to port 8000.
PowerShell commands above are separate lines; do not append a backslash to the port.

For macOS/Linux, create/activate a Python virtual environment, use its `python`,
and use `npm` instead of `npm.cmd`.

## Try a measured demo

Choose **Broken package import** or **Configuration type mismatch**, select
**Full investigation and repair**, and enable **Share selected evidence with
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
| Compare releases and repair regressions | Test good/bad releases, bisect failures, reverse candidates and iterate on source repairs. |
| Full investigation and repair | Reproduce HEAD, search recent history, run reversals and request a tested repair. |
| AI diagnosis and development suggestions | Explain baseline errors or suggest optional improvements without requiring a historical boundary. |
| Git regression and reversal | Collect history/reversal evidence without model requests. |
| Reproduce failure only | Run the selected committed baseline without model requests. |

Model-assisted modes require explicit sharing opt-in. It starts disabled and
resets when changing repositories/paths. The selected source/config files, logs
and diffs are sent to **Nebius Token Factory** at runtime. Environment files,
hidden paths, credential/secret paths and symbolic links are excluded; this is
not a general secret scanner. Review committed code before sharing it.

Context is bounded to 12 files, 100,000 source characters, 40,000 log characters
and 20,000 diff characters. Files mentioned in errors/diffs and manifests receive
priority. Reports disclose selected and omitted files. Nemotron returns likely
causes, evidence, next steps, suggested tests and optional improvements. Advice
is a hypothesis until independently verified.

## Release repair agent

Enter the last working tag/commit and the broken tag/commit. The broken release
can differ from current HEAD. Select 1–5 repair attempts and opt into AI sharing.

1. Verify the working release passes and the broken release actually fails.
2. Group failing tests or collection errors and bisect their selected Git range.
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

Bisection follows first-parent history across at most 2,048 commits, using at
most 32 cached historical suite runs, 20 failure groups and three distinct
candidate reversals. It assumes one passing-to-failing transition per test and
confirms an adjacent boundary, not the absence of earlier transient failures.
Missing/skipped historical evidence stops that search; changed tests prevent a
claim of implementation causality. Multiple failing tests may share one bug.
Ordinary HEAD history search is limited to 16 first-parent revisions.

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

[REVIEW.md](REVIEW.md) records measured checks and remaining live validation.

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

## Submission and operating scope

See [SUBMISSION.md](SUBMISSION.md) for the description and demonstration sequence.
MIT license. Use one API worker bound to localhost: this prototype has no
multi-tenant authentication and is intended for trusted local repositories.
