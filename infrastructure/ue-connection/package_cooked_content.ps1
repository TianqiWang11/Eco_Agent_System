param(
    [string]$EngineRoot = "D:\UE_5.4",
    [string]$CookedRoot = "",
    [string]$SourcePackage = "",
    [string]$OutputRoot = ""
)

$ErrorActionPreference = "Stop"

function Get-SafeRelativePath {
    param([string]$BasePath, [string]$ChildPath)

    $BaseFullPath = [System.IO.Path]::GetFullPath($BasePath).TrimEnd('\') + '\'
    $ChildFullPath = [System.IO.Path]::GetFullPath($ChildPath)
    if (-not $ChildFullPath.StartsWith($BaseFullPath, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Path is outside its expected root: $ChildFullPath"
    }
    return $ChildFullPath.Substring($BaseFullPath.Length)
}

$UeDataRoot = if ($env:CHEBALING_UE_DATA_ROOT) {
    [System.IO.Path]::GetFullPath($env:CHEBALING_UE_DATA_ROOT)
} else {
    "D:\TQ_Projects\UE_data"
}
$ProjectRoot = Join-Path $UeDataRoot "CheBaLingPlatform"
$PackageRoot = Join-Path $UeDataRoot "packages"
if ([string]::IsNullOrWhiteSpace($CookedRoot)) {
    $CookedRoot = Join-Path $ProjectRoot "Saved\Cooked\Windows"
}
if ([string]::IsNullOrWhiteSpace($SourcePackage)) {
    $SourcePackage = Join-Path $PackageRoot "CheBaLingPlatform_packed\CheBaLingPlatform\Windows"
}
if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    $OutputRoot = Join-Path $PackageRoot "CheBaLingPlatform_rebuilt\Windows"
}

$UnrealPak = Join-Path $EngineRoot "Engine\Binaries\Win64\UnrealPak.exe"
$CookedRoot = (Resolve-Path $CookedRoot).Path
$SourcePackage = (Resolve-Path $SourcePackage).Path

if (-not (Test-Path $UnrealPak -PathType Leaf)) {
    throw "UnrealPak not found: $UnrealPak"
}
if (-not (Test-Path (Join-Path $CookedRoot "CheBaLingPlatform") -PathType Container)) {
    throw "Cooked project directory not found: $CookedRoot\CheBaLingPlatform"
}

$OutputRoot = [System.IO.Path]::GetFullPath($OutputRoot)
if ($OutputRoot -eq $SourcePackage -or $OutputRoot.StartsWith($SourcePackage + [System.IO.Path]::DirectorySeparatorChar)) {
    throw "OutputRoot must be separate from the existing package."
}

Write-Host "Copying the existing runtime shell to the rebuilt package..."
New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null
$OldPakDirectory = Join-Path $SourcePackage "CheBaLingPlatform\Content\Paks"
& robocopy $SourcePackage $OutputRoot /E /XD $OldPakDirectory /R:2 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Host
if ($LASTEXITCODE -ge 8) {
    throw "Robocopy failed with exit code $LASTEXITCODE"
}

$OutputPakDirectory = Join-Path $OutputRoot "CheBaLingPlatform\Content\Paks"
New-Item -ItemType Directory -Force -Path $OutputPakDirectory | Out-Null
$OutputPak = Join-Path $OutputPakDirectory "CheBaLingPlatform-Windows.pak"
$ResponseFile = Join-Path $PSScriptRoot ".runtime\rebuilt_pak_response.txt"
New-Item -ItemType Directory -Force -Path (Split-Path $ResponseFile) | Out-Null

Write-Host "Building the UnrealPak response file..."
$CookedFiles = Get-ChildItem $CookedRoot -Recurse -File | Where-Object {
    $relative = Get-SafeRelativePath $CookedRoot $_.FullName
    -not $relative.StartsWith("CheBaLingPlatform\Metadata\", [System.StringComparison]::OrdinalIgnoreCase)
}

$ResponseLines = @($CookedFiles | ForEach-Object {
    $File = $_
    $RelativePath = (Get-SafeRelativePath $CookedRoot $File.FullName).Replace('\', '/')
    $SourcePath = $File.FullName.Replace('\', '/')
    '"{0}" "../../../{1}"' -f $SourcePath, $RelativePath
})

$ProjectConfigRoot = Join-Path $ProjectRoot "Config"
$ResponseLines += @(Get-ChildItem $ProjectConfigRoot -Recurse -File | ForEach-Object {
    $RelativePath = (Get-SafeRelativePath $ProjectConfigRoot $_.FullName).Replace('\', '/')
    $SourcePath = $_.FullName.Replace('\', '/')
    '"{0}" "../../../CheBaLingPlatform/Config/{1}"' -f $SourcePath, $RelativePath
})
[System.IO.File]::WriteAllLines($ResponseFile, $ResponseLines, [System.Text.UTF8Encoding]::new($false))

Write-Host "Packing $($CookedFiles.Count) cooked files..."
& $UnrealPak $OutputPak "-Create=$ResponseFile" -compress
if ($LASTEXITCODE -ne 0) {
    throw "UnrealPak failed with exit code $LASTEXITCODE"
}

$DaylightExec = Join-Path $PSScriptRoot "ue_daylight.exec"
$WorkerDirectory = Join-Path $OutputRoot "CheBaLingPlatform\Binaries\Win64"
if (Test-Path $DaylightExec -PathType Leaf) {
    Copy-Item $DaylightExec (Join-Path $WorkerDirectory "ue_daylight.exec") -Force
}

$PakSize = [math]::Round((Get-Item $OutputPak).Length / 1GB, 2)
Write-Host "Rebuilt package ready: $OutputRoot"
Write-Host "Pak: $OutputPak ($PakSize GB)"
