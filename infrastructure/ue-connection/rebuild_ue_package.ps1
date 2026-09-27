param(
    [string]$EngineRoot = "",
    [string]$ArchiveDirectory = "",
    [ValidateSet("Development", "Shipping")]
    [string]$ClientConfiguration = "Development",
    [string[]]$Maps = @(),
    [switch]$CookMapsOnly,
    [switch]$IgnoreLegacyCookErrors,
    [string]$UbtArgs = "-Define:__has_feature(x)=0",
    [switch]$SkipEditorBuild
)

$ErrorActionPreference = "Stop"
$runtimeRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$workspaceRoot = Split-Path -Parent (Split-Path -Parent $runtimeRoot)
$ueDataRoot = if ($env:CHEBALING_UE_DATA_ROOT) {
    [System.IO.Path]::GetFullPath($env:CHEBALING_UE_DATA_ROOT)
} else {
    "D:\TQ_Projects\UE_data"
}
$projectFile = Join-Path $ueDataRoot "CheBaLingPlatform\CheBaLingPlatform.uproject"

if (-not $EngineRoot) {
    $launcherManifest = "C:\ProgramData\Epic\UnrealEngineLauncher\LauncherInstalled.dat"
    if (Test-Path -LiteralPath $launcherManifest) {
        $installations = (Get-Content -LiteralPath $launcherManifest -Raw | ConvertFrom-Json).InstallationList
        $ue54 = $installations | Where-Object AppName -eq "UE_5.4" | Select-Object -First 1
        if ($ue54) { $EngineRoot = $ue54.InstallLocation }
    }
}

if (-not $EngineRoot) {
    throw "UE 5.4 was not found. Install UE 5.4, or pass -EngineRoot with its installation directory."
}

$runUat = Join-Path $EngineRoot "Engine\Build\BatchFiles\RunUAT.bat"
if (-not (Test-Path -LiteralPath $runUat)) {
    throw "RunUAT.bat was not found below EngineRoot: $EngineRoot"
}
if (-not (Test-Path -LiteralPath $projectFile)) {
    throw "Project file was not found: $projectFile"
}

if (-not $ArchiveDirectory) {
    $ArchiveDirectory = Join-Path $ueDataRoot "packages\CheBaLingPlatform_rebuilt"
}
$archiveFullPath = [System.IO.Path]::GetFullPath($ArchiveDirectory)
$ueDataPrefix = $ueDataRoot.TrimEnd('\') + '\'
if (-not $archiveFullPath.StartsWith($ueDataPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "ArchiveDirectory must stay inside the UE data root: $ueDataRoot"
}

New-Item -ItemType Directory -Force -Path $archiveFullPath | Out-Null

$uatArgs = @(
    "BuildCookRun",
    "-project=$projectFile",
    "-noP4",
    "-installed",
    "-utf8output",
    "-platform=Win64",
    "-clientconfig=$ClientConfiguration",
    "-build",
    "-cook",
    "-stage",
    "-pak",
    "-iostore",
    "-archive",
    "-archivedirectory=$archiveFullPath",
    "-prereqs"
)

if ($Maps.Count -gt 0) {
    $uatArgs += "-map=$($Maps -join '+')"
} else {
    $uatArgs += "-allmaps"
}
if ($CookMapsOnly) {
    $uatArgs += "-cookmapsonly"
}
if ($IgnoreLegacyCookErrors) {
    # The source project still contains disabled HttpLibrary/JsonLibrary nodes in
    # BP_GameState. UE records their stale serialized structs as cook errors even
    # though the plugins and that legacy integration are intentionally disabled.
    $uatArgs += "-IgnoreCookErrors"
}
if ($UbtArgs) {
    $uatArgs += "-ubtargs=$UbtArgs"
}
if ($SkipEditorBuild) {
    $uatArgs += "-nocompileeditor"
}

Write-Host "Starting a full UE 5.4 $ClientConfiguration cook/package. This recompiles all material shaders." -ForegroundColor Cyan
Write-Host "Archive: $archiveFullPath" -ForegroundColor Cyan
& $runUat @uatArgs
if ($LASTEXITCODE -ne 0) {
    throw "UE packaging failed with exit code $LASTEXITCODE."
}

Write-Host "UE package completed: $archiveFullPath" -ForegroundColor Green
