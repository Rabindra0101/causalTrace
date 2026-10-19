# CausalTrace

Find the Git change that broke working software, explain the evidence with
NVIDIA Nemotron on Nebius Token Factory, and test a proposed repair.

The main dashboard runs one connected investigation:

1. Reproduce the failure at committed HEAD in a temporary Git worktree.
2. Test up to 16 first-parent revisions to find an adjacent passing/failing boundary.
3. Reverse the suspected commit on HEAD and compare it with reversing the latest commit.
4. Send the actual test output, candidate diff and relevant Python source to Nemotron.
5. Validate the model's proposed source replacements and run unchanged tests before/after.
6. Save an evidence report with independent reversal and repair outcomes.

A verified reversal supports a commit's contribution to the observed failure.
A verified repair means the original tests fail before the patch and pass afterward.
Neither establishes correctness beyond the tested behavior.

## Requirements

- Python 3.11 or later
- Git 2.28 or later
- Node.js 22.12+ or a newer supported LTS (for frontend development/building from source)
- Docker Desktop running Linux containers
- Nebius Token Factory API key with access to the configured NVIDIA model

## Windows PowerShell setup

Extract this project into a separate folder. Open that main folder in VS Code/Cursor.

First terminal, from the folder containing requirements.txt:

~~~powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
~~~

Edit .env and set NEBIUS_API_KEY to your own key. Do not upload .env or paste its
contents into a screenshot. Preserve your existing .env if applying these changes
to an existing checkout. NEBIUS_MODEL defaults to nvidia/nemotron-3-super-120b-a12b;
choose an available NVIDIA model if your account's model access differs.

Start Docker Desktop, then build the test image:

~~~powershell
docker build -f Dockerfile.test-runner -t causaltrace-test-runner:local .
python -m uvicorn causaltrace.api:app --reload --host 127.0.0.1 --port 8000
~~~

The reviewed ZIP includes a built frontend. Open http://127.0.0.1:8000 to use it
directly. You do not need a separate frontend terminal for that release build.

For frontend development, or if using a source checkout without frontend/dist,
open a second terminal:

~~~powershell
cd frontend
npm ci
npm run dev
~~~

Open the localhost URL Vite prints in development mode. Check the Readiness panel, select
Configuration type mismatch, and click Run full investigation.

Expected results for that demo:

- Committed HEAD fails because get_port returns a string.
- The passing parent and breaking implementation commit are identified.
- Reversing the breaking commit restores passing tests.
- Reversing the unrelated latest documentation commit leaves tests failing.
- A correct model patch converts the environment variable value to int.
- The repair is verified only if actual tests pass after the patch.

A model may return an invalid or ineffective patch. The app rejects or reports
those outcomes instead of marking them verified. Read the evidence.

macOS/Linux: activate with source .venv/bin/activate and copy the environment
template with cp .env.example .env. Remaining commands are the same.

## Which repository is investigated?

The dashboard has independent Repository and Investigation type selectors. Choose
one of the bundled demos or **Local Git repository**, then enter its absolute path
and a relative, self-contained test directory (default `.`). Local repositories
must have a committed HEAD. Local-path runs create an independent temporary Git
snapshot, leaving the original checkout, `.env`, index and worktree metadata
unchanged. Uncommitted edits are ignored; no stash or commit is required to run.
Select a supported test runner
or detect it from committed project manifests. Dependencies must be installed
in its Docker image. See [MULTILANGUAGE.md](MULTILANGUAGE.md) for setup.
For non-Python projects, optional preparation can download dependencies and
build frontend assets in disposable containers before the offline test run.
The report shows preparation errors separately from test failures.
Original source files remain unchanged. Local results include boundary commit
IDs and test evidence; the interactive demo timeline is available for demos only.

- **Reproduce failure only** runs tests at committed HEAD.
- **Git regression and reversal** also searches history and runs reversal controls.
- **Full investigation and repair** additionally sends committed source,
  test logs and the candidate diff to Nebius, proposes a repair, and tests it.

Only the full mode contacts the model. Review committed sources for secrets
before using it on your own repository. Keep this local API bound to localhost.

The dashboard defaults to bundled demo repositories, not the CausalTrace application folder.
Each demo is generated from shipped source recipes with real, local Git commits:
a passing baseline, an implementation regression, and unrelated documentation.
They are created lazily under .causaltrace/demos and do not require this ZIP to
contain the author's original .git directory.

Available demos: configuration type mismatch, broken import, empty API result,
unrelated-commit control, calculator and inventory.

The API demo is a Python response-handler fixture, not a full HTTP server.
The control demonstrates that reversing an unrelated commit does not repair a bug.

