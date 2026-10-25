# CausalTrace submission

## Entry and access

- Track: **Coding and Agentic Engineering**.
- Public MIT source: https://github.com/Rabindra0101/causalTrace/tree/mainWorking
- Downloadable source test build: https://github.com/Rabindra0101/causalTrace/archive/refs/heads/mainWorking.zip
- Setup: README.md. Windows launcher: `powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1 -Setup`.
- After setup: `.\scripts\start.ps1`. Open http://127.0.0.1:8000.

The reviewed work is on **mainWorking**, not the repository's default branch.
This is a local test build requiring Python, Node, Git, Docker Desktop and an
independently configured Nebius API key. It is not a hosted inference service.
Do not publish the filesystem/Docker API as an unauthenticated public server.

## Description

An application update breaks working behavior. CausalTrace reproduces the test
failure, tests recent Git history to locate a passing/failing transition, and
challenges candidate commits with reversal experiments. NVIDIA Nemotron on
Nebius Token Factory explains selected evidence and proposes source repairs.
A bounded agent loop tests each proposal against the unchanged suite and can
retain incremental repairs without losing earlier passing tests. Reports separate
measured outcomes from AI hypotheses and provide reviewable cumulative patches.

Python, JavaScript/TypeScript, Java and Go adapters support compatible projects.
Examples cover broken imports, configuration types, API contracts and ordinary
logic failures. Original repositories stay unchanged in disposable snapshots.
There is no promise of zero bugs or universal framework compatibility.

## Judge walkthrough

1. Follow README setup and configure your own key locally. Never share `.env`.
2. Choose **Broken package import**, then **Find the breaking change**.
3. Opt into **Share selected evidence with Nebius for this run** and run.
4. Inspect actual failure, tested history, candidate/control reversals, Nemotron
   analysis and separately verified repair. Model proposals can fail verification.
5. Download the evidence report. Choose **Repair a broken update** for the same
   demo with working `HEAD~2` and broken `HEAD`; inspect iterative repair evidence
   and download an accepted patch when available.
6. Try pause/resume/stop, or **Explore test history** without AI sharing.

Bundled tiny demos use synthetic labeled histories. Public upstream selections
preserve original commits/dates; their pinned original suites have not reproduced
a failing baseline. They are not advertised as verified public regressions.
Automated model responses are mocked; real Docker tests validate execution and
repair acceptance, not live model quality. Provider inference needs live access.

## Official requirements checked October 25, 2026

[Official rules](https://nebiusglobalaihackathon.devpost.com/rules) and
[event page](https://nebiusglobalaihackathon.devpost.com/).

Submission closes **October 30, 2026 at 10:00 AM PDT / noon CDT**. Supply the
working demo or test-build URL, public source/setup, project description, track,
and public YouTube demonstration **under three minutes**. Demonstrate runtime
Nebius Token Factory inference and an NVIDIA open model; a mocked test alone
does not establish this requirement. Keep judge access usable through December 15.
Explain substantial new work if the project predates the allowed build period.

## Final publication fields

- YouTube URL: record and publish the walkthrough in DEMO_SCRIPT.md.
- Live inference rehearsal: repeat with a valid account/key and available credits.
- Nebius/NVIDIA feedback: describe your actual integration experience; do not invent
  cost, latency, accuracy or throughput measurements.
- Devpost: paste the branch/test-build URLs above and complete required entry fields.
- Verify judge access does not require your private files or credentials.

These account-owned publication steps remain necessary before calling the entry
submitted. The repository does not contain a fabricated video or feedback record.
