# Full upstream repository investigations

The four public project entries now clone **complete original Git repositories**
into `.causaltrace/upstream/` inside CausalTrace. They check out pinned historical
revisions, run the original committed test suites, and show original commit IDs
and author dates. Investigation start time is displayed separately in local time.
No generated regression commits or authored replay tests are injected.

| Project | Pinned revision | Original-suite outcome verified locally |
| --- | --- | --- |
| [humanize](https://github.com/python-humanize/humanize) | `392aef707c0e74341ab4a51420984e9ea6b566c5` | 856 passed |
| [PySnooper](https://github.com/cool-RR/PySnooper) | `e21a31162f4c54be693d8ca8260e42393b39abd3` | 28 passed |
| [Cookiecutter](https://github.com/cookiecutter/cookiecutter) | `c15633745df6abdb24e02746b82aadb20b8cdf8c` | 294 passed, 1 skipped |
| [Apache Commons CSV](https://github.com/apache/commons-csv) | `0833f45bffd40f44ba6f294d84e9bac8a9ba0a37` | 53 passed, 2 skipped |

These historical revisions contain the previously demonstrated defects, but their
original test suites do not reproduce those defects in these runners. Full-mode
investigations therefore stop with **no failure reproduced**. They do not claim
verified regression boundaries, model diagnoses, or repairs. Skipped tests remain
visible and prevent a claim that every test passed. A failing baseline is required
before the existing historical search and reversal workflow proceeds; search is
limited to 16 first-parent revisions. Full Git history is retained by the clone.

From CausalTrace, prepare all four projects in Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -m causaltrace.upstream_projects all
if ($LASTEXITCODE -ne 0) { throw 'Upstream checkout preparation failed' }
docker build -f Dockerfile.multilang-runner -t causaltrace-multilang-runner:local .
if ($LASTEXITCODE -ne 0) { throw 'Base runner build failed' }
foreach ($project in @('humanize', 'pysnooper', 'cookiecutter')) {
    docker build -f Dockerfile.upstream-python --target $project -t "causaltrace-upstream-${project}:local" .
    if ($LASTEXITCODE -ne 0) { throw "Runner build failed: $project" }
}
docker build -f Dockerfile.upstream-csv -t causaltrace-upstream-commons-csv:local .causaltrace/upstream/commons-csv
if ($LASTEXITCODE -ne 0) { throw 'CSV runner build failed' }
.\.venv\Scripts\python.exe -m scripts.run_upstream_investigations all
if ($LASTEXITCODE -ne 0) { throw 'Investigation failed' }
```

Select a **full upstream repository** in the dashboard and run an investigation
to display its report and timeline. Restart the backend after updating the code.
The first clone and runner image builds require network access. Tests run offline
in disposable containers; repository mounts are read-only. Working copies use LF
line endings for Linux. Humanize's generated version and translation binaries are
built only in the disposable container. CSV uses Java 8 and its own Maven POM;
Python profiles use their revision-compatible dependencies and Python versions.
Dependency versions are pinned where explicitly listed in the Dockerfile;
transitive packages and base image tags are not a complete dependency lock.

Existing local changes in a cached upstream checkout are rejected and preserved.
FileSync is neither accessed nor modified. No API key or `.env` file is copied.
Old downloaded replay reports retain their reconstructed timelines; re-run an
investigation to obtain original upstream history. The six tiny bundled fixtures
remain synthetic demos and now label generated commits without misleading dates.

Obsolete extracted replay code and its regeneration scripts have been removed.
Saved report JSON files are preserved. An old replay timeline can still use its
existing cache under `.causaltrace/demos/public-*`; absent replay caches are not
regenerated. Run a new upstream investigation for authentic original history.

To repeat the complete original-suite Docker integration checks:

```powershell
$env:CAUSALTRACE_UPSTREAM_TESTS = '1'
.\.venv\Scripts\python.exe -m pytest tests/test_upstream_projects.py -q
```
