param(
    [string]$UeExecutable = "",
    [int]$PortalPort = 8000,
    [int]$StreamHttpPort = 8080,
    [int]$StreamerPort = 8888,
    [int]$StreamWidth = 1440,
    [int]$StreamHeight = 810,
    [int]$StreamFps = 50,
    [int]$RenderScale = 85,
    [int]$StreamMinBitrate = 1500000,
    [int]$StreamStartBitrate = 6000000,
    [int]$StreamMaxBitrate = 12000000,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$runtimeRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$workspaceRoot = Split-Path -Parent (Split-Path -Parent $runtimeRoot)
$ueDataRoot = if ($env:CHEBALING_UE_DATA_ROOT) {
    [System.IO.Path]::GetFullPath($env:CHEBALING_UE_DATA_ROOT)
} else {
    "D:\TQ_Projects\UE_data"
}
$aiRoot = $workspaceRoot
$packageRoot = Join-Path $ueDataRoot "packages"
$infraRoot = Join-Path $ueDataRoot "PixelStreamingInfrastructure-UE5.4"
$signallingRoot = Join-Path $infraRoot "SignallingWebServer"
$nodeExe = Join-Path $signallingRoot "platform_scripts\cmd\node\node.exe"
$pythonExe = Join-Path $aiRoot ".venv\Scripts\python.exe"
$daylightExecFile = "Win64/ue_daylight.exec"
$stateRoot = Join-Path $runtimeRoot ".runtime"
$logRoot = Join-Path $stateRoot "logs"

New-Item -ItemType Directory -Force -Path $stateRoot, $logRoot | Out-Null

function Test-ListeningPort([int]$Port) {
    return [bool](Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
}

function Get-ListeningProcessId([int]$Port) {
    $connection = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($connection) { return [int]$connection.OwningProcess }
    return $null
}

function Find-PackagedUeExecutable {
    $preferredCandidates = @(
        # UE 5.4 build verified on 2026-09-21 after copying all 1,383
        # database-matched tree identifiers into runtime Actor Tags.
        (Join-Path $packageRoot "CheBaLingPlatform_prediction_tagged_20260921\Windows\CheBaLingPlatform.exe"),
        # UE 5.4 build verified on 2026-09-20 with LCC4Unreal,
        # PredictionSceneBridge and TreeSimulation loaded at runtime.
        (Join-Path $packageRoot "CheBaLingPlatform_prediction_20260920b\Windows\CheBaLingPlatform.exe"),
        (Join-Path $packageRoot "CheBaLingPlatform_agent\Windows\CheBaLingPlatform.exe"),
        (Join-Path $packageRoot "CheBaLingPlatform_fixed_full\Windows\CheBaLingPlatform.exe"),
        (Join-Path $packageRoot "CheBaLingPlatform_fixed\Windows\CheBaLingPlatform.exe"),
        # The UE 5.4.4 Development stage is currently the verified stable
        # Pixel Streaming build. Keep the Shipping stage as a fallback.
        (Join-Path $packageRoot "CheBaLingPlatform_debug\Windows\CheBaLingPlatform.exe"),
        (Join-Path $packageRoot "CheBaLingPlatform_staged\Windows\CheBaLingPlatform.exe"),
        (Join-Path $packageRoot "CheBaLingPlatform_rebuilt\Windows\CheBaLingPlatform.exe"),
        (Join-Path $packageRoot "CheBaLingPlatform_packed\CheBaLingPlatform\Windows\CheBaLingPlatform.exe")
    )
    foreach ($candidate in $preferredCandidates) {
        if (Test-Path -LiteralPath $candidate) { return $candidate }
    }

    foreach ($directory in Get-ChildItem -LiteralPath $packageRoot -Directory -ErrorAction SilentlyContinue) {
        $match = Get-ChildItem -LiteralPath $directory.FullName `
            -Recurse -File -Filter "CheBaLingPlatform.exe" -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($match) { return $match.FullName }
    }
    return ""
}

function Wait-HttpReady([string]$Url, [int]$TimeoutSeconds = 45) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) { return $true }
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    return $false
}

function Wait-UeWorkerProcessId([int]$LauncherProcessId, [int]$TimeoutSeconds = 90) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $worker = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
            Where-Object {
                $_.ParentProcessId -eq $LauncherProcessId -and
                $_.Name -like "CheBaLingPlatform*.exe"
            } |
            Select-Object -First 1
        if ($worker) { return [int]$worker.ProcessId }
        Start-Sleep -Milliseconds 500
    }
    return $null
}

function Get-ProjectUeProcesses {
    return Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -like "CheBaLingPlatform*.exe" -and
            $_.ExecutablePath -and
            $_.ExecutablePath.StartsWith($ueDataRoot, [System.StringComparison]::OrdinalIgnoreCase)
        }
}

if (-not (Test-Path -LiteralPath $nodeExe)) {
    throw "Pixel Streaming Node runtime not found: $nodeExe"
}
if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "Platform Python runtime not found: $pythonExe"
}

if (-not $UeExecutable) {
    $UeExecutable = Find-PackagedUeExecutable
    if ($UeExecutable) {
        Write-Host "Found packaged UE application: $UeExecutable" -ForegroundColor Green
    }
}

$processState = [ordered]@{
    started_at = (Get-Date).ToString("o")
    portal_port = $PortalPort
    stream_http_port = $StreamHttpPort
    streamer_port = $StreamerPort
    stream_width = $StreamWidth
    stream_height = $StreamHeight
    stream_fps = $StreamFps
    render_scale = $RenderScale
    stream_min_bitrate = $StreamMinBitrate
    stream_start_bitrate = $StreamStartBitrate
    stream_max_bitrate = $StreamMaxBitrate
    signalling_pid = $null
    signalling_launcher_pid = $null
    portal_pid = $null
    portal_launcher_pid = $null
    ue_pid = $null
    ue_launcher_pid = $null
}

if (Test-ListeningPort $StreamHttpPort) {
    Write-Host "Pixel Streaming HTTP port $StreamHttpPort is already listening; skipping startup." -ForegroundColor Yellow
    $processState.signalling_pid = Get-ListeningProcessId $StreamHttpPort
} else {
    $signallingOut = Join-Path $logRoot "signalling.out.log"
    $signallingErr = Join-Path $logRoot "signalling.err.log"
    $signallingArgs = @(
        "cirrus.js",
        "--HttpPort=$StreamHttpPort",
        "--StreamerPort=$StreamerPort"
    )
    $signalling = Start-Process -FilePath $nodeExe `
        -ArgumentList $signallingArgs `
        -WorkingDirectory $signallingRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $signallingOut `
        -RedirectStandardError $signallingErr `
        -PassThru
    $processState.signalling_launcher_pid = $signalling.Id
}

$streamUrl = "http://127.0.0.1:$StreamHttpPort"
if (-not (Wait-HttpReady $streamUrl 45)) {
    throw "Pixel Streaming signalling service is not ready. Check logs: $logRoot"
}
if ($processState.signalling_launcher_pid) {
    $processState.signalling_pid = Get-ListeningProcessId $StreamHttpPort
}

if (Test-ListeningPort $PortalPort) {
    Write-Host "Portal port $PortalPort is already listening; skipping startup." -ForegroundColor Yellow
    $processState.portal_pid = Get-ListeningProcessId $PortalPort
} else {
    $env:PIXEL_STREAMING_HTTP_PORT = [string]$StreamHttpPort
    $env:PIXEL_STREAMING_PLAYER_PATH = "/uiless.html"
    $env:PIXEL_STREAMING_AUTO_CONNECT = "true"
    $portalOut = Join-Path $logRoot "portal.out.log"
    $portalErr = Join-Path $logRoot "portal.err.log"
    $portal = Start-Process -FilePath $pythonExe `
        -ArgumentList @("-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", [string]$PortalPort) `
        -WorkingDirectory $aiRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $portalOut `
        -RedirectStandardError $portalErr `
        -PassThru
    $processState.portal_launcher_pid = $portal.Id
}

$portalUrl = "http://127.0.0.1:$PortalPort"
# Cold-starting the Excel-backed service can take longer while pandas loads
# the source workbooks, especially immediately after a UE package build.
if (-not (Wait-HttpReady "$portalUrl/health" 180)) {
    throw "Portal service is not ready. Check logs: $logRoot"
}
if ($processState.portal_launcher_pid) {
    $processState.portal_pid = Get-ListeningProcessId $PortalPort
}

if ($UeExecutable) {
    $resolvedUe = (Resolve-Path -LiteralPath $UeExecutable).Path
    $existingUeProcesses = @(Get-ProjectUeProcesses)
    if ($existingUeProcesses.Count -gt 0) {
        $existingLauncher = $existingUeProcesses |
            Where-Object { $_.ExecutablePath -eq $resolvedUe } |
            Select-Object -First 1
        $existingWorker = $existingUeProcesses |
            Where-Object { $_.ExecutablePath -like "*\Binaries\Win64\CheBaLingPlatform*.exe" } |
            Select-Object -First 1
        $processState.ue_launcher_pid = if ($existingLauncher) { [int]$existingLauncher.ProcessId } else { $null }
        $processState.ue_pid = if ($existingWorker) { [int]$existingWorker.ProcessId } else { [int]$existingUeProcesses[0].ProcessId }
        Write-Host "CheBaLingPlatform is already running; skipping duplicate UE startup." -ForegroundColor Yellow
    } else {
    # Presentation profile: prioritize responsive navigation and a bright, clear forest scene.
    # The cloud/fog/particle overrides also prevent the packaged build's failed weather request
    # from leaving users in its dark rainy fallback state.
    $renderCommands = @(
        "t.MaxFPS $StreamFps",
        "r.ScreenPercentage $RenderScale",
        "r.MotionBlurQuality 0",
        "sg.ViewDistanceQuality 2",
        "sg.ShadowQuality 1",
        "sg.GlobalIlluminationQuality 1",
        "sg.ReflectionQuality 1",
        # Keep low-cost effects, then restore the cooked High material permutation.
        # EffectsQuality 0 alone switches materials to Low and invalidates shader-map IDs.
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
        "-d3d11",
        "-NoVSync",
        "-USEALLAVAILABLECORES",
        "-ExecCmds=`"$renderCommands`"",
        "-Exec=$daylightExecFile",
        "-Unattended"
    )
    $ue = Start-Process -FilePath $resolvedUe -ArgumentList $ueArgs -WorkingDirectory (Split-Path -Parent $resolvedUe) -PassThru
    $processState.ue_launcher_pid = $ue.Id
    $ueWorkerProcessId = Wait-UeWorkerProcessId $ue.Id 90
    $processState.ue_pid = if ($ueWorkerProcessId) { $ueWorkerProcessId } else { $ue.Id }
    if (-not $ueWorkerProcessId) {
        Write-Host "UE launcher started but its render process was not found within 90 seconds." -ForegroundColor Yellow
    }
    }
} else {
    Write-Host "No packaged UE executable was supplied. The player will wait for UE on port $StreamerPort." -ForegroundColor Yellow
}

$processState | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $stateRoot "processes.json") -Encoding UTF8

if ($UeExecutable) {
    $streamerCheck = Join-Path $runtimeRoot "smoke_streamer.js"
    $webSocketModule = Join-Path $signallingRoot "node_modules\ws"
    if (-not (Test-Path -LiteralPath $streamerCheck)) {
        throw "Pixel Streaming health check is missing: $streamerCheck"
    }

    Write-Host "Waiting for UE to register with Pixel Streaming..." -ForegroundColor Cyan
    & $nodeExe $streamerCheck $StreamHttpPort 120000 $webSocketModule
    if ($LASTEXITCODE -ne 0) {
        throw "UE process started but did not register with Pixel Streaming on port $StreamerPort."
    }
    Write-Host "UE streamer registered successfully." -ForegroundColor Green
}

Write-Host ""
Write-Host "Unified portal: $portalUrl" -ForegroundColor Green
Write-Host "Pixel Streaming player: $streamUrl" -ForegroundColor Green
Write-Host "UE signalling target: ws://127.0.0.1:$StreamerPort" -ForegroundColor Green
Write-Host "Logs: $logRoot"

if (-not $NoBrowser) {
    Start-Process $portalUrl
}
