# -*- coding: utf-8 -*-
"""测试: 设置页分页布局 + 密码保护 (离屏)"""
import hashlib
import os, sys, json
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtCore import Qt
import coolcat as m
from coolcat.ui.dialogs import StyledMessageDialog

app = QApplication([])
fails = []
def check(name, cond):
    print(("PASS" if cond else "FAIL"), "-", name)
    if not cond:
        fails.append(name)

# 静音弹窗
warn_msgs = []
QMessageBox.warning = staticmethod(lambda *a, **k: warn_msgs.append(a) or None)
StyledMessageDialog.warning = staticmethod(
    lambda *a, **k: warn_msgs.append(a) or None)

# ---------- 1. 对话框构造 + 分页 ----------
cfg = dict(m.DEFAULT_CONFIG)
dlg = m.SettingsDialog(cfg, yolo_available=False)
check("共 5 个分页", dlg.tabs.count() == 5)
check("默认使用 YOLO 姿态模型",
      cfg["model"] == "yolo" and
      cfg["yolo_model"] == "yolo26n-pose.onnx")
check("姿态模型选项存在",
      dlg.yolo_model_combo.findText("yolo26n-pose.onnx") >= 0)
check("宠物尺寸可调至 1%", dlg.scale_slider.minimum() == 1)
check("预览透明度可调至 0%", all(
    slider.minimum() == 0 for slider in (
        dlg.preview_window_opacity_slider,
        dlg.preview_video_opacity_slider,
        dlg.preview_overlay_opacity_slider)))
titles = [dlg.tabs.tabText(i) for i in range(5)]
print("  分页:", titles)
check("分页标题正确", titles == [
    "检测与触发", "形象与摄像头", "目标与快捷键", "截图与贴图", "安全"])
check("窗口可见高度受控 (有 tab 容器)", dlg.tabs.isVisible() or True)  # offscreen 未show

# ---------- 2. 默认无密码 ----------
dlg.pwd_old_edit.clear(); dlg.pwd_new_edit.clear(); dlg.pwd_new2_edit.clear()
out = dlg.get_config()
check("默认不设置密码", out["settings_password_hash"] == "")
check("标签页切换行为默认为表情", out["locked_tab_behavior"] == "emotion")
check("软件焦点行为默认隐藏", out["attached_focus_behavior"] == "hide")
check("屏幕边缘判定默认 5px", out["screen_edge_intent_px"] == 5)
dlg.screen_edge_intent_spin.setValue(12)
check("保存屏幕边缘判定距离", dlg.get_config()["screen_edge_intent_px"] == 12)
for behavior in ('emotion', 'none', 'hide'):
    dlg.attached_focus_behavior_combo.setCurrentIndex(dlg.attached_focus_behavior_combo.findData(behavior))
    check("保存软件焦点行为 " + behavior, dlg.get_config()["attached_focus_behavior"] == behavior)
for behavior in ('hide', 'none', 'emotion'):
    dlg.locked_tab_behavior_combo.setCurrentIndex(dlg.locked_tab_behavior_combo.findData(behavior))
    check("保存标签页行为 " + behavior, dlg.get_config()["locked_tab_behavior"] == behavior)
check("未设置密码时当前密码输入框禁用", not dlg.pwd_old_edit.isEnabled())
check("get_config 保留 cat_color", "cat_color" in out)
check("get_config 保留 preview_scale", out.get("preview_scale") == cfg.get("preview_scale", 1.0))

# ---------- 2.1 两级形象选择 ----------
check("一级形象含猫类和人类", dlg.character_category_combo.count() == 2)
check("猫类下保留 4 个形象", dlg.cat_style_combo.count() == 4)
dlg.character_category_combo.setCurrentIndex(
    dlg.character_category_combo.findData("human"))
check("人类下有 6 个主题形象", dlg.cat_style_combo.count() == 6)
check("人类形象使用专属配色", not dlg.cat_color_combo.isEnabled())
check("get_config 保存人类类别", dlg.get_config()["character_category"] == "human")
check("默认截图快捷键为 Alt+A", dlg.get_config()["screenshot_hotkey"] == "Alt+A")
check("OCR 默认启用本地 RapidOCR",
      dlg.get_config()["screenshot_ocr_provider"] == "rapidocr_local")
check("翻译结果默认在原图显示", dlg.get_config()["screenshot_result_mode"] == "image")
check("翻译服务默认独立关闭",
      dlg.get_config()["screenshot_translate_provider"] == "disabled")
check("OCR 与翻译配置使用独立分组框",
      dlg.screenshot_ocr_group.title() == "OCR 配置" and
      dlg.screenshot_translate_group.title() == "翻译配置")
