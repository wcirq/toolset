from .common import *
from .cat_window import CatWindow

# ======================== 入口 ========================
def _check_yolo_runtime():
    """确认 ONNX Runtime 可用。"""
    try:
        import onnxruntime  # noqa: F401
        _log("ONNX Runtime 可用")
        return True
    except Exception as e:
        _log(f"ONNX Runtime 不可用 (YOLO/RapidOCR 将不可用): {e}")
        return False


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    cfg = load_config()
    if cfg.get("model") == "yolo":
        _check_yolo_runtime()
    cat = CatWindow()
    cat.show()
    sys.exit(app.exec_())


