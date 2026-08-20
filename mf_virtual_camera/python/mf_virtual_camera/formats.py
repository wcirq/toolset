from __future__ import annotations

import cv2
import numpy as np


def fit_bgr(frame: np.ndarray, width: int, height: int) -> np.ndarray:
    if frame.ndim != 3 or frame.shape[2] != 3:
        raise ValueError("expected an HxWx3 BGR frame")
    source_height, source_width = frame.shape[:2]
    if source_width <= 0 or source_height <= 0:
        raise ValueError("source frame has invalid dimensions")

    scale = min(width / source_width, height / source_height)
    resized_width = max(1, round(source_width * scale))
    resized_height = max(1, round(source_height * scale))
    interpolation = cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
    resized = cv2.resize(frame, (resized_width, resized_height), interpolation=interpolation)

    canvas = np.zeros((height, width, 3), dtype=np.uint8)
    left = (width - resized_width) // 2
    top = (height - resized_height) // 2
    canvas[top : top + resized_height, left : left + resized_width] = resized
    return canvas


def bgr_to_nv12(frame: np.ndarray) -> bytes:
    height, width = frame.shape[:2]
    if width % 2 or height % 2:
        raise ValueError("NV12 width and height must be even")

    i420 = cv2.cvtColor(np.ascontiguousarray(frame), cv2.COLOR_BGR2YUV_I420).reshape(-1)
    luma_size = width * height
    chroma_plane_size = luma_size // 4
    y_plane = i420[:luma_size]
    u_plane = i420[luma_size : luma_size + chroma_plane_size]
    v_plane = i420[luma_size + chroma_plane_size :]
    uv_plane = np.empty(chroma_plane_size * 2, dtype=np.uint8)
    uv_plane[0::2] = u_plane
    uv_plane[1::2] = v_plane
    return y_plane.tobytes() + uv_plane.tobytes()

