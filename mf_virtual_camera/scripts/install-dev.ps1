[CmdletBinding()]
param(
    [switch]$SkipBuild,
    [switch]$RefreshFrameServer,
    [switch]$PruneOldVersions
)

$ErrorActionPreference = 'Stop'
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$buildDll = [System.IO.Path]::GetFullPath((Join-Path $projectRoot 'build\windows-x64\native\media_source\Release\SSKJVirtualCameraMediaSource.dll'))
$registrar = [System.IO.Path]::GetFullPath((Join-Path $projectRoot 'build\windows-x64\native\registrar\Release\SSKJVirtualCameraRegistrar.exe'))
$regsvr32 = [System.IO.Path]::GetFullPath((Join-Path $env:SystemRoot 'System32\regsvr32.exe'))
$runtimeRoot = 'C:\ProgramData\SSKJVirtualCamera'
$deployDirectory = Join-Path $runtimeRoot 'bin'
$clsidPath = 'Registry::HKEY_LOCAL_MACHINE\Software\Classes\CLSID\{7C81C5D6-7424-47DC-8F4D-12261522C239}\InprocServer32'

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Development installation must run from an elevated PowerShell window.'
}

if (-not $SkipBuild) {
    & (Join-Path $PSScriptRoot 'build.ps1') -Configuration Release
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
if (-not (Test-Path -LiteralPath $buildDll)) { throw "MediaSource DLL not found: $buildDll" }
if (-not (Test-Path -LiteralPath $registrar)) { throw "Registrar not found: $registrar" }

& (Join-Path $PSScriptRoot 'prepare-runtime.ps1') | Out-Null
New-Item -ItemType Directory -Force -Path $deployDirectory | Out-Null
& "$env:SystemRoot\System32\icacls.exe" $deployDirectory /inheritance:r /grant:r `
    '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' `
    '*S-1-5-19:(OI)(CI)RX' '*S-1-5-32-545:(OI)(CI)RX' /T /C | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Failed to secure deployment directory (icacls exit $LASTEXITCODE)" }

$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $buildDll).Hash.Substring(0, 12).ToLowerInvariant()
$dll = Join-Path $deployDirectory "SSKJVirtualCameraMediaSource-$hash.dll"
if (-not (Test-Path -LiteralPath $dll)) {
    Copy-Item -LiteralPath $buildDll -Destination $dll
}
& "$env:SystemRoot\System32\icacls.exe" $dll /inheritance:r /grant:r `
    '*S-1-5-18:F' '*S-1-5-32-544:F' '*S-1-5-19:RX' '*S-1-5-32-545:RX' /C | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Failed to secure deployed DLL (icacls exit $LASTEXITCODE)" }

$previousDll = $null
if (Test-Path -LiteralPath $clsidPath) {
    $previousDll = (Get-ItemProperty -LiteralPath $clsidPath).'(default)'
}

& $regsvr32 /s $dll
if ($LASTEXITCODE -ne 0) { throw "regsvr32 failed with exit code $LASTEXITCODE" }

try {
    & $registrar install
    if ($LASTEXITCODE -ne 0) { throw "Registrar failed with exit code $LASTEXITCODE" }
} catch {
    & $regsvr32 /s /u $dll
    if ($previousDll -and (Test-Path -LiteralPath $previousDll)) {
        & $regsvr32 /s $previousDll
    }
    throw
}

Write-Output "SSKJ Windows Virtual Camera development instance installed from $dll"
if ($RefreshFrameServer) {
    & (Join-Path $PSScriptRoot 'refresh-frame-server.ps1')
}
if ($PruneOldVersions) {
    $resolvedDeployDirectory = [System.IO.Path]::GetFullPath($deployDirectory)
    if ($resolvedDeployDirectory -ne 'C:\ProgramData\SSKJVirtualCamera\bin') {
        throw "Deployment directory validation failed: $resolvedDeployDirectory"
    }
    Get-ChildItem -LiteralPath $resolvedDeployDirectory -Filter 'SSKJVirtualCameraMediaSource-*.dll' -File |
        Where-Object FullName -ne $dll |
        ForEach-Object {
            $oldDll = $_.FullName
            try { Remove-Item -LiteralPath $oldDll -Force -ErrorAction Stop }
            catch { Write-Warning "Could not remove old DLL ${oldDll}: $($_.Exception.Message)" }
        }
}
