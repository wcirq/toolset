#!/usr/bin/env python3
"""
酷炫小猫悬浮窗 - Cool Cat Floating Pet (人体检测版)
一个可以交互的桌面悬浮小猫宠物 + 摄像头人体检测

交互方式:
  - 左键点击猫头: 聊天框 (暂时禁用)
  - 左键点击身体: 摸摸猫 (爱心粒子)
  - 左键长按(不拖动): 显示摄像头预览 (人体检测画面)
  - 左键拖拽:     移动小猫 / 贴边吸附
  - 双击:         切换睡觉 / 醒来
  - 右键:         打开菜单 (换颜色/跟随鼠标/设置/退出)
  - 滚轮(预览窗口): 放大/缩小视频画面
  - 全局快捷键:   快速切换到设置中指定的目标程序

人体检测:
  - 后台线程持续读取笔记本摄像头 (HOG+Haar 或 YOLOv26, 可配置)
  - 最大人体标记绿框 (主人), 其他人体标记红框
  - 检测到多人 (可配置人数/持续秒数) 时, 自动切换到指定目标程序
"""

import sys
import math
import random
import os
import time
import traceback
import subprocess
import threading
import ctypes
import winreg
import hashlib
from ctypes import wintypes
from datetime import datetime

import cv2
import numpy as np

# ⚠️ torch 必须在 PyQt5 之前导入!
# Windows 上若 PyQt5 先加载, torch 的 c10.dll 会报
# "WinError 1114 动态链接库(DLL)初始化例程失败"。
# 这里静默预导入 (未安装则跳过, YOLO 功能自动回退到 HOG)。
try:
    import torch  # noqa: F401
except Exception:
    torch = None

from PyQt5.QtWidgets import (
    QApplication, QWidget, QMenu, QSystemTrayIcon, QLineEdit,
    QDialog, QComboBox, QSpinBox, QDoubleSpinBox, QSlider, QPushButton,
    QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QGroupBox, QCheckBox,
    QTabWidget, QAction
)
from PyQt5.QtCore import (
    Qt, QTimer, QPointF, QRectF, QPoint, QEvent,
    QThread, pyqtSignal, QMutex, QAbstractNativeEventFilter
)
from PyQt5.QtGui import (
    QPainter, QColor, QPen, QBrush, QPainterPath, QFont,
    QCursor, QIcon, QPixmap, QRadialGradient, QLinearGradient,
    QImage
)

