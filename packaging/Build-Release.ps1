[CmdletBinding()]
param(
    [string]$Version = "1.4.7",
    [switch]$SkipTests,
    [switch]$SkipFfmpegFetch,
    [switch]$SkipYoutubeResolverFetch
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$python = (Get-Command python -ErrorAction Stop).Source
$node = (Get-Command node -ErrorAction Stop).Source
$cscCandidates = @(
    "$env:WINDIR\Microsoft.NET\Framework64\v4.0.30319\csc.exe",
    "$env:WINDIR\Microsoft.NET\Framework\v4.0.30319\csc.exe"
)
$csc = $cscCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
if (-not $csc) { throw "未找到 .NET Framework C# 编译器。" }

function Assert-UnderProject([string]$Path) {
    $full = [System.IO.Path]::GetFullPath($Path)
    $prefix = $projectRoot.TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar
    if (-not $full.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "拒绝操作项目目录之外的路径：$full"
    }
    return $full
}

function Reset-GeneratedDirectory([string]$Path) {
    $full = Assert-UnderProject $Path
    if (Test-Path -LiteralPath $full) {
        Remove-Item -LiteralPath $full -Recurse -Force
    }
    New-Item -ItemType Directory -Path $full | Out-Null
    return $full
}

function Invoke-Checked([string]$Label, [scriptblock]$Action) {
    Write-Host "[$Label]"
    & $Action
    if ($LASTEXITCODE -ne 0) { throw "$Label 失败，退出码 $LASTEXITCODE" }
}

if ($Version -ne "1.4.7") {
    throw "本分支只允许构建已经同步版本号的 1.4.7。"
}

if (-not $SkipTests) {
    $previousPythonPath = $env:PYTHONPATH
    try {
        $env:PYTHONPATH = Join-Path $projectRoot "src"
        Push-Location $projectRoot
        try {
            Invoke-Checked "Python 全量测试" { & $python -m unittest discover -s tests -p "test_*.py" -v }
            foreach ($script in Get-ChildItem -LiteralPath (Join-Path $projectRoot "chrome-extension") -Recurse -File -Filter "*.js") {
                & $node --check $script.FullName
                if ($LASTEXITCODE -ne 0) { throw "JavaScript 语法检查失败：$($script.FullName)" }
            }
            Get-Content -LiteralPath (Join-Path $projectRoot "chrome-extension\manifest.json") -Raw -Encoding UTF8 | ConvertFrom-Json | Out-Null
            Get-Content -LiteralPath (Join-Path $projectRoot "chrome-extension\manifest.firefox.json") -Raw -Encoding UTF8 | ConvertFrom-Json | Out-Null
        }
        finally {
            Pop-Location
        }
    }
    finally {
        $env:PYTHONPATH = $previousPythonPath
    }
}

if (-not $SkipFfmpegFetch) {
    & (Join-Path $projectRoot "packaging\Fetch-FFmpeg.ps1")
    if ($LASTEXITCODE -ne 0) { throw "FFmpeg 获取或校验失败。" }
}
if (-not $SkipYoutubeResolverFetch) {
    & (Join-Path $projectRoot "packaging\Fetch-YouTube-Resolver.ps1")
    if ($LASTEXITCODE -ne 0) { throw "YouTube 解析工具获取或校验失败。" }
}

$ffmpeg = Join-Path $projectRoot "media-tools\ffmpeg.exe"
$ffprobe = Join-Path $projectRoot "media-tools\ffprobe.exe"
$ytDlp = Join-Path $projectRoot "media-tools\yt-dlp.exe"
$deno = Join-Path $projectRoot "media-tools\deno.exe"
foreach ($required in @($ffmpeg, $ffprobe, $ytDlp, $deno, (Join-Path $projectRoot "media-tools\FFMPEG-VERSION.json"), (Join-Path $projectRoot "media-tools\YOUTUBE-RESOLVER-VERSION.json"))) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "缺少发行资产：$required" }
}

$buildTools = Join-Path $projectRoot ".build-tools\pyinstaller-6.21.0"
$venvPython = Join-Path $buildTools "Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    New-Item -ItemType Directory -Path (Split-Path $buildTools -Parent) -Force | Out-Null
    Invoke-Checked "创建隔离构建环境" { & $python -m venv $buildTools }
}
Invoke-Checked "安装固定 PyInstaller 6.21.0" { & $venvPython -m pip install --disable-pip-version-check --quiet "PyInstaller==6.21.0" }
$installedVersion = (& $venvPython -m PyInstaller --version).Trim()
if ($installedVersion -ne "6.21.0") { throw "PyInstaller 版本错误：$installedVersion" }

