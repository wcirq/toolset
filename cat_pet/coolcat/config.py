from .runtime import *

# ======================== 配置文件 ========================
CONFIG_PATH = (os.path.join(BASE_DIR, "config.json")
               if getattr(sys, "frozen", False)
               else os.path.join(BASE_DIR, "config", "config.json"))

DEFAULT_CONFIG = {
    "model": "hog",            # "hog" = HOG+Haar 传统检测, "yolo" = YOLOv26 深度学习
    "yolo_model": "yolo26n.pt",  # YOLO 权重文件 (ultralytics 会自动下载)
    "yolo_conf": 0.4,          # YOLO 置信度阈值
    "pose_kpt_conf": 0.5,      # pose 模型: 头部关键点(鼻/眼/耳)置信度阈值
    "dedup_iou": 0.55,         # 重复框合并: IoU/包含率超过该值的框视为同一人
    "trigger_count": 2,        # 检测到 >= 该人数(pose模型=头部数)时触发切换
    "sustain_sec": 1.5,        # 持续检出超过该秒数才触发 (0 = 立即)
    "trigger_cooldown_sec": 10.0,  # 触发切换后的冷却时间 (0 = 不冷却)
    "cat_scale": 1.0,          # 小猫尺寸倍率 (0.6 ~ 2.0)
    "camera_index": 0,         # 摄像头编号
    "target_exe": "devenv",    # 目标程序可执行名关键字 (devenv=VS, Code=VSCode, idea64=IDEA...)
    "target_title": "visual studio",  # 目标程序窗口标题关键字
    "maximize_target": False,  # 切换时最大化目标程序
    "hotkey": "Ctrl+Alt+V",    # 全局快捷键 (快速切换到目标程序)
    "hotkey_enabled": True,    # 是否启用全局快捷键
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
    "cat_style": 0,            # 小猫品种索引 (对应 CAT_STYLES)
    "settings_password_hash": _hash_password("wcy206211"),  # 设置页面密码哈希 (SHA-256)
}

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
            # 迁移: 旧版单一预览透明度 -> 摄像头画面透明度
            if "preview_opacity" in saved and "preview_video_opacity" not in saved:
                saved["preview_video_opacity"] = saved["preview_opacity"]
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
        _log(f"配置已保存: {cfg}")
    except Exception as e:
        _log(f"保存配置失败: {e}")

__all__ = [name for name in globals() if not name.startswith('__')]
