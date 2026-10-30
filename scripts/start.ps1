param([switch]$Setup, [switch]$UsePrebuiltFrontend, [switch]$AccessLog, [ValidateRange(1,65535)][int]$Port = 8000)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
function Assert-Success([string]$Step) {
    if ($LASTEXITCODE -ne 0) { throw "$Step failed (exit $LASTEXITCODE)" }
}
if ($Setup) {
    if ($UsePrebuiltFrontend -and -not (Test-Path -LiteralPath 'frontend\dist\index.html')) {
        throw 'This directory has no prebuilt frontend. Omit -UsePrebuiltFrontend to build it.'
    }
    if (-not (Test-Path -LiteralPath $python)) {
        python -m venv .venv
        Assert-Success 'Virtual environment creation'
    }
    & $python -m pip install -r requirements.txt
    Assert-Success 'Backend dependency installation'
    if (-not $UsePrebuiltFrontend) {
        Push-Location frontend
        try {
            npm.cmd ci
            Assert-Success 'Frontend dependency installation'
            npm.cmd run build
            Assert-Success 'Frontend build'
        } finally { Pop-Location }
    }
    docker build -f Dockerfile.test-runner -t causaltrace-test-runner:local .
    Assert-Success 'Docker runner build'
}
if (-not (Test-Path -LiteralPath $python)) { throw 'Run .\scripts\start.ps1 -Setup first.' }
if (-not (Test-Path -LiteralPath 'frontend\dist\index.html')) { throw 'Frontend build missing. Run .\scripts\start.ps1 -Setup.' }
Write-Host "Open http://127.0.0.1:$Port ; Ctrl+C stops the server."
$serverArguments = @('-m', 'uvicorn', 'causaltrace.api:app', '--host', '127.0.0.1', '--port', "$Port")
if (-not $AccessLog) { $serverArguments += '--no-access-log' }
& $python @serverArguments
Assert-Success 'Backend'
