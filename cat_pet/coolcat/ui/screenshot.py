# -*- coding: utf-8 -*-
"""区域截图、OCR/翻译和无边框置顶贴图。"""
import base64
import ctypes
from ctypes import wintypes
import hashlib
import hmac
import json
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from email.utils import format_datetime

# 必须先于 PyQt5 加载其原生 DLL（Windows 下可避免初始化顺序冲突）。
try:
    import onnxruntime  # noqa: F401
except Exception:
    onnxruntime = None

from PyQt5.QtCore import (Qt, QPoint, QRect, QSize, QBuffer, QByteArray,
                          pyqtSignal, QThread, QTimer, QEvent)
from PyQt5.QtGui import (QColor, QCursor, QFont, QFontMetrics, QKeySequence,
                         QPainter, QPen, QPixmap, QTextCursor)
from PyQt5.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QLabel, QMenu, QMessageBox,
    QPushButton, QTextEdit, QVBoxLayout, QWidget,
)


def _top_level_window_rect_at(global_pos, excluded_hwnd=0):
    """返回指定屏幕坐标下最上层的可见应用窗口矩形。"""
    if not hasattr(ctypes, "windll"):
        return QRect()
    user32 = ctypes.windll.user32
    point_x, point_y = int(global_pos.x()), int(global_pos.y())
    found = []
    rect_type = wintypes.RECT
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND,
                                      wintypes.LPARAM)

    def visit(hwnd, _lparam):
        if int(hwnd) == int(excluded_hwnd) or not user32.IsWindowVisible(hwnd):
            return True
        if user32.IsIconic(hwnd):
            return True
        class_name = ctypes.create_unicode_buffer(128)
        user32.GetClassNameW(hwnd, class_name, len(class_name))
        if class_name.value in ("Progman", "WorkerW", "Shell_TrayWnd"):
            return True
        native_rect = rect_type()
        if not user32.GetWindowRect(hwnd, ctypes.byref(native_rect)):
            return True
        if (native_rect.left <= point_x < native_rect.right and
                native_rect.top <= point_y < native_rect.bottom and
                native_rect.right - native_rect.left >= 8 and
                native_rect.bottom - native_rect.top >= 8):
            found.append(QRect(native_rect.left, native_rect.top,
                               native_rect.right - native_rect.left,
                               native_rect.bottom - native_rect.top))
            return False
        return True

    callback = callback_type(visit)
    user32.EnumWindows(callback, 0)
    return found[0] if found else QRect()


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
            raise RuntimeError("RapidOCR 初始化失败：" + str(exc)) from exc
        _rapidocr_engine = RapidOCR(params={"Global.log_level": "critical"})
    return _rapidocr_engine


def call_openai_compatible(config, pixmap, translate=False):
    prefix = "screenshot_translate_api" if translate else "screenshot_ocr_api"
    endpoint = str(config.get(prefix + "_endpoint", "")).strip()
    api_key = str(config.get(prefix + "_key", "")).strip()
    model = str(config.get(prefix + "_model", "")).strip()
    if not endpoint or not model:
        service = "翻译" if translate else "OCR"
        raise ValueError(f"请先在设置中填写{service}接口地址和模型")
    if not endpoint.lower().startswith(("https://", "http://")):
        raise ValueError("OCR 接口地址必须以 http:// 或 https:// 开头")
    if translate:
        language = _language_prompt_name(
            config.get("screenshot_translate_language", "cn"))
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
    endpoint = str(config.get("screenshot_translate_api_endpoint", "")).strip()
    api_key = str(config.get("screenshot_translate_api_key", "")).strip()
    model = str(config.get("screenshot_translate_api_model", "")).strip()
    if not endpoint or not model:
        raise ValueError("原图翻译需要填写 OpenAI-compatible 接口地址和模型")
    language = _language_prompt_name(
        config.get("screenshot_translate_language", "cn"))
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


XFYUN_LANGUAGE_CODES = {
    "中文": "cn", "简体中文": "cn", "汉语": "cn", "cn": "cn",
    "英语": "en", "英文": "en", "english": "en", "en": "en",
    "日语": "ja", "日本語": "ja", "ja": "ja",
    "韩语": "ko", "ko": "ko", "法语": "fr", "fr": "fr",
    "德语": "de", "de": "de", "俄语": "ru", "ru": "ru",
    "西班牙语": "es", "es": "es", "阿拉伯语": "ar", "ar": "ar",
    "意大利语": "it", "it": "it", "葡萄牙语": "pt", "pt": "pt",
    "越南语": "vi", "vi": "vi", "泰语": "th", "th": "th",
}

LANGUAGE_CODE_NAMES = {
    "cn": "汉语普通话", "en": "英语", "ii": "彝语", "yue": "广东话",
    "ja": "日语", "ru": "俄语", "fr": "法语", "es": "西班牙语",
    "ar": "阿拉伯语", "it": "意大利语", "tr": "土耳其语", "vi": "越南语",
    "th": "泰语", "ko": "韩语", "de": "德语", "kka": "哈萨克语",
    "pt": "葡萄牙语",
}


