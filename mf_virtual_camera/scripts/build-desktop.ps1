[CmdletBinding()]
param([switch]$SkipNative)
$ErrorActionPreference = 'Stop'
$root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$python = 'C:\Users\sskj\.conda\envs\mf_virtual_camera\python.exe'
$iscc = 'C:\Users\sskj\AppData\Local\Programs\Inno Setup 6\ISCC.exe'
if (-not (Test-Path -LiteralPath $python)) { throw "Conda 环境不存在：$python" }
if (-not (Test-Path -LiteralPath $iscc)) { throw "Inno Setup 编译器不存在：$iscc" }
if (-not $SkipNative) {
    & (Join-Path $PSScriptRoot 'build.ps1') -Configuration Release
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & (Join-Path $PSScriptRoot 'build-directshow.ps1')
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
$env:PYTHONNOUSERSITE = '1'
& $python -m PyInstaller --noconfirm --clean --distpath (Join-Path $root 'dist') `
    --workpath (Join-Path $root 'build\pyinstaller') (Join-Path $root 'packaging\camera_studio.spec')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Output "桌面程序已生成：$root\dist\SSKJCameraStudio\SSKJCameraStudio.exe"
& $iscc (Join-Path $root 'packaging\camera_studio.iss')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Output "中文安装包已生成：$root\dist\installer\SSKJ-Camera-Studio-Setup-0.2.4.exe"
