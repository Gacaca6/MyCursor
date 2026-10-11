# Run as administrator. Scope input access to this interpreter, TCP port,
# and directly attached subnets; do not change the network's trust category.
param([int]$Port = 8765)
$ErrorActionPreference = 'Stop'
$phoneRoot = Split-Path -Parent $PSScriptRoot
$phoneExecutables = @(
    (Join-Path $phoneRoot '.venv\Scripts\python.exe'),
    (Join-Path $phoneRoot '.venv\Scripts\pythonw.exe'),
    (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'),
    (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\pythonw.exe')
)
try {
    $phoneBase = & (Join-Path $phoneRoot '.venv\Scripts\python.exe') -c 'import sys; print(sys.base_prefix)'
    $phoneExecutables += (Join-Path $phoneBase 'python.exe'), (Join-Path $phoneBase 'pythonw.exe')
    $phoneExecutables = $phoneExecutables | Select-Object -Unique
    $phoneIndex = 0
    foreach ($phoneExecutable in $phoneExecutables) {
        if (-not (Test-Path -LiteralPath $phoneExecutable)) { continue }
        $phoneIndex++
        $phoneRule = "MyCursor-Phone-$Port-$phoneIndex"
        if (Get-NetFirewallRule -Name $phoneRule -ErrorAction SilentlyContinue) { continue }
        New-NetFirewallRule -Name $phoneRule -DisplayName "MyCursor phone touchpad ($Port)" -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Port -RemoteAddress LocalSubnet -Program $phoneExecutable -Profile Any | Out-Null
    }
    'Phone firewall setup complete.' | Set-Content -LiteralPath (Join-Path $phoneRoot 'phone-firewall-status.txt')
} catch {
    $_.Exception.Message | Set-Content -LiteralPath (Join-Path $phoneRoot 'phone-firewall-status.txt')
    throw
}
