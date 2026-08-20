from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import cv2
import numpy as np

IMAGE_SUFFIXES = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}


def frames_from_path(path: Path, loop: bool = True) -> tuple[Iterator[np.ndarray], float]:
    if path.suffix.lower() in IMAGE_SUFFIXES:
        frame = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError(f"cannot read image: {path}")

        def image_frames() -> Iterator[np.ndarray]:
            yield frame
            while loop:
                yield frame

        return image_frames(), 30.0

    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise ValueError(f"cannot open video: {path}")
    fps = float(capture.get(cv2.CAP_PROP_FPS))
    if not np.isfinite(fps) or fps <= 0:
        fps = 30.0

    def video_frames() -> Iterator[np.ndarray]:
        try:
            while True:
                ok, frame = capture.read()
                if ok:
                    yield frame
                    continue
                if not loop:
                    return
                capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ok, frame = capture.read()
                if not ok:
                    raise ValueError(f"video contains no readable frames: {path}")
                yield frame
        finally:
            capture.release()

    return video_frames(), fps
