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
64 by default (up to 2,048); unavailable evidence and limits stop explicitly.
Reports persist every tested commit's original metadata, status and output, mark
the latest pass/fail, and serve local timelines without reopening source paths.
Passing HEAD can show a historical recovery without inventing a current regression.

Validation: 47 backend tests and 33 subtests passed; 14 optional checks skipped.
Both non-AI modes separately passed real Docker history checks with no model
requests. A 21-commit fixture covers the old truncation limit, saved local history,
search limits and unavailable evidence. Frontend build and lint passed.
