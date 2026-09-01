import numpy as np
import cv2

from mf_virtual_camera.formats import bgr_to_nv12, fit_bgr
from mf_virtual_camera.media import frames_from_path, frames_from_pattern


def test_fit_bgr_preserves_aspect_ratio_with_black_bars() -> None:
    source = np.full((100, 200, 3), 255, dtype=np.uint8)
    output = fit_bgr(source, 1280, 720)
    assert output.shape == (720, 1280, 3)
    assert output[0].sum() == 0
    assert output[360].sum() > 0


def test_bgr_to_nv12_size() -> None:
    source = np.zeros((720, 1280, 3), dtype=np.uint8)
    output = bgr_to_nv12(source)
    assert len(output) == 1280 * 720 * 3 // 2


def test_image_no_loop_yields_exactly_one_frame(tmp_path) -> None:
    path = tmp_path / "frame.png"
    assert cv2.imwrite(str(path), np.zeros((4, 4, 3), dtype=np.uint8))
    frames, fps = frames_from_path(path, loop=False)
    assert fps == 30.0
    assert sum(1 for _ in frames) == 1


def test_generated_clock_pattern_has_requested_shape() -> None:
    frames, fps = frames_from_pattern("clock", 640, 480, 25.0)
    frame = next(frames)
    assert fps == 25.0
    assert frame.shape == (480, 640, 3)