Advanced: investigate pasted logs and Python files opens the earlier Build Doctor
workspace. It remains useful for evidence outside a configured Git repository.
It does not scan local files or GitHub automatically.

## Investigate your own repository from the CLI

See [MULTILANGUAGE.md](MULTILANGUAGE.md) for JavaScript/TypeScript, Java and Go
runner setup, dependency images and supported test frameworks.

~~~powershell
python -m causaltrace.main --repo "C:\path\to\your\repository" --test-dir "tests"
~~~

Set --test-dir to a directory containing the implementation and tests needed for
execution. Use "." for a small self-contained repository.
Source is read from committed HEAD in an independent snapshot. Untracked application files are
not included. The entire test directory is mounted read-only into the container;
it must be self-contained. Dependencies beyond pytest must already exist in your
runner image, because test containers have no network. Patches are not written to
your original repository.

Bundled demo CLI:

~~~powershell
python -m causaltrace.main --repository config
~~~

## Reports and statuses

Reports are saved as reports/<investigation-id>.json. The dashboard downloads the
specific run's report. reports/latest_investigation.json is a compatibility copy.
Generated reports and demo repositories are ignored by Git.

- completed: investigation and model analysis finished; inspect individual outcomes.
- partial: Git evidence exists but model analysis/repair processing was unavailable.
- no_failure: committed HEAD passed.
- execution_error: baseline execution could not be evaluated.
- inconclusive: no reliable regression boundary was established.
- repair verified: the reproduced failure becomes a passing run on the same tests.
- reversal not_supported: the reversal applied but tests still failed.

Skipped-only tests, no collected tests, Docker failures and timeouts cannot verify
a repair. Source patches cannot change test files, conftest or configuration.
Reports retain before/after output and historical test statuses.

## Tests and validation

~~~powershell
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
cd frontend
npm run build
npm run lint
~~~

Automated integration checks run real Git history/reversal experiments and pytest
on the six trusted bundled fixtures using a host runner available only in tests.
Nemotron is mocked there. Production application execution always uses Docker.
See REVIEW.md for what was checked and what still requires a live test.

## Single-process production preview

~~~powershell
cd frontend
npm ci
npm run build
cd ..
python -m uvicorn causaltrace.api:app --host 127.0.0.1 --port 8000
~~~

Open http://127.0.0.1:8000 after starting the backend. Build first, then start/restart
the backend, so it detects frontend/dist. Vite development mode is not needed here.

This prototype is intended for local operation. There is no authentication or
multi-tenant isolation. Keep the API bound to localhost; exposing Docker-backed
execution publicly needs a separate deployment review. Run one API worker.
No public deployment has been performed by this update.

## NVIDIA and Nebius integration

causaltrace/nemotron_client.py sends runtime inference requests to Nebius Token
Factory at https://api.tokenfactory.nebius.com/v1/. The default NVIDIA open model
is nvidia/nemotron-3-super-120b-a12b. Actual logs, diff and source form the evidence
for structured diagnosis and repair proposals. Test and Git outcomes are measured
by the application, not supplied by the model. There is no canned model fallback.

Source and logs are sent to Nebius when model analysis runs. Remove secrets before
using the advanced pasted-evidence workspace. Git evidence remains available when
the model is unavailable and that condition is shown explicitly.

## Project map

- causaltrace/pipeline.py: connected investigation and persisted reports
- causaltrace/verifier.py: Git worktrees and reversal experiments
- causaltrace/test_runner.py: restricted Docker execution and pytest evidence
- causaltrace/build_doctor.py: structured model diagnosis, patch validation and repair tests
- causaltrace/demo_setup.py: reproducible Git demo histories
- causaltrace/api.py: readiness, investigation, reports and timeline endpoints
- frontend/src/InvestigationDashboard.tsx: main submission workflow
- frontend/src/BuildDoctor.tsx: optional pasted-evidence workspace
- tests/test_submission_workflow.py: trusted-fixture integration checks

Older duplicated dashboard and report-building code has been removed. Original
sample files and the inventory Git bundle are retained as reference material;
the current dashboard uses the reproducible source recipes.

## Submission

See SUBMISSION.md for the focused project description, judge instructions and
demo sequence. The working target is October 28, leaving time before the official
deadline. Review the current official rules:
https://nebiusglobalaihackathon.devpost.com/rules

MIT license.

## Public upstream investigations

humanize, PySnooper, Cookiecutter and Apache Commons CSV now use full original
upstream checkouts, committed tests and authentic commit dates. See
[PUBLIC_DEMOS.md](PUBLIC_DEMOS.md) for pinned revisions, actual test outcomes,
runner preparation and investigation commands. Earlier reconstructed replay
reports remain distinguishable from new upstream reports.