$buildRoot = Reset-GeneratedDirectory (Join-Path $projectRoot "build\release-$Version")
$pyiDist = Join-Path $buildRoot "dist"
$pyiWork = Join-Path $buildRoot "work"
New-Item -ItemType Directory -Path $pyiDist, $pyiWork -Force | Out-Null
Push-Location $projectRoot
try {
    Invoke-Checked "构建冻结后端" {
        & $venvPython -m PyInstaller --noconfirm --clean --distpath $pyiDist --workpath $pyiWork (Join-Path $projectRoot "packaging\DownloadTransferStation.spec")
    }
}
finally {
    Pop-Location
}

$releaseOuter = Reset-GeneratedDirectory (Join-Path $projectRoot "release\下载中转站-$Version-Windows-x64")
$releaseRoot = Join-Path $releaseOuter "下载中转站-$Version"
$payload = Join-Path $releaseRoot "app"
$runtimeTarget = Join-Path $payload "runtime\下载中转站后台"
$mediaTarget = Join-Path $payload "media-tools"
New-Item -ItemType Directory -Path $payload, $runtimeTarget, $mediaTarget -Force | Out-Null

$icon = Join-Path $projectRoot "assets\download-transfer-station.ico"
$launcherSource = Join-Path $projectRoot "launcher\Launcher.cs"
$commonCsc = @(
    "/nologo", "/target:winexe", "/optimize+", "/platform:anycpu",
    "/reference:System.dll", "/reference:System.Core.dll",
    "/reference:System.Drawing.dll", "/reference:System.Windows.Forms.dll",
    "/win32icon:$icon"
)
Invoke-Checked "编译桌面启动器" { & $csc @commonCsc "/out:$(Join-Path $payload '下载中转站.exe')" $launcherSource }
Invoke-Checked "编译 IDM 接收器" { & $csc @commonCsc "/out:$(Join-Path $payload 'IdmEagleHook.exe')" $launcherSource }

$frozenRoot = Join-Path $pyiDist "下载中转站后台"
if (-not (Test-Path -LiteralPath (Join-Path $frozenRoot "下载中转站后台.exe") -PathType Leaf)) {
    throw "冻结后端构建不完整。"
}
Copy-Item -Path (Join-Path $frozenRoot "*") -Destination $runtimeTarget -Recurse -Force
Copy-Item -LiteralPath (Join-Path $projectRoot "chrome-extension") -Destination $payload -Recurse -Force
Copy-Item -LiteralPath $ffmpeg, $ffprobe, $ytDlp, $deno, (Join-Path $projectRoot "media-tools\FFMPEG-VERSION.json"), (Join-Path $projectRoot "media-tools\YOUTUBE-RESOLVER-VERSION.json") -Destination $mediaTarget -Force
Copy-Item -LiteralPath (Join-Path $projectRoot "licenses") -Destination $payload -Recurse -Force
Copy-Item -LiteralPath (Join-Path $projectRoot "LICENSE"), (Join-Path $projectRoot "COPYING.md"), (Join-Path $projectRoot "installer\THIRD_PARTY_NOTICES.txt") -Destination $payload -Force

$installerExe = Join-Path $releaseRoot "一键安装.exe"
Invoke-Checked "编译一键安装器" {
    & $csc @commonCsc "/out:$installerExe" (Join-Path $projectRoot "installer\Setup.cs")
}

Copy-Item -LiteralPath (Join-Path $projectRoot "installer\给接收者的使用说明.txt") -Destination (Join-Path $releaseRoot "使用说明.txt") -Force
Copy-Item -LiteralPath (Join-Path $projectRoot "LICENSE"), (Join-Path $projectRoot "COPYING.md"), (Join-Path $projectRoot "installer\THIRD_PARTY_NOTICES.txt") -Destination $releaseRoot -Force
Copy-Item -LiteralPath (Join-Path $projectRoot "licenses") -Destination $releaseRoot -Recurse -Force
Copy-Item -LiteralPath (Join-Path $projectRoot "third_party") -Destination $releaseRoot -Recurse -Force
Copy-Item -LiteralPath (Join-Path $projectRoot "docs\UPSTREAM_PROVENANCE.md") -Destination $releaseRoot -Force

