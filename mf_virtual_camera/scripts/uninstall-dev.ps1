[CmdletBinding()]
param(
    [switch]$RefreshFrameServer,
    [switch]$RemoveRuntimeData
)

$ErrorActionPreference = 'Stop'
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$registrar = [System.IO.Path]::GetFullPath((Join-Path $projectRoot 'build\windows-x64\native\registrar\Release\SSKJVirtualCameraRegistrar.exe'))
$regsvr32 = [System.IO.Path]::GetFullPath((Join-Path $env:SystemRoot 'System32\regsvr32.exe'))
$clsidPath = 'Registry::HKEY_LOCAL_MACHINE\Software\Classes\CLSID\{7C81C5D6-7424-47DC-8F4D-12261522C239}\InprocServer32'

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Development uninstall must run from an elevated PowerShell window.'
}

function Remove-CameraIfPresent([string]$Command) {
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $null = & $registrar $Command 2>&1
    $code = $LASTEXITCODE
    $ErrorActionPreference = $previousPreference
    if ($code -eq 0) { Write-Output "$Command succeeded." }
    else { Write-Output "$Command skipped: the virtual camera was already absent." }
}

if (Test-Path -LiteralPath $registrar) {
    Remove-CameraIfPresent remove-wecom-test
    Remove-CameraIfPresent remove-wecom-test-legacy
    Remove-CameraIfPresent remove
}
$dll = $null
if (Test-Path -LiteralPath $clsidPath) {
    $dll = (Get-ItemProperty -LiteralPath $clsidPath).'(default)'
}
if ($dll -and (Test-Path -LiteralPath $dll)) {
    & $regsvr32 /s /u $dll
    if ($LASTEXITCODE -ne 0) { throw "regsvr32 uninstall failed with exit code $LASTEXITCODE" }
}

if ($RefreshFrameServer) {
    & (Join-Path $PSScriptRoot 'refresh-frame-server.ps1')
}
if ($RemoveRuntimeData) {
    $runtimeRoot = [System.IO.Path]::GetFullPath('C:\ProgramData\SSKJVirtualCamera')
    if ($runtimeRoot -ne 'C:\ProgramData\SSKJVirtualCamera') {
        throw "Runtime directory validation failed: $runtimeRoot"
    }
    if (Test-Path -LiteralPath $runtimeRoot) {
        Remove-Item -LiteralPath $runtimeRoot -Recurse -Force
    }
}

Write-Output 'SSKJ Windows Virtual Camera development instance removed.'
