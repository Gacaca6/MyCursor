# Make MyCursor start with Windows, with no terminal window.
#
#   powershell -ExecutionPolicy Bypass -File tools\install_startup.ps1
#   powershell -ExecutionPolicy Bypass -File tools\install_startup.ps1 -Mode hand
#   powershell -ExecutionPolicy Bypass -File tools\install_startup.ps1 -Remove
#
# It drops a shortcut in your Startup folder pointing at pythonw.exe, the
# interpreter that runs without a console. After a reboot MyCursor is idle in
# the background -- no camera open, no inference, no window -- and Ctrl+Alt+Space
# wakes it.
#
# No administrator rights needed: the per-user Startup folder is yours.

[CmdletBinding()]
param(
    [ValidateSet("phone", "head", "hand")] [string]$Mode = "phone",
    [switch]$Remove,
    [switch]$StartNow
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$pythonw = Join-Path $root ".venv\Scripts\pythonw.exe"
$startup = [Environment]::GetFolderPath("Startup")
$linkPath = Join-Path $startup "MyCursor.lnk"

function Say([string]$t, [string]$c = "Gray") { Write-Host "  $t" -ForegroundColor $c }

Write-Host ""
Write-Host "=== MyCursor startup ===" -ForegroundColor Cyan
Write-Host ""

# --- remove --------------------------------------------------------------
if ($Remove) {
    if (Test-Path $linkPath) {
        Remove-Item $linkPath -Force
        Say "removed $linkPath" "Green"
        Say "MyCursor will no longer start with Windows." "Green"
    } else {
        Say "nothing to remove - no startup shortcut found" "Yellow"
    }
    Write-Host ""
    exit 0
}

# --- checks --------------------------------------------------------------
if (-not (Test-Path $pythonw)) {
    Say "pythonw.exe not found at:" "Red"
    Say "  $pythonw" "Red"
    Say "Create the venv first:" "Yellow"
    Say "  py -3.12 -m venv .venv" "Gray"
    Say "  .\.venv\Scripts\python.exe -m pip install -r requirements.txt" "Gray"
    Write-Host ""
    exit 1
}

# Confirm the package imports before wiring it to login. A shortcut that
# fails silently at every boot is worse than no shortcut, because pythonw
# has no console to show you the error.
Push-Location $root
try {
    & (Join-Path $root ".venv\Scripts\python.exe") -c "import mycursor" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Say "the mycursor package does not import - fix that first" "Red"
        Write-Host ""
        exit 1
    }
} finally {
    Pop-Location
}
Say "package imports OK" "Green"

# --- build the shortcut --------------------------------------------------
$arguments = "-m mycursor"
if ($Mode) { $arguments += " --mode $Mode" }

$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut($linkPath)
$link.TargetPath = $pythonw
$link.Arguments = $arguments
$link.WorkingDirectory = $root   # -m mycursor only resolves from the project root
$link.WindowStyle = 7            # minimised, belt-and-braces with pythonw
$link.Description = "MyCursor - $Mode input"
$link.Save()

Say "installed $linkPath" "Green"
Say "target    $pythonw $arguments" "DarkGray"
Say "workdir   $root" "DarkGray"

if ($Mode -eq 'phone') {
    Say 'MyCursor Phone will open its pairing window when you sign in.' 'Green'
    Say 'Scan the QR code with your iPhone. Ctrl+Alt+Z pauses; Ctrl+Alt+Q quits.' 'White'
    if ($StartNow) {
        Start-Process -FilePath $pythonw -ArgumentList $arguments -WorkingDirectory $root -WindowStyle Hidden
    }
    exit 0
}

# --- tell the user what to expect ---------------------------------------
$cfg = Join-Path $root "settings.json"
$toggle = "ctrl+alt+space"
$quit = "ctrl+alt+q"
if (Test-Path $cfg) {
    try {
        $json = Get-Content $cfg -Raw | ConvertFrom-Json
        if ($json.hotkeys.toggle_enable) { $toggle = $json.hotkeys.toggle_enable }
        if ($json.hotkeys.quit) { $quit = $json.hotkeys.quit }
    } catch {}
}

Write-Host ""
Say "After your next sign-in MyCursor sits idle in the background:" "White"
Say "  no camera open, no inference, no window." "DarkGray"
Say "  $toggle   wake it / put it back to sleep" "White"
Say "  $quit   quit it entirely" "White"
Write-Host ""
Say "It has no console, so it logs to:" "Gray"
Say "  $(Join-Path $root 'mycursor.log')" "Gray"
Write-Host ""

if ($StartNow) {
    Say "starting it now..." "Gray"
    Start-Process -FilePath $pythonw -ArgumentList $arguments -WorkingDirectory $root -WindowStyle Hidden
    Start-Sleep -Seconds 3
    $running = Get-Process pythonw -ErrorAction SilentlyContinue
    if ($running) { Say "running (PID $($running.Id -join ', '))" "Green" }
    else { Say "it exited - check mycursor.log" "Red" }
    Write-Host ""
}
