[CmdletBinding()]
param(
    [ValidateSet('Debug', 'Release')]
    [string]$Configuration = 'Debug'
)

$ErrorActionPreference = 'Stop'
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$cmake = 'C:\Program Files\Microsoft Visual Studio\18\Community\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe'
$vcvars = 'C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvars64.bat'

if (-not (Test-Path -LiteralPath $cmake)) {
    throw "Visual Studio bundled CMake was not found: $cmake"
}
if (-not (Test-Path -LiteralPath $vcvars)) {
    throw "Visual Studio x64 developer environment was not found: $vcvars"
}

$preset = $Configuration.ToLowerInvariant()
$command = 'set "VSLANG=1033" && call "{0}" && "{1}" --preset windows-x64 -S "{2}" && "{1}" --build --preset {3}' -f $vcvars, $cmake, $projectRoot, $preset
& cmd.exe /d /s /c $command
exit $LASTEXITCODE
