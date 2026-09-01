from __future__ import annotations

import time
import traceback
from dataclasses import dataclass

import cv2
from PyQt5.QtCore import QThread, pyqtSignal

from ..formats import bgr_to_nv12, fit_bgr
from ..ipc import FrameWriter
from ..media import frames_from_camera, frames_from_path, frames_from_pattern, frames_from_stream
from ..protocol import FrameLayout
from .plugin_host import load_plugin


@dataclass(slots=True)
class SenderConfig:
    source_type: str
    source: str
    fps: float = 30.0
    loop: bool = True
    mirror: bool = False
    plugin_code: str = ""


class SenderThread(QThread):
    preview = pyqtSignal(object)
    status = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, config: SenderConfig, parent=None):
        super().__init__(parent)
        self.config = config

    def _frames(self):
        kind, value = self.config.source_type, self.config.source
        if kind == "file":
            return frames_from_path(__import__("pathlib").Path(value), self.config.loop)
        if kind == "camera":
            return frames_from_camera(int(value))
        if kind == "stream":
            return frames_from_stream(value)
        return frames_from_pattern("clock", 1280, 720, self.config.fps)

    def run(self):
        try:
            frames, source_fps = self._frames()
            fps = self.config.fps or source_fps
            plugin = load_plugin(self.config.plugin_code) if self.config.plugin_code.strip() else None
            layout = FrameLayout(1280, 720, round(fps * 1000), 1000)
            period, deadline, frame_index = 1.0 / fps, time.perf_counter(), 0
            self.status.emit("正在发送")
            with FrameWriter(layout) as writer:
                for frame in frames:
                    if self.isInterruptionRequested():
                        break
                    output = fit_bgr(frame, 1280, 720)
                    if self.config.mirror:
                        output = cv2.flip(output, 1)
                    if plugin:
                        try:
                            context = {"frame_index": frame_index, "timestamp": time.time(),
                                       "fps": fps, "width": 1280, "height": 720}
                            output = fit_bgr(plugin(output, context), 1280, 720)
                        except Exception:
                            self.failed.emit("插件运行失败，已停止发送：\n" + traceback.format_exc())
                            break
                    writer.send(bgr_to_nv12(output))
                    if frame_index % max(1, round(fps / 10)) == 0:
                        self.preview.emit(output.copy())
                    frame_index += 1
                    deadline += period
                    delay = deadline - time.perf_counter()
                    if delay > 0:
                        time.sleep(delay)
                    elif delay < -period:
                        deadline = time.perf_counter()
            self.status.emit("已停止")
        except Exception:
            self.failed.emit(traceback.format_exc())
            self.status.emit("启动失败")

    def stop(self):
        self.requestInterruption()
        self.wait(3000)
