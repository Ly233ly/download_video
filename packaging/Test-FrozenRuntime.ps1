[CmdletBinding()]
param(
    [string]$PackageRoot = "",
    [string]$EvidencePath = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
if ([string]::IsNullOrWhiteSpace($PackageRoot)) {
    $PackageRoot = Join-Path $projectRoot "release\下载中转站-1.4.0-Windows-x64\下载中转站-1.4.0"
}
$PackageRoot = [IO.Path]::GetFullPath($PackageRoot)
$backend = Join-Path $PackageRoot "app\runtime\下载中转站后台\下载中转站后台.exe"
if (-not (Test-Path -LiteralPath $backend -PathType Leaf)) { throw "找不到冻结后端：$backend" }

$runId = [Guid]::NewGuid().ToString("N")
$scratchRoot = [IO.Path]::GetFullPath((Join-Path $projectRoot ".scratch"))
$dataRoot = Join-Path $scratchRoot ("frozen-data-" + $runId)
$downloadRoot = Join-Path $scratchRoot ("frozen-downloads-" + $runId)
New-Item -ItemType Directory -Path $dataRoot, $downloadRoot -Force | Out-Null
$sample = Join-Path $downloadRoot "冻结接收器 样例.mp4"
[IO.File]::WriteAllBytes($sample, [byte[]](0, 1, 2, 3))

$env:IDM_EAGLE_DATA_DIR = $dataRoot
$env:IDM_EAGLE_DOWNLOAD_ROOT = $downloadRoot
$env:IDM_EAGLE_DISABLE_AUTO_START = "1"
$process = $null
try {
    $existingListener = Get-NetTCPConnection -LocalAddress "127.0.0.1" -LocalPort 47652 -State Listen -ErrorAction SilentlyContinue
    if ($null -ne $existingListener) {
        throw "端口 47652 已有助手运行；请先正常退出已安装版本，避免误把其他进程当作待测构建。"
    }
    try {
        Invoke-RestMethod -Uri "http://127.0.0.1:47652/health" -TimeoutSec 1 | Out-Null
        throw "端口 47652 已有助手运行；请先正常退出已安装版本，避免误把其他进程当作待测构建。"
    }
    catch {
        if ($_.Exception.Message -like "端口 47652 已有助手运行*") { throw }
    }
    $process = Start-Process -FilePath $backend -ArgumentList "--headless --interval 60" -PassThru -WindowStyle Hidden
    $health = $null
    $deadline = [DateTime]::UtcNow.AddSeconds(20)
    while ([DateTime]::UtcNow -lt $deadline -and $null -eq $health) {
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:47652/health" -TimeoutSec 1
        }
        catch {
            Start-Sleep -Milliseconds 250
        }
    }
    if ($null -eq $health) { throw "冻结后端未在 20 秒内通过健康检查。" }
    if ($process.HasExited) { throw "待测冻结后端已提前退出，健康响应不属于该进程。" }
    $listener = Get-NetTCPConnection -LocalAddress "127.0.0.1" -LocalPort 47652 -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($null -eq $listener -or [int]$listener.OwningProcess -ne [int]$process.Id) {
        throw "端口 47652 的健康响应不属于待测冻结后端进程。"
    }
    if ([string]$health.version -ne "1.4.0" -or [int]$health.extensionProtocol -ne 1 -or [int]$health.databaseSchema -ne 6 -or -not [bool]$health.mediaReady -or -not [bool]$health.youtubeResolverReady -or [string]$health.downloadEngine -ne "desktop_ffmpeg" -or [string]$health.wechatChannels.state -ne "off" -or [string]$health.wechatChannels.bridgeHash -notmatch "^[0-9a-f]{16}$") {
        $healthSummary = $health | ConvertTo-Json -Compress
        throw "冻结后端健康门字段不符合 1.4.0 要求：$healthSummary"
    }

    $quotedSample = '"' + $sample.Replace('"', '\"') + '"'
    $receiver = Start-Process -FilePath $backend -ArgumentList ("--receive " + $quotedSample) -Wait -PassThru -WindowStyle Hidden
    if ($receiver.ExitCode -ne 0) { throw "冻结 IDM 接收模式失败，退出码 $($receiver.ExitCode)。" }

    Start-Sleep -Milliseconds 300
    $databasePath = Join-Path $dataRoot "bridge.db"
    $pythonCode = "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); print(c.execute('select count(*) from jobs where file_path=?',(sys.argv[2],)).fetchone()[0])"
    $jobCount = [int](& python -c $pythonCode $databasePath $sample)
    if ($LASTEXITCODE -ne 0 -or $jobCount -ne 1) { throw "冻结接收模式未持久化唯一任务。" }

    $evidence = [ordered]@{
        version = "1.4.0"
        testedAtUtc = [DateTime]::UtcNow.ToString("o")
        backend = "app/runtime/下载中转站后台/下载中转站后台.exe"
        processName = $process.ProcessName
        healthVersion = [string]$health.version
        extensionProtocol = [int]$health.extensionProtocol
        databaseSchema = [int]$health.databaseSchema
        mediaReady = [bool]$health.mediaReady
        youtubeResolverReady = [bool]$health.youtubeResolverReady
        downloadEngine = [string]$health.downloadEngine
        wechatChannelsState = [string]$health.wechatChannels.state
        wechatChannelsBridgeHash = [string]$health.wechatChannels.bridgeHash
        receiverExit = $receiver.ExitCode
        receiverJobCount = $jobCount
        ffmpegBundled = (Test-Path -LiteralPath (Join-Path $PackageRoot "app\media-tools\ffmpeg.exe"))
        ffprobeBundled = (Test-Path -LiteralPath (Join-Path $PackageRoot "app\media-tools\ffprobe.exe"))
        ytDlpBundled = (Test-Path -LiteralPath (Join-Path $PackageRoot "app\media-tools\yt-dlp.exe"))
        denoBundled = (Test-Path -LiteralPath (Join-Path $PackageRoot "app\media-tools\deno.exe"))
    }
    if ([string]::IsNullOrWhiteSpace($EvidencePath)) {
        $EvidencePath = Join-Path $scratchRoot "frozen-runtime-1.4.0-evidence.json"
    }
    $evidence | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $EvidencePath -Encoding UTF8
    $evidence | ConvertTo-Json -Depth 4
}
finally {
    if ($null -ne $process -and -not $process.HasExited) {
        Stop-Process -Id $process.Id -Force
        $process.WaitForExit()
    }
    Remove-Item Env:IDM_EAGLE_DATA_DIR, Env:IDM_EAGLE_DOWNLOAD_ROOT, Env:IDM_EAGLE_DISABLE_AUTO_START -ErrorAction SilentlyContinue
}
