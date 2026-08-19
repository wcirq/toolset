"""Stream an image or video file to a virtual camera device."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterator

import cv2
import numpy as np
import pyvirtualcam

IMAGE_SUFFIXES = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
DEFAULT_FPS = 30.0


def fit_frame(frame: np.ndarray, width: int, height: int) -> np.ndarray:
    """Resize without distortion and pad remaining space with black."""
    source_height, source_width = frame.shape[:2]
    if source_width <= 0 or source_height <= 0:
        raise ValueError("输入帧尺寸无效")

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


def image_frames(path: Path) -> Iterator[np.ndarray]:
    frame = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError(f"无法读取图片：{path}")
    while True:
        yield frame


def video_frames(path: Path, loop: bool) -> tuple[Iterator[np.ndarray], float]:
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise ValueError(f"无法打开视频：{path}")
    source_fps = capture.get(cv2.CAP_PROP_FPS)
    if not np.isfinite(source_fps) or source_fps <= 0:
        source_fps = DEFAULT_FPS

    def frames() -> Iterator[np.ndarray]:
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
                    raise ValueError(f"视频中没有可读取的帧：{path}")
                yield frame
        finally:
            capture.release()

    return frames(), float(source_fps)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="把图片或视频模拟为虚拟摄像头画面")
    parser.add_argument("source", nargs="?", type=Path, help="图片或视频文件")
    parser.add_argument("--width", type=int, default=1280, help="输出宽度（默认 1280）")
    parser.add_argument("--height", type=int, default=720, help="输出高度（默认 720）")
    parser.add_argument("--fps", type=float, help="输出帧率；视频默认使用源帧率，图片默认 30")
    parser.add_argument("--mirror", action="store_true", help="水平镜像画面")
    parser.add_argument("--no-loop", action="store_true", help="视频播放完毕后退出")
    parser.add_argument("--backend", help="pyvirtualcam 后端名称，例如 obs")
    parser.add_argument("--device", help="指定虚拟摄像头设备名称")
    parser.add_argument("--list-backends", action="store_true", help="列出可用后端并退出")
    return parser


def run(args: argparse.Namespace) -> int:
    if args.list_backends:
        print("可用后端：", ", ".join(pyvirtualcam.Camera.backends()) or "无")
        return 0
    if args.source is None:
        raise ValueError("请提供图片或视频文件，或使用 --list-backends")
    if not args.source.is_file():
        raise ValueError(f"输入文件不存在：{args.source}")
    if args.width <= 0 or args.height <= 0:
        raise ValueError("输出宽度和高度必须大于 0")
    if args.fps is not None and args.fps <= 0:
        raise ValueError("帧率必须大于 0")

    if args.source.suffix.lower() in IMAGE_SUFFIXES:
        frames = image_frames(args.source)
        source_fps = DEFAULT_FPS
    else:
        frames, source_fps = video_frames(args.source, loop=not args.no_loop)
    output_fps = args.fps or source_fps

    camera_options = {
        "width": args.width,
        "height": args.height,
        "fps": output_fps,
        "fmt": pyvirtualcam.PixelFormat.BGR,
    }
    if args.backend:
        camera_options["backend"] = args.backend
    if args.device:
        camera_options["device"] = args.device

    with pyvirtualcam.Camera(**camera_options) as camera:
        print(f"虚拟摄像头已启动：{camera.device} ({args.width}x{args.height} @ {output_fps:g} FPS)")
        print("按 Ctrl+C 停止。")
        for frame in frames:
            output = fit_frame(frame, args.width, args.height)
            if args.mirror:
                output = cv2.flip(output, 1)
            camera.send(output)
            camera.sleep_until_next_frame()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run(args)
    except KeyboardInterrupt:
        print("\n虚拟摄像头已停止。")
        return 0
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

