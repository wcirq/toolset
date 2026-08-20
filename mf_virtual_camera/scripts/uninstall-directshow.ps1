[CmdletBinding()]
param(
    [switch]$RemoveDeployedFiles
)

$ErrorActionPreference = 'Stop'
$regsvr32 = "$env:SystemRoot\SysWOW64\regsvr32.exe"
$clsidPath = 'Registry::HKEY_LOCAL_MACHINE\Software\Classes\WOW6432Node\CLSID\{3F0C8EC8-D587-43B7-A29B-B4106B91E431}\InprocServer32'
$deployDirectory = [System.IO.Path]::GetFullPath('C:\ProgramData\SSKJVirtualCamera\bin\x86')

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'DirectShow uninstall must run from an elevated PowerShell window.'
}

$dll = $null
if (Test-Path -LiteralPath $clsidPath) {
    $dll = (Get-ItemProperty -LiteralPath $clsidPath).'(default)'
}
if ($dll -and (Test-Path -LiteralPath $dll)) {
    & $regsvr32 /s /u $dll
    if ($LASTEXITCODE -ne 0) { throw "32-bit regsvr32 uninstall failed with exit code $LASTEXITCODE" }
}

if ($RemoveDeployedFiles -and (Test-Path -LiteralPath $deployDirectory)) {
    if ($deployDirectory -ne 'C:\ProgramData\SSKJVirtualCamera\bin\x86') {
        throw "Deployment directory validation failed: $deployDirectory"
    }
    Remove-Item -LiteralPath $deployDirectory -Recurse -Force
}
Write-Output 'Removed x86 SSKJ DirectShow Camera.'
