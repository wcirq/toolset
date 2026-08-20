[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$runtimeDirectory = 'C:\ProgramData\SSKJVirtualCamera'
$frameFile = Join-Path $runtimeDirectory 'frames.v1.bin'
$frameFileSize = 128 + 2 * (1280 * 720 * 3 / 2)

New-Item -ItemType Directory -Force -Path $runtimeDirectory | Out-Null
$stream = [System.IO.File]::Open($frameFile, 'OpenOrCreate', 'ReadWrite', 'ReadWrite')
try { $stream.SetLength($frameFileSize) } finally { $stream.Dispose() }

& "$env:SystemRoot\System32\icacls.exe" $runtimeDirectory /grant `
    '*S-1-5-19:(OI)(CI)M' '*S-1-5-32-545:(OI)(CI)M' /T /C | Out-Null
if ($LASTEXITCODE -ne 0) { throw "icacls failed with exit code $LASTEXITCODE" }

Write-Output $frameFile
