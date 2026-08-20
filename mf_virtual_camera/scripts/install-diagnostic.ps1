[CmdletBinding()]
param(
    [switch]$SkipBuild,
    [switch]$RefreshFrameServer,
    [switch]$PruneOldVersions
)

$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$log = Join-Path $projectRoot 'build\install-dev.log'

$arguments = @{
    SkipBuild = $SkipBuild
    RefreshFrameServer = $RefreshFrameServer
    PruneOldVersions = $PruneOldVersions
}
try {
    & (Join-Path $PSScriptRoot 'install-dev.ps1') @arguments 2>&1 |
        Out-File -LiteralPath $log -Encoding utf8
    $code = $LASTEXITCODE
    if ($null -eq $code) { $code = 0 }
} catch {
    $_ | Out-String | Set-Content -LiteralPath $log -Encoding utf8
    $code = 1
}
Add-Content -LiteralPath $log -Value "EXIT=$code"
exit $code
