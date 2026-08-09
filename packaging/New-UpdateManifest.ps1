param(
    [Parameter(Mandatory = $true)]
    [string]$Version,
    [Parameter(Mandatory = $true)]
    [string]$ZipPath,
    [Parameter(Mandatory = $true)]
    [string]$OutputPath,
    [string]$Notes = "Stability improvements and bug fixes.",
    [string]$AssetName = "",
    [string]$PrivateKeyPath = ""
)

$ErrorActionPreference = "Stop"
$project = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($PrivateKeyPath)) {
    $PrivateKeyPath = Join-Path $project "secrets\update-signing-private.xml"
}
$resolvedZip = (Resolve-Path -LiteralPath $ZipPath).Path
$resolvedKey = (Resolve-Path -LiteralPath $PrivateKeyPath).Path
$file = Get-Item -LiteralPath $resolvedZip
$checksum = (Get-FileHash -LiteralPath $resolvedZip -Algorithm SHA256).Hash.ToLowerInvariant()
if ([string]::IsNullOrWhiteSpace($AssetName)) {
    $AssetName = $file.Name
}
if ([IO.Path]::GetFileName($AssetName) -ne $AssetName) {
    throw "发布资产名称不能包含目录：$AssetName"
}
$encodedAssetName = [Uri]::EscapeDataString($AssetName).Replace("%2F", "/")
$downloadUrl = "https://github.com/Ly233ly/download_video/releases/download/v$Version/$encodedAssetName"

# Keep this property order aligned with the client's sort_keys=True canonical form.
$unsigned = [ordered]@{
    downloadUrl = $downloadUrl
    notes = $Notes
    schemaVersion = 1
    sha256 = $checksum
    size = [long]$file.Length
    version = $Version
}
$canonical = $unsigned | ConvertTo-Json -Compress
# Windows PowerShell escapes HTML-sensitive characters even when the JSON value
# itself contains the literal character. The updater canonicalizes with Python's
# ensure_ascii=False, so normalize those optional JSON escapes before signing.
$canonical = $canonical.Replace('\u003c', '<').Replace('\u003e', '>').Replace('\u0026', '&').Replace('\u0027', "'")
$rsa = New-Object System.Security.Cryptography.RSACryptoServiceProvider
try {
    $rsa.FromXmlString([System.IO.File]::ReadAllText($resolvedKey))
    $signature = $rsa.SignData(
        [System.Text.Encoding]::UTF8.GetBytes($canonical),
        [System.Security.Cryptography.CryptoConfig]::MapNameToOID("SHA256")
    )
    $manifest = [ordered]@{}
    foreach ($entry in $unsigned.GetEnumerator()) {
        $manifest[$entry.Key] = $entry.Value
    }
    $manifest.signature = [Convert]::ToBase64String($signature)
    $parent = Split-Path -Parent $OutputPath
    if ($parent) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }
    [System.IO.File]::WriteAllText(
        $OutputPath,
        ($manifest | ConvertTo-Json -Depth 4),
        (New-Object System.Text.UTF8Encoding($false))
    )
}
finally {
    $rsa.PersistKeyInCsp = $false
    $rsa.Dispose()
}

Write-Output $OutputPath
