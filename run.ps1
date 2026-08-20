# Run JobScanner from the repo root with the local venv when present.
# Usage:
#   .\run.ps1
#   .\run.ps1 -Channel offerclaw
#   .\run.ps1 --days 10
# Extra args are passed through to scanner/main.py.

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
Set-Location $Root

$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (Test-Path $VenvPython) {
    $Python = $VenvPython
} else {
    $Python = "python"
}

& $Python (Join-Path $Root "scanner\main.py") @args
exit $LASTEXITCODE