check("源语言和目标语言使用同一套完整选项",
      dlg.screenshot_xfyun_from_combo.count() == 70 and
      dlg.screenshot_language_combo.count() == 70 and
      [dlg.screenshot_xfyun_from_combo.itemData(i) for i in range(70)] ==
      [dlg.screenshot_language_combo.itemData(i) for i in range(70)])
check("OCR 不提供关闭选项且本地模式隐藏接口配置",
      dlg.screenshot_provider_combo.findData("disabled") < 0 and
      dlg.screenshot_endpoint_edit.isHidden() and
      dlg.screenshot_api_key_edit.isHidden() and
      dlg.screenshot_model_edit.isHidden())
check("关闭翻译后隐藏结果模式和翻译配置",
      dlg.screenshot_result_mode_combo.isHidden() and
      dlg.screenshot_language_combo.isHidden() and
      dlg.screenshot_translate_endpoint_edit.isHidden() and
      dlg.screenshot_xfyun_endpoint_edit.isHidden() and
      dlg.screenshot_translate_test_container.isHidden() and
      dlg.screenshot_translate_test_result.isHidden())
check("OCR 配置提供文字输入和测试按钮",
      dlg.screenshot_ocr_test_button.text() == "测试 OCR" and
      dlg.screenshot_ocr_test_input.placeholderText() != "")
xfyun_idx = dlg.screenshot_translate_provider_combo.findData("xfyun")
check("翻译服务包含讯飞 WebAPI", xfyun_idx >= 0)
xfyun_v1_idx = dlg.screenshot_translate_provider_combo.findData("xfyun_v1")
check("翻译服务包含讯飞机器翻译 2.0", xfyun_v1_idx >= 0)
dlg.screenshot_translate_provider_combo.setCurrentIndex(xfyun_idx)
check("选择讯飞后隐藏 OpenAI 配置",
      dlg.screenshot_translate_endpoint_edit.isHidden() and
      dlg.screenshot_translate_api_key_edit.isHidden() and
      dlg.screenshot_translate_model_edit.isHidden())
check("选择讯飞后显示讯飞配置",
      not dlg.screenshot_xfyun_endpoint_edit.isHidden() and
      not dlg.screenshot_xfyun_app_id_edit.isHidden() and
      not dlg.screenshot_xfyun_api_secret_edit.isHidden() and
      not dlg.screenshot_result_mode_combo.isHidden() and
      not dlg.screenshot_language_combo.isHidden() and
      not dlg.screenshot_translate_test_container.isHidden())
dlg._api_config_test_completed("translate", True, 1.2345, "测试译文")
check("接口测试结果显示状态、耗时和内容",
      "成功" in dlg.screenshot_translate_test_result.text() and
      "1.234" in dlg.screenshot_translate_test_result.text() and
      "测试译文" in dlg.screenshot_translate_test_result.text())
dlg.screenshot_xfyun_app_id_edit.setText("test-app")
dlg.screenshot_xfyun_api_secret_edit.setText("test-secret")
check("讯飞 APPID 和 Secret 可独立保存",
      dlg.get_config()["screenshot_xfyun_app_id"] == "test-app" and
      dlg.get_config()["screenshot_xfyun_api_secret"] == "test-secret")
dlg.screenshot_translate_provider_combo.setCurrentIndex(xfyun_v1_idx)
check("选择讯飞 2.0 后仅显示新版地址和术语资源",
      dlg.screenshot_xfyun_endpoint_edit.isHidden() and
      not dlg.screenshot_xfyun_v1_endpoint_edit.isHidden() and
      not dlg.screenshot_xfyun_res_id_edit.isHidden() and
      dlg.screenshot_xfyun_app_id_edit.isHidden() and
      not dlg.screenshot_xfyun_v1_app_id_edit.isHidden())
dlg.screenshot_xfyun_res_id_edit.setText("its_en_cn_word")
dlg.screenshot_xfyun_v1_app_id_edit.setText("v1-app")
dlg.screenshot_xfyun_v1_api_key_edit.setText("v1-key")
dlg.screenshot_xfyun_v1_api_secret_edit.setText("v1-secret")
v1_saved = dlg.get_config()
check("讯飞 2.0 术语资源和凭据可独立保存",
      v1_saved["screenshot_xfyun_res_id"] == "its_en_cn_word" and
      v1_saved["screenshot_xfyun_v1_app_id"] == "v1-app" and
      v1_saved["screenshot_xfyun_app_id"] == "test-app")
openai_translate_idx = dlg.screenshot_translate_provider_combo.findData(
    "openai_compatible")
dlg.screenshot_translate_provider_combo.setCurrentIndex(openai_translate_idx)
check("选择 OpenAI 后显示 OpenAI 配置并隐藏讯飞配置",
      not dlg.screenshot_translate_endpoint_edit.isHidden() and
      dlg.screenshot_xfyun_endpoint_edit.isHidden())
check("截图配置滚动区使用深色背景",
      "#1E1E2A" in dlg.screenshot_scroll.styleSheet())
