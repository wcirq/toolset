# -*- coding: utf-8 -*-
"""区域截图、OCR/翻译和无边框置顶贴图。"""
import base64
import json
import threading
import urllib.error
import urllib.request

# 必须先于 PyQt5 加载其原生 DLL（Windows 下可避免初始化顺序冲突）。
try:
    import onnxruntime  # noqa: F401
except Exception:
    onnxruntime = None

from PyQt5.QtCore import Qt, QPoint, QRect, QSize, QBuffer, QByteArray, pyqtSignal, QThread
from PyQt5.QtGui import (QColor, QCursor, QFont, QFontMetrics, QKeySequence,
                         QPainter, QPen, QPixmap)
from PyQt5.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QLabel, QMenu, QMessageBox,
    QPushButton, QTextEdit, QVBoxLayout, QWidget,
)


def pixmap_to_data_url(pixmap):
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QBuffer.WriteOnly)
    pixmap.save(buffer, "PNG")
    return "data:image/png;base64," + base64.b64encode(bytes(data)).decode("ascii")


def pixmap_to_base64(pixmap):
    """将截图编码为不带 data URL 前缀的 PNG Base64。"""
    return pixmap_to_data_url(pixmap).split(",", 1)[1]


def call_rapidocr_details(pixmap):
    """返回 RapidOCR 文本、四点框和置信度。"""
    image_bytes = base64.b64decode(pixmap_to_base64(pixmap))
    with _rapidocr_lock:
        result = get_rapidocr_engine()(image_bytes)
    texts = getattr(result, "txts", None)
    boxes = getattr(result, "boxes", None)
    scores = getattr(result, "scores", None)
    if texts is None and isinstance(result, (tuple, list)) and result:
        rows = result[0] or []
        texts = [row[1] for row in rows if len(row) > 1]
        boxes = [row[0] for row in rows if len(row) > 1]
        scores = [row[2] for row in rows if len(row) > 2]
    texts = [str(item) for item in (texts if texts is not None else [])]
    box_list = [] if boxes is None else [
        [[float(point[0]), float(point[1])] for point in box]
        for box in boxes]
    score_list = [] if scores is None else [float(item) for item in scores]
    regions = []
    for index, text in enumerate(texts):
        if text.strip() and index < len(box_list):
            regions.append({
                "text": text, "box": box_list[index],
                "score": score_list[index] if index < len(score_list) else 1.0,
            })
    return {"text": "\n".join(texts).strip(), "regions": regions}


def call_umi_ocr(config, pixmap):
    details = call_rapidocr_details(pixmap)
    return details["text"] or "（未识别到文字）"


_rapidocr_engine = None
_rapidocr_lock = threading.Lock()


def get_rapidocr_engine():
    """延迟创建并复用进程内 RapidOCR SMALL 模型。"""
    global _rapidocr_engine
    if _rapidocr_engine is None:
        try:
            from rapidocr import RapidOCR
        except ImportError as exc:
            raise RuntimeError(
                "当前 Python 环境未安装 rapidocr 和 onnxruntime") from exc
        _rapidocr_engine = RapidOCR(params={"Global.log_level": "critical"})
    return _rapidocr_engine


def call_openai_compatible(config, pixmap, translate=False):
    endpoint = str(config.get("screenshot_api_endpoint", "")).strip()
    api_key = str(config.get("screenshot_api_key", "")).strip()
    model = str(config.get("screenshot_api_model", "")).strip()
    if not endpoint or not model:
        raise ValueError("请先在设置中填写 OCR 接口地址和模型")
    if not endpoint.lower().startswith(("https://", "http://")):
        raise ValueError("OCR 接口地址必须以 http:// 或 https:// 开头")
    if translate:
        language = str(config.get("screenshot_translate_language", "简体中文")).strip()
        prompt = (
            "识别图片中的全部文字并翻译为" + language +
            "。保持原有段落和顺序，只输出翻译结果；无法识别的部分用 [无法识别] 标记。")
    else:
        prompt = "准确识别图片中的全部文字，保持原有段落、顺序和标点，只输出识别文本。"
    payload = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {
                    "url": pixmap_to_data_url(pixmap)}},
            ],
        }],
        "temperature": 0,
    }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = "Bearer " + api_key
    request = urllib.request.Request(
        endpoint, data=json.dumps(payload).encode("utf-8"),
        headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"接口返回 HTTP {exc.code}: {detail}") from exc
    choices = result.get("choices") or []
    if not choices:
        raise RuntimeError("接口响应中没有 choices")
    content = choices[0].get("message", {}).get("content", "")
    if isinstance(content, list):
        content = "\n".join(
            str(item.get("text", "")) for item in content
            if isinstance(item, dict) and item.get("text"))
    if not str(content).strip():
        raise RuntimeError("接口没有返回文字")
    return str(content).strip()


