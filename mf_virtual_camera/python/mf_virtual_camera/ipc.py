from __future__ import annotations

import mmap
import os
import struct
import time
from types import TracebackType

from .protocol import HEADER, SLOT_COUNT, FrameLayout, pack_header

MAPPING_PATH = r"C:\ProgramData\SSKJVirtualCamera\frames.v1.bin"
PUBLISHED_SEQUENCE_OFFSET = 48
TIMESTAMP_OFFSET = 56
UINT64 = struct.Struct("<Q")


class FrameWriter:
    def __init__(self, layout: FrameLayout, mapping_path: str = MAPPING_PATH) -> None:
        self.layout = layout
        self.mapping_path = mapping_path
        self._file = None
        self._mapping: mmap.mmap | None = None
        self._sequence = 0

    def open(self) -> None:
        if self._mapping is not None:
            raise RuntimeError("frame writer is already open")
        self._file = open(self.mapping_path, "r+b", buffering=0)
        if os.fstat(self._file.fileno()).st_size != self.layout.mapping_size:
            self._file.close()
            self._file = None
            raise RuntimeError(
                f"runtime frame file has the wrong size; reinstall the camera: {self.mapping_path}"
            )
        self._mapping = mmap.mmap(self._file.fileno(), self.layout.mapping_size, access=mmap.ACCESS_WRITE)
        self._mapping[: HEADER.size] = pack_header(self.layout, 0, 0, os.getpid())

    def close(self) -> None:
        if self._mapping is not None:
            self._mapping.close()
            self._mapping = None
        if self._file is not None:
            self._file.close()
            self._file = None

    def send(self, nv12_frame: bytes, timestamp_100ns: int | None = None) -> int:
        if self._mapping is None:
            raise RuntimeError("frame writer is not open")
        if len(nv12_frame) != self.layout.slot_size:
            raise ValueError(
                f"invalid NV12 frame size: expected {self.layout.slot_size}, got {len(nv12_frame)}"
            )

        next_sequence = self._sequence + 1
        slot_index = next_sequence % SLOT_COUNT
        slot_offset = HEADER.size + slot_index * self.layout.slot_size
        self._mapping[slot_offset : slot_offset + self.layout.slot_size] = nv12_frame

        timestamp = timestamp_100ns if timestamp_100ns is not None else time.monotonic_ns() // 100
        UINT64.pack_into(self._mapping, TIMESTAMP_OFFSET, timestamp)
        UINT64.pack_into(self._mapping, PUBLISHED_SEQUENCE_OFFSET, next_sequence)
        self._sequence = next_sequence
        return next_sequence

    def __enter__(self) -> FrameWriter:
        self.open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
