[CmdletBinding()]
param(
    [switch]$SkipBuild,
    [switch]$PruneOldVersions
)

$ErrorActionPreference = 'Stop'
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$buildDll = Join-Path $projectRoot 'build\windows-x86\native\directshow_source\Release\SSKJDirectShowCamera.dll'
$deployDirectory = 'C:\ProgramData\SSKJVirtualCamera\bin\x86'
$regsvr32 = "$env:SystemRoot\SysWOW64\regsvr32.exe"

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'DirectShow installation must run from an elevated PowerShell window.'
}

if (-not $SkipBuild) {
    & (Join-Path $PSScriptRoot 'build-directshow.ps1')
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
if (-not (Test-Path -LiteralPath $buildDll)) { throw "x86 DirectShow DLL not found: $buildDll" }

New-Item -ItemType Directory -Force -Path $deployDirectory | Out-Null
& "$env:SystemRoot\System32\icacls.exe" $deployDirectory /inheritance:r /grant:r `
    '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' '*S-1-5-32-545:(OI)(CI)RX' /T /C | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Failed to secure x86 deployment directory (icacls exit $LASTEXITCODE)" }

$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $buildDll).Hash.Substring(0, 12).ToLowerInvariant()
$dll = Join-Path $deployDirectory "SSKJDirectShowCamera-$hash.dll"
if (-not (Test-Path -LiteralPath $dll)) { Copy-Item -LiteralPath $buildDll -Destination $dll }
& "$env:SystemRoot\System32\icacls.exe" $dll /inheritance:r /grant:r `
    '*S-1-5-18:F' '*S-1-5-32-544:F' '*S-1-5-32-545:RX' /C | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Failed to secure x86 DirectShow DLL (icacls exit $LASTEXITCODE)" }

& $regsvr32 /s $dll
if ($LASTEXITCODE -ne 0) { throw "32-bit regsvr32 failed with exit code $LASTEXITCODE" }

if ($PruneOldVersions) {
    Get-ChildItem -LiteralPath $deployDirectory -Filter 'SSKJDirectShowCamera-*.dll' -File |
        Where-Object FullName -ne $dll |
        ForEach-Object {
            try { Remove-Item -LiteralPath $_.FullName -Force -ErrorAction Stop }
            catch { Write-Warning "Could not remove old DirectShow DLL $($_.FullName): $($_.Exception.Message)" }
        }
}

Write-Output "Installed x86 SSKJ DirectShow Camera from $dll"
