from .common import *
from .cat_window import CatWindow

# ======================== 入口 ========================
def _preload_yolo():
    """
    在主线程预加载 torch/ultralytics。
    Windows 上 torch 的 DLL (c10.dll 等) 必须在主线程首次加载,
    否则在工作线程内 import 会报 WinError 1114 动态链接库初始化失败。
    """
    try:
        import torch  # noqa: F401
        import ultralytics  # noqa: F401
        _log("torch/ultralytics 主线程预加载成功")
        return True
    except Exception as e:
        _log(f"torch/ultralytics 预加载失败 (YOLO 将不可用): {e}")
        return False


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    cfg = load_config()
    if cfg.get("model") == "yolo":
        _preload_yolo()
    cat = CatWindow()
    cat.show()
    sys.exit(app.exec_())


