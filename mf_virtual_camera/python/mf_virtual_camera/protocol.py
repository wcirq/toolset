from __future__ import annotations

import struct
from dataclasses import dataclass

MAGIC = b"MFVCFRM1"
VERSION_MAJOR = 1
VERSION_MINOR = 0
SLOT_COUNT = 2
PIXEL_FORMAT_NV12 = 0x3231564E
HEADER = struct.Struct("<8sHH9I3Q48s8x")


@dataclass(frozen=True, slots=True)
class FrameLayout:
    width: int
    height: int
    fps_numerator: int = 30
    fps_denominator: int = 1

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("width and height must be positive")
        if self.width % 2 or self.height % 2:
            raise ValueError("NV12 width and height must be even")
        if self.fps_numerator <= 0 or self.fps_denominator <= 0:
            raise ValueError("frame rate must be positive")

    @property
    def stride(self) -> int:
        return self.width

    @property
    def slot_size(self) -> int:
        return self.stride * self.height * 3 // 2

    @property
    def mapping_size(self) -> int:
        return HEADER.size + SLOT_COUNT * self.slot_size


def pack_header(layout: FrameLayout, sequence: int, timestamp_100ns: int, process_id: int) -> bytes:
    return HEADER.pack(
        MAGIC,
        VERSION_MAJOR,
        VERSION_MINOR,
        HEADER.size,
        SLOT_COUNT,
        layout.slot_size,
        layout.width,
        layout.height,
        layout.stride,
        PIXEL_FORMAT_NV12,
        layout.fps_numerator,
        layout.fps_denominator,
        sequence,
        timestamp_100ns,
        process_id,
        bytes(48),
    )

