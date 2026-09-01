"""YOLO26 end-to-end ONNX Runtime 推理（检测与 COCO Pose）。"""
import os

import cv2
import numpy as np


class YoloOnnx:
    """解析 YOLO26 导出的 (1, 300, 6/57) end-to-end 输出。"""

    def __init__(self, model_path):
        import onnxruntime as ort

        options = ort.SessionOptions()
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        options.log_severity_level = 3
        self.session = ort.InferenceSession(
            os.fspath(model_path), sess_options=options,
            providers=["CPUExecutionProvider"])
        model_input = self.session.get_inputs()[0]
        self.input_name = model_input.name
        shape = model_input.shape
        self.height = int(shape[2]) if isinstance(shape[2], int) else 480
        self.width = int(shape[3]) if isinstance(shape[3], int) else 480
        output_shape = self.session.get_outputs()[0].shape
        self.pose = bool(output_shape and len(output_shape) == 3
                         and isinstance(output_shape[2], int)
                         and output_shape[2] > 6)

    def _preprocess(self, frame):
        height, width = frame.shape[:2]
        gain = min(self.width / width, self.height / height)
        resized_w = max(1, round(width * gain))
        resized_h = max(1, round(height * gain))
        resized = cv2.resize(frame, (resized_w, resized_h),
                             interpolation=cv2.INTER_LINEAR)
        pad_x = (self.width - resized_w) / 2
        pad_y = (self.height - resized_h) / 2
        left, top = round(pad_x - 0.1), round(pad_y - 0.1)
        right = self.width - resized_w - left
        bottom = self.height - resized_h - top
        image = cv2.copyMakeBorder(
            resized, top, bottom, left, right, cv2.BORDER_CONSTANT,
            value=(114, 114, 114))
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        tensor = np.ascontiguousarray(image.transpose(2, 0, 1), dtype=np.float32)
        tensor = tensor[None] / 255.0
        return tensor, gain, left, top

    def predict(self, frame, confidence=0.4, class_id=0):
        tensor, gain, pad_x, pad_y = self._preprocess(frame)
        output = self.session.run(None, {self.input_name: tensor})[0]
        rows = output[0] if output.ndim == 3 else output
        results = []
        orig_h, orig_w = frame.shape[:2]
        for row in rows:
            if len(row) < 6:
                continue
            score = float(row[4])
            detected_class = int(round(float(row[5])))
            if score < confidence or detected_class != class_id:
                continue
            x1 = float(np.clip((row[0] - pad_x) / gain, 0, orig_w))
            y1 = float(np.clip((row[1] - pad_y) / gain, 0, orig_h))
            x2 = float(np.clip((row[2] - pad_x) / gain, 0, orig_w))
            y2 = float(np.clip((row[3] - pad_y) / gain, 0, orig_h))
            if x2 - x1 <= 1 or y2 - y1 <= 1:
                continue
            keypoints = []
            if len(row) >= 57:
                raw = np.asarray(row[6:57], dtype=np.float32).reshape(17, 3)
                for kx, ky, kc in raw:
                    keypoints.append((
                        float(np.clip((kx - pad_x) / gain, 0, orig_w)),
                        float(np.clip((ky - pad_y) / gain, 0, orig_h)),
                        float(kc)))
            results.append({
                "box": (x1, y1, x2, y2), "score": score,
                "class_id": detected_class, "keypoints": keypoints,
            })
        return results


__all__ = ["YoloOnnx"]
