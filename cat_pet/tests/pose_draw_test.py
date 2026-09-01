# -*- coding: utf-8 -*-
"""离屏测试: pose 模式调试绘制 (SKIP 框 + 头部关键点)"""
import os, sys
import numpy as np
import cv2

os.environ["QT_QPA_PLATFORM"] = "offscreen"
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

import coolcat as m

# ---- 构造 CameraThread 实例 (不 start) ----
cam = m.CameraThread.__new__(m.CameraThread)
cam.pose_mode = True
cam.model = "yolo"
cam.pose_kpt_conf = 0.5
cam.yolo_conf = 0.4
cam.dedup_iou = 0.55
cam.DETECT_WIDTH = 640
cam._last_boxes, cam._last_confs = [], []
cam._last_skipped, cam._last_kpts = [], []
cam._last_display = None

# ---- 假 YOLO 结果: 3 人 (头置信度 0.9 / 0.2 / 0.7) ----
class FakeYolo:
    def predict(self, *a, **k):
        k1 = np.zeros((17, 3)); k1[0] = [100, 60, 0.9]; k1[3] = [70, 40, 0.6]
        k2 = np.zeros((17, 3)); k2[0] = [350, 80, 0.2]
        k3 = np.zeros((17, 3)); k3[2] = [560, 120, 0.7]
        return [
            {"box": (50, 40, 200, 400), "score": 0.9, "keypoints": k1},
            {"box": (300, 60, 420, 380), "score": 0.8, "keypoints": k2},
            {"box": (500, 100, 610, 350), "score": 0.7, "keypoints": k3},
        ]
cam.yolo = FakeYolo()

frame = np.full((480, 640, 3), 40, dtype=np.uint8)
boxes = cam._detect(frame, 640, 480)
print("计入人数:", len(boxes), "(期望 2)")
print("SKIP 数:", len(cam._last_skipped), "(期望 1)")
print("关键点数:", len(cam._last_kpts), "(期望 3: 0.9/0.6/0.7)")

assert len(boxes) == 2 and len(cam._last_skipped) == 1 and len(cam._last_kpts) == 3

# ---- 绘制 + 存图 ----
disp = cam._draw_boxes(frame.copy(), boxes, cam._last_confs,
                       cam._last_skipped, cam._last_kpts)
cam._last_display = disp
cam.debug_save = True
cam._save_debug_shot(len(boxes))

# 检查 SKIP 框灰色像素 & 黄色关键点是否画上
gray_px = (np.abs(disp[:, :, 0].astype(int) - 160) < 30).sum()
yellow_px = ((disp[:, :, 0] < 80) & (disp[:, :, 1] > 200) & (disp[:, :, 2] > 200)).sum()
print("灰色像素:", gray_px, " 黄色像素:", yellow_px)
assert gray_px > 0 and yellow_px > 0

shot_root = os.path.join(m.BASE_DIR, "debug_shots")
shots = []
for root, _dirs, files in os.walk(shot_root):
    shots.extend(os.path.join(root, f) for f in files if f.startswith("trigger_"))
shots.sort()
img = cv2.imread(shots[-1])
print("存图:", os.path.basename(shots[-1]), img.shape)
assert img is not None
print("PASS: pose 调试绘制 OK (计入2/SKIP1/关键点3)")
