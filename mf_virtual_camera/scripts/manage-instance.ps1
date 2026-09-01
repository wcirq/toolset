[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateNotNullOrEmpty()]
    [string]$Name,
    [Guid]$InstanceId = [Guid]::Empty,
    [switch]$Remove,
    [switch]$RefreshFrameServer
)

$ErrorActionPreference = 'Stop'
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$registrar = Join-Path $projectRoot 'build\windows-x64\native\registrar\Release\SSKJVirtualCameraRegistrar.exe'
$primaryClsidPath = 'Registry::HKEY_LOCAL_MACHINE\Software\Classes\CLSID\{7C81C5D6-7424-47DC-8F4D-12261522C239}\InprocServer32'

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Instance management must run from an elevated PowerShell window.'
}
if (-not (Test-Path -LiteralPath $registrar)) { throw "Registrar not found: $registrar" }
if ($InstanceId -eq [Guid]::Empty) {
    if ($Remove) { throw '-InstanceId is required when removing an instance.' }
    $InstanceId = [Guid]::NewGuid()
}

$sourceId = '{' + $InstanceId.ToString().ToUpperInvariant() + '}'
$classRoot = "Registry::HKEY_LOCAL_MACHINE\Software\Classes\CLSID\$sourceId"
$inproc = Join-Path $classRoot 'InprocServer32'

if ($Remove) {
    & $registrar remove-custom $Name $sourceId
    if ($LASTEXITCODE -ne 0) { throw "Custom camera removal failed with exit code $LASTEXITCODE" }
    if (Test-Path -LiteralPath $classRoot) { Remove-Item -LiteralPath $classRoot -Recurse -Force }
    Write-Output "Removed virtual camera instance '$Name' ($sourceId)."
} else {
    if (-not (Test-Path -LiteralPath $primaryClsidPath)) {
        throw 'Primary MediaSource is not installed. Run install-dev.ps1 first.'
    }
    $dll = (Get-ItemProperty -LiteralPath $primaryClsidPath).'(default)'
    New-Item -ItemType Directory -Force -Path $inproc | Out-Null
    Set-Item -LiteralPath $classRoot -Value 'SSKJ MF Virtual Camera Instance'
    Set-Item -LiteralPath $inproc -Value $dll
    New-ItemProperty -LiteralPath $inproc -Name ThreadingModel -Value Both -PropertyType String -Force | Out-Null
    try {
        & $registrar install-custom $Name $sourceId
        if ($LASTEXITCODE -ne 0) { throw "Custom camera installation failed with exit code $LASTEXITCODE" }
    } catch {
        Remove-Item -LiteralPath $classRoot -Recurse -Force -ErrorAction SilentlyContinue
        throw
    }
    Write-Output "Installed virtual camera instance '$Name'."
    Write-Output "InstanceId=$sourceId"
}

if ($RefreshFrameServer) {
    & (Join-Path $PSScriptRoot 'refresh-frame-server.ps1')
}
