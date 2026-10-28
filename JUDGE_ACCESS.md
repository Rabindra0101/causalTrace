# Private judge access - preparation guide

Do not put an API key in this file, GitHub, a release asset, a screenshot or video.
The entrant selected private judge-only Nebius access. Prepare the following in
the private Devpost testing-instructions field (confirm it is not public first).

1. Create a dedicated, revocable Nebius key for judging with sufficient model
   access and credits. Do not reuse the personal development key.
2. Share the key only through the organizer-approved private channel. If Devpost
   offers no private field, contact the organizer for a secure delivery method.
3. Keep access funded and usable through December 15, 2026. Monitor availability
   privately; never publish the key or add a short expiry before judging ends.
4. Send the public test-build download, checksums and exact instructions below.
5. Test the instructions on a clean directory. Revoke the key after judging.

## Text for private testing instructions

Project: CausalTrace - Coding and Agentic Engineering.
Download: use the test-build URL in SUBMISSION.md, then extract the ZIP.
Platform: Windows desktop with Python 3.11+, Git 2.28+ and Docker Desktop running
Linux containers. The prebuilt frontend does not need Node.js. Backend dependencies
and the initial Docker image build need network access.

From the extracted causalTrace directory, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1 -Setup -UsePrebuiltFrontend
```

In a separate PowerShell terminal in that same directory:

```powershell
# Create a local settings file only if absent; do not overwrite an existing one.
if (-not (Test-Path -LiteralPath '.env')) { Copy-Item '.env.example' '.env' }
notepad .env
```

Enter the privately supplied judge key as NEBIUS_API_KEY and retain the NVIDIA
model configured by the example. Save and close the editor. Do not send or publish
this file. Reload http://127.0.0.1:8000 and select Broken package import, then Find
the breaking change. Check Share selected evidence with Nebius for this run, then
run. The selected demo sends only its bundled synthetic source and test evidence.

Expected: collection failure, a passing parent/failing child, a successful
suspected reversal, an unsuccessful unrelated reversal, and model analysis.
Inspect the independent repair result; model success is not guaranteed. Download
the evidence report. For release repair use good HEAD~2 and broken HEAD.

The source archive fallback needs Node.js 22.12+ and uses -Setup without
-UsePrebuiltFrontend. No judge should have to purchase inference credits for the
provided access. The entrant is responsible for supplying the actual private key;
this guide deliberately contains none.