## AI diagnosis and development suggestions

Choose **AI diagnosis and development suggestions** to analyze a project's
baseline without requiring a proven Git regression. Enable **Share selected
evidence with Nebius for this run** to opt in to a model request. Sharing starts
disabled and resets when the repository selection/path changes.

The model can explain dependency/import/configuration errors, compiler/build
failures, API contract and empty-result bugs, and ordinary logic/test failures.
It returns evidence, likely causes, next steps, suggested regression tests and
optional development improvements. Passing tests permit optional review advice
in this mode; they never become a claim that a bug was reproduced.

In **Full investigation and repair**, setup errors, inconclusive history, and
boundaries involving test changes can still receive AI suggestions after opt-in.
Those suggestions do not establish which commit caused a failure. Source patches
are verified against the complete committed project in Docker with original
fixtures and tests. Dependency/configuration changes are recommendations only;
CausalTrace does not execute model-suggested installation commands or change
configuration/tests to manufacture passing results.

The selected evidence is capped at 12 source/config files, 100,000 source
characters, 40,000 log characters and 20,000 diff characters. It prioritizes files
mentioned in errors/diffs and manifests. Reports disclose selected/omitted files;
large files can be omitted. Environment files, hidden paths, credential/secret
paths and symbolic links are excluded. Review committed code before opting in:
these exclusions are not a general secret scanner. AI suggestions can be wrong,
and a verified patch only establishes success for the unchanged tests executed.

Executable adapters currently cover Python/pytest, JavaScript/TypeScript
(Node/Vitest/Jest), Java/Maven and Go. This is not universal support for every
language, framework, external service, GUI or hardware environment. Use a prepared
runner image for additional dependencies. Missing tests or unavailable services
remain explicit limits in the evidence.

## Release regression repair agent

Select **Compare releases and repair regressions**, choose the last working tag
or commit and the broken tag or commit, then set a repair attempt budget (1–5).
Enable **Share selected evidence with Nebius for this run** to let Nemotron
propose source repairs. Without consent, release testing, bisection and reversal
experiments still run, but no model request is made.

CausalTrace executes a bounded coding-agent cycle:

1. Resolve both release references and create an independent snapshot at the
   selected broken release, even when it is not your current HEAD.
2. Require the working release's complete selected test suite to pass and a valid
   failure at the broken release. Setup errors, missing tests and skips are not
   treated as evidence of a verified working release.
3. Group failures by test identity (or a collection-error path), then bisect each
   between the releases. Full-suite executions are cached across groups.
4. Reverse up to three distinct candidate commits in temporary worktrees and
   check whether each target failure disappears without losing passing tests.
5. Let Nemotron inspect bounded source, release diffs and failure output, propose
   implementation edits, and run the complete unchanged suite before and after.
6. Keep a partial repair only when it reduces failures, preserves test identities
   and existing passing outcomes, introduces no new failures/skips, and the
   baseline reproduces consistently. Feed remaining failures into the next model
   request. Stop when the suite passes, the attempt limit is reached, or a model
   proposal cannot be applied/tested.

Accepted changes are checkpointed **only inside the disposable snapshot**.
Download the cumulative Git patch from the report. It is exported byte-for-byte
from Git and checked for clean application in integration tests, including
Windows line endings. Review it against the selected broken release before
applying. Partial patches are labeled partial and may leave unresolved failures.
No original source, branch, `.env`, Git metadata or remote branch is changed by
an investigation; this workflow does not auto-deploy or auto-publish a repair PR.

Search currently follows the first-parent history over at most 2,048 commits,
with up to 32 cached historical suite executions and 20 failure groups. Bisection
assumes a single passing-to-failing transition for each test; it confirms a tested
adjacent boundary, not the absence of all earlier transient failures. Missing or
skipped historical tests stop that group's search. Changed tests between releases
prevent a claim of implementation causality. Multiple failing tests can share
one underlying bug. A passing final suite verifies tested behavior, not a claim
that the application has zero bugs. Reproduction tests/logs and a compatible
runner are still required for failures unique to production.

The agent uses the supported Python, JavaScript/TypeScript, Java and Go runners
and the existing explicit Nebius sharing controls and source/context limits.
Additional dependencies need a prepared runner. It does not execute arbitrary
shell instructions returned by the model or modify tests/configuration to make a
patch pass. Suggested dependency changes remain instructions for review.

To repeat the real Docker experiment (two regressions introduced in different
commits, repaired in two successive attempts), with mocked Nemotron responses:

```powershell
$env:CAUSALTRACE_RELEASE_DOCKER_TESTS = '1'
.\.venv\Scripts\python.exe -m pytest tests/test_release_investigation.py -q
```
