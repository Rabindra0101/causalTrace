# Submission readiness review

## Original repository isolation — October 18, 2026

- Local-path investigations use independent temporary Git snapshots rather than
  registering experimental worktrees in the source repository.
- Fixture tests verified a complete historical/reversal investigation preserves
  all source and Git metadata file hashes and modification timestamps, including
  a dirty tracked file, an ignored environment file and untracked local work.
- Verified independent object storage, cleanup after failure, and rejection of
  report output paths inside the original repository.
- FileSync was not accessed or modified for these changes or checks.

## Project preparation update — October 18, 2026

- Added opt-in dependency downloads and frontend builds in disposable per-run
  volumes. A separate network-disabled container executes the actual tests.
- Verified a downloaded Go module can be used in offline tests, frontend output
  satisfies Go embed requirements, and preparation failures cannot verify tests.
- Verified source/test rewrites during preparation are rejected, the original
  fixture files stay unchanged, `.env` is not copied, and volumes are cleaned up.
- Added actionable setup diagnostics and separate preparation output in reports.
- Added an optional Linux GTK/WebKit runner for Wails v2-compatible native code;
  it does not provide a desktop display or Windows-only build support.
- Built that image and verified an offline Go/CGO fixture links and calls GTK
  and WebKit version functions without starting a desktop application.
- Changes and validation fixtures are confined to CausalTrace. No FileSync files
  were modified or tested as part of this update.

## Multilingual runner update — October 18, 2026

- Added committed-manifest detection and explicit pytest, Node, Vitest, Jest,
  Maven/Surefire and Go runner selections, including prepared dependency images.
- Verified actual offline Docker passing/failing fixtures for Node, Go,
  TypeScript/Vitest, Jest and Java/Maven. Node and Go zero-test runs cannot pass.
- Verified a complete Node Git boundary, suspected reversal, unrelated reversal
  and repair experiment with a mocked model. Original HEAD/source stayed unchanged.
- Adapter fixtures cover skips, absent testcases, build failures without evidence,
  protected tests/manifests, committed detection and runner context cleanup.
- Non-Python repair verification uses the full committed worktree and the same
  selected test runner; model repairs cannot edit recognized test files/config.
- This does not certify arbitrary projects. Dependencies/native libraries must be
  prepared in the selected image, actual tests must exist, and the documented
  source-context/resource limits still apply. See MULTILANGUAGE.md.

## Original blockers found

- Git investigation and Build Doctor were separate workflows. Git results did not feed repair proposals.
- Original Git demos demonstrated arithmetic regressions only.
- Reports used a single global latest file, so concurrent readers could pick up a different run.
- Missing NEBIUS_API_KEY raised during module import, preventing inspection/testing of the original CLI.
- Import/collection failures were classified as infrastructure errors in the original Git engine.
- Temporary repair directories had private permissions that could block the non-root Docker user.
- The original README lacked install, run, model and judge instructions.
- The original EvidenceGraph effect triggered a frontend lint error.

## Changes made

- Connected reproduction, history search, reversal controls, model diagnosis, source repair and before/after tests.
- Added real generated Git histories for configuration, import and API-handler regressions.
- Added readiness checks, run-specific report IDs, downloads and historical test outcomes.
- Preserved Git evidence when the model is unavailable and labeled the run partial.
- Required actual pytest collection/outcome evidence and unchanged collected tests for repair success.
- Kept Docker-only execution in production, with no host-runner fallback.
- Kept pasted evidence as an advanced workspace beneath the main investigation.
- Removed the unused LegacyApp.tsx, git_analyzer.py and report_generator.py after their responsibilities moved to the connected pipeline.
- Excluded dependency directories, personal Git metadata, caches and stale generated reports from the delivery ZIP. Included the checked frontend production build so the release can run from one backend process.

## Verified in the review environment

- Backend suite: seven test methods passed, including the complete workflow on all six demos and a full API investigation/report/graph/timeline run.
- Real Git and pytest: every demo had a passing parent, a failing regression, a verified suspected reversal, an unsupported unrelated reversal and a passing repaired implementation.
- Original repository HEAD/source stayed unchanged; temporary Git worktrees were cleaned up.
- Missing model preserves experimental evidence; invalid paths and protected-file patches are rejected.
- Docker errors, no-test runs and skipped-only runs cannot produce verified outcomes.
- API validation, missing report handling, run identity and cross-repository report rejection passed.
- Frontend TypeScript/Vite production build and ESLint passed.
- Production HTML and its bundled JavaScript/CSS assets were served successfully by the backend.

The automated model reply is mocked. Trusted demo tests execute on the host only
through a test-specific injected runner. The application itself always uses Docker.

## Still needs a live check before calling this submission-ready

1. Windows Docker Desktop: build the image and run configuration and import investigations in the app.
2. Nebius: use your configured key to produce and test actual model patches for those runs.
3. Browser: confirm readable results, source/diff display, timeline, graph and report download.
4. Submission access: choose a judge-accessible test build or demo route and verify it from a clean setup.
5. Finish the public repository, actual Nebius feedback and public YouTube demonstration.

No Docker engine, API key or browser binary was available for live execution in
this review environment. Successful local integration checks do not replace those checks.

Do not record a simulated model result as the final demo. Record a fresh live run.

## Four public-project regression replays — October 18, 2026

- Added separate humanize significant-figure, PySnooper Unicode, Cookiecutter
  UTF-8 context and Apache Commons CSV carriage-return regression tests.
- Vendored pinned upstream extracts/class, licenses, Apache NOTICE and provenance.
  Histories and authored tests are explicitly labeled as reconstructed replays.
- Real offline Docker checks verified each historical bug fails and the fixed
  source passes with unchanged tests. All four also confirmed a historical
  boundary, a verified suspected reversal and an unsupported unrelated reversal.
- Backend suite: 32 passed, 6 optional suites skipped, 33 subtests passed with
  public-demo Docker checks enabled. An additional API runner-selection test
  passed afterward (5 fast checks passed; 8 Docker checks skipped in that rerun).
- Frontend production build and lint passed; existing bundle-size warning remains.
- No live Nebius inference was used for these checks. Full diagnosis/repair remains
  a separate live experiment, independently verified by the existing app workflow.
- Work stayed within CausalTrace. FileSync and environment secrets were untouched.
