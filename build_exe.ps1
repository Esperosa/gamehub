[CmdletBinding()]
param(
    [string]$Version = "",
    [switch]$NoClean
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptPath = Join-Path $PSScriptRoot "scripts\build_windows.ps1"
if (-not (Test-Path $scriptPath)) {
    throw "Missing script: $scriptPath"
}

& $scriptPath -Version $Version -NoClean:$NoClean
