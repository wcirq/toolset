[CmdletBinding()]
param()

$ErrorActionPreference = 'Continue'
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$registrar = Join-Path $projectRoot 'build\windows-x64\native\registrar\Release\SSKJVirtualCameraRegistrar.exe'
$log = Join-Path $projectRoot 'build\registrar-install.log'

& $registrar install *> $log
$code = $LASTEXITCODE
Add-Content -LiteralPath $log -Value "EXIT=$code"
exit $code

