[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

Get-Process -Name SSKJVirtualCameraProbe -ErrorAction SilentlyContinue |
    Stop-Process -Force -ErrorAction SilentlyContinue

$service = Get-CimInstance Win32_Service -Filter "Name='FrameServer'"
if (-not $service) { throw 'FrameServer service was not found.' }

if ($service.ProcessId -ne 0) {
    $hostedServices = @(Get-CimInstance Win32_Service |
        Where-Object ProcessId -eq $service.ProcessId)
    if ($hostedServices.Count -ne 1 -or $hostedServices[0].Name -ne 'FrameServer') {
        $names = ($hostedServices.Name -join ', ')
        throw "Refusing to terminate shared service host. Hosted services: $names"
    }
    $process = Get-Process -Id $service.ProcessId -ErrorAction Stop
    if ($process.ProcessName -ne 'svchost') {
        throw "Refusing to terminate unexpected FrameServer host: $($process.ProcessName)"
    }
    Stop-Process -Id $service.ProcessId -Force
    Write-Output "Stopped FrameServer host PID $($service.ProcessId)."
} else {
    Write-Output 'FrameServer was already stopped.'
}
