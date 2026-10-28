# Devpost project story

Copy the sections below into the project description. Links and test-build access
are in SUBMISSION.md. Review the first-person wording before publishing.

## Inspiration

An update can break behavior that worked yesterday. Logs tell us what failed,
but the latest commit is not necessarily responsible. An AI explanation alone
cannot establish causality, and a plausible patch can introduce another failure.
We wanted a developer tool that keeps a clear chain from failure to Git change,
from hypothesis to experiment, and from proposed repair to unchanged test result.

## What it does

CausalTrace investigates committed application history without modifying the
original checkout. It runs compatible tests in Docker, searches backward to the
newest measured passing/failing transition, and reverses candidate changes in
disposable snapshots. An unrelated latest commit provides a useful control.

NVIDIA Nemotron, served by Nebius Token Factory, receives selected source, logs
and diffs after explicit opt-in. It explains likely causes, suggests next steps,
and proposes bounded implementation edits. The release repair agent can retain
incremental fixes while testing for lost or regressed passing outcomes. Evidence
reports distinguish AI hypotheses, causal experiments and tested repairs.

## How we built it

The local application combines FastAPI, React/TypeScript, Git and restricted
Docker runners. Supported adapters cover Python/pytest, JavaScript/TypeScript
with Node/Vitest/Jest, Java/Maven and Go. Source snapshots isolate work from the
original repository, and model proposals cannot edit tests or configuration.

Runtime inference uses the OpenAI-compatible API at
`https://api.tokenfactory.nebius.com/v1/`. The default NVIDIA model is
`nvidia/nemotron-3-super-120b-a12b`. Nemotron supplies structured diagnosis and
replacement proposals; Git and Docker independently measure the outcomes.
Nebius AI Cloud compute, Tavily and other NVIDIA runtime tools are not used.

## Challenges

Historical environments differ from current development environments. Missing
dependencies, collection errors and skipped tests must remain visible rather
than being converted into passing evidence. We also had to preserve local work,
keep Docker worktrees outside OneDrive-hosted Git metadata, and make pause/stop
interrupt real operations. Provider generation itself cannot be remotely paused.

## Accomplishments

CausalTrace separates a repair that passes supplied tests from a proven causal
experiment. It measures suspected and unrelated reversals separately, preserves
original source, and exports reviewable patches. CI checks frontend, backend and
real Docker execution with mocked inference. Live model demonstrations must be
identified separately from automated mocked-provider tests.

## What we learned

A reliable coding agent needs a testable contract and honest uncertainty, not
just a larger prompt. Public upstream projects can have passing original suites
at historical revisions; those are not claimed as reproduced regressions. Tests
establish only the behavior they cover, and the app does not promise zero bugs.

## What's next

Expand framework/service fixtures, improve reproducibility of historical
runtimes, and add authenticated team workflows. These are future work, not
features represented as complete in this submission.

## Work during the submission period

The current implementation adds release comparison, iterative source repair,
multilingual Docker adapters, tested first-parent history across all modes,
independent snapshots, active pause/resume/stop controls, an accessible dashboard,
and automated submission checks. Repository commits document the changes.
If an earlier version existed before August 26, 2026, add its exact scope and
explain how this period's changes significantly extend it; do not invent dates.

## Nebius / NVIDIA feedback draft

The OpenAI-compatible Token Factory interface allowed the project to use a
standard client while selecting an NVIDIA Nemotron model. Structured responses
make proposed edits easier to validate, but a valid response still needs parsing,
path restrictions and independent test execution. Request cancellation and token
usage need careful presentation: closing a client connection does not establish
that provider computation or billing stopped. More explicit cancellation status
and actionable structured-output diagnostics would help tools like this one.

This feedback describes implementation observations. Add only personally observed
service behavior; no cost, latency or accuracy benchmark is claimed.
