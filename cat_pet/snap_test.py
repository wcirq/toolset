# -*- coding: utf-8 -*-
"""自动测试贴边效果: 强制吸附后截屏保存"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

try:
    import torch  # noqa: 必须在 PyQt5 之前
except Exception:
    pass

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QTimer

import main as m

app = QApplication(sys.argv)

# 禁用摄像头, 加快测试
m.CatWindow._start_camera_thread = lambda self: None

win = m.CatWindow()
win.show()

results = []

def snap_and_shot(edge):
    def do():
        screen = app.primaryScreen().geometry()
        win.snap_edge = edge
        win.snap_target = 0.0
        if edge in ("left", "right"):
            win.snap_pos = screen.height() // 2
        else:
            win.snap_pos = screen.width() // 2
        # 让 _update_snap 立即算隐藏位置, 并确保 anim < 0.3 触发特效
        for _ in range(120):
            win._update_snap()
        win.snap_anim = 0.0  # 强制完全隐藏
        win.snap_target = 0.0
        QTimer.singleShot(400, lambda: shot(edge))
    return do

def make_snap(edge):
    return lambda: snap_and_shot(edge)()

def shot(edge):
    # 1) widget 自渲染 (包含透明区域, 真实绘制结果)
    pix = win.grab()
    path1 = os.path.abspath(f"snap_test_{edge}_widget.png")
    pix.save(path1)
    # 2) 屏幕实拍 (还原到屏幕的视觉效果)
    screen = app.primaryScreen()
    g = win.geometry()
    x = max(0, g.x())
    y = max(0, g.y())
    w = min(g.width(), screen.geometry().width() - x)
    h = min(g.height(), screen.geometry().height() - y)
    pix2 = screen.grabWindow(0, x, y, w, h)
    path2 = os.path.abspath(f"snap_test_{edge}.png")
    pix2.save(path2)
    print(f"edge={edge} geo={g.x()},{g.y()} {g.width()}x{g.height()} "
          f"peek={win._peek_amount()} anim={win.snap_anim:.4f} "
          f"widget={path1} screen={path2}")
    results.append(edge)
    next_edge = {"left": "right", "right": "bottom"}.get(edge)
    if next_edge:
        # 先复位
        win.snap_edge = None
        win.move(300, 300)
        QTimer.singleShot(300, make_snap(next_edge))
    else:
        app.quit()

QTimer.singleShot(1500, make_snap("left"))
app.exec_()
print("done:", results)