def call_openai_translation_lines(config, lines):
    """逐行翻译，返回与 OCR 框数量一致的文字列表。"""
    endpoint = str(config.get("screenshot_api_endpoint", "")).strip()
    api_key = str(config.get("screenshot_api_key", "")).strip()
    model = str(config.get("screenshot_api_model", "")).strip()
    if not endpoint or not model:
        raise ValueError("原图翻译需要填写 OpenAI-compatible 接口地址和模型")
    language = str(config.get("screenshot_translate_language", "简体中文")).strip()
    prompt = (
        f"将下面 JSON 数组中的每一项分别翻译为{language}。"
        "保持数组项数量和顺序完全一致，只输出 JSON 字符串数组：\n" +
        json.dumps(list(lines), ensure_ascii=False))
    payload = {"model": model, "messages": [{"role": "user", "content": prompt}],
               "temperature": 0}
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = "Bearer " + api_key
    request = urllib.request.Request(
        endpoint, data=json.dumps(payload).encode("utf-8"),
        headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=60) as response:
        result = json.loads(response.read().decode("utf-8"))
    content = str((result.get("choices") or [{}])[0].get(
        "message", {}).get("content", "")).strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        translated = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError("翻译接口未返回有效的 JSON 字符串数组") from exc
    if not isinstance(translated, list) or len(translated) != len(lines):
        raise RuntimeError("翻译结果行数与 OCR 文字框数量不一致")
    return [str(item) for item in translated]


