$ErrorActionPreference = 'Stop'
$shortcutRoot = Split-Path -Parent $PSScriptRoot
$shortcutPython = Join-Path $shortcutRoot '.venv\Scripts\pythonw.exe'
if (-not (Test-Path -LiteralPath $shortcutPython)) { throw 'Run Start Phone Touchpad.cmd first to install Python dependencies.' }
$shortcutShell = New-Object -ComObject WScript.Shell
$shortcutFile = Join-Path ([Environment]::GetFolderPath('Desktop')) 'MyCursor Phone Touchpad.lnk'
$shortcut = $shortcutShell.CreateShortcut($shortcutFile)
$shortcut.TargetPath = $shortcutPython
$shortcut.Arguments = '-m mycursor --mode phone'
$shortcut.WorkingDirectory = $shortcutRoot
$shortcut.Description = 'Connect your iPhone or Android phone as a touchpad'
$shortcut.Save()
Write-Host 'Desktop shortcut installed: MyCursor Phone Touchpad'
