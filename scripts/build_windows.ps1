[CmdletBinding()]
param(
    [string]$Version = "",
    [switch]$NoClean
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repoRoot

$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

$specPath = Join-Path $repoRoot "GameHub_allmods.spec"
if (-not (Test-Path $specPath)) {
    throw "Missing spec file: $specPath"
}

function Get-GitValue {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [string]$Fallback = ""
    )

    try {
        $value = (& git @Arguments 2>$null)
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($value)) {
            return $Fallback
        }
        return $value.Trim()
    } catch {
        return $Fallback
    }
}

if ([string]::IsNullOrWhiteSpace($Version)) {
    $Version = Get-GitValue -Arguments @("describe", "--tags", "--always") -Fallback "dev"
}
$Version = $Version.Trim()
$VersionSafe = ($Version -replace "[^0-9A-Za-z._-]", "_")

$hash = Get-GitValue -Arguments @("rev-parse", "--short", "HEAD") -Fallback "local"
$status = Get-GitValue -Arguments @("status", "--porcelain") -Fallback ""
$dirty = if ([string]::IsNullOrWhiteSpace($status)) { "" } else { "_dirty" }

$exeName = "GameHub_${VersionSafe}_${hash}${dirty}_windows_x64"
$env:GAMEHUB_EXE_NAME = $exeName

Write-Host "Building Windows artifact: $exeName"

if (Test-Path "requirements-lock.txt") {
    & $python -m pip install --upgrade pip
    & $python -m pip install -r requirements-lock.txt
} else {
    & $python -m pip install --upgrade pip
    & $python -m pip install -r requirements-dev.txt
}
if ($LASTEXITCODE -ne 0) {
    throw "Dependency install failed."
}

$buildArgs = @("-m", "PyInstaller", "--noconfirm")
if (-not $NoClean) {
    $buildArgs += "--clean"
}
$buildArgs += "GameHub_allmods.spec"

& $python @buildArgs
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed."
}

$distDir = Join-Path $repoRoot "dist"
$exePath = Join-Path $distDir ($exeName + ".exe")
if (-not (Test-Path $exePath)) {
    throw "Build finished, but exe not found: $exePath"
}

$zipPath = Join-Path $distDir ($exeName + ".zip")
if (Test-Path $zipPath) {
    Remove-Item $zipPath -Force
}
Compress-Archive -Path $exePath -DestinationPath $zipPath

$shaFile = Join-Path $distDir "SHA256SUMS_windows.txt"
$exeHash = (Get-FileHash -Algorithm SHA256 $exePath).Hash.ToLower()
$zipHash = (Get-FileHash -Algorithm SHA256 $zipPath).Hash.ToLower()
"$exeHash *$($exeName).exe" | Set-Content -Path $shaFile -Encoding ascii
"$zipHash *$($exeName).zip" | Add-Content -Path $shaFile -Encoding ascii

Write-Host "Build OK: $exePath"
Write-Host "ZIP OK:   $zipPath"
Write-Host "SHA256:   $shaFile"
