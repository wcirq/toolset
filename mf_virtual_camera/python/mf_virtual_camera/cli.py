from __future__ import annotations

import argparse
import sys
import time
from fractions import Fraction
from pathlib import Path

import cv2

from .formats import bgr_to_nv12, fit_bgr
from .ipc import FrameWriter
from .media import frames_from_path
from .protocol import FrameLayout

OUTPUT_WIDTH = 1280
OUTPUT_HEIGHT = 720
OUTPUT_FPS = 30.0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Send an image or video to SSKJ MF Virtual Camera")
    parser.add_argument("source", type=Path)
    parser.add_argument("--width", type=int, default=OUTPUT_WIDTH)
    parser.add_argument("--height", type=int, default=OUTPUT_HEIGHT)
    parser.add_argument("--fps", type=float)
    parser.add_argument("--mirror", action="store_true")
    parser.add_argument("--no-loop", action="store_true")
    return parser


def run(args: argparse.Namespace) -> int:
    if not args.source.is_file():
        raise ValueError(f"input file does not exist: {args.source}")
    if (args.width, args.height) != (OUTPUT_WIDTH, OUTPUT_HEIGHT):
        raise ValueError(
            f"this camera build supports only {OUTPUT_WIDTH}x{OUTPUT_HEIGHT}; "
            f"got {args.width}x{args.height}"
        )
    frames, source_fps = frames_from_path(args.source, loop=not args.no_loop)
    fps = args.fps or source_fps
    if fps <= 0:
        raise ValueError("frame rate must be positive")
    fraction = Fraction(fps).limit_denominator(1001)
    layout = FrameLayout(args.width, args.height, fraction.numerator, fraction.denominator)
    frame_period = 1.0 / fps

    with FrameWriter(layout) as writer:
        print(f"sending {args.source} at {args.width}x{args.height} @ {fps:g} FPS")
        print("press Ctrl+C to stop")
        deadline = time.perf_counter()
        for frame in frames:
            output = fit_bgr(frame, args.width, args.height)
            if args.mirror:
                output = cv2.flip(output, 1)
            writer.send(bgr_to_nv12(output))
            deadline += frame_period
            delay = deadline - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
            elif delay < -frame_period:
                deadline = time.perf_counter()
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        return run(build_parser().parse_args(argv))
    except KeyboardInterrupt:
        print("\nstopped")
        return 0
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
