# -*- coding: utf-8 -*-
"""截图裁剪、贴图窗口与第三方 OCR 请求离屏测试。"""
import base64
import json
import os
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from PyQt5.QtCore import Qt, QPoint, QRect, QEvent
from PyQt5.QtGui import QColor, QKeyEvent, QPainter, QPixmap
from PyQt5.QtWidgets import QApplication, QPushButton

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
assert not overlay.translate_button.isEnabled()
overlay.snapshot = QPixmap(300, 200)
overlay.snapshot.fill(QColor("#FF8844"))
assert overlay._pixel_rgb(QPoint(10, 10)) == (255, 136, 68)
assert overlay._pixel_rgb(QPoint(-1, -1)) is None
assert overlay._format_color((255, 136, 68)) == "#FF8844  RGB(255, 136, 68)"
overlay.resize(300, 200)
assert overlay.rect().contains(overlay._magnifier_rect(QPoint(20, 20)))
assert overlay.rect().contains(overlay._magnifier_rect(QPoint(290, 190)))
mag_rect = overlay._magnifier_rect(QPoint(290, 190))
assert overlay.rect().contains(overlay._magnifier_info_rect(mag_rect))
overlay.selection = QRect(20, 30, 90, 60)
selected = overlay.selected_pixmap()
assert selected.width() == 90 and selected.height() == 60
# 单击窗口或完成拖拽后，鼠标移动不得再让窗口候选覆盖最终选区。
locked_selection = QRect(overlay.selection)
overlay._selection_confirmed = True
overlay._window_candidate = lambda _pos: QRect(0, 0, 300, 200)
overlay._update_window_candidate(locked_selection.topLeft())
assert overlay.selection == locked_selection

# 已确认选区支持内部拖动和八方向边缘缩放，并限制在屏幕范围内。
overlay.resize(300, 200)
overlay.selection = QRect(20, 30, 90, 60)
overlay._selection_confirmed = True
overlay._pressed_window_rect = QRect(overlay.selection)
overlay._interaction = "move"
assert overlay._move_selection(QPoint(25, 15)) == QRect(45, 45, 90, 60)
assert overlay._move_selection(QPoint(-100, -100)).topLeft() == QPoint(0, 0)
overlay._resize_edges = ("right", "bottom")
overlay._pressed_window_rect = QRect(20, 30, 90, 60)
assert overlay._resize_selection(QPoint(139, 109)) == QRect(20, 30, 120, 80)
assert set(overlay._resize_hit_test(QPoint(20, 30))) == {"left", "top"}
overlay.close()

# 慢任务显示提示；第一次 Esc 取消任务，第二次 Esc 退出截图界面。
busy_overlay = shot.ScreenshotOverlay({})
busy_overlay.show()
class FakeRunningWorker:
    running = True
    def isRunning(self): return self.running
fake_worker = FakeRunningWorker()
busy_overlay._active_worker = fake_worker
busy_overlay._active_mode = "ocr"
busy_overlay._operation_cancelled = False
busy_overlay._selection_confirmed = False
busy_overlay.selection = QRect(20, 20, 80, 50)
busy_overlay._window_candidate = lambda _pos: QRect(0, 0, 300, 200)
busy_overlay._update_window_candidate(busy_overlay.selection.topLeft())
assert busy_overlay.selection == QRect(20, 20, 80, 50)
assert busy_overlay._operation_blocks_selection()
busy_overlay._show_slow_progress(fake_worker, "ocr")
assert not busy_overlay.progress_label.isHidden()
escape = QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier)
busy_overlay.keyPressEvent(escape)
assert busy_overlay._operation_cancelled and busy_overlay.progress_label.isHidden()
assert not busy_overlay._operation_blocks_selection()
busy_overlay.keyPressEvent(escape)
assert busy_overlay._close_after_worker and busy_overlay.isHidden()
fake_worker.running = False
busy_overlay._active_worker = None
busy_overlay.close()
configured_overlay = shot.ScreenshotOverlay({
    "screenshot_translate_provider": "openai_compatible",
    "screenshot_translate_api_endpoint": "https://translate.test/v1/chat/completions",
    "screenshot_translate_api_model": "translate-model",
})
assert configured_overlay.translate_button.isEnabled()
configured_overlay.close()
xfyun_overlay = shot.ScreenshotOverlay({
    "screenshot_translate_provider": "xfyun",
    "screenshot_xfyun_endpoint": "https://itrans.xfyun.cn/v2/its",
    "screenshot_xfyun_app_id": "app",
    "screenshot_xfyun_api_key": "key",
    "screenshot_xfyun_api_secret": "secret",
})
assert xfyun_overlay.translate_button.isEnabled()
xfyun_overlay.close()

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
        "screenshot_ocr_api_endpoint": "https://example.test/v1/chat/completions",
        "screenshot_ocr_api_key": "secret",
        "screenshot_ocr_api_model": "vision-model",
        "screenshot_translate_language": "简体中文",
    }, pixmap, translate=False)
finally:
    shot.urllib.request.urlopen = original_urlopen

