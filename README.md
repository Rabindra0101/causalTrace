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
must have a committed HEAD and no tracked edits. Select a supported test runner
or detect it from committed project manifests. Dependencies must be installed
in its Docker image. See [MULTILANGUAGE.md](MULTILANGUAGE.md) for setup.
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
execution. Use "." for a small self-contained repository. Commit/stash tracked edits
first. Source is read from committed HEAD. Untracked application files are
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