def _sample_background(image, rect):
    """采样文字框外围颜色，取各通道中位数以降低噪点影响。"""
    outer = rect.adjusted(-3, -3, 3, 3).intersected(image.rect())
    colors = []
    step = max(1, min(4, max(outer.width(), outer.height()) // 50))
    for x in range(outer.left(), outer.right() + 1, step):
        colors.extend((image.pixelColor(x, outer.top()),
                       image.pixelColor(x, outer.bottom())))
    for y in range(outer.top(), outer.bottom() + 1, step):
        colors.extend((image.pixelColor(outer.left(), y),
                       image.pixelColor(outer.right(), y)))
    if not colors:
        return QColor(Qt.white)
    channels = [sorted(getattr(color, name)() for color in colors)
                for name in ("red", "green", "blue")]
    middle = len(colors) // 2
    return QColor(channels[0][middle], channels[1][middle], channels[2][middle])


def render_text_on_image(pixmap, regions, replacement_texts=None):
    """擦除原文字并在对应 OCR 框内绘制识别/翻译结果。"""
    result = pixmap.copy()
    image = result.toImage()
    painter = QPainter(result)
    painter.setRenderHint(QPainter.TextAntialiasing)
    for index, region in enumerate(regions):
        points = region.get("box") or []
        if len(points) < 4:
            continue
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        rect = QRect(int(min(xs)), int(min(ys)),
                     max(2, int(max(xs) - min(xs))),
                     max(2, int(max(ys) - min(ys)))).intersected(result.rect())
        if rect.isEmpty():
            continue
        background = _sample_background(image, rect)
        painter.fillRect(rect.adjusted(-1, -1, 1, 1), background)
        text = (replacement_texts[index] if replacement_texts is not None
                and index < len(replacement_texts) else region.get("text", ""))
        luminance = (background.red() * 299 + background.green() * 587
                     + background.blue() * 114) / 1000
        painter.setPen(QColor("#111111") if luminance > 145 else QColor("#F5F5F5"))
        font = QFont("Microsoft YaHei UI")
        size = max(8, int(rect.height() * 0.72))
        draw_rect = rect.adjusted(1, 0, -1, 0)
        while size > 7:
            font.setPixelSize(size)
            bounds = QFontMetrics(font).boundingRect(
                draw_rect, Qt.AlignLeft | Qt.AlignVCenter | Qt.TextWordWrap, text)
            if bounds.width() <= draw_rect.width() and bounds.height() <= draw_rect.height():
                break
            size -= 1
        painter.setFont(font)
        painter.drawText(draw_rect,
                         Qt.AlignLeft | Qt.AlignVCenter | Qt.TextWordWrap, text)
    painter.end()
    return result


class ScreenshotApiWorker(QThread):
    succeeded = pyqtSignal(str, object)
    failed = pyqtSignal(str)

    def __init__(self, config, pixmap, mode, parent=None):
        super().__init__(parent)
        self.config = dict(config)
        self.pixmap = QPixmap(pixmap)
        self.mode = mode

    def run(self):
        try:
            provider = self.config.get("screenshot_ocr_provider", "disabled")
            image_mode = self.config.get("screenshot_result_mode", "image") == "image"
            if image_mode:
                details = call_rapidocr_details(self.pixmap)
                if not details["regions"]:
                    raise RuntimeError("未识别到可在原图定位的文字")
                replacements = None
                if self.mode == "translate":
                    replacements = call_openai_translation_lines(
                        self.config, [item["text"] for item in details["regions"]])
                payload = {"text": "\n".join(replacements) if replacements
                           else details["text"], "regions": details["regions"],
                           "replacements": replacements}
            elif provider in ("umi_ocr", "rapidocr_local"):
                if self.mode == "translate":
                    raise ValueError("弹窗翻译请切换到 OpenAI-compatible 服务")
                payload = {"text": call_umi_ocr(self.config, self.pixmap)}
            else:
                payload = {"text": call_openai_compatible(
                    self.config, self.pixmap, self.mode == "translate")}
            self.succeeded.emit(self.mode, payload)
        except Exception as exc:
            self.failed.emit(str(exc))


class TextResultDialog(QDialog):
    def __init__(self, title, text, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self.resize(560, 360)
        layout = QVBoxLayout(self)
        edit = QTextEdit()
        edit.setPlainText(text)
        layout.addWidget(edit)
        row = QHBoxLayout()
        copy_btn = QPushButton("复制文字")
        copy_btn.clicked.connect(
            lambda: QApplication.clipboard().setText(edit.toPlainText()))
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        row.addStretch(); row.addWidget(copy_btn); row.addWidget(close_btn)
        layout.addLayout(row)


class PinnedImageWindow(QWidget):
    closed = pyqtSignal(object)

    def __init__(self, pixmap, position=None):
        super().__init__(None)
        self.pixmap = QPixmap(pixmap)
        self._drag_offset = None
        self._scale = 1.0
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setCursor(Qt.SizeAllCursor)
        self._apply_size()
        if position is None:
            position = QCursor.pos() + QPoint(16, 16)
        self.move(position)
        self.setToolTip("拖动移动 · 滚轮缩放 · 双击关闭 · 右键操作")

    def _apply_size(self):
        base = self.pixmap.size() / max(1.0, self.pixmap.devicePixelRatio())
        width = max(80, min(1600, int(base.width() * self._scale)))
        height = max(60, min(1200, int(base.height() * self._scale)))
        self.resize(width, height)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.drawPixmap(self.rect(), self.pixmap)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_offset = event.globalPos() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPos() - self._drag_offset)

    def mouseReleaseEvent(self, event):
        self._drag_offset = None

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.close()

    def wheelEvent(self, event):
        old_center = self.frameGeometry().center()
        self._scale = max(0.2, min(4.0,
            self._scale * (1.1 if event.angleDelta().y() > 0 else 1 / 1.1)))
        self._apply_size()
        self.move(old_center - self.rect().center())

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.addAction("复制图片", lambda: QApplication.clipboard().setPixmap(self.pixmap))
        menu.addAction("原始大小", self._reset_scale)
        menu.addSeparator()
        menu.addAction("关闭贴图", self.close)
        menu.exec_(event.globalPos())

    def _reset_scale(self):
        self._scale = 1.0
        self._apply_size()

    def closeEvent(self, event):
        self.closed.emit(self)
        super().closeEvent(event)


class ScreenshotOverlay(QWidget):
    pin_requested = pyqtSignal(QPixmap, QPoint)

    def __init__(self, config, parent=None):
        super().__init__(None)
        self.config = dict(config)
        self.screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        self.snapshot = self.screen.grabWindow(0)
        self.origin = QPoint()
        self.current = QPoint()
        self.selecting = False
        self.selection = QRect()
        self._workers = []
        self._close_after_worker = False
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setCursor(Qt.CrossCursor)
        self.setGeometry(self.screen.geometry())
        self.toolbar = self._create_toolbar()
        self.toolbar.hide()

    def _create_toolbar(self):
        bar = QWidget(self)
        bar.setStyleSheet(
            "QWidget{background:#202124;border-radius:6px;}"
            "QPushButton{color:white;background:transparent;border:0;padding:7px 10px;}"
            "QPushButton:hover{background:#3c4043;border-radius:4px;}")
        row = QHBoxLayout(bar)
        row.setContentsMargins(5, 4, 5, 4); row.setSpacing(2)
        for title, callback in (
            ("复制", self._copy), ("OCR", lambda: self._run_api("ocr")),
            ("翻译", lambda: self._run_api("translate")),
            ("贴图", self._pin), ("取消", self.close)):
            button = QPushButton(title)
            button.clicked.connect(callback)
            row.addWidget(button)
        bar.adjustSize()
        return bar

    def selected_pixmap(self):
        rect = self.selection.normalized().intersected(self.rect())
        if rect.width() < 2 or rect.height() < 2:
            return QPixmap()
        dpr = self.snapshot.devicePixelRatio()
        source = QRect(int(rect.x() * dpr), int(rect.y() * dpr),
                       int(rect.width() * dpr), int(rect.height() * dpr))
        pixmap = self.snapshot.copy(source)
        pixmap.setDevicePixelRatio(dpr)
        return pixmap

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawPixmap(self.rect(), self.snapshot)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 105))
        rect = self.selection.normalized()
        if not rect.isEmpty():
            dpr = self.snapshot.devicePixelRatio()
            source = QRect(int(rect.x() * dpr), int(rect.y() * dpr),
                           int(rect.width() * dpr), int(rect.height() * dpr))
            painter.drawPixmap(rect, self.snapshot, source)
            painter.setPen(QPen(QColor("#39A8FF"), 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(rect.adjusted(0, 0, -1, -1))
            painter.setPen(Qt.white)
            painter.drawText(rect.topLeft() + QPoint(5, -7),
                             f"{rect.width()} × {rect.height()}")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and not self.toolbar.geometry().contains(event.pos()):
            self.toolbar.hide()
            self.origin = event.pos(); self.current = event.pos()
            self.selection = QRect(self.origin, self.current)
            self.selecting = True; self.update()

    def mouseMoveEvent(self, event):
        if self.selecting:
            self.current = event.pos()
            self.selection = QRect(self.origin, self.current).normalized()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.selecting:
            self.selecting = False
            self.selection = QRect(self.origin, event.pos()).normalized()
            if self.selection.width() < 8 or self.selection.height() < 8:
                self.selection = QRect(); self.update(); return
            self.toolbar.adjustSize()
            x = min(self.width() - self.toolbar.width() - 8,
                    max(8, self.selection.right() - self.toolbar.width()))
            y = self.selection.bottom() + 8
            if y + self.toolbar.height() > self.height():
                y = max(8, self.selection.top() - self.toolbar.height() - 8)
            self.toolbar.move(x, y); self.toolbar.show(); self.toolbar.raise_()
            self.update()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter) and not self.selection.isEmpty():
            self._pin()

    def _copy(self):
        pixmap = self.selected_pixmap()
        if not pixmap.isNull():
            QApplication.clipboard().setPixmap(pixmap)
            self.close()

    def _pin(self):
        pixmap = self.selected_pixmap()
        if not pixmap.isNull():
            pos = self.mapToGlobal(self.selection.topLeft())
            self.pin_requested.emit(pixmap, pos)
            self.close()

    def _run_api(self, mode):
        if self.config.get("screenshot_ocr_provider", "disabled") == "disabled":
            QMessageBox.information(self, "OCR 未配置", "请先在设置中启用并配置第三方 OCR 接口。")
            return
        pixmap = self.selected_pixmap()
        if pixmap.isNull():
            return
        self.toolbar.setEnabled(False)
        worker = ScreenshotApiWorker(self.config, pixmap, mode, self)
        self._workers.append(worker)
        worker.succeeded.connect(self._api_succeeded)
        worker.failed.connect(self._api_failed)
        worker.finished.connect(lambda: self.toolbar.setEnabled(True))
        worker.finished.connect(lambda: self._workers.remove(worker)
                                if worker in self._workers else None)
        worker.finished.connect(self._finish_api_worker)
        worker.start()

    def _api_succeeded(self, mode, payload):
        title = "截图翻译结果" if mode == "translate" else "OCR 识别结果"
        if self.config.get("screenshot_result_mode", "image") == "image":
            pixmap = render_text_on_image(
                self.selected_pixmap(), payload.get("regions", []),
                payload.get("replacements"))
            pos = self.mapToGlobal(self.selection.topLeft())
            self.pin_requested.emit(pixmap, pos)
            self.hide()
            self._close_after_worker = True
        else:
            TextResultDialog(title, payload.get("text", ""), self).exec_()

    def _finish_api_worker(self):
        if self._close_after_worker and not any(
                worker.isRunning() for worker in self._workers):
            self.close()

    def _api_failed(self, message):
        QMessageBox.warning(self, "调用失败", message)

    def closeEvent(self, event):
        # urllib 请求无法安全强杀；避免运行中的 QThread 随窗口析构。
        if any(worker.isRunning() for worker in self._workers):
            event.ignore()
            return
        super().closeEvent(event)


__all__ = [
    "PinnedImageWindow", "ScreenshotOverlay", "call_openai_compatible",
    "call_umi_ocr", "call_rapidocr_details", "get_rapidocr_engine",
    "pixmap_to_base64", "render_text_on_image",
]
