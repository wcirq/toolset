from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
import time

import cv2
import numpy as np

IMAGE_SUFFIXES = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}


def _capture_frames(capture: cv2.VideoCapture, description: str) -> tuple[Iterator[np.ndarray], float]:
    if not capture.isOpened():
        capture.release()
        raise ValueError(f"cannot open {description}")
    fps = float(capture.get(cv2.CAP_PROP_FPS))
    if not np.isfinite(fps) or fps <= 0:
        fps = 30.0

    def frames() -> Iterator[np.ndarray]:
        try:
            while True:
                ok, frame = capture.read()
                if not ok:
                    raise RuntimeError(f"lost {description}")
                yield frame
        finally:
            capture.release()

    return frames(), fps


def frames_from_camera(index: int) -> tuple[Iterator[np.ndarray], float]:
    if index < 0:
        raise ValueError("camera index must not be negative")
    return _capture_frames(cv2.VideoCapture(index, cv2.CAP_DSHOW), f"camera {index}")


def frames_from_stream(url: str) -> tuple[Iterator[np.ndarray], float]:
    if not url.strip():
        raise ValueError("stream URL must not be empty")
    return _capture_frames(cv2.VideoCapture(url), f"network stream {url}")


def frames_from_pattern(
    pattern: str, width: int, height: int, fps: float
) -> tuple[Iterator[np.ndarray], float]:
    if pattern != "clock":
        raise ValueError(f"unsupported generated pattern: {pattern}")

    def frames() -> Iterator[np.ndarray]:
        frame_number = 0
        while True:
            frame = np.zeros((height, width, 3), dtype=np.uint8)
            frame[:, : width // 3] = (160, 64, 32)
            frame[:, width // 3 : 2 * width // 3] = (32, 160, 64)
            frame[:, 2 * width // 3 :] = (64, 32, 160)
            cv2.putText(
                frame,
                time.strftime("%Y-%m-%d %H:%M:%S"),
                (max(20, width // 20), height // 2),
                cv2.FONT_HERSHEY_SIMPLEX,
                max(0.6, width / 1280),
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )
            cv2.putText(
                frame,
                f"frame {frame_number}",
                (max(20, width // 20), height // 2 + 50),
                cv2.FONT_HERSHEY_SIMPLEX,
                max(0.5, width / 1600),
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )
            frame_number += 1
            yield frame

    return frames(), fps


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