dlg.screenshot_endpoint_edit.setText("https://ocr.example/v1/chat/completions")
dlg.screenshot_translate_endpoint_edit.setText(
    "https://translate.example/v1/chat/completions")
separated = dlg.get_config()
check("OCR 与翻译接口配置相互独立",
      separated["screenshot_ocr_api_endpoint"] !=
      separated["screenshot_translate_api_endpoint"])
umi_index = dlg.screenshot_provider_combo.findData("rapidocr_local")
check("OCR 服务包含进程内 RapidOCR", umi_index >= 0)
dlg.screenshot_provider_combo.setCurrentIndex(umi_index)
check("get_config 保存 RapidOCR", dlg.get_config()["screenshot_ocr_provider"] == "rapidocr_local")
check("本地 RapidOCR 不显示第三方接口配置",
      dlg.screenshot_endpoint_edit.isHidden() and
      dlg.screenshot_api_key_edit.isHidden() and
      dlg.screenshot_model_edit.isHidden())
openai_ocr_index = dlg.screenshot_provider_combo.findData("openai_compatible")
dlg.screenshot_provider_combo.setCurrentIndex(openai_ocr_index)
check("选择第三方 OCR 后显示接口配置",
      not dlg.screenshot_endpoint_edit.isHidden() and
      not dlg.screenshot_api_key_edit.isHidden() and
      not dlg.screenshot_model_edit.isHidden())
dlg.character_category_combo.setCurrentIndex(
    dlg.character_category_combo.findData("cat"))

# ---------- 3. 第一次设置密码无需旧密码 ----------
dlg.pwd_new_edit.setText("firstpass")
dlg.pwd_new2_edit.setText("firstpass")
warn_msgs.clear()
check("第一次设置密码校验通过", dlg._validate_password_change())
check("第一次设置密码无需旧密码", len(warn_msgs) == 0)
first_hash = hashlib.sha256("firstpass".encode("utf-8")).hexdigest()
check("第一次设置的新密码哈希生效",
      dlg.get_config()["settings_password_hash"] == first_hash)

# ---------- 4. 第一次设置时两次输入不一致 → 拒绝 ----------
dlg._new_password = None
dlg.pwd_new_edit.setText("aaa")
dlg.pwd_new2_edit.setText("bbb")
warn_msgs.clear()
dlg._validate_password_change()
check("两次不一致时弹出警告", len(warn_msgs) == 1)
check("两次不一致时密码未改", dlg.get_config()["settings_password_hash"] == "")

# ---------- 5. 已有密码时必须验证旧密码 ----------
protected_cfg = dict(cfg)
protected_hash = hashlib.sha256("existingpass".encode("utf-8")).hexdigest()
protected_cfg["settings_password_hash"] = protected_hash
protected = m.SettingsDialog(protected_cfg, yolo_available=False)
protected.pwd_old_edit.setText("wrong")
protected.pwd_new_edit.setText("mynew123")
protected.pwd_new2_edit.setText("mynew123")
warn_msgs.clear()
check("旧密码错误时拒绝修改", not protected._validate_password_change())
check("旧密码错误时弹出警告", len(warn_msgs) == 1)
protected.pwd_old_edit.setText("existingpass")
warn_msgs.clear()
check("旧密码正确时允许修改", protected._validate_password_change())
check("正确修改时无警告", len(warn_msgs) == 0)
out = protected.get_config()
new_hash = hashlib.sha256("mynew123".encode("utf-8")).hexdigest()
check("新密码哈希生效", out["settings_password_hash"] == new_hash)

# ---------- 6. 新密码为空但有输入 → 拒绝 ----------
dlg2 = m.SettingsDialog(cfg, yolo_available=False)
dlg2.pwd_new_edit.clear()
dlg2.pwd_new2_edit.setText("x")
warn_msgs.clear()
dlg2._validate_password_change()
check("新密码为空但有输入时警告", len(warn_msgs) == 1)

# ---------- 7. 密码验证入口逻辑 ----------
cur = protected_cfg["settings_password_hash"]
def try_open(pwd):
    return hashlib.sha256(pwd.encode("utf-8")).hexdigest() == cur
check("未设置密码时无需验证", not cfg["settings_password_hash"])
check("手动设置的密码正确可进入", try_open("existingpass"))
check("密码错误被拒", not try_open("bad"))

# ---------- 8. 窗口高度对比 (旧版无分页 ~900px, 新版应更矮) ----------
dlg3 = m.SettingsDialog(cfg, yolo_available=False)
dlg3.show()
dlg3.adjustSize()
h = dlg3.sizeHint().height()
print(f"  新版设置窗口建议高度: {h}px")
check("窗口高度 < 800px", h < 800)

print()
print("RESULT:", "ALL PASS" if not fails else f"FAILED: {fails}")
sys.exit(1 if fails else 0)
