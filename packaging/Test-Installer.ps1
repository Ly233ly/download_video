[CmdletBinding()]
param(
    [string]$PackageRoot = "",
    [string]$EvidencePath = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$versionSource = Get-Content -LiteralPath (Join-Path $projectRoot "src\idm_eagle_bridge\constants.py") -Raw -Encoding UTF8
$versionMatch = [regex]::Match($versionSource, 'APP_VERSION\s*=\s*"([^"]+)"')
if (-not $versionMatch.Success) { throw "无法从 constants.py 读取当前版本号。" }
$currentVersion = $versionMatch.Groups[1].Value
if ([string]::IsNullOrWhiteSpace($PackageRoot)) {
    $PackageRoot = Join-Path $projectRoot "release\留底下载器-$currentVersion-Windows-x64\留底下载器-$currentVersion"
}
$PackageRoot = [IO.Path]::GetFullPath($PackageRoot)
$installer = Join-Path $PackageRoot "留底安装器.exe"
if (-not (Test-Path -LiteralPath $installer -PathType Leaf)) { throw "找不到待测试安装器：$installer" }
$expectedVersion = $currentVersion
$projectPrefix = $projectRoot.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
$packageDisplay = $PackageRoot
if ($PackageRoot.StartsWith($projectPrefix, [StringComparison]::OrdinalIgnoreCase)) {
    $packageDisplay = $PackageRoot.Substring($projectPrefix.Length).Replace("\", "/")
}

$runId = [Guid]::NewGuid().ToString("N")
$scratchRoot = [IO.Path]::GetFullPath((Join-Path $projectRoot ".scratch"))
$testRoot = [IO.Path]::GetFullPath((Join-Path $scratchRoot ("installer-" + $expectedVersion + "-" + $runId)))
$safePrefix = $scratchRoot.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
if (-not $testRoot.StartsWith($safePrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw "测试目录不在项目专用临时目录中。"
}
New-Item -ItemType Directory -Path $scratchRoot -Force | Out-Null

$resultPath = Join-Path $scratchRoot ("installer-result-" + $runId + ".txt")
$versionKey = "V" + $expectedVersion.Replace(".", "")
$idmSub = "Software\IDMEagleAutoImport\InstallerTest\" + $versionKey + "-" + $runId + "-IDM"
$stateSub = "Software\IDMEagleAutoImport\InstallerTest\" + $versionKey + "-" + $runId + "-State"
$idmPath = "HKCU:\" + $idmSub
$statePath = "HKCU:\" + $stateSub

$env:IDM_EAGLE_INSTALL_ROOT = $testRoot
$env:IDM_EAGLE_TEST_RESULT = $resultPath
$env:IDM_EAGLE_IDM_REGISTRY_SUBKEY = $idmSub
$env:IDM_EAGLE_STATE_REGISTRY_SUBKEY = $stateSub

try {
    $process = Start-Process -FilePath $installer -ArgumentList "--test-install" -Wait -PassThru -WindowStyle Hidden
    if ($process.ExitCode -ne 0) {
        throw "全新安装失败：$(Get-Content -LiteralPath $resultPath -Raw -ErrorAction SilentlyContinue)"
    }
    $fresh = [ordered]@{
        result = ([string](Get-Content -LiteralPath (Join-Path $testRoot "install-test-result.txt") -Raw)).Trim()
        backend = (Test-Path -LiteralPath (Join-Path $testRoot "runtime\留底桌面端后台\留底桌面端后台.exe"))
        ffmpeg = (Test-Path -LiteralPath (Join-Path $testRoot "media-tools\ffmpeg.exe"))
        ffprobe = (Test-Path -LiteralPath (Join-Path $testRoot "media-tools\ffprobe.exe"))
        ytDlp = (Test-Path -LiteralPath (Join-Path $testRoot "media-tools\yt-dlp.exe"))
        deno = (Test-Path -LiteralPath (Join-Path $testRoot "media-tools\deno.exe"))
        extensionVersion = ((Get-Content -LiteralPath (Join-Path $testRoot "chrome-extension\manifest.json") -Raw -Encoding UTF8 | ConvertFrom-Json).version)
        bootstrap = (Test-Path -LiteralPath (Join-Path $testRoot "test-data\pairing-bootstrap.json"))
        idmProgramUnderTestRoot = ([string](Get-ItemProperty -LiteralPath $idmPath).VScannerProgram).StartsWith($testRoot, [StringComparison]::OrdinalIgnoreCase)
    }

    $bootstrapBefore = (Get-FileHash -LiteralPath (Join-Path $testRoot "chrome-extension\bootstrap.js") -Algorithm SHA256).Hash
    Set-Content -LiteralPath (Join-Path $testRoot "obsolete-from-old-version.txt") -Value "remove on successful replacement" -Encoding ASCII
    $process = Start-Process -FilePath $installer -ArgumentList "--test-update" -Wait -PassThru -WindowStyle Hidden
    if ($process.ExitCode -ne 0) {
        throw "成功升级场景失败：$(Get-Content -LiteralPath $resultPath -Raw -ErrorAction SilentlyContinue)"
    }
    $update = [ordered]@{
        obsoleteRemoved = (-not (Test-Path -LiteralPath (Join-Path $testRoot "obsolete-from-old-version.txt")))
        bootstrapRotated = ((Get-FileHash -LiteralPath (Join-Path $testRoot "chrome-extension\bootstrap.js") -Algorithm SHA256).Hash -ne $bootstrapBefore)
        bootstrapCredentialReady = (Test-Path -LiteralPath (Join-Path $testRoot "test-data\pairing-bootstrap.json"))
        backupRemoved = (-not (Test-Path -LiteralPath ($testRoot + ".update-backup")))
    }

    Set-Content -LiteralPath (Join-Path $testRoot "rollback-marker.txt") -Value "must survive" -Encoding ASCII
    $exeHash = (Get-FileHash -LiteralPath (Join-Path $testRoot "留底下载器.exe") -Algorithm SHA256).Hash
    $env:IDM_EAGLE_TEST_UPDATE_FAIL = "1"
    $process = Start-Process -FilePath $installer -ArgumentList "--test-update" -Wait -PassThru -WindowStyle Hidden
    $rollbackExit = $process.ExitCode
    Remove-Item Env:IDM_EAGLE_TEST_UPDATE_FAIL -ErrorAction SilentlyContinue
    if ($rollbackExit -eq 0) { throw "故障注入升级意外成功。" }
    $rollback = [ordered]@{
        failureExit = $rollbackExit
        markerRestored = (Test-Path -LiteralPath (Join-Path $testRoot "rollback-marker.txt"))
        executableRestored = ((Get-FileHash -LiteralPath (Join-Path $testRoot "留底下载器.exe") -Algorithm SHA256).Hash -eq $exeHash)
        backupRemoved = (-not (Test-Path -LiteralPath ($testRoot + ".update-backup")))
    }

    $process = Start-Process -FilePath $installer -ArgumentList "--test-uninstall" -Wait -PassThru -WindowStyle Hidden
    if ($process.ExitCode -ne 0) {
        throw "卸载测试失败：$(Get-Content -LiteralPath $resultPath -Raw -ErrorAction SilentlyContinue)"
    }
    $idmProperties = Get-ItemProperty -LiteralPath $idmPath -ErrorAction SilentlyContinue
    $uninstall = [ordered]@{
        installRemoved = (-not (Test-Path -LiteralPath $testRoot))
        idmProgramRestoredToEmpty = ($null -eq $idmProperties -or -not ($idmProperties.PSObject.Properties.Name -contains "VScannerProgram"))
        stateRemoved = (-not (Test-Path -LiteralPath $statePath))
    }

    $evidence = [ordered]@{
        version = $expectedVersion
        testedAtUtc = [DateTime]::UtcNow.ToString("o")
        packageRoot = $packageDisplay
        fresh = $fresh
        update = $update
        rollback = $rollback
        uninstall = $uninstall
    }
    if ([string]::IsNullOrWhiteSpace($EvidencePath)) {
        $EvidencePath = Join-Path $scratchRoot "installer-$expectedVersion-evidence.json"
    }
    $evidence | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $EvidencePath -Encoding UTF8
    $evidence | ConvertTo-Json -Depth 6
}
finally {
    Remove-Item Env:IDM_EAGLE_TEST_UPDATE_FAIL -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $idmPath -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $statePath -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item Env:IDM_EAGLE_INSTALL_ROOT, Env:IDM_EAGLE_TEST_RESULT, Env:IDM_EAGLE_IDM_REGISTRY_SUBKEY, Env:IDM_EAGLE_STATE_REGISTRY_SUBKEY -ErrorAction SilentlyContinue
}
