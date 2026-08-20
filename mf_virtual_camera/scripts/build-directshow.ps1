[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$cmake = 'C:\Program Files\Microsoft Visual Studio\18\Community\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe'
$vcvars32 = 'C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvars32.bat'

if (-not (Test-Path -LiteralPath $cmake)) { throw "CMake not found: $cmake" }
if (-not (Test-Path -LiteralPath $vcvars32)) { throw "x86 developer environment not found: $vcvars32" }

$command = 'set "VSLANG=1033" && call "{0}" && "{1}" --preset windows-x86 -S "{2}" && "{1}" --build --preset directshow-release-x86' -f $vcvars32, $cmake, $projectRoot
& cmd.exe /d /s /c $command
exit $LASTEXITCODE
