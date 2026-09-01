# -*- coding: utf-8 -*-
"""纯 ONNX YOLO26 预处理、检测和姿态输出解析测试。"""
import os
import sys

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from coolcat.detection.onnx_yolo import YoloOnnx


class FakeSession:
    def __init__(self, output):
        self.output = output
        self.feed = None

    def run(self, _outputs, feed):
        self.feed = feed
        return [self.output]


def make_runner(output, pose=False):
    runner = YoloOnnx.__new__(YoloOnnx)
    runner.session = FakeSession(output)
    runner.input_name = "images"
    runner.width = 480
    runner.height = 480
    runner.pose = pose
    return runner


# 640x480 输入会缩放到 480x360，上下各补 60；输出应正确映射回原图。
frame = np.zeros((480, 640, 3), dtype=np.uint8)
det_output = np.zeros((1, 300, 6), dtype=np.float32)
det_output[0, 0] = [120, 120, 360, 360, 0.9, 0]
det_output[0, 1] = [0, 0, 20, 20, 0.2, 0]  # 低置信度过滤
det = make_runner(det_output)
items = det.predict(frame, confidence=0.4)
assert len(items) == 1
assert np.allclose(items[0]["box"], (160, 80, 480, 400), atol=1)
tensor = det.session.feed["images"]
assert tensor.shape == (1, 3, 480, 480)
assert tensor.dtype == np.float32

# Pose: 6 个检测字段 + 17*3 关键点。
pose_output = np.zeros((1, 300, 57), dtype=np.float32)
pose_output[0, 0, :6] = [120, 120, 360, 360, 0.85, 0]
for index in range(17):
    pose_output[0, 0, 6 + index * 3:9 + index * 3] = [240, 240, 0.8]
pose = make_runner(pose_output, pose=True)
items = pose.predict(frame, confidence=0.4)
assert len(items) == 1 and len(items[0]["keypoints"]) == 17
assert np.allclose(items[0]["keypoints"][0], (320, 240, 0.8), atol=1)

print("PASS: YOLO26 ONNX detection and pose output parsing")
