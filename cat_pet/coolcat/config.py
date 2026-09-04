from .runtime import *

# ======================== 配置文件 ========================
CONFIG_PATH = (os.path.join(BASE_DIR, "config.json")
               if getattr(sys, "frozen", False)
               else os.path.join(BASE_DIR, "config", "config.json"))

DEFAULT_CONFIG = {
    "model": "yolo",           # "hog" = HOG+Haar 传统检测, "yolo" = YOLOv26 深度学习
    "yolo_model": "yolo26n-pose.onnx",  # ONNX Runtime 姿态模型
    "yolo_conf": 0.4,          # YOLO 置信度阈值
    "pose_kpt_conf": 0.5,      # pose 模型: 头部关键点(鼻/眼/耳)置信度阈值
    "dedup_iou": 0.55,         # 重复框合并: IoU/包含率超过该值的框视为同一人
    "trigger_count": 2,        # 检测到 >= 该人数(pose模型=头部数)时触发切换
    "sustain_sec": 1.5,        # 持续检出超过该秒数才触发 (0 = 立即)
    "trigger_cooldown_sec": 10.0,  # 触发切换后的冷却时间 (0 = 不冷却)
    "cat_scale": 1.0,          # 小猫尺寸倍率 (0.01 ~ 2.0)
    "locked_tab_behavior": "emotion",  # emotion / hide / none
    "attached_focus_behavior": "hide",  # hide / emotion / none
    "attached_roam_enabled": True,  # 吸附后沿窗口/屏幕边缘自主活动
    "screen_edge_intent_px": 5,  # 最大化窗口与屏幕边缘重合时的贴屏判定距离
    "camera_index": 0,         # 摄像头编号
    "target_exe": "devenv",    # 目标程序可执行名关键字 (devenv=VS, Code=VSCode, idea64=IDEA...)
    "target_title": "visual studio",  # 目标程序窗口标题关键字
    "maximize_target": False,  # 切换时最大化目标程序
    "hotkey": "Ctrl+Alt+V",    # 全局快捷键 (快速切换到目标程序)
    "hotkey_enabled": True,    # 是否启用全局快捷键
    "monitor_hotkey": "Ctrl+Alt+M",  # 启用/禁用监控
    "monitor_hotkey_enabled": True,
    "monitor_effect_size": 220,  # 左上角渐变闪烁范围 (px)
    "screenshot_hotkey": "Alt+A",  # 区域截图/OCR/翻译/贴图
    "screenshot_hotkey_enabled": True,
    "screenshot_ocr_provider": "rapidocr_local",  # openai_compatible / rapidocr_local
    "screenshot_result_mode": "image",  # 仅翻译结果: image / popup
    "screenshot_ocr_api_endpoint": "",
    "screenshot_ocr_api_key": "",
    "screenshot_ocr_api_model": "",
    "screenshot_translate_provider": "disabled",  # disabled / openai_compatible / xfyun / xfyun_v1
    "screenshot_translate_api_endpoint": "",
    "screenshot_translate_api_key": "",
    "screenshot_translate_api_model": "",
    "screenshot_xfyun_endpoint": "https://itrans.xfyun.cn/v2/its",
    "screenshot_xfyun_v1_endpoint": "https://itrans.xf-yun.com/v1/its",
    "screenshot_xfyun_res_id": "",
    "screenshot_xfyun_v1_app_id": "",
    "screenshot_xfyun_v1_api_key": "",
    "screenshot_xfyun_v1_api_secret": "",
    "screenshot_xfyun_app_id": "",
    "screenshot_xfyun_api_key": "",
    "screenshot_xfyun_api_secret": "",
    "screenshot_xfyun_from": "cn",
    "screenshot_translate_language": "cn",
    "chat_enabled": False,     # 聊天输入功能 (暂时禁用)
    "debug_save": False,       # 调试: 满足切换条件时保存标注检测图片到 debug_shots/
    "auto_pause_fullscreen": False,  # 全屏游戏/会议/演示时自动暂停监控
    "auto_return_enabled": False,    # 人员离开后自动切回原窗口
    "auto_return_delay_sec": 10.0,   # 人员离开后延迟切回秒数
    "preview_scale": 1.0,      # 预览窗口缩放 (滚轮调整, 自动记忆)
    "preview_window_opacity": 0.85,  # 预览窗口背景/边框/信息栏透明度
    "preview_video_opacity": 0.85,   # 摄像头画面透明度
    "preview_overlay_opacity": 1.0,  # 人体框/关键点/标签透明度
    "cat_color": 0,            # 小猫颜色索引 (对应 COLORS 列表, 右键换颜色后自动记忆)
    "character_category": "cat",  # 一级形象类别: cat / human
    "cat_style": 0,            # 小猫品种索引 (对应 CAT_STYLES)
    "settings_password_hash": "",  # 留空表示未设置访问密码
}

