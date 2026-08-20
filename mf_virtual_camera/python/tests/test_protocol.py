from mf_virtual_camera.protocol import HEADER, MAGIC, FrameLayout, pack_header
from mf_virtual_camera.cli import OUTPUT_HEIGHT, OUTPUT_WIDTH, build_parser, run


def test_header_matches_native_abi() -> None:
    layout = FrameLayout(1280, 720, 30, 1)
    packed = pack_header(layout, sequence=7, timestamp_100ns=11, process_id=13)
    values = HEADER.unpack(packed)

    assert HEADER.size == 128
    assert values[0] == MAGIC
    assert values[5] == 1_382_400
    assert values[6:9] == (1280, 720, 1280)
    assert values[12:15] == (7, 11, 13)


def test_layout_rejects_odd_nv12_dimensions() -> None:
    try:
        FrameLayout(1279, 720)
    except ValueError as exc:
        assert "even" in str(exc)
    else:
        raise AssertionError("odd NV12 width was accepted")


def test_cli_rejects_unsupported_output_size(tmp_path) -> None:
    source = tmp_path / "input.jpg"
    source.write_bytes(b"placeholder")
    args = build_parser().parse_args([str(source), "--width", "640", "--height", "480"])
    try:
        run(args)
    except ValueError as exc:
        assert f"{OUTPUT_WIDTH}x{OUTPUT_HEIGHT}" in str(exc)
    else:
        raise AssertionError("unsupported output size was accepted")
