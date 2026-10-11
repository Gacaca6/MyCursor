# Launch MyCursor. Phone touchpad is now the default; -Hand selects webcam mode.
param([string]$Mode = "", [switch]$Hand, [switch]$NoPreview, [switch]$NoPointer)
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot
if (-not $Hand -and $Mode -notin @('head', 'hand')) {
    & (Join-Path $PSScriptRoot 'run-phone.ps1')
    exit $LASTEXITCODE
}
$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host "No venv found. Creating one..." -ForegroundColor Yellow
    py -3.12 -m venv .venv
    & $py -m pip install --upgrade pip
    & $py -m pip install -r requirements.txt
}
$cliArgs = @()
if ($Hand)      { $cliArgs += @("--mode", "hand") }
elseif ($Mode)  { $cliArgs += @("--mode", $Mode) }
if ($NoPreview) { $cliArgs += "--no-preview" }
if ($NoPointer) { $cliArgs += "--no-pointer" }
& $py -m mycursor @cliArgs
