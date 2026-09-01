# -*- coding: utf-8 -*-
"""截图裁剪、贴图窗口与第三方 OCR 请求离屏测试。"""
import json
import os
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from PyQt5.QtCore import Qt, QRect
from PyQt5.QtGui import QColor, QPainter, QPixmap
from PyQt5.QtWidgets import QApplication

from coolcat.ui import screenshot as shot


app = QApplication.instance() or QApplication([])

# PNG data URL 必须携带真实图片内容。
pixmap = QPixmap(120, 80)
pixmap.fill(QColor("#39A8FF"))
data_url = shot.pixmap_to_data_url(pixmap)
assert data_url.startswith("data:image/png;base64,")
assert len(data_url) > 100

# 贴图必须无边框且置顶。
pinned = shot.PinnedImageWindow(pixmap)
assert pinned.windowFlags() & Qt.FramelessWindowHint
assert pinned.windowFlags() & Qt.WindowStaysOnTopHint
assert pinned.size().width() == 120
assert pinned.size().height() == 80
pinned.close()

# 区域裁剪使用框选尺寸。
overlay = shot.ScreenshotOverlay({})
overlay.snapshot = QPixmap(300, 200)
overlay.snapshot.fill(QColor("#FF8844"))
overlay.selection = QRect(20, 30, 90, 60)
selected = overlay.selected_pixmap()
assert selected.width() == 90 and selected.height() == 60
overlay.close()

# 模拟 OpenAI-compatible 服务，验证图片消息与返回解析。
captured = {}
class FakeResponse:
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self):
        return json.dumps({
            "choices": [{"message": {"content": "识别成功"}}]
        }).encode("utf-8")

def fake_urlopen(request, timeout=0):
    captured["payload"] = json.loads(request.data.decode("utf-8"))
    captured["authorization"] = request.headers.get("Authorization")
    captured["timeout"] = timeout
    return FakeResponse()

original_urlopen = shot.urllib.request.urlopen
shot.urllib.request.urlopen = fake_urlopen
try:
    result = shot.call_openai_compatible({
        "screenshot_api_endpoint": "https://example.test/v1/chat/completions",
        "screenshot_api_key": "secret",
        "screenshot_api_model": "vision-model",
        "screenshot_translate_language": "简体中文",
    }, pixmap, translate=False)
finally:
    shot.urllib.request.urlopen = original_urlopen

assert result == "识别成功"
assert captured["authorization"] == "Bearer secret"
content = captured["payload"]["messages"][0]["content"]
assert content[1]["type"] == "image_url"
assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")

# 模拟 RapidOCR Python 引擎，验证进程内离线推理和文本返回。
captured.clear()
class FakeResult:
    txts = ["本地识别成功"]
class FakeEngine:
    def __call__(self, image):
        captured["image"] = image
        return FakeResult()

original_get_engine = shot.get_rapidocr_engine
shot.get_rapidocr_engine = lambda: FakeEngine()
try:
    result = shot.call_umi_ocr({}, pixmap)
finally:
    shot.get_rapidocr_engine = original_get_engine

assert result == "本地识别成功"
assert captured["image"].startswith(b"\x89PNG")

# 原图模式应按 OCR 框采样背景、覆盖原区域并重绘文字。
source = QPixmap(320, 120)
source.fill(QColor("#E8D8C8"))
# 模拟原文字区域，使背景覆盖即使在 offscreen 无字体渲染时也可验证。
source_painter = QPainter(source)
source_painter.fillRect(QRect(60, 45, 120, 12), QColor("#252525"))
source_painter.end()
source_before = shot.pixmap_to_base64(source)
painted = shot.render_text_on_image(source, [{
    "text": "OCR 文字",
    "box": [[30, 30], [250, 30], [250, 80], [30, 80]],
    "score": 0.99,
}])
assert painted.size() == source.size()
assert shot.pixmap_to_base64(painted) != source_before

print("PASS: screenshot crop, pinned window, OCR contracts and image redraw")
