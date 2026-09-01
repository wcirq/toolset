"""比较 PyTorch 权重和项目 ONNX Runtime 封装的真实图片检测结果。"""
import argparse
from pathlib import Path
import sys

import cv2
from ultralytics import YOLO

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))
from coolcat.detection.onnx_yolo import YoloOnnx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("image")
    args = parser.parse_args()
    image = cv2.imread(args.image)
    if image is None:
        raise ValueError("无法读取测试图片")
    model_dir = PROJECT_DIR / "assets" / "models"
    for stem in ("yolo26n", "yolo26n-pose"):
        pt_results = YOLO(str(model_dir / f"{stem}.pt")).predict(
            image, conf=0.25, classes=[0], imgsz=480, verbose=False)[0]
        ort_results = YoloOnnx(model_dir / f"{stem}.onnx").predict(
            image, confidence=0.25)
        pt_count = len(pt_results.boxes)
        print(f"{stem}: PyTorch={pt_count}, ONNX={len(ort_results)}")
        if pt_count != len(ort_results):
            raise RuntimeError(f"{stem} 人体数量不一致")
        if "pose" in stem and ort_results:
            if any(len(item["keypoints"]) != 17 for item in ort_results):
                raise RuntimeError("Pose 关键点数量错误")


if __name__ == "__main__":
    main()
