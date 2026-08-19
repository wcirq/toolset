# -*- coding: utf-8 -*-
"""测试: 颜色记忆 + 开机启动注册表读写 (测试后恢复原状)"""
import os, sys, json
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

import winreg
import coolcat as m

fails = []
def check(name, cond):
    print(("PASS" if cond else "FAIL"), "-", name)
    if not cond:
        fails.append(name)

# ---------- 1. 开机启动: 注册表读写 ----------
orig = m.is_autostart_enabled()
print("初始状态:", orig)

cmd = m._autostart_command()
print("启动命令:", cmd)
check("命令含绝对路径", (":\\" in cmd) or ("/" in cmd))

# 开启
m.set_autostart(True)
check("开启后 is_autostart_enabled()==True", m.is_autostart_enabled() == True)
# 注册表里确实有值
with winreg.OpenKey(winreg.HKEY_CURRENT_USER, m.AUTOSTART_REG_PATH) as k:
    val, _ = winreg.QueryValueEx(k, m.AUTOSTART_REG_NAME)
check("注册表项已写入", bool(val))

# 关闭
m.set_autostart(False)
check("关闭后 is_autostart_enabled()==False", m.is_autostart_enabled() == False)

# 恢复原状
if orig:
    m.set_autostart(True)
    print("已恢复为开启状态")
else:
    print("原本未开启, 保持关闭")

# ---------- 2. 颜色记忆: _init_state 读 config ----------
from PyQt5.QtWidgets import QApplication
app = QApplication([])

# 写一个 cat_color=3 的临时配置
test_cfg = dict(m.DEFAULT_CONFIG)
test_cfg["cat_color"] = 3
with open(m.CONFIG_PATH, "w", encoding="utf-8") as f:
    json.dump(test_cfg, f, ensure_ascii=False, indent=2)

cat = m.CatWindow.__new__(m.CatWindow)
cat.config = m.load_config()
cat._init_state()
check("cat_color=3 启动后是灰猫", cat.color_idx == 3 and cat.c["name"] == "灰猫")

# 越界回退
cat.config["cat_color"] = 99
cat._init_state()
check("越界回退橘猫", cat.color_idx == 0 and cat.c["name"] == "橘猫")

# ---------- 3. _change_color 写配置 ----------
cat.config = m.load_config()
cat._say = lambda *a, **k: None
cat._spawn_particles = lambda *a, **k: None
cat.color_idx = 1
from coolcat import COLORS
# 模拟: 当前 idx=1(黑猫), 换色 → 2(白猫) 并写配置
cat._change_color()
check("换色后 idx=2", cat.color_idx == 2)
saved = m.load_config()
check("配置文件里 cat_color=2", saved.get("cat_color") == 2)

# _toggle_autostart 行为
cat._toggle_autostart(True)
check("toggle(True) 后开启", m.is_autostart_enabled() == True and cat._autostart_on == True)
cat._toggle_autostart(False)
check("toggle(False) 后关闭", m.is_autostart_enabled() == False and cat._autostart_on == False)

# 恢复原状
if orig:
    m.set_autostart(True)

# 恢复配置为默认
with open(m.CONFIG_PATH, "w", encoding="utf-8") as f:
    json.dump(m.DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)

print()
print("RESULT:", "ALL PASS" if not fails else f"FAILED: {fails}")
sys.exit(1 if fails else 0)