assert result == "识别成功"
assert captured["authorization"] == "Bearer secret"
content = captured["payload"]["messages"][0]["content"]
assert content[1]["type"] == "image_url"
assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")

# 翻译必须使用独立的 endpoint/key/model，且逐行返回。
class FakeTranslateResponse:
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self):
        return json.dumps({"choices": [{"message": {
            "content": json.dumps(["译文一", "译文二"], ensure_ascii=False)
        }}]}, ensure_ascii=False).encode("utf-8")

def fake_translate_urlopen(request, timeout=0):
    captured["translate_url"] = request.full_url
    captured["translate_auth"] = request.headers.get("Authorization")
    return FakeTranslateResponse()

shot.urllib.request.urlopen = fake_translate_urlopen
try:
    translated = shot.call_openai_translation_lines({
        "screenshot_translate_api_endpoint": "https://translate.test/v1/chat/completions",
        "screenshot_translate_api_key": "translate-secret",
        "screenshot_translate_api_model": "translate-model",
        "screenshot_translate_language": "简体中文",
    }, ["one", "two"])
finally:
    shot.urllib.request.urlopen = original_urlopen
assert translated == ["译文一", "译文二"]
assert captured["translate_url"].startswith("https://translate.test/")
assert captured["translate_auth"] == "Bearer translate-secret"

# 讯飞翻译：验证 HMAC 鉴权头、业务参数和返回解析。
class FakeXfyunResponse:
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self):
        return json.dumps({
            "code": 0, "message": "success",
            "data": {"result": {"trans_result": {
                "src": "hello", "dst": json.dumps({
                    "from": "en", "to": "cn",
                    "trans_result": {"src": "hello", "dst": "你好"}
                }, ensure_ascii=False)}}}
        }, ensure_ascii=False).encode("utf-8")

def fake_xfyun_urlopen(request, timeout=0):
    captured["xfyun_headers"] = dict(request.header_items())
    captured["xfyun_body"] = json.loads(request.data.decode("utf-8"))
    captured["xfyun_timeout"] = timeout
    return FakeXfyunResponse()

shot.urllib.request.urlopen = fake_xfyun_urlopen
try:
    xfyun_text = shot.call_xfyun_translation({
        "screenshot_xfyun_endpoint": "https://itrans.xfyun.cn/v2/its",
        "screenshot_xfyun_app_id": "app-id",
        "screenshot_xfyun_api_key": "api-key",
        "screenshot_xfyun_api_secret": "api-secret",
        "screenshot_xfyun_from": "en",
        "screenshot_translate_language": "简体中文",
    }, "hello")
finally:
    shot.urllib.request.urlopen = original_urlopen
assert xfyun_text == "你好"
xfyun_headers = {key.lower(): value for key, value in captured["xfyun_headers"].items()}
assert xfyun_headers["authorization"].startswith('api_key="api-key"')
assert xfyun_headers["digest"].startswith("SHA-256=")
assert captured["xfyun_body"]["common"]["app_id"] == "app-id"
assert captured["xfyun_body"]["business"] == {"from": "en", "to": "cn"}

# 讯飞机器翻译 2.0：查询参数鉴权、新请求结构、RES_ID 和 Base64 返回。
class FakeXfyunV1Response:
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self):
        return json.dumps({
            "header": {"code": 0, "message": "success"},
            "payload": {"result": {"text": base64.b64encode(
                json.dumps({"from": "en", "to": "cn", "trans_result": {
                    "src": "hello", "dst": "新版译文"}},
                    ensure_ascii=False).encode("utf-8")).decode("ascii")}}
        }, ensure_ascii=False).encode("utf-8")

def fake_xfyun_v1_urlopen(request, timeout=0):
    captured["xfyun_v1_url"] = request.full_url
    captured["xfyun_v1_body"] = json.loads(request.data.decode("utf-8"))
    return FakeXfyunV1Response()

shot.urllib.request.urlopen = fake_xfyun_v1_urlopen
try:
    xfyun_v1_text = shot.call_xfyun_v1_translation({
        "screenshot_xfyun_v1_endpoint": "https://itrans.xf-yun.com/v1/its",
        "screenshot_xfyun_v1_app_id": "v1-app-id",
        "screenshot_xfyun_v1_api_key": "v1-api-key",
        "screenshot_xfyun_v1_api_secret": "v1-api-secret",
        "screenshot_xfyun_res_id": "its_en_cn_word",
        "screenshot_xfyun_from": "en",
        "screenshot_translate_language": "cn",
    }, "hello")
finally:
    shot.urllib.request.urlopen = original_urlopen
assert xfyun_v1_text == "新版译文"
v1_query = shot.urllib.parse.parse_qs(
    shot.urllib.parse.urlparse(captured["xfyun_v1_url"]).query)
assert all(key in v1_query for key in ("host", "date", "authorization"))
v1_body = captured["xfyun_v1_body"]
assert v1_body["header"]["app_id"] == "v1-app-id"
assert v1_body["header"]["res_id"] == "its_en_cn_word"
assert v1_body["parameter"]["its"]["from"] == "en"
assert v1_body["parameter"]["its"]["to"] == "cn"
assert base64.b64decode(v1_body["payload"]["input_data"]["text"]).decode() == "hello"
assert base64.b64decode(captured["xfyun_body"]["data"]["text"]).decode() == "hello"

