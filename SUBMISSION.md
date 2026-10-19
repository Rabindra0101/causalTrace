# CausalTrace submission draft

## One-sentence description

CausalTrace investigates Python regressions by testing Git history, evaluating
candidate changes through reversal experiments, and using NVIDIA Nemotron on
Nebius Token Factory to propose repairs that are checked against unchanged tests.

## Track

Coding and Agentic Engineering.

## Problem and approach

A failing build gives developers symptoms, but a recent commit is not automatically
the cause. CausalTrace combines historical tests with a control experiment: reverse
the suspected change, then compare that outcome with reversing an unrelated commit.
Nemotron receives the measured failure, relevant source and candidate diff to
explain the hypothesis and propose a minimal source repair. The application tests
the proposal and distinguishes verified, unsupported and inconclusive outcomes.

## What judges can try

Follow README.md to install the app and runner. Supply a valid Nebius key in .env.
Choose Configuration type mismatch and run the full investigation. Inspect the
historical boundary, compare the two reversals, review the proposed conversion to
an integer, and inspect before/after repair results. Repeat with Broken package
import. Download the report for each run. Demo histories are generated locally
from included recipes; the resulting Git and test evidence is measured at runtime.

## Demonstration sequence: target 2 minutes 40 seconds

- 0:00–0:20: Explain the problem: finding a breaking change and validating a repair.
- 0:20–0:45: Show the configuration scenario and start a live run. Trim waiting time in the video and disclose the cut.
- 0:45–1:15: Show the failing HEAD, passing parent and identified breaking commit.
- 1:15–1:45: Compare the verified suspected reversal with the unrelated reversal that still fails.
- 1:45–2:15: Show the actual Nemotron proposal and failing-to-passing repair tests.
- 2:15–2:40: Show a second non-math example and the downloaded evidence report; state the current scope.

## Scope to state accurately

Local Python prototype; six curated repositories with real Git history; explicit
CLI configuration for other self-contained repositories; pytest-based verification;
temporary patches; one API process. No automatic GitHub Actions ingestion, universal
language support, production hosting or unrestricted dependency installation.

## Submission items still to fill

- Public repository URL with the existing MIT license.
- Working demo or downloadable test-build URL and complete judge instructions.
- Public YouTube video link under three minutes.
- Actual feedback based on your Nebius/NVIDIA usage. Do not invent performance metrics.
- Confirm the live API key/model account can support the intended judging access.

## Schedule

- By October 21: validate the connected configuration and import workflows with live Nebius and Docker.
- October 22–24: resolve only defects found by those runs; validate a clean installation and judge access.
- October 25–26: record the demo and finalize repository documentation and submission text.
- October 27–28: verify all links and complete submission, leaving a buffer.

Official rules checked during this review: https://nebiusglobalaihackathon.devpost.com/rules
The page lists October 30, 2026 at 10:00 a.m. PDT (noon Central). October 28 remains
the project completion target. The rules require a runtime Nebius/NVIDIA integration,
a public licensed code repository, demo/test-build access, a project description,
track selection, tool feedback and a public YouTube demonstration under three minutes.
