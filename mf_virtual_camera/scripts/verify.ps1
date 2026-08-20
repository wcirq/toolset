[CmdletBinding()]
param(
    [switch]$SkipBuild,
    [string]$Source,
    [string]$PythonPath = 'python'
)

$ErrorActionPreference = 'Stop'
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$pythonRoot = Join-Path $projectRoot 'python'
$ctest = 'C:\Program Files\Microsoft Visual Studio\18\Community\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\ctest.exe'
$probe = Join-Path $projectRoot 'build\windows-x64\tools\frame_probe\Release\SSKJVirtualCameraProbe.exe'
$sender = $null

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'System verification must run from an elevated PowerShell window.'
}

if (-not $SkipBuild) {
    & (Join-Path $PSScriptRoot 'build.ps1') -Configuration Release
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
if (-not (Test-Path -LiteralPath $ctest)) { throw "ctest was not found: $ctest" }
if (-not (Test-Path -LiteralPath $probe)) { throw "Frame probe was not found: $probe" }

Push-Location $projectRoot
try {
    & $ctest --preset release --output-on-failure
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally {
    Pop-Location
}

Push-Location $pythonRoot
try {
    & $PythonPath -m pytest -q
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    if ($Source) {
        $resolvedSource = (Resolve-Path -LiteralPath $Source).Path
        $sender = Start-Process -FilePath $PythonPath `
            -ArgumentList @('-u', '-m', 'mf_virtual_camera.cli', $resolvedSource) `
            -WorkingDirectory $pythonRoot -WindowStyle Hidden -PassThru
        Start-Sleep -Seconds 2
        if ($sender.HasExited) { throw "Frame sender exited with code $($sender.ExitCode)." }
    }

    $previousErrorPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & $probe
        $probeExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorPreference
    }
    exit $probeExitCode
} finally {
    if ($sender -and -not $sender.HasExited) {
        Stop-Process -Id $sender.Id -Force -ErrorAction SilentlyContinue
    }
    Pop-Location
}
