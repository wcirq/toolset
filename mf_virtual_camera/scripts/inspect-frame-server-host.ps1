[CmdletBinding()]
param()

$log = 'D:\projects\temp\mf_virtual_camera\build\frame-server-host.log'
$frameServer = Get-CimInstance Win32_Service -Filter "Name='FrameServer'"
if (-not $frameServer) { throw 'FrameServer service was not found.' }

Get-CimInstance Win32_Service |
    Where-Object ProcessId -eq $frameServer.ProcessId |
    Select-Object Name, DisplayName, State, ProcessId, PathName |
    Format-List | Out-File -LiteralPath $log -Encoding utf8
