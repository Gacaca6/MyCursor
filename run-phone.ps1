param([int]$Port = 8765)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$phonePython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $phonePython)) {
    py -3.12 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 is required. Install it, then run this again.' }
}
& $phonePython -c 'import aiohttp,qrcode,PIL' 2>$null
if ($LASTEXITCODE -ne 0) {
    & $phonePython -m pip install -r requirements-phone.txt
    if ($LASTEXITCODE -ne 0) { throw 'Phone dependencies could not be installed.' }
}
& (Join-Path $PSScriptRoot 'tools\install_shortcut.ps1')
& $phonePython -m mycursor --mode phone --port $Port
