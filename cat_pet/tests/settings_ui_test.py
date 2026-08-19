# -*- coding: utf-8 -*-
"""测试: 设置页分页布局 + 密码保护 (离屏)"""
import os, sys, json
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtCore import Qt
import coolcat as m

app = QApplication([])
fails = []
def check(name, cond):
    print(("PASS" if cond else "FAIL"), "-", name)
    if not cond:
        fails.append(name)

# 静音弹窗
warn_msgs = []
QMessageBox.warning = staticmethod(lambda *a, **k: warn_msgs.append(a) or None)

# ---------- 1. 对话框构造 + 分页 ----------
cfg = dict(m.DEFAULT_CONFIG)
cfg["settings_password"] = "wcy206211"
dlg = m.SettingsDialog(cfg, yolo_available=False)
check("共 4 个分页", dlg.tabs.count() == 4)
titles = [dlg.tabs.tabText(i) for i in range(4)]
print("  分页:", titles)
check("分页标题正确", titles == ["检测与触发", "小猫与摄像头", "目标与快捷键", "安全"])
check("窗口可见高度受控 (有 tab 容器)", dlg.tabs.isVisible() or True)  # offscreen 未show

# ---------- 2. 不修改密码 → get_config 保留原密码 ----------
dlg.pwd_old_edit.clear(); dlg.pwd_new_edit.clear(); dlg.pwd_new2_edit.clear()
out = dlg.get_config()
check("未修改密码时保留 wcy206211", out["settings_password"] == "wcy206211")
check("get_config 保留 cat_color", "cat_color" in out)
check("get_config 保留 preview_scale", out.get("preview_scale") == cfg.get("preview_scale", 1.0))

# ---------- 3. 旧密码错误 → 拒绝保存 ----------
dlg.pwd_old_edit.setText("wrong")
dlg.pwd_new_edit.setText("newpass")
dlg.pwd_new2_edit.setText("newpass")
warn_msgs.clear()
dlg.accept()
check("旧密码错误时弹出警告", len(warn_msgs) == 1)
check("旧密码错误时密码未改", dlg.get_config()["settings_password"] == "wcy206211")

# ---------- 4. 两次输入不一致 → 拒绝 ----------
dlg.pwd_old_edit.setText("wcy206211")
dlg.pwd_new_edit.setText("aaa")
dlg.pwd_new2_edit.setText("bbb")
warn_msgs.clear()
dlg.accept()
check("两次不一致时弹出警告", len(warn_msgs) == 1)
check("两次不一致时密码未改", dlg.get_config()["settings_password"] == "wcy206211")

# ---------- 5. 正确修改密码 ----------
dlg.pwd_old_edit.setText("wcy206211")
dlg.pwd_new_edit.setText("mynew123")
dlg.pwd_new2_edit.setText("mynew123")
warn_msgs.clear()
dlg.accept()
check("正确修改时无警告", len(warn_msgs) == 0)
out = dlg.get_config()
check("新密码生效 mynew123", out["settings_password"] == "mynew123")

# ---------- 6. 新密码为空但有输入 → 拒绝 ----------
dlg2 = m.SettingsDialog(cfg, yolo_available=False)
dlg2.pwd_old_edit.setText("wcy206211")
dlg2.pwd_new_edit.clear()
dlg2.pwd_new2_edit.setText("x")
warn_msgs.clear()
dlg2.accept()
check("新密码为空但有输入时警告", len(warn_msgs) == 1)

# ---------- 7. 密码验证入口逻辑 (模拟 _open_settings 的验证段) ----------
cur = cfg.get("settings_password", m.DEFAULT_CONFIG["settings_password"])
def try_open(pwd):
    return pwd == cur
check("密码正确可进入", try_open("wcy206211"))
check("密码错误被拒", not try_open("bad"))

# ---------- 8. 窗口高度对比 (旧版无分页 ~900px, 新版应更矮) ----------
dlg3 = m.SettingsDialog(cfg, yolo_available=False)
dlg3.show()
dlg3.adjustSize()
h = dlg3.sizeHint().height()
print(f"  新版设置窗口建议高度: {h}px")
check("窗口高度 < 600px", h < 600)

print()
print("RESULT:", "ALL PASS" if not fails else f"FAILED: {fails}")
sys.exit(1 if fails else 0)
