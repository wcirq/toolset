from mf_virtual_camera.desktop.camera_manager import CameraManager


def test_powershell_arguments_keep_switches_and_quote_values():
    rendered = CameraManager._format_arguments([
        "-Name", "我的虚拟摄像头", "-InstanceId",
        "{12345678-1234-1234-1234-123456789ABC}", "-RefreshFrameServer",
    ])
    assert rendered == (
        "-Name '我的虚拟摄像头' -InstanceId "
        "'{12345678-1234-1234-1234-123456789ABC}' -RefreshFrameServer"
    )


def test_powershell_switch_is_not_positional_string():
    assert CameraManager._format_arguments(["-Remove", "-RefreshFrameServer"]) == (
        "-Remove -RefreshFrameServer"
    )
