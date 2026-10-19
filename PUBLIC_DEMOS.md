# Four public-project regression demos

Select a **public bug replay** in the Repository dropdown. Each replay contains
pinned upstream code, a newly authored regression test, a passing baseline, a
commit reintroducing the historical defect, and an unrelated documentation control.
These are focused reconstructed histories, not clones of the upstream repositories
or claims that our generated commit IDs are upstream commits.

| Project | Test | Upstream fix |
| --- | --- | --- |
| humanize | Metric rounding preserves significant figures near the quetta boundary | [PR 406](https://github.com/python-humanize/humanize/pull/406) |
| PySnooper | UTF-8 source without an encoding cookie retains Chinese characters | [Unicode fix](https://github.com/cool-RR/PySnooper/commit/56f22f8ffe1c6b2be4d2cf3ad1987fdb66113da2) |
| Cookiecutter | Non-ASCII JSON context loads even with an ASCII default locale | [Context decoding fix](https://github.com/cookiecutter/cookiecutter/commit/7f6804c4953a18386809f11faf4d86898570debc) |
| Apache Commons CSV | Standalone carriage returns advance the line counter | [CSV-75](https://issues.apache.org/jira/browse/CSV-75) / Defects4J Csv-1 |

The first three extract relevant upstream functions. PySnooper has minimal
Python 3 compatibility shims; Cookiecutter has a local exception harness and
simulates an ASCII locale in its test. Commons CSV includes its full reader
class and an authored JUnit test. Original license texts and Apache NOTICE are
included beside each fixture. `replay.json` records the pinned source and mutation.
The model receives source/test evidence, not the replay mutation metadata.

Run these PowerShell commands from CausalTrace to prepare images:

```powershell
docker build -f Dockerfile.test-runner -t causaltrace-test-runner:local .
if ($LASTEXITCODE -ne 0) { throw 'Python image build failed' }
docker build -f Dockerfile.multilang-runner -t causaltrace-multilang-runner:local .
if ($LASTEXITCODE -ne 0) { throw 'Multilingual image build failed' }
docker build -t causaltrace-framework-fixtures:local tests/fixtures/multilang
if ($LASTEXITCODE -ne 0) { throw 'Java dependency image build failed' }
$env:CAUSALTRACE_PUBLIC_DEMO_TESTS = '1'
.\.venv\Scripts\python.exe -m pytest tests/test_public_demos.py -q
```

The opt-in checks exercise real Docker tests on broken and repaired source, plus
Git boundary discovery, suspected reversal and an unrelated reversal control.
They do not call Nebius. Choose **Full investigation and repair** in the running
app to test live model diagnosis and a separately verified proposed patch.

Fixture creation during app usage is offline and confined to
`.causaltrace/demos/public-*` under CausalTrace. No FileSync path is read or written.
To regenerate vendored extracts, run `scripts/import_public_demo_sources.py`
(network required), then `scripts/build_public_demos.py`. Regeneration is a
maintainer operation and is never performed when selecting a demo.
