[CmdletBinding()]
param()

$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$probe = Join-Path $projectRoot 'build\windows-x64\tools\frame_probe\Release\SSKJVirtualCameraProbe.exe'
$log = Join-Path $projectRoot 'build\frame-probe.log'

& $probe *> $log
$code = $LASTEXITCODE
Add-Content -LiteralPath $log -Value "EXIT=$code"
exit $code