def _language_prompt_name(value):
    code = _xfyun_language_code(value)
    return f"{LANGUAGE_CODE_NAMES.get(code, code)}（{code}）"


def _xfyun_language_code(value):
    text = str(value).strip()
    return XFYUN_LANGUAGE_CODES.get(text.lower(),
                                     XFYUN_LANGUAGE_CODES.get(text, text))


def _normalize_xfyun_translation_text(value):
    """兼容讯飞返回纯文本或再次 JSON 编码的翻译结果。"""
    if isinstance(value, dict):
        trans_result = value.get("trans_result")
        if isinstance(trans_result, dict) and "dst" in trans_result:
            return _normalize_xfyun_translation_text(trans_result["dst"])
        for key in ("dst", "text", "result"):
            if key in value:
                return _normalize_xfyun_translation_text(value[key])
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "\n".join(_normalize_xfyun_translation_text(item)
                         for item in value)
    text = str(value).strip()
    if not text:
        return text
    try:
        decoded = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        # 有些响应由多个独立 JSON 对象按行组成。
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if len(lines) > 1:
            parsed_lines = []
            for line in lines:
                try:
                    parsed_lines.append(_normalize_xfyun_translation_text(
                        json.loads(line)))
                except (json.JSONDecodeError, TypeError):
                    return text
            return "\n".join(parsed_lines)
        return text
    if isinstance(decoded, (dict, list)):
        return _normalize_xfyun_translation_text(decoded)
    return str(decoded)


def call_xfyun_translation(config, text):
    """调用讯飞机器翻译 WebAPI v2。"""
    endpoint = str(config.get(
        "screenshot_xfyun_endpoint", "https://itrans.xfyun.cn/v2/its")).strip()
    app_id = str(config.get("screenshot_xfyun_app_id", "")).strip()
    api_key = str(config.get("screenshot_xfyun_api_key", "")).strip()
    api_secret = str(config.get("screenshot_xfyun_api_secret", "")).strip()
    if not all((endpoint, app_id, api_key, api_secret)):
        raise ValueError("请填写讯飞翻译的 APPID、API Key、API Secret 和接口地址")
    parsed = urllib.parse.urlparse(endpoint)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("讯飞翻译接口地址无效")
    host = parsed.netloc
    request_uri = parsed.path or "/v2/its"
    if parsed.query:
        request_uri += "?" + parsed.query
    source = _xfyun_language_code(
        config.get("screenshot_xfyun_from", "cn"))
    target = _xfyun_language_code(
        config.get("screenshot_translate_language", "cn"))
    body = json.dumps({
        "common": {"app_id": app_id},
        "business": {"from": source, "to": target},
        "data": {"text": base64.b64encode(
            str(text).encode("utf-8")).decode("ascii")},
    }, ensure_ascii=False, separators=(",", ":"))
    digest = "SHA-256=" + base64.b64encode(
        hashlib.sha256(body.encode("utf-8")).digest()).decode("ascii")
    date = format_datetime(datetime.now(timezone.utc), usegmt=True)
    signature_origin = (
        f"host: {host}\ndate: {date}\nPOST {request_uri} HTTP/1.1\n"
        f"digest: {digest}")
    signature = base64.b64encode(hmac.new(
        api_secret.encode("utf-8"), signature_origin.encode("utf-8"),
        hashlib.sha256).digest()).decode("ascii")
    authorization = (
        f'api_key="{api_key}", algorithm="hmac-sha256", '
        f'headers="host date request-line digest", signature="{signature}"')
    request = urllib.request.Request(endpoint, data=body.encode("utf-8"), headers={
        "Content-Type": "application/json", "Accept": "application/json",
        "Host": host, "Date": date, "Digest": digest,
        "Authorization": authorization,
    }, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"讯飞翻译 HTTP {exc.code}: {detail}") from exc
    if int(result.get("code", -1)) != 0:
        raise RuntimeError(
            f"讯飞翻译失败 code={result.get('code')}: {result.get('message', '')}")
    try:
        return _normalize_xfyun_translation_text(
            result["data"]["result"]["trans_result"]["dst"])
    except (KeyError, TypeError) as exc:
        raise RuntimeError("讯飞翻译响应中缺少目标文本") from exc


