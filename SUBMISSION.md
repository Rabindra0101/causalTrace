# CausalTrace submission draft

## Description

CausalTrace finds software regressions by comparing working and broken releases,
testing Git history, challenging candidate commits with reversal experiments,
and using NVIDIA Nemotron on Nebius Token Factory to propose code repairs.
Its bounded coding-agent loop tests each patch and iterates on remaining failures
in an isolated workspace, producing an evidence report and a reviewable Git patch.

## Problem and approach

A production update can introduce several bugs in different commits. Logs alone
do not establish which change caused a failure, and an AI-generated patch is not
proof of a repair. CausalTrace measures historical tests, separates causal
experiments from model hypotheses, and accepts incremental repairs only when
tests improve without losing previous passing outcomes. Original repositories
remain unchanged.

Supported execution adapters cover Python, JavaScript/TypeScript, Java and Go.
AI suggestions also address imports, configuration, dependency/build failures,
API contracts, empty/null handling and ordinary logic failures. Model-assisted
runs require explicit consent to send selected evidence to Nebius.

## Judge instructions

Follow README.md to install the backend, build the frontend and Docker runner,
and configure a valid Nebius key locally. Start the API on 127.0.0.1:8000.

1. Choose **Broken package import** and **Full investigation and repair**.
2. Enable evidence sharing and run. Inspect the measured failure, historical
   boundary, suspected/control reversals and independently tested model proposal.
3. Choose **Compare releases and repair regressions** for the same synthetic demo.
   Use `HEAD~2` as the working release and `HEAD` as the broken release. Enable AI
   sharing and inspect the boundary and repair attempts. A correct proposal should
   restore the original import contract; model output is not guaranteed.
4. Download the evidence report and accepted cumulative patch, if any.
5. Repeat with a local repository, compatible runner and known good/bad references.

Synthetic demo commits are labeled generated. Full public upstream repositories
have original dates/IDs, but their pinned original test suites currently show no
reproduced regression. Do not present those as verified failing public projects.

## Suggested demonstration sequence

- Explain a working release followed by a broken update.
- Run the import demo and show actual Git and Docker evidence.
- Show Nemotron's explanation and proposed code change, then its test result.
- Show the release agent controls and downloaded report/patch.
- State the tested scope and the isolation of the source repository.

Keep the recording concise. Disclose trimmed waiting time and whether a displayed
model response is live or mocked. Check current official submission requirements
at https://nebiusglobalaihackathon.devpost.com/rules before publishing.

## Claims and remaining submission items

The automatic regression suite mocks provider responses. The release-agent Docker
experiment measures two bugs introduced in different commits and two cumulative
repairs with unchanged tests. It does not validate live Nemotron behavior for that
experiment. A live judging run requires model access, credit and compatible images.
Tests cannot establish that an app has zero bugs; production failures require
reproducible evidence. Search and repair attempts are bounded as documented.

- Repository: https://github.com/Rabindra0101/causalTrace (MIT).
- Provide the final submission URL, usable judge/demo access and video link.
- Complete actual Nebius/NVIDIA usage feedback without invented metrics.
- Recheck live model access and credits before the demonstration.
