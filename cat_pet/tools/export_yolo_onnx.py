"""一次性将项目 YOLO26 权重转换为部署用 ONNX。"""
from pathlib import Path

import torch
from ultralytics import YOLO


def main():
    model_dir = Path(__file__).resolve().parents[1] / "assets" / "models"
    models = []
    for name in ("yolo26n.pt", "yolo26n-pose.pt"):
        path = model_dir / name
        model = YOLO(str(path))
        models.append((name, model))
        dummy = torch.zeros(1, 3, 480, 480)
        with torch.no_grad():
            output = model.model.eval()(dummy)
        values = output if isinstance(output, (tuple, list)) else [output]
        shapes = [tuple(item.shape) for item in values if hasattr(item, "shape")]
        print(f"{name}: raw output {shapes}")
    for name, model in models:
        exported = model.export(
            format="onnx", imgsz=480, dynamic=False, simplify=False,
            opset=17, nms=False, batch=1, device="cpu")
        print(f"{name}: {exported}")


if __name__ == "__main__":
    main()
