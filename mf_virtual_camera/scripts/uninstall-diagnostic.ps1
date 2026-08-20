[CmdletBinding()]
param()

$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$log = Join-Path $projectRoot 'build\uninstall-dev.log'

& (Join-Path $PSScriptRoot 'uninstall-dev.ps1') *> $log
$code = $LASTEXITCODE
Add-Content -LiteralPath $log -Value "EXIT=$code"
exit $code
