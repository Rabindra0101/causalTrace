# Submission validation

## Scope

CausalTrace is a local evidence-driven regression investigation and bounded
Nemotron coding-agent prototype. It supports Python/pytest, JavaScript/TypeScript
(Node/Vitest/Jest), Java/Maven and Go through isolated Docker runners.

The release agent compares selected working/broken commits, bisects individual
failures, reverses candidates and iterates on protected source patches. Accepted
changes remain in independent disposable snapshots and are exported as a Git
patch for review. Verified means unchanged executed tests pass, not zero bugs.

## Measured evidence

- The release-agent Docker experiment reproduced two failures introduced in two
  different commits, located both boundaries, supported both reversals and
  verified two cumulative repairs with the complete unchanged suite passing.
- A real Docker import-error repair passed with original JSON fixtures intact,
  without needing a known passing historical parent.
- Synthetic demo checks exercise boundary, suspected/control reversal and repair
  outcomes using real Git histories and trusted test fixtures.
- Isolation checks compare source and Git metadata hashes/timestamps, including
  dirty tracked files, untracked work and ignored environment files.
- Runner checks cover missing dependencies, build failures, empty/skipped suites,
  protected test/config edits, unavailable historical evidence and preparation
  that changes committed source. These outcomes cannot manufacture verification.
- Full original upstream suites were measured at pinned revisions: humanize 856
  passed; PySnooper 28 passed; Cookiecutter 294 passed / 1 skipped; Commons CSV 53
  passed / 2 skipped. No regression was reproduced by those original suites.

All automated model replies in these checks are mocked. Provider integration is
wired to runtime NVIDIA Nemotron inference on Nebius Token Factory, but the new
release-agent experiment has not been rerun with live inference. Complete a live
judge rehearsal using your own configured account before claiming that result.

## Cleanup audit

The root audit removed the unused pasted-log frontend/API, starter artwork,
duplicate reference samples and Git bundle, obsolete public replay source and
generation scripts, and superseded Git/source-selection helpers. Pinned upstream
metadata and cached legacy report lookup remain. Active release, diagnosis,
upstream, runner, isolation and workflow tests are retained. The useful public
runner-selection API check was moved into the upstream suite.

Verification now always tests a full committed worktree and writes only changed
implementation files after its untouched baseline. The retired supplied-files-only
verification path was removed. Runtime pytest was moved to development dependencies;
container images continue to provide the test runners.

Saved reports, upstream checkouts, replay caches, dependencies and `.env` were
preserved. FileSync was neither accessed nor modified. No environment secrets
were printed or committed. README and submission instructions now describe the
active product instead of retired features.

## Repeat checks

See README.md for the standard backend suite and frontend build/lint commands.
Docker integration suites opt in with environment flags documented in the
relevant test modules, MULTILANGUAGE.md and PUBLIC_DEMOS.md. Check actual model
access, credits, runner images and demonstration links separately.

Cleanup validation: 43 backend tests and 33 subtests passed; 12 optional checks
skipped. The final release-agent Docker experiment passed separately. Frontend
production build and lint passed, and the retained CLI help was checked.

## Tested history in both non-AI modes

Git regression/reversal and reproduce-only now test each first-parent commit from
HEAD through the newest passing/failing transition. Their configurable limit is
64 by default (up to 2,048); unavailable evidence stays visible while older commits are tested.
Reports persist every tested commit's original metadata, status and output, mark
the latest pass/fail, and serve local timelines without reopening source paths.
Passing HEAD can show a historical recovery without inventing a current regression.

Validation: 47 backend tests and 33 subtests passed; 14 optional checks skipped.
Both non-AI modes separately passed real Docker history checks with no model
requests. A 21-commit fixture covers the old truncation limit, saved local history,
search limits and unavailable evidence. Frontend build and lint passed.

All five modes now share the same first-parent search from the selected revision
through the most recent passing/failing transition, bounded by the history limit.
Repair mode additionally tests the selected working endpoint and restricts its
per-test analysis to the recent tested interval. No mode scans the full history
after finding the transition. All attempted failures, skips and runner errors
remain visible, even when the selected HEAD passes.
The 12-file source-context cap is separate from historical test execution.

## Public repository cleanup and readiness

Live API checks reproduced Windows permission errors when removing Git worktree
metadata from the OneDrive-hosted humanize and Commons CSV caches. All modes now
use independent temporary snapshots for bundled/public repositories as well as
local repositories. Worktree metadata stays out of the source cache; original
upstream commit IDs, author dates and provenance are retained.

Two-revision Docker checks completed without that Git error for all four public
projects. Baselines: humanize 856 passed; PySnooper 28 passed; Cookiecutter 294
passed and 1 skipped; Commons CSV 53 passed and 2 skipped. Skips remain incomplete
coverage, not verified repairs. These checks made no AI requests.

Readiness now shows a visible cross on the affected component, distinguishes
repository Git-operation errors from Git installation, and marks all checks
unavailable when the backend cannot be reached. Component failures are explained
inside their cards instead of a separate error banner.

## Submission audit - October 25, 2026

Audited the tracked CausalTrace source tree, excluding protected environment and
credential files. FileSync was not accessed or modified. Added Docker context
exclusions, credential-isolated tests, GitHub Actions backend/frontend/container
checks, a Windows setup launcher, branch-specific submission/test-build links
and a timed demonstration script. Updated instructions to match current labels
and shared recent-history behavior. Non-AI graphs no longer name an unused model.

Frontend now uses distinct investigation accent colors, richer backgrounds,
card depth, hover feedback and short entrance/illustration animations. Existing
large text, focus indicators and responsive layout are retained. Reduced-motion
preferences disable motion; forced-color text stays visible. Build and lint pass.
After Chrome was connected, the desktop dashboard was visually inspected at
http://127.0.0.1:5174/. Colors, alignment and readiness cards rendered correctly.
The existing active investigation was left untouched.

Production npm dependency audit: zero vulnerabilities. Python dependency check:
no broken requirements. Default Docker runner builds successfully. All four
public upstream projects completed two-revision Docker investigations without
Git cleanup errors: humanize 856 passed; PySnooper 28 passed; Cookiecutter 294
passed/1 skipped; Commons CSV 53 passed/2 skipped. These are measured baselines,
not verified public regressions. Real container coverage includes release repair,
multilingual execution, historical outcomes and active pause/resume/cancellation;
provider responses in automated tests are mocked.

Automatic approval review blocked loading the local environment file for a live
provider health check. No process-environment Nebius credential was available,
so this audit did not repeat live inference. Existing secrets were preserved.
A real inference rehearsal, public under-three-minute YouTube video and final
Devpost entry fields remain account-owned publication steps; see SUBMISSION.md.

Final expanded validation: **74 tests and 33 subtests passed; 8 optional checks
skipped**. Frontend production build and lint passed. Both default and Commons CSV
runner images rebuilt successfully. The final suite enables actual Docker
history, repair, multilingual and pause/resume/stop checks with mocked inference.
