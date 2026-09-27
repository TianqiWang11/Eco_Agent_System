param(
    [int]$StreamerPort = 8888,
    [int]$StreamWidth = 1440,
    [int]$StreamHeight = 810,
    [int]$StreamFps = 50,
    [int]$RenderScale = 85,
    [int]$StreamMinBitrate = 1500000,
    [int]$StreamStartBitrate = 6000000,
    [int]$StreamMaxBitrate = 12000000,
    [ValidateSet("D3D12", "D3D11")]
    [string]$GraphicsRhi = "D3D11"
)

$ErrorActionPreference = "Stop"
$runtimeRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$workspaceRoot = Split-Path -Parent (Split-Path -Parent $runtimeRoot)
$ueDataRoot = if ($env:CHEBALING_UE_DATA_ROOT) {
    [System.IO.Path]::GetFullPath($env:CHEBALING_UE_DATA_ROOT)
} else {
    "D:\TQ_Projects\UE_data"
}
$packageRoot = Join-Path $ueDataRoot "packages"
$fullFixedExecutable = Join-Path $packageRoot "CheBaLingPlatform_fixed_full\Windows\CheBaLingPlatform.exe"
$fixedExecutable = Join-Path $packageRoot "CheBaLingPlatform_fixed\Windows\CheBaLingPlatform.exe"
$developmentExecutable = Join-Path $packageRoot "CheBaLingPlatform_debug\Windows\CheBaLingPlatform.exe"
$stagedExecutable = Join-Path $packageRoot "CheBaLingPlatform_staged\Windows\CheBaLingPlatform.exe"
$rebuiltExecutable = Join-Path $packageRoot "CheBaLingPlatform_rebuilt\Windows\CheBaLingPlatform.exe"
$legacyExecutable = Join-Path $packageRoot "CheBaLingPlatform_packed\CheBaLingPlatform\Windows\CheBaLingPlatform.exe"
$ueExecutable = if (Test-Path -LiteralPath $fullFixedExecutable) {
    $fullFixedExecutable
} elseif (Test-Path -LiteralPath $fixedExecutable) {
    $fixedExecutable
} elseif (Test-Path -LiteralPath $developmentExecutable) {
    $developmentExecutable
} elseif (Test-Path -LiteralPath $stagedExecutable) {
    $stagedExecutable
} elseif (Test-Path -LiteralPath $rebuiltExecutable) {
    $rebuiltExecutable
} else {
    $legacyExecutable
}
$daylightExecFile = "Win64/ue_daylight.exec"

if (-not (Test-Path -LiteralPath $ueExecutable)) {
    throw "Packaged UE application not found: $ueExecutable"
}

$projectProcesses = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
        $_.Name -like "CheBaLingPlatform*.exe" -and
        $_.ExecutablePath -and
        $_.ExecutablePath.StartsWith($ueDataRoot, [System.StringComparison]::OrdinalIgnoreCase)
    })

foreach ($process in $projectProcesses) {
    Stop-Process -Id ([int]$process.ProcessId) -Force -ErrorAction SilentlyContinue
}

$deadline = (Get-Date).AddSeconds(15)
do {
    $remaining = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -like "CheBaLingPlatform*.exe" -and
            $_.ExecutablePath -and
            $_.ExecutablePath.StartsWith($ueDataRoot, [System.StringComparison]::OrdinalIgnoreCase)
        })
    if ($remaining.Count -eq 0) { break }
    Start-Sleep -Milliseconds 250
} while ((Get-Date) -lt $deadline)

if ($remaining.Count -gt 0) {
    throw "The previous UE process did not stop in time."
}

$renderCommands = @(
    "t.MaxFPS $StreamFps",
    "r.ScreenPercentage $RenderScale",
    "r.MotionBlurQuality 0",
    "sg.ViewDistanceQuality 2",
    "sg.ShadowQuality 1",
    "sg.GlobalIlluminationQuality 1",
    "sg.ReflectionQuality 1",
    # Keep low-cost effects while aligning materials with the cooked High shaders.
    "sg.EffectsQuality 0",
    "r.MaterialQualityLevel 1",
    "sg.FoliageQuality 1",
    "sg.TextureQuality 2",
    "r.VolumetricCloud 0",
    "r.VolumetricFog 0",
    "r.Fog 0",
    "r.EmitterSpawnRateScale 0",
    "r.LightFunctionQuality 0",
    "r.BloomQuality 0",
    "r.LensFlareQuality 0",
    "r.DefaultFeature.Bloom 0",
    "r.DefaultFeature.LensFlare 0",
    "r.EyeAdaptationQuality 2",
    "r.DefaultFeature.AutoExposure 1",
    "r.AmbientOcclusionLevels 0",
    "r.VSync 0",
    "r.OneFrameThreadLag 0"
) -join ","
$ueArgs = @(
    "-PixelStreamingURL=ws://127.0.0.1:$StreamerPort",
    "-RenderOffscreen",
    "-AudioMixer",
    "-ForceRes",
    "-ResX=$StreamWidth",
    "-ResY=$StreamHeight",
    "-PixelStreamingWebRTCMaxFps=$StreamFps",
    "-PixelStreamingWebRTCMinBitrate=$StreamMinBitrate",
    "-PixelStreamingWebRTCStartBitrate=$StreamStartBitrate",
    "-PixelStreamingWebRTCMaxBitrate=$StreamMaxBitrate",
    "-PixelStreamingEncoderCodec=H264",
    "-AllowPixelStreamingCommands",
    $(if ($GraphicsRhi -eq "D3D11") { "-d3d11" } else { "-d3d12" }),
    "-NoVSync",
    "-USEALLAVAILABLECORES",
    "-ExecCmds=`"$renderCommands`"",
    "-Exec=$daylightExecFile",
    "-Unattended"
)

$ue = Start-Process -FilePath $ueExecutable `
    -ArgumentList $ueArgs `
    -WorkingDirectory (Split-Path -Parent $ueExecutable) `
    -PassThru

$workerId = $null
$deadline = (Get-Date).AddSeconds(30)
while ((Get-Date) -lt $deadline) {
    $worker = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.ParentProcessId -eq $ue.Id -and
            $_.Name -like "CheBaLingPlatform*.exe"
        } |
        Select-Object -First 1
    if ($worker) {
        $workerId = [int]$worker.ProcessId
        break
    }
    if ($ue.HasExited) {
        throw "UE exited before its render process was ready."
    }
    Start-Sleep -Milliseconds 250
}

if (-not $workerId) {
    throw "UE render process was not ready in time."
}

Write-Output "UE_RESTARTED launcher=$($ue.Id) worker=$workerId"
