[CmdletBinding()]
param(
    [switch]$SkipFrontend
)

$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$testTemp = Join-Path $projectRoot ".sentinel-test-tmp"
$previousTemp = $env:TEMP
$previousTmp = $env:TMP

if (-not (Test-Path $python)) {
    throw "Python environment not found at $python. Create it and install backend requirements first."
}

if (Test-Path $testTemp) {
    Remove-Item -LiteralPath $testTemp -Recurse -Force
}
New-Item -ItemType Directory -Path $testTemp | Out-Null

try {
    # Keep pytest artifacts in the project so verification does not depend on a
    # user-profile temporary directory or leave state outside the repository.
    $env:TEMP = $testTemp
    $env:TMP = $testTemp

    Push-Location $projectRoot
    try {
        & $python -m compileall -q backend\agents backend\api backend\core backend\tools
        if ($LASTEXITCODE -ne 0) { throw "Backend compilation failed." }

        & $python scripts\check_stubs.py
        if ($LASTEXITCODE -ne 0) { throw "Production stub check failed." }

        & $python -m pytest backend\tests --disable-warnings --maxfail=5 -v --tb=short --no-header
        if ($LASTEXITCODE -ne 0) { throw "Backend tests failed." }

        if (-not $SkipFrontend) {
            Push-Location frontend
            try {
                npm.cmd test -- --run
                if ($LASTEXITCODE -ne 0) { throw "Frontend tests failed." }
            }
            finally {
                Pop-Location
            }
        }
    }
    finally {
        Pop-Location
    }
}
finally {
    $env:TEMP = $previousTemp
    $env:TMP = $previousTmp
    if (Test-Path $testTemp) {
        Remove-Item -LiteralPath $testTemp -Recurse -Force -ErrorAction SilentlyContinue
    }
}