# 多个 OCR 文字框应合并为一次讯飞请求，再拆回原文字框顺序。
batch_calls = []
def fake_batch_translate(_config, text):
    batch_calls.append(text)
    return text.replace("first", "第一").replace("second", "第二").replace(
        "third", "第三")
original_xfyun_translate = shot.call_xfyun_translation
shot.call_xfyun_translation = fake_batch_translate
try:
    batch_result = shot.call_translation_lines({
        "screenshot_translate_provider": "xfyun"
    }, ["first", "second", "third"])
finally:
    shot.call_xfyun_translation = original_xfyun_translate
assert batch_result == ["第一", "第二", "第三"]
assert len(batch_calls) == 1
assert "__CCSEP_0001__" in batch_calls[0]
json_lines = "\n".join(json.dumps({"from": "en", "to": "cn",
    "trans_result": {"src": src, "dst": dst}}, ensure_ascii=False)
    for src, dst in (("i", "我"), ("am", "是"), ("tony!", "东尼！")))
assert shot._normalize_xfyun_translation_text(json_lines) == "我\n是\n东尼！"

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
# 重绘应从原文字区域估算并沿用接近原文的深色，而非固定黑白色。
sample_image = source.toImage()
sample_bg = shot._sample_background(sample_image, QRect(30, 30, 220, 50))
sample_fg = shot._sample_text_color(
    sample_image, QRect(30, 30, 220, 50), sample_bg)
assert sample_fg.red() < 80 and sample_fg.green() < 80 and sample_fg.blue() < 80
source_before = shot.pixmap_to_base64(source)
painted = shot.render_text_on_image(source, [{
    "text": "OCR 文字",
    "box": [[30, 30], [250, 30], [250, 80], [30, 80]],
    "score": 0.99,
}])
assert painted.size() == source.size()
assert shot.pixmap_to_base64(painted) != source_before

# OCR 结果控件：右侧文字可选择复制，也可一键复制全部。
ocr_dialog = shot.OcrImageResultDialog(source, "第一行文字\n第二行文字")
assert ocr_dialog.windowFlags() & Qt.FramelessWindowHint
assert ocr_dialog.text_edit.toPlainText() == "第一行文字\n第二行文字"
cursor = ocr_dialog.text_edit.textCursor()
cursor.setPosition(0)
cursor.setPosition(3, cursor.KeepAnchor)
ocr_dialog.text_edit.setTextCursor(cursor)
ocr_dialog._copy_selected()
assert QApplication.clipboard().text() == "第一行"
ocr_dialog._copy_all()
assert QApplication.clipboard().text() == "第一行文字\n第二行文字"
button_texts = [button.text() for button in ocr_dialog.findChildren(QPushButton)]
assert button_texts == ["一键复制全部", "关闭"]
ocr_dialog._close_explicitly()

# OCR 图片文字框与右侧文本支持双向高亮。
linked_dialog = shot.OcrImageResultDialog(source, "", regions=[{
    "text": "OCR 文字", "box": [[30, 30], [250, 30], [250, 80], [30, 80]],
    "score": 0.99,
}])
linked_dialog.show()
linked_dialog.reject()
assert linked_dialog.isVisible()
assert len(linked_dialog.image_label.regions) == 1
assert linked_dialog.text_edit.toPlainText() == "OCR 文字"
linked_cursor = linked_dialog.text_edit.textCursor()
linked_cursor.setPosition(0)
linked_cursor.setPosition(3, linked_cursor.KeepAnchor)
linked_dialog.text_edit.setTextCursor(linked_cursor)
linked_dialog._highlight_text_region(0)
assert len(linked_dialog.text_edit.extraSelections()) == 1
assert linked_dialog.text_edit.textCursor().selectedText() == "OCR"
linked_dialog.image_label.set_highlighted_region(0)
assert linked_dialog.image_label.highlighted_index == 0
linked_dialog._close_explicitly()

# 翻译弹窗复用 OCR 展示，并可在原文与译文之间切换。
translation_dialog = shot.OcrImageResultDialog(source, "我叫托尼", regions=[{
    "text": "I am Tony!",
    "box": [[30, 30], [250, 30], [250, 80], [30, 80]], "score": 0.99,
}], translated_texts=["我叫托尼！"])
assert translation_dialog.text_edit.toPlainText() == "我叫托尼！"
assert translation_dialog.toggle_text_button.text() == "切换原文"
translation_dialog._toggle_original_text()
assert translation_dialog.text_edit.toPlainText() == "I am Tony!"
assert translation_dialog.toggle_text_button.text() == "切换译文"
translation_dialog._toggle_original_text()
assert translation_dialog.text_edit.toPlainText() == "我叫托尼！"
translation_dialog._close_explicitly()

print("PASS: screenshot, OCR, OpenAI/Xfyun translation and image redraw")
