Download the **test-build ZIP** and its **SHA256** file from the assets below.
The ZIP contains the reviewed source, prebuilt frontend, MIT license, setup guide,
and BUILD.json with the source commit and individual file hashes. Local credentials,
environment files and investigation reports are excluded.

Windows prerequisites: Python 3.11+, Git 2.28+, Docker Desktop with Linux containers.
Extract the ZIP and, from its causalTrace directory, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1 -Setup -UsePrebuiltFrontend
```

Open http://127.0.0.1:8000. Initial setup downloads Python dependencies and builds
the Docker runner. Node.js is not required for this prebuilt frontend.

Start with **Broken package import / Find the breaking change**. AI investigations
need a separately configured Nebius Token Factory key. Judges should follow
JUDGE_ACCESS.md and the privately supplied access instructions. No key is embedded
in this release. The entrant remains responsible for providing private judge access.

The small demos use labeled synthetic histories. Public upstream selections retain
original commits but are not claimed as reproduced public regressions. Model
diagnosis, reversal experiments and repair verification are distinct outcomes.
Passing tests do not establish that an entire application is bug-free.

This is a local developer test build, not a hosted multi-tenant service. See
SUBMISSION.md, DEVPOST_STORY.md and DEMO_SCRIPT.md for the submission materials.
The video, private judge credentials and final Devpost entry are separate entrant
publication steps; this release does not claim the entry has been submitted.
