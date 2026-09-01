[CmdletBinding()]
param(
    [switch]$Remove,
    [switch]$RefreshFrameServer
)

$ErrorActionPreference = 'Stop'
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$registrar = [System.IO.Path]::GetFullPath((Join-Path $projectRoot 'build\windows-x64\native\registrar\Release\SSKJVirtualCameraRegistrar.exe'))
$clsidPath = 'Registry::HKEY_LOCAL_MACHINE\Software\Classes\CLSID\{E98467C5-18B5-46B3-9408-1CE4C5C59437}\InprocServer32'

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'The WeCom enumeration test must run from an elevated PowerShell window.'
}
if (-not (Test-Path -LiteralPath $registrar)) {
    throw "Registrar not found: $registrar. Build Release first."
}

function Invoke-Registrar([string]$Command, [switch]$AllowMissing) {
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $messages = @(& $registrar $Command 2>&1)
    $code = $LASTEXITCODE
    $ErrorActionPreference = $previousPreference
    if ($code -ne 0) {
        if ($AllowMissing) {
            Write-Output "$Command skipped: the virtual camera was already absent."
            return
        }
        throw "Registrar command '$Command' failed with exit code $code.`n$($messages -join [Environment]::NewLine)"
    }
    $messages | ForEach-Object { Write-Output $_.ToString() }
}

if ($Remove) {
    Invoke-Registrar remove-wecom-test -AllowMissing
} else {
    if (-not (Test-Path -LiteralPath $clsidPath)) {
        throw 'The MediaSource COM component is not installed. Run install-dev.ps1 first.'
    }
    Invoke-Registrar install-wecom-test
}

# Clean up the short-lived development instance that used the primary source CLSID.
Invoke-Registrar remove-wecom-test-legacy -AllowMissing

if ($RefreshFrameServer) {
    & (Join-Path $PSScriptRoot 'refresh-frame-server.ps1')
}

if ($Remove) {
    Write-Output 'Removed SSKJ WeCom Detection Test virtual camera.'
} else {
    Write-Output 'Installed SSKJ WeCom Detection Test (Windows Virtual Camera).'
    Write-Output 'Fully exit WeCom (including its tray process), restart it, and compare its camera list.'
}