def call_xfyun_v1_translation(config, text):
    """调用讯飞机器翻译 2.0（/v1/its 新版协议）。"""
    endpoint = str(config.get(
        "screenshot_xfyun_v1_endpoint",
        "https://itrans.xf-yun.com/v1/its")).strip()
    app_id = str(config.get("screenshot_xfyun_v1_app_id", "")).strip()
    api_key = str(config.get("screenshot_xfyun_v1_api_key", "")).strip()
    api_secret = str(config.get("screenshot_xfyun_v1_api_secret", "")).strip()
    res_id = str(config.get("screenshot_xfyun_res_id", "")).strip()
    if not all((endpoint, app_id, api_key, api_secret)):
        raise ValueError(
            "请填写讯飞翻译 2.0 的 APPID、API Key、API Secret 和接口地址")
    parsed = urllib.parse.urlparse(endpoint)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("讯飞翻译 2.0 接口地址无效")
    source = _xfyun_language_code(config.get("screenshot_xfyun_from", "cn"))
    target = _xfyun_language_code(
        config.get("screenshot_translate_language", "cn"))
    if (source == "cn") == (target == "cn"):
        raise ValueError("讯飞翻译 2.0 目前仅支持汉语普通话与其他语种互译")
    raw_text = str(text)
    encoded_text = raw_text.encode("utf-8")
    byte_limit = 15000 if source == "cn" else 5000
    if len(raw_text) > 5000 or len(encoded_text) > byte_limit:
        raise ValueError(
            f"翻译文本超出讯飞限制（最多 5000 字符，当前源语言字节上限 {byte_limit}）")
    request_path = parsed.path or "/v1/its"
    date = format_datetime(datetime.now(timezone.utc), usegmt=True)
    signature_origin = (
        f"host: {parsed.netloc}\ndate: {date}\nPOST {request_path} HTTP/1.1")
    signature = base64.b64encode(hmac.new(
        api_secret.encode("utf-8"), signature_origin.encode("utf-8"),
        hashlib.sha256).digest()).decode("ascii")
    authorization_origin = (
        f'api_key="{api_key}", algorithm="hmac-sha256", '
        f'headers="host date request-line", signature="{signature}"')
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query.extend((
        ("host", parsed.netloc), ("date", date),
        ("authorization", base64.b64encode(
            authorization_origin.encode("utf-8")).decode("ascii"))))
    request_url = urllib.parse.urlunparse(parsed._replace(
        query=urllib.parse.urlencode(query)))
    header = {"app_id": app_id, "status": 3}
    if res_id:
        header["res_id"] = res_id
    body = {
        "header": header,
        "parameter": {"its": {
            "from": source, "to": target, "result": {}}},
        "payload": {"input_data": {
            "encoding": "utf8", "status": 3,
            "text": base64.b64encode(encoded_text).decode("ascii")}},
    }
    request = urllib.request.Request(
        request_url, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Host": parsed.netloc,
                 "app_id": app_id}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"讯飞翻译 2.0 HTTP {exc.code}: {detail}") from exc
    response_header = result.get("header") or {}
    if int(response_header.get("code", 0)) != 0:
        raise RuntimeError(
            f"讯飞翻译 2.0 失败 code={response_header.get('code')}: "
            f"{response_header.get('message', '')}")
    try:
        encoded_result = result["payload"]["result"]["text"]
        return _normalize_xfyun_translation_text(
            base64.b64decode(encoded_result).decode("utf-8"))
    except (KeyError, TypeError, ValueError, UnicodeDecodeError) as exc:
        raise RuntimeError("讯飞翻译 2.0 响应中缺少有效目标文本") from exc


def call_translation_lines(config, lines):
    provider = config.get("screenshot_translate_provider", "disabled")
    if provider == "xfyun":
        return _call_xfyun_translation_lines(
            config, lines, call_xfyun_translation)
    if provider == "xfyun_v1":
        return _call_xfyun_translation_lines(
            config, lines, call_xfyun_v1_translation)
    if provider == "openai_compatible":
        return call_openai_translation_lines(config, lines)
    raise ValueError("请先配置翻译服务")


def _call_xfyun_translation_lines(config, lines, translate_one):
    """合并 OCR 文本为一次讯飞请求，并恢复到原文字框顺序。"""
    source_lines = [str(line) for line in lines]
    if not source_lines:
        return []
    if len(source_lines) == 1:
        return [translate_one(config, source_lines[0])]
    separators = [f"__CCSEP_{index:04d}__"
                  for index in range(1, len(source_lines))]
    pieces = []
    for index, line in enumerate(source_lines):
        if index:
            pieces.append(separators[index - 1])
        pieces.append(line)
    batched_text = "\n".join(pieces)
    try:
        translated = translate_one(config, batched_text)
    except ValueError as exc:
        if "超出讯飞限制" in str(exc):
            return [translate_one(config, line) for line in source_lines]
        raise
    # 大多数机器翻译接口会原样保留 ASCII 标记；允许标记前后空白变化。
    parts = re.split(r"\s*__CCSEP_\d{4}__\s*", translated)
    if len(parts) == len(source_lines):
        return [part.strip() for part in parts]
    translated_lines = [line.strip() for line in translated.splitlines()
                        if line.strip()]
    if len(translated_lines) == len(source_lines):
        return translated_lines
    # 少数语言模型可能破坏分隔符，此时保证正确性，回退为逐条请求。
    return [translate_one(config, line) for line in source_lines]


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


