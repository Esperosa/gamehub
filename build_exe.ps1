[CmdletBinding()]
param(
    [switch]$NoClean
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
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
        [Parameter(Mandatory = $true)]
        [string]$Fallback
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

$hash = Get-GitValue -Arguments @("rev-parse", "--short", "HEAD") -Fallback "local"
$status = Get-GitValue -Arguments @("status", "--porcelain") -Fallback ""
$dirty = if ([string]::IsNullOrWhiteSpace($status)) { "" } else { "_dirty" }
$env:GAMEHUB_EXE_NAME = "GameHub_v${hash}${dirty}_allmods"

Write-Host "Using exe name: $env:GAMEHUB_EXE_NAME"

& $python -m pip install --upgrade pyinstaller
if ($LASTEXITCODE -ne 0) {
    throw "Failed to install/upgrade pyinstaller."
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

$exePath = Join-Path $repoRoot ("dist\" + $env:GAMEHUB_EXE_NAME + ".exe")
if (-not (Test-Path $exePath)) {
    throw "Build finished, but exe not found: $exePath"
}

Write-Host "Build OK: $exePath"