# ======================== 调试日志 ========================
def _get_base_dir():
    """程序根目录: 打包成 exe 后返回 exe 所在目录, 否则返回源码目录"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    # common.py 位于 cat_pet/coolcat/，源码运行时配置仍放在 cat_pet/。
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BASE_DIR = _get_base_dir()
LOG_PATH = os.path.join(BASE_DIR, "cat_debug.log")

def _log(msg):
    """写入调试日志"""
    try:
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass

def _global_excepthook(exc_type, exc_value, exc_tb):
    """全局未捕获异常 → 写入日志"""
    tb_lines = traceback.format_exception(exc_type, exc_value, exc_tb)
    _log("!!! 未捕获异常 !!!\n" + "".join(tb_lines))
    sys.__excepthook__(exc_type, exc_value, exc_tb)

sys.excepthook = _global_excepthook

_log("========== CoolCat 启动 ==========")


def _hash_password(pwd):
    """密码 SHA-256 哈希 (配置文件只存哈希, 不存明文)"""
    return hashlib.sha256(str(pwd).encode("utf-8")).hexdigest()

# ======================== 配置 ========================
W, H = 240, 290          # 窗口大小
CX, CY = 120, 125        # 猫头中心
HEAD_R = 50              # 头部半径
BODY_CX, BODY_CY = 120, 195  # 身体中心
BODY_RX, BODY_RY = 33, 30    # 身体半径
FPS = 60                 # 动画帧率

# 配色方案
COLORS = [
    {"name": "橘猫",   "body": "#FFB347", "dark": "#E89530", "ear": "#FF9999", "belly": "#FFE0B0"},
    {"name": "黑猫",   "body": "#3D3D3D", "dark": "#2A2A2A", "ear": "#885555", "belly": "#555555"},
    {"name": "白猫",   "body": "#F2F2F2", "dark": "#D0D0D0", "ear": "#FFB6C1", "belly": "#FFFFFF"},
    {"name": "灰猫",   "body": "#909090", "dark": "#707070", "ear": "#FFAAAA", "belly": "#B0B0B0"},
    {"name": "奶茶",   "body": "#D4A574", "dark": "#B8895A", "ear": "#FFB6C1", "belly": "#E8C9A0"},
    {"name": "蓝猫",   "body": "#7CB9E8", "dark": "#5A9BCF", "ear": "#FFB6C1", "belly": "#B0DAF0"},
]

# 小猫品种特征; 品种结构与配色独立组合
CAT_STYLES = [
    {"name": "中华田园猫", "breed": "tabby", "ear_type": "upright",
     "head_rx": 50, "head_ry": 50, "ear_x": 48, "ear_h": 72,
     "body_rx": 33, "body_ry": 30, "eye_x": 15, "tail_len": 72, "tail_w": 11},
    {"name": "暹罗猫", "breed": "siamese", "ear_type": "large",
     "head_rx": 47, "head_ry": 52, "ear_x": 55, "ear_h": 86,
     "body_rx": 29, "body_ry": 34, "eye_x": 15, "tail_len": 82, "tail_w": 9},
    {"name": "布偶猫", "breed": "ragdoll", "ear_type": "fluffy",
     "head_rx": 55, "head_ry": 50, "ear_x": 49, "ear_h": 72,
     "body_rx": 38, "body_ry": 34, "eye_x": 17, "tail_len": 76, "tail_w": 15},
    {"name": "苏格兰折耳", "breed": "fold", "ear_type": "folded",
     "head_rx": 56, "head_ry": 52, "ear_x": 47, "ear_h": 61,
     "body_rx": 40, "body_ry": 34, "eye_x": 16, "tail_len": 60, "tail_w": 13},
]

HUMAN_STYLES = [
    {"name": "原图宝宝 · 暖橘", "kind": "bow_baby", "render": "portrait", "palette": 0},
    {"name": "原图宝宝 · 酷黑", "kind": "bow_baby", "render": "portrait", "palette": 1},
    {"name": "童话宝宝 · 奶油白", "kind": "bow_baby", "render": "cartoon", "palette": 2},
    {"name": "简笔宝宝 · 银灰", "kind": "bow_baby", "render": "cartoon", "palette": 3},
    {"name": "软萌宝宝 · 奶茶", "kind": "bow_baby", "render": "abstract", "palette": 4},
    {"name": "几何宝宝 · 天空蓝", "kind": "bow_baby", "render": "abstract", "palette": 5},
]

# 与猫咪六套颜色逐项对应；body 始终是肤色，其余字段负责服装与装饰主题。
HUMAN_PALETTES = [
    {"name": "暖橘", "body": "#FFD8C2", "dark": "#3A2B29", "ear": "#F4A58E",
     "belly": "#FFF0D2", "bow": "#FFB347", "dress": "#FFF7E9", "blush": "#F5A0A2"},
    {"name": "酷黑", "body": "#F6CDB8", "dark": "#211D22", "ear": "#E99A91",
     "belly": "#68636B", "bow": "#3D3D3D", "dress": "#555158", "blush": "#E58E9A"},
    {"name": "奶油白", "body": "#FFDCC8", "dark": "#493738", "ear": "#F4A7A0",
     "belly": "#FFFFFF", "bow": "#F2F2F2", "dress": "#FFFDF7", "blush": "#F7A8B3"},
    {"name": "银灰", "body": "#F2CBB8", "dark": "#4A4143", "ear": "#E79C96",
     "belly": "#D5D5D8", "bow": "#909090", "dress": "#ECECEE", "blush": "#E79AA3"},
    {"name": "奶茶", "body": "#F7D1BB", "dark": "#4B352D", "ear": "#EFA29A",
     "belly": "#E8C9A0", "bow": "#D4A574", "dress": "#F3E1CB", "blush": "#EA9A9A"},
    {"name": "天空蓝", "body": "#FFD7C4", "dark": "#293B51", "ear": "#F0A0A0",
     "belly": "#D8EEFA", "bow": "#7CB9E8", "dress": "#EAF7FF", "blush": "#EE9FA9"},
]
HUMAN_PALETTE = HUMAN_PALETTES[0]

# 对话文本
SPEECHES = {
    "idle":  ["喵~", "喵呜~", "......", "呼~", "在看什么?"],
    "happy": ["喵喵!", "好开心~", "嘿嘿~", "再摸摸!", "舒服~"],
    "sleep": ["Zzz...", "呼噜~", "好困...", "......"],
    "play":  ["玩游戏!", "耶!", "喵喵喵!", "好棒~"],
    "drag":  ["哇!", "喵?!", "放我下来!", "好高~"],
}

__all__ = [name for name in globals() if not name.startswith('__')]
