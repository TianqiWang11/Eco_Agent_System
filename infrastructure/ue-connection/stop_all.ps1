$ErrorActionPreference = "Stop"
$runtimeRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$workspaceRoot = Split-Path -Parent (Split-Path -Parent $runtimeRoot)
$ueDataRoot = if ($env:CHEBALING_UE_DATA_ROOT) {
    [System.IO.Path]::GetFullPath($env:CHEBALING_UE_DATA_ROOT)
} else {
    "D:\TQ_Projects\UE_data"
}
$stateFile = Join-Path $runtimeRoot ".runtime\processes.json"

if (-not (Test-Path -LiteralPath $stateFile)) {
    Write-Host "No runtime state created by start_all.ps1 was found."
    exit 0
}

$state = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
$stopped = @{}
foreach ($property in @("ue_pid", "ue_launcher_pid", "portal_pid", "portal_launcher_pid", "signalling_pid", "signalling_launcher_pid")) {
    $processId = $state.$property
    if (-not $processId -or $stopped.ContainsKey([string]$processId)) { continue }
    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if ($process) {
        Stop-Process -Id $processId -ErrorAction SilentlyContinue
        if (-not (Get-Process -Id $processId -ErrorAction SilentlyContinue)) {
            Write-Host "Stopped $property : $processId"
        }
    }
    $stopped[[string]$processId] = $true
}

# Also remove project UE processes left by an interrupted or repeated startup.
$projectUeProcesses = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
        $_.Name -like "CheBaLingPlatform*.exe" -and
        $_.ExecutablePath -and
        $_.ExecutablePath.StartsWith($ueDataRoot, [System.StringComparison]::OrdinalIgnoreCase)
    } |
    Sort-Object { $_.ExecutablePath.Length } -Descending
foreach ($ueProcess in $projectUeProcesses) {
    Stop-Process -Id $ueProcess.ProcessId -ErrorAction SilentlyContinue
}

Write-Host "Unified platform services have been stopped."