$sourceRoot = Join-Path $releaseRoot "source\download-for-eagle-$Version-src"
New-Item -ItemType Directory -Path $sourceRoot -Force | Out-Null
foreach ($directory in @("assets", "chrome-extension", "docs", "launcher", "licenses", "src", "tests", "third_party")) {
    Copy-Item -LiteralPath (Join-Path $projectRoot $directory) -Destination $sourceRoot -Recurse -Force
}
# Tests and local source runs create Python bytecode caches. They are neither
# corresponding source nor runtime payload, so keep them out of the share ZIP.
Get-ChildItem -LiteralPath $sourceRoot -Directory -Recurse -Force -Filter "__pycache__" |
    Sort-Object FullName -Descending |
    Remove-Item -Recurse -Force
Get-ChildItem -LiteralPath $sourceRoot -File -Recurse -Force -Include "*.pyc", "*.pyo" |
    Remove-Item -Force
$currentVerification = Join-Path $sourceRoot "docs\RELEASE_VERIFICATION_$Version.md"
if (Test-Path -LiteralPath $currentVerification -PathType Leaf) {
    Remove-Item -LiteralPath $currentVerification -Force
}
New-Item -ItemType Directory -Path (Join-Path $sourceRoot "installer"), (Join-Path $sourceRoot "packaging"), (Join-Path $sourceRoot "media-tools") -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $projectRoot "installer\Setup.cs"), (Join-Path $projectRoot "installer\THIRD_PARTY_NOTICES.txt"), (Join-Path $projectRoot "installer\给接收者的使用说明.txt") -Destination (Join-Path $sourceRoot "installer") -Force
Copy-Item -Path (Join-Path $projectRoot "packaging\*.ps1"), (Join-Path $projectRoot "packaging\*.py"), (Join-Path $projectRoot "packaging\*.spec"), (Join-Path $projectRoot "packaging\*.txt") -Destination (Join-Path $sourceRoot "packaging") -Force
Copy-Item -LiteralPath (Join-Path $projectRoot "media-tools\README.md"), (Join-Path $projectRoot "media-tools\FFMPEG-VERSION.json"), (Join-Path $projectRoot "media-tools\YOUTUBE-RESOLVER-VERSION.json") -Destination (Join-Path $sourceRoot "media-tools") -Force
foreach ($file in @(".gitignore", "ACCEPTANCE.md", "AGENTS.md", "CONTEXT.md", "COPYING.md", "DEVELOPMENT.md", "design-qa.md", "LICENSE", "README.md", "SECURITY.md", "STATUS.md", "TASKS.md", "pyproject.toml")) {
    Copy-Item -LiteralPath (Join-Path $projectRoot $file) -Destination $sourceRoot -Force
}

$binaryInventory = foreach ($file in Get-ChildItem -LiteralPath $releaseRoot -Recurse -File | Where-Object { $_.Extension -in @(".exe", ".dll", ".pyd") }) {
    [ordered]@{
        path = $file.FullName.Substring($releaseRoot.Length + 1).Replace("\", "/")
        bytes = $file.Length
        sha256 = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}
$inventoryDocument = [ordered]@{
    product = "下载中转站"
    version = $Version
    architecture = "Windows-x64"
    generatedAtUtc = [DateTime]::UtcNow.ToString("o")
    binaries = @($binaryInventory)
}
$inventoryDocument | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $releaseRoot "BINARY-INVENTORY.json") -Encoding UTF8

$zipPath = Join-Path $releaseOuter "download-transfer-station-$Version-windows-x64.zip"
Compress-Archive -LiteralPath $releaseRoot -DestinationPath $zipPath -CompressionLevel Optimal
$zipHash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
[System.IO.File]::WriteAllText(
    "$zipPath.sha256.txt",
    "$zipHash  $([System.IO.Path]::GetFileName($zipPath))`n",
    (New-Object System.Text.UTF8Encoding($false))
)

[ordered]@{
    version = $Version
    package = $releaseRoot
    zip = $zipPath
    bytes = (Get-Item -LiteralPath $zipPath).Length
    sha256 = $zipHash
    pyinstaller = $installedVersion
    ffmpeg = (Get-Content -LiteralPath (Join-Path $projectRoot "media-tools\FFMPEG-VERSION.json") -Raw -Encoding UTF8 | ConvertFrom-Json).version
    ytDlp = (Get-Content -LiteralPath (Join-Path $projectRoot "media-tools\YOUTUBE-RESOLVER-VERSION.json") -Raw -Encoding UTF8 | ConvertFrom-Json).ytDlpVersion
    deno = (Get-Content -LiteralPath (Join-Path $projectRoot "media-tools\YOUTUBE-RESOLVER-VERSION.json") -Raw -Encoding UTF8 | ConvertFrom-Json).denoVersion
} | ConvertTo-Json -Depth 4