def _sample_text_color(image, rect, background):
    """从文字框内部估算原文字前景色。"""
    inner = rect.adjusted(1, 1, -1, -1).intersected(image.rect())
    if inner.isEmpty():
        return QColor("#111111")
    bg_luma = (background.red() * 299 + background.green() * 587
               + background.blue() * 114) / 1000
    candidates = []
    step = max(1, min(3, max(inner.width(), inner.height()) // 80))
    for y in range(inner.top(), inner.bottom() + 1, step):
        for x in range(inner.left(), inner.right() + 1, step):
            color = image.pixelColor(x, y)
            distance = ((color.red() - background.red()) ** 2
                        + (color.green() - background.green()) ** 2
                        + (color.blue() - background.blue()) ** 2) ** 0.5
            luma = (color.red() * 299 + color.green() * 587
                    + color.blue() * 114) / 1000
            # 文字通常位于背景亮度的另一侧；同时保留明显的彩色文字。
            opposite = ((bg_luma >= 145 and luma < bg_luma - 28) or
                        (bg_luma < 145 and luma > bg_luma + 28))
            if distance >= 55 and (opposite or distance >= 100):
                candidates.append(color)
    if not candidates:
        return QColor("#111111") if bg_luma > 145 else QColor("#F5F5F5")
    channels = [sorted(getattr(color, name)() for color in candidates)
                for name in ("red", "green", "blue")]
    middle = len(candidates) // 2
    sampled = QColor(channels[0][middle], channels[1][middle], channels[2][middle])
    # 避免采样结果与填充背景过近而看不清。
    if abs((sampled.red() * 299 + sampled.green() * 587
            + sampled.blue() * 114) / 1000 - bg_luma) < 24:
        return QColor("#111111") if bg_luma > 145 else QColor("#F5F5F5")
    return sampled


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
        foreground = _sample_text_color(image, rect, background)
        painter.fillRect(rect.adjusted(-1, -1, 1, 1), background)
        text = (replacement_texts[index] if replacement_texts is not None
                and index < len(replacement_texts) else region.get("text", ""))
        painter.setPen(foreground)
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
            ocr_provider = self.config.get(
                "screenshot_ocr_provider", "rapidocr_local")
            translate_provider = self.config.get(
                "screenshot_translate_provider", "disabled")
            if self.mode == "translate":
                details = call_rapidocr_details(self.pixmap)
                if not details["regions"]:
                    raise RuntimeError("未识别到可翻译的文字")
                if translate_provider not in (
                        "openai_compatible", "xfyun", "xfyun_v1"):
                    raise ValueError("请先在设置中启用并配置翻译服务")
                replacements = call_translation_lines(
                    self.config, [item["text"] for item in details["regions"]])
                payload = {
                    "text": "\n".join(replacements),
                    "original_text": details["text"],
                    "regions": details["regions"],
                    "replacements": replacements,
                }
            elif self.mode == "ocr":
                details = call_rapidocr_details(self.pixmap)
                regions = details["regions"]
                text = details["text"]
                if ocr_provider == "openai_compatible":
                    text = call_openai_compatible(
                        self.config, self.pixmap, translate=False)
                    cloud_lines = [line.strip() for line in text.splitlines()
                                   if line.strip()]
                    if len(cloud_lines) == len(regions):
                        regions = [dict(region, text=cloud_lines[index])
                                   for index, region in enumerate(regions)]
                    else:
                        # 云端文本无法与本地框可靠对应时，不显示错误映射。
                        regions = []
                payload = {"text": text, "regions": regions}
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


class OcrRegionImageLabel(QLabel):
    region_hovered = pyqtSignal(int)

    def __init__(self, source_pixmap, regions, parent=None):
        super().__init__(parent)
        self.source_pixmap = QPixmap(source_pixmap)
        self.regions = list(regions or [])
        self.highlighted_index = -1
        self.display_pixmap = self.source_pixmap.scaled(
            760, 650, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.setPixmap(self.display_pixmap)
        self.setAlignment(Qt.AlignCenter)
        self.setMouseTracking(True)
        self.setStyleSheet("background:#17181A;border-radius:4px;")

    def _display_region_rect(self, region):
        points = region.get("box") or []
        if len(points) < 4 or self.source_pixmap.isNull():
            return QRect()
        source_size = self.source_pixmap.size() / max(
            1.0, self.source_pixmap.devicePixelRatio())
        scale_x = self.display_pixmap.width() / max(1, source_size.width())
        scale_y = self.display_pixmap.height() / max(1, source_size.height())
        offset_x = (self.width() - self.display_pixmap.width()) // 2
        offset_y = (self.height() - self.display_pixmap.height()) // 2
        xs, ys = [point[0] for point in points], [point[1] for point in points]
        return QRect(
            offset_x + int(min(xs) * scale_x),
            offset_y + int(min(ys) * scale_y),
            max(2, int((max(xs) - min(xs)) * scale_x)),
            max(2, int((max(ys) - min(ys)) * scale_y)))

    def set_highlighted_region(self, index):
        index = index if 0 <= index < len(self.regions) else -1
        if index != self.highlighted_index:
            self.highlighted_index = index
            self.update()

    def mouseMoveEvent(self, event):
        hovered = -1
        # 小框优先，避免重叠区域总命中较大的外框。
        matches = []
        for index, region in enumerate(self.regions):
            rect = self._display_region_rect(region)
            if rect.contains(event.pos()):
                matches.append((rect.width() * rect.height(), index))
        if matches:
            hovered = min(matches)[1]
        if hovered != self.highlighted_index:
            self.set_highlighted_region(hovered)
            self.region_hovered.emit(hovered)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        if self.highlighted_index != -1:
            self.set_highlighted_region(-1)
            self.region_hovered.emit(-1)
        super().leaveEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        for index, region in enumerate(self.regions):
            rect = self._display_region_rect(region)
            if rect.isEmpty():
                continue
            highlighted = index == self.highlighted_index
            painter.setPen(QPen(
                QColor("#FFD54F") if highlighted else QColor("#39A8FF"),
                3 if highlighted else 1))
            painter.setBrush(QColor(255, 213, 79, 55) if highlighted
                             else QColor(57, 168, 255, 20))
            painter.drawRect(rect.adjusted(0, 0, -1, -1))
        painter.end()


class OcrImageResultDialog(QDialog):
    """左侧原图、右侧可选择和一键复制的 OCR 文本面板。"""

    def __init__(self, pixmap, text, parent=None, regions=None,
                 translated_texts=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self._explicit_close_requested = False
        self.source_pixmap = QPixmap(pixmap)
        self.regions = list(regions or [])
        self.original_lines = [
            str(region.get("text", "")).replace("\n", " ")
            for region in self.regions]
        self.translated_lines = ([str(item) for item in translated_texts]
                                 if translated_texts is not None else None)
        self._showing_original = False
        self._highlighted_text_index = -1
        self._drag_offset = None

        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        self.image_label = OcrRegionImageLabel(
            self.source_pixmap, self.regions)
        display = self.image_label.display_pixmap
        self.image_label.setMinimumSize(min(240, display.width()),
                                        min(160, display.height()))
        root.addWidget(self.image_label, 1)

        panel = QWidget()
        panel.setMinimumWidth(260)
        panel.setMaximumWidth(380)
        side = QVBoxLayout(panel)
        side.setContentsMargins(8, 8, 8, 8)
        title = QLabel("识别到的文本")
        title.setStyleSheet("font-weight:bold;")
        side.addWidget(title)
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        mapped_text = ("\n".join(self.translated_lines)
                       if self.translated_lines is not None
                       else "\n".join(self.original_lines)
                       if self.regions else text)
        self.text_edit.setPlainText(mapped_text)
        self.text_edit.setToolTip("可鼠标选择文字后按 Ctrl+C，或使用下方复制按钮")
        self.text_edit.setContextMenuPolicy(Qt.CustomContextMenu)
        self.text_edit.customContextMenuRequested.connect(self._show_text_menu)
        self.text_edit.viewport().setMouseTracking(True)
        self.text_edit.viewport().installEventFilter(self)
        self.image_label.region_hovered.connect(self._highlight_text_region)
        side.addWidget(self.text_edit, 1)
        buttons = QHBoxLayout()
        if self.translated_lines is not None:
            self.toggle_text_button = QPushButton("切换原文")
            self.toggle_text_button.setAutoDefault(False)
            self.toggle_text_button.clicked.connect(self._toggle_original_text)
            buttons.addWidget(self.toggle_text_button)
        self.copy_all_button = QPushButton("一键复制全部")
        self.copy_all_button.setAutoDefault(False)
        self.copy_all_button.setDefault(False)
        self.copy_all_button.clicked.connect(self._copy_all)
        buttons.addWidget(self.copy_all_button)
        close_button = QPushButton("关闭")
        close_button.setAutoDefault(False)
        close_button.setDefault(False)
        close_button.clicked.connect(self._close_explicitly)
        buttons.addWidget(close_button)
        side.addLayout(buttons)
        panel.setStyleSheet("QWidget{background:#F5F6F8;border-radius:5px;}")
        root.addWidget(panel)

        width = min(1180, max(620, display.width() + 310))
        height = min(720, max(360, display.height() + 24))
        self.resize(width, height)

    def _toggle_original_text(self):
        if self.translated_lines is None:
            return
        self._showing_original = not self._showing_original
        lines = (self.original_lines if self._showing_original
                 else self.translated_lines)
        self.text_edit.setPlainText("\n".join(lines))
        self.text_edit.setExtraSelections([])
        self._highlighted_text_index = -1
        self.image_label.set_highlighted_region(-1)
        self.toggle_text_button.setText(
            "切换译文" if self._showing_original else "切换原文")

    def _highlight_text_region(self, index):
        index = index if 0 <= index < len(self.regions) else -1
        if index == self._highlighted_text_index:
            return
        self._highlighted_text_index = index
        selections = []
        if index >= 0:
            block = self.text_edit.document().findBlockByNumber(index)
            if block.isValid():
                selection = QTextEdit.ExtraSelection()
                selection.cursor = QTextCursor(block)
                selection.cursor.select(QTextCursor.BlockUnderCursor)
                selection.format.setBackground(QColor("#FFE082"))
                selections.append(selection)
        self.text_edit.setExtraSelections(selections)

    def eventFilter(self, watched, event):
        if watched is self.text_edit.viewport() and self.regions:
            if event.type() == QEvent.MouseMove:
                if event.buttons() & Qt.LeftButton:
                    # 用户拖选文字时暂停联动，避免高频额外选区刷新。
                    self.image_label.set_highlighted_region(-1)
                    if self._highlighted_text_index != -1:
                        self._highlighted_text_index = -1
                        self.text_edit.setExtraSelections([])
                    return super().eventFilter(watched, event)
                cursor = self.text_edit.cursorForPosition(event.pos())
                index = cursor.blockNumber()
                self.image_label.set_highlighted_region(index)
                self._highlight_text_region(index)
            elif event.type() == QEvent.Leave:
                self.image_label.set_highlighted_region(-1)
                self._highlighted_text_index = -1
                self.text_edit.setExtraSelections([])
        return super().eventFilter(watched, event)

    def _copy_selected(self):
        cursor = self.text_edit.textCursor()
        if cursor.hasSelection():
            QApplication.clipboard().setText(cursor.selectedText().replace("\u2029", "\n"))

    def _show_text_menu(self, position):
        menu = QMenu(self.text_edit)
        menu.setStyleSheet("""
            QMenu {
                background: #FFFFFF;
                color: #202124;
                border: 1px solid #C8CCD2;
                padding: 4px;
            }
            QMenu::item {
                background: transparent;
                color: #202124;
                padding: 6px 28px 6px 12px;
                border-radius: 3px;
            }
            QMenu::item:selected {
                background: #2D7DFF;
                color: #FFFFFF;
            }
            QMenu::item:disabled {
                color: #9AA0A6;
                background: transparent;
            }
        """)
        copy_action = menu.addAction("复制")
        copy_action.setEnabled(self.text_edit.textCursor().hasSelection())
        copy_action.triggered.connect(self._copy_selected)
        menu.addAction("全选", self.text_edit.selectAll)
        menu.exec_(self.text_edit.mapToGlobal(position))

    def _copy_all(self):
        QApplication.clipboard().setText(self.text_edit.toPlainText())

    def _close_explicitly(self):
        self._explicit_close_requested = True
        super().accept()

    def accept(self):
        if self._explicit_close_requested:
            super().accept()

    def reject(self):
        # 无标题栏结果窗口只能通过“关闭”按钮结束，避免文本操作、
        # Esc 或系统工具窗口焦点切换误触发 QDialog.reject()。
        if self._explicit_close_requested:
            super().reject()

    def closeEvent(self, event):
        if not self._explicit_close_requested:
            event.ignore()
            return
        super().closeEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            image_pos = self.image_label.mapFromGlobal(event.globalPos())
            if self.image_label.rect().contains(image_pos):
                self._drag_offset = (
                    event.globalPos() - self.frameGeometry().topLeft())
                event.accept()
            else:
                # 文本选择和按钮点击绝不能触发外层无边框窗口拖动。
                self._drag_offset = None
                event.ignore()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            target = event.globalPos() - self._drag_offset
            screen = QApplication.screenAt(event.globalPos()) or QApplication.primaryScreen()
            available = screen.availableGeometry()
            target.setX(max(available.left(), min(
                target.x(), available.right() - self.width() + 1)))
            target.setY(max(available.top(), min(
                target.y(), available.bottom() - self.height() + 1)))
            self.move(target)
            event.accept()
            return
        if event.buttons() & Qt.LeftButton:
            event.ignore()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_offset = None
        if event.button() == Qt.LeftButton:
            event.ignore()
            return
        super().mouseReleaseEvent(event)


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
        self._drag_started = False
        self._selection_confirmed = False
        self._pressed_window_rect = QRect()
        self.selection = QRect()
        self._workers = []
        self._active_worker = None
        self._active_mode = None
        self._operation_cancelled = False
        self._close_after_worker = False
        self._result_dialog = None
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setCursor(Qt.CrossCursor)
        self.setMouseTracking(True)
        self.setGeometry(self.screen.geometry())
        self.toolbar = self._create_toolbar()
        self.toolbar.hide()
        self.progress_label = QLabel(self)
        self.progress_label.setAlignment(Qt.AlignCenter)
        self.progress_label.setStyleSheet(
            "color:white;background:rgba(32,33,36,235);"
            "border:1px solid #555;border-radius:8px;padding:12px 18px;"
            "font-size:14px;")
        self.progress_label.hide()
        self._spinner_frames = ("◐", "◓", "◑", "◒")
        self._spinner_index = 0
        self._spinner_timer = QTimer(self)
        self._spinner_timer.setInterval(160)
        self._spinner_timer.timeout.connect(self._advance_spinner)

    def showEvent(self, event):
        super().showEvent(event)
        self._update_window_candidate(self.mapFromGlobal(QCursor.pos()))

    def _window_candidate(self, local_pos):
        global_pos = self.mapToGlobal(local_pos)
        native_rect = _top_level_window_rect_at(global_pos, int(self.winId()))
        if native_rect.isEmpty():
            return QRect()
        screen_rect = self.screen.geometry()
        clipped = native_rect.intersected(screen_rect)
        if clipped.isEmpty():
            return QRect()
        return clipped.translated(-screen_rect.topLeft())

    def _update_window_candidate(self, local_pos):
        if self._selection_confirmed or self._operation_blocks_selection():
            return
        candidate = self._window_candidate(local_pos)
        if candidate != self.selection:
            self.selection = candidate
            self.update()

    def _create_toolbar(self):
        bar = QWidget(self)
        bar.setStyleSheet(
            "QWidget{background:#202124;border-radius:6px;}"
            "QPushButton{color:white;background:transparent;border:0;padding:7px 10px;}"
            "QPushButton:hover{background:#3c4043;border-radius:4px;}"
            "QPushButton:disabled{color:#777;background:transparent;}")
        row = QHBoxLayout(bar)
        row.setContentsMargins(5, 4, 5, 4); row.setSpacing(2)
        for title, callback in (
            ("复制", self._copy), ("OCR", lambda: self._run_api("ocr")),
            ("翻译", lambda: self._run_api("translate")),
            ("贴图", self._pin), ("取消", self.close)):
            button = QPushButton(title)
            button.clicked.connect(callback)
            if title == "翻译":
                self.translate_button = button
                translate_provider = self.config.get(
                    "screenshot_translate_provider")
                if translate_provider in ("xfyun", "xfyun_v1"):
                    endpoint_key = ("screenshot_xfyun_v1_endpoint"
                                    if translate_provider == "xfyun_v1"
                                    else "screenshot_xfyun_endpoint")
                    credential_keys = (("screenshot_xfyun_v1_app_id",
                                        "screenshot_xfyun_v1_api_key",
                                        "screenshot_xfyun_v1_api_secret")
                                       if translate_provider == "xfyun_v1"
                                       else ("screenshot_xfyun_app_id",
                                             "screenshot_xfyun_api_key",
                                             "screenshot_xfyun_api_secret"))
                    configured = all(bool(str(self.config.get(key, "")).strip())
                                     for key in (endpoint_key,) + credential_keys)
                else:
                    configured = (
                        translate_provider == "openai_compatible" and
                        bool(str(self.config.get(
                            "screenshot_translate_api_endpoint", "")).strip()) and
                        bool(str(self.config.get(
                            "screenshot_translate_api_model", "")).strip()))
                button.setEnabled(configured)
                if not configured:
                    button.setToolTip("请先在设置中完整配置翻译服务")
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
        if self._operation_blocks_selection():
            event.accept()
            return
        over_toolbar = (self.toolbar.isVisible() and
                        self.toolbar.geometry().contains(event.pos()))
        if event.button() == Qt.LeftButton and not over_toolbar:
            self.toolbar.hide()
            self.origin = event.pos(); self.current = event.pos()
            self._selection_confirmed = False
            if not self.selection.isEmpty() and self.selection.contains(event.pos()):
                self._pressed_window_rect = QRect(self.selection)
            else:
                self._pressed_window_rect = self._window_candidate(event.pos())
            self.selection = QRect(self._pressed_window_rect)
            self._drag_started = False
            self.selecting = True; self.update()

    def mouseMoveEvent(self, event):
        if self._operation_blocks_selection():
            event.accept()
            return
        if self.selecting:
            if (event.pos() - self.origin).manhattanLength() >= 5:
                self._drag_started = True
            if self._drag_started:
                self.current = event.pos()
                self.selection = QRect(self.origin, self.current).normalized()
                self.update()
        else:
            self._update_window_candidate(event.pos())

    def mouseReleaseEvent(self, event):
        if self._operation_blocks_selection():
            event.accept()
            return
        if event.button() == Qt.LeftButton and self.selecting:
            self.selecting = False
            if self._drag_started:
                self.selection = QRect(self.origin, event.pos()).normalized()
            else:
                self.selection = QRect(self._pressed_window_rect)
            if self.selection.width() < 8 or self.selection.height() < 8:
                self.selection = QRect(); self.update(); return
            self._selection_confirmed = True
            self._show_toolbar_for_selection()

    def _show_toolbar_for_selection(self):
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
            if self._active_worker is not None and self._active_worker.isRunning():
                if not self._operation_cancelled:
                    self._cancel_active_operation()
                else:
                    # 请求线程需自行结束；界面立即退出，结束后再安全析构。
                    self._close_after_worker = True
                    self.hide()
            else:
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
        if self._active_worker is not None and self._active_worker.isRunning():
            return
        provider_key = ("screenshot_translate_provider" if mode == "translate"
                        else "screenshot_ocr_provider")
        if self.config.get(provider_key, "rapidocr_local" if mode == "ocr"
                           else "disabled") == "disabled":
            service = "翻译" if mode == "translate" else "OCR"
            QMessageBox.information(
                self, f"{service}未配置", f"请先在设置中启用并配置{service}服务。")
            return
        pixmap = self.selected_pixmap()
        if pixmap.isNull():
            return
        self.toolbar.setEnabled(False)
        worker = ScreenshotApiWorker(self.config, pixmap, mode, self)
        self._workers.append(worker)
        self._active_worker = worker
        self._active_mode = mode
        self._operation_cancelled = False
        self.selecting = False
        self.setCursor(Qt.WaitCursor)
        worker.succeeded.connect(self._api_succeeded)
        worker.failed.connect(self._api_failed)
        worker.finished.connect(lambda: self._api_worker_finished(worker))
        worker.start()
        QTimer.singleShot(3000, lambda: self._show_slow_progress(worker, mode))

    def _show_slow_progress(self, worker, mode):
        if (worker is not self._active_worker or not worker.isRunning()
                or self._operation_cancelled or not self.isVisible()):
            return
        self._spinner_index = 0
        self._update_progress_text()
        self.progress_label.adjustSize()
        self.progress_label.move(
            max(8, (self.width() - self.progress_label.width()) // 2),
            max(8, (self.height() - self.progress_label.height()) // 2))
        self.progress_label.show()
        self.progress_label.raise_()
        self._spinner_timer.start()

    def _advance_spinner(self):
        self._spinner_index = (self._spinner_index + 1) % len(self._spinner_frames)
        self._update_progress_text()

    def _update_progress_text(self):
        service = "翻译" if self._active_mode == "translate" else "OCR"
        self.progress_label.setText(
            f"{self._spinner_frames[self._spinner_index]} {service} 处理中…\n"
            "按 Esc 取消，返回截图选区")

    def _hide_progress(self):
        self._spinner_timer.stop()
        self.progress_label.hide()

    def _cancel_active_operation(self):
        self._operation_cancelled = True
        self._hide_progress()
        self.toolbar.setEnabled(True)
        self.setCursor(Qt.CrossCursor)

    def _operation_blocks_selection(self):
        return (self._active_worker is not None and
                self._active_worker.isRunning() and
                not self._operation_cancelled)

    def _api_worker_finished(self, worker):
        if worker in self._workers:
            self._workers.remove(worker)
        if worker is self._active_worker:
            self._hide_progress()
            self._active_worker = None
            self._active_mode = None
            self.toolbar.setEnabled(True)
            self.setCursor(Qt.CrossCursor)
        self._finish_api_worker()

    def _api_succeeded(self, mode, payload):
        if self._operation_cancelled:
            return
        title = "截图翻译结果" if mode == "translate" else "OCR 识别结果"
        if mode == "ocr":
            self.hide()
            dialog = OcrImageResultDialog(
                self.selected_pixmap(), payload.get("text", ""), None,
                payload.get("regions", []))
            dialog.finished.connect(self._ocr_dialog_closed)
            dialog.destroyed.connect(lambda: setattr(self, "_result_dialog", None))
            self._result_dialog = dialog
            dialog.show()
            dialog.raise_()
            dialog.activateWindow()
        elif (mode == "translate" and
                self.config.get("screenshot_result_mode", "image") == "image"):
            pixmap = render_text_on_image(
                self.selected_pixmap(), payload.get("regions", []),
                payload.get("replacements"))
            pos = self.mapToGlobal(self.selection.topLeft())
            self.pin_requested.emit(pixmap, pos)
            self.hide()
            self._close_after_worker = True
        else:
            self.hide()
            dialog = OcrImageResultDialog(
                self.selected_pixmap(), payload.get("text", ""), None,
                payload.get("regions", []), payload.get("replacements", []))
            dialog.finished.connect(self._ocr_dialog_closed)
            dialog.destroyed.connect(lambda: setattr(self, "_result_dialog", None))
            self._result_dialog = dialog
            dialog.show()
            dialog.raise_()
            dialog.activateWindow()

    def _finish_api_worker(self):
        if self._close_after_worker and not any(
                worker.isRunning() for worker in self._workers):
            self.close()

    def _ocr_dialog_closed(self):
        self._close_after_worker = True
        if not any(worker.isRunning() for worker in self._workers):
            self.close()

    def _api_failed(self, message):
        if self._operation_cancelled:
            return
        QMessageBox.warning(self, "调用失败", message)

    def closeEvent(self, event):
        # urllib 请求无法安全强杀；避免运行中的 QThread 随窗口析构。
        if any(worker.isRunning() for worker in self._workers):
            event.ignore()
            return
        super().closeEvent(event)


__all__ = [
    "PinnedImageWindow", "ScreenshotOverlay", "OcrImageResultDialog",
    "call_openai_compatible", "call_xfyun_translation",
    "call_xfyun_v1_translation",
    "call_umi_ocr", "call_rapidocr_details", "get_rapidocr_engine",
    "pixmap_to_base64", "render_text_on_image",
]