# 旧版本内置密码的 SHA-256，仅用于把已有配置迁移为“未设置密码”。
_LEGACY_DEFAULT_PASSWORD_HASH = (
    "f6e0a1e2ac41945a9aa7ff8a8aaa0cebc12a3bcc981a929ad5cf810a090e11ae")

def load_config():
    cfg = dict(DEFAULT_CONFIG)
    try:
        import json
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
            # 迁移: 旧版明文 settings_password -> settings_password_hash
            if "settings_password" in saved and "settings_password_hash" not in saved:
                saved["settings_password_hash"] = _hash_password(saved["settings_password"])
                saved.pop("settings_password", None)
                try:
                    with open(CONFIG_PATH, "w", encoding="utf-8") as f2:
                        json.dump(saved, f2, ensure_ascii=False, indent=2)
                    _log("已迁移 settings_password -> settings_password_hash (哈希加密)")
                except Exception as e:
                    _log(f"迁移密码哈希写回失败: {e}")
            if saved.get("settings_password_hash") == _LEGACY_DEFAULT_PASSWORD_HASH:
                saved["settings_password_hash"] = ""
                try:
                    with open(CONFIG_PATH, "w", encoding="utf-8") as f2:
                        json.dump(saved, f2, ensure_ascii=False, indent=2)
                    _log("已取消旧版本内置设置密码")
                except Exception as e:
                    _log(f"取消旧版本内置设置密码写回失败: {e}")
            # 迁移: 旧版单一预览透明度 -> 摄像头画面透明度
            if "preview_opacity" in saved and "preview_video_opacity" not in saved:
                saved["preview_video_opacity"] = saved["preview_opacity"]
            # 迁移: 旧版 OCR/翻译共用一套 API 配置 -> 两套独立配置。
            old_endpoint = saved.get("screenshot_api_endpoint", "")
            old_key = saved.get("screenshot_api_key", "")
            old_model = saved.get("screenshot_api_model", "")
            if "screenshot_ocr_api_endpoint" not in saved:
                saved["screenshot_ocr_api_endpoint"] = old_endpoint
                saved["screenshot_ocr_api_key"] = old_key
                saved["screenshot_ocr_api_model"] = old_model
            if "screenshot_translate_api_endpoint" not in saved:
                saved["screenshot_translate_api_endpoint"] = old_endpoint
                saved["screenshot_translate_api_key"] = old_key
                saved["screenshot_translate_api_model"] = old_model
                saved["screenshot_translate_provider"] = (
                    "openai_compatible" if old_endpoint and old_model else "disabled")
            # OCR 现为截图翻译的基础能力，不再允许关闭。
            if saved.get("screenshot_ocr_provider") == "disabled":
                saved["screenshot_ocr_provider"] = "rapidocr_local"
            for k in DEFAULT_CONFIG:
                if k in saved:
                    cfg[k] = saved[k]
    except Exception as e:
        _log(f"读取配置失败, 使用默认值: {e}")
    return cfg

def save_config(cfg):
    try:
        import json
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        logged = dict(cfg)
        for key in ("screenshot_ocr_api_key", "screenshot_translate_api_key",
                    "screenshot_xfyun_api_key", "screenshot_xfyun_api_secret",
                    "screenshot_xfyun_v1_api_key",
                    "screenshot_xfyun_v1_api_secret"):
            if logged.get(key):
                logged[key] = "***"
        _log(f"配置已保存: {logged}")
    except Exception as e:
        _log(f"保存配置失败: {e}")

__all__ = [name for name in globals() if not name.startswith('__')]
