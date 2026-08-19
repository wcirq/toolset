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
    QTabWidget, QInputDialog, QMessageBox
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
    return os.path.dirname(os.path.abspath(__file__))

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

# 对话文本
SPEECHES = {
    "idle":  ["喵~", "喵呜~", "......", "呼~", "在看什么?"],
    "happy": ["喵喵!", "好开心~", "嘿嘿~", "再摸摸!", "舒服~"],
    "sleep": ["Zzz...", "呼噜~", "好困...", "......"],
    "play":  ["玩游戏!", "耶!", "喵喵喵!", "好棒~"],
    "drag":  ["哇!", "喵?!", "放我下来!", "好高~"],
}


# ======================== 粒子效果 ========================
class Particle:
    """单个粒子，用于爱心、星星、Z等视觉效果"""

    def __init__(self, x, y, kind="heart"):
        self.x = float(x)
        self.y = float(y)
        self.vx = random.uniform(-1.5, 1.5)
        self.vy = random.uniform(-3.5, -1.5)
        self.life = 1.0
        self.decay = random.uniform(0.012, 0.025)
        self.size = random.uniform(12, 20)
        self.kind = kind
        self.rot = random.uniform(0, 360)
        self.rot_spd = random.uniform(-4, 4)
        self.gravity = 0.06

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.vy += self.gravity
        self.life -= self.decay
        self.rot += self.rot_spd

    @property
    def alive(self):
        return self.life > 0

    def draw(self, painter):
        if self.life <= 0:
            return
        painter.save()
        painter.translate(self.x, self.y)
        painter.rotate(self.rot)
        painter.setOpacity(max(0.0, min(1.0, self.life)))
        if self.kind == "heart":
            self._draw_heart(painter)
        elif self.kind == "star":
            self._draw_star(painter)
        elif self.kind == "z":
            self._draw_z(painter)
        elif self.kind == "sparkle":
            self._draw_sparkle(painter)
        painter.restore()

    def _draw_heart(self, p):
        p.setBrush(QBrush(QColor(255, 85, 120)))
        p.setPen(Qt.NoPen)
        s = self.size / 2
        path = QPainterPath()
        path.moveTo(0, s * 0.35)
        path.cubicTo(-s * 0.2, -s * 0.1, -s, -s * 0.3, -s * 0.5, -s * 0.6)
        path.cubicTo(-s * 0.2, -s * 0.8, 0, -s * 0.6, 0, -s * 0.3)
        path.cubicTo(0, -s * 0.6, s * 0.2, -s * 0.8, s * 0.5, -s * 0.6)
        path.cubicTo(s, -s * 0.3, s * 0.2, -s * 0.1, 0, s * 0.35)
        p.drawPath(path)

    def _draw_star(self, p):
        p.setBrush(QBrush(QColor(255, 210, 70)))
        p.setPen(Qt.NoPen)
        s = self.size / 2
        path = QPainterPath()
        for i in range(5):
            a1 = math.radians(i * 72 - 90)
            a2 = math.radians(i * 72 - 54)
            x1, y1 = math.cos(a1) * s, math.sin(a1) * s
            x2, y2 = math.cos(a2) * s * 0.4, math.sin(a2) * s * 0.4
            if i == 0:
                path.moveTo(x1, y1)
            else:
                path.lineTo(x1, y1)
            path.lineTo(x2, y2)
        path.closeSubpath()
        p.drawPath(path)

    def _draw_z(self, p):
        font = QFont("Arial", int(self.size), QFont.Bold)
        p.setFont(font)
        p.setPen(QPen(QColor(100, 150, 255)))
        r = QRectF(-self.size, -self.size, self.size * 2, self.size * 2)
        p.drawText(r, Qt.AlignCenter, "Z")

    def _draw_sparkle(self, p):
        c = QColor(255, 255, 200)
        c.setAlpha(200)
        p.setBrush(QBrush(c))
        p.setPen(Qt.NoPen)
        s = self.size / 3
        path = QPainterPath()
        path.moveTo(0, -s)
        path.cubicTo(s * 0.3, -s * 0.3, s * 0.3, -s * 0.3, s, 0)
        path.cubicTo(s * 0.3, s * 0.3, s * 0.3, s * 0.3, 0, s)
        path.cubicTo(-s * 0.3, s * 0.3, -s * 0.3, s * 0.3, -s, 0)
        path.cubicTo(-s * 0.3, -s * 0.3, -s * 0.3, -s * 0.3, 0, -s)
        p.drawPath(path)


# ======================== 顶部聊天悬浮窗 ========================
class ChatOverlay(QWidget):
    """毛玻璃聊天框 — 顶部居中，四边渐变半透明，按回车发送气泡向上浮出"""

    def __init__(self, cat_window):
        _log("ChatOverlay.__init__ 开始")
        try:
            super().__init__()
            self.cat = cat_window
            self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
            self.setAttribute(Qt.WA_TranslucentBackground)
            _log("ChatOverlay 窗口属性已设置")

            self._W = 420
            self._min_h = 88
            self._max_h = 480
            self._pad = 16
            self._input_h = 50
            self._bubble_h = 34
            self._gap = 8
            _log(f"ChatOverlay 尺寸参数: W={self._W} min_h={self._min_h}")

            self.messages = []  # [(text, age_seconds)]

            screen = QApplication.primaryScreen().geometry()
            _log(f"屏幕尺寸: {screen.width()}x{screen.height()}")
            self.resize(self._W, self._min_h)
            self.move((screen.width() - self._W) // 2, 6)
            _log(f"ChatOverlay 已定位到 ({self.x()}, {self.y()})")

            # 输入框
            self.input_edit = QLineEdit(self)
            self.input_edit.setPlaceholderText("跟小猫说点什么...  ↵ 发送")
            self.input_edit.returnPressed.connect(self._send)
            self._style_input()
            self._relayout()
            _log("ChatOverlay input_edit 已创建")

            # 消息老化计时器
            self._fade_timer = QTimer(self)
            self._fade_timer.timeout.connect(self._age_messages)

            # 外部点击检测定时器 (每 200ms 检查鼠标是否在外面)
            self._outside_timer = QTimer(self)
            self._outside_timer.timeout.connect(self._check_outside_click)
            _log("ChatOverlay 定时器已创建")

            # 焦点变化 → 检测是否应该关闭
            QApplication.instance().focusChanged.connect(self._on_focus_changed)
            _log("ChatOverlay 焦点监听已连接")
            _log("ChatOverlay.__init__ 完成")
        except Exception as e:
            _log(f"!!! ChatOverlay.__init__ 异常: {e}\n{traceback.format_exc()}")
            raise

    # ---------- 布局 & 样式 ----------

    def _relayout(self):
        h = self.height()
        self.input_edit.setGeometry(
            self._pad, h - self._input_h - 14,
            self._W - 2 * self._pad, self._input_h
        )

    def _style_input(self):
        self.input_edit.setStyleSheet("""
            QLineEdit {
                background: rgba(255, 255, 255, 30);
                border: 1px solid rgba(255, 255, 255, 56);
                border-radius: 22px;
                padding: 8px 20px;
                color: #ffffff;
                font-size: 15px;
                font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif;
                selection-background-color: rgba(255, 180, 130, 89);
            }
            QLineEdit:focus {
                border: 1px solid rgba(255, 200, 150, 140);
                background: rgba(255, 255, 255, 46);
            }
            QLineEdit::placeholder {
                color: rgba(255, 255, 255, 89);
            }
        """)

    # ---------- 发送消息 ----------

    def _send(self):
        text = self.input_edit.text().strip()
        if not text:
            return
        _log(f"ChatOverlay._send: text='{text}'")
        self.messages.append((text, 0))
        _log(f"ChatOverlay._send: messages count={len(self.messages)}")
        self.input_edit.clear()

        # 小猫复读 + 爱心粒子
        self.cat._say(text, 180)
        self.cat._spawn_particles("heart", 3)

        # 延迟一帧调整高度，确保信号处理完成后再重绘
        QTimer.singleShot(10, self._adjust_height)

    def _adjust_height(self):
        n = len(self.messages)
        needed = self._min_h + n * (self._bubble_h + self._gap)
        new_h = min(needed, self._max_h)
        _log(f"ChatOverlay._adjust_height: n={n} old_h={self.height()} new_h={new_h}")
        self.resize(self._W, new_h)
        self._relayout()
        self.repaint()  # 强制立即重绘

    def _age_messages(self):
        """每秒老化消息，超过40秒的移除"""
        if not self.messages:
            if self.height() > self._min_h:
                self.resize(self._W, self._min_h)
                self._relayout()
                self.repaint()
            return

        changed = False
        new_msgs = []
        for text, age in self.messages:
            if age < 40:
                new_msgs.append((text, age + 1))
            else:
                changed = True

        if len(new_msgs) != len(self.messages):
            changed = True

        self.messages = new_msgs
        if changed:
            self._adjust_height()
        else:
            self.update()

    # ---------- 绘制 ----------

    def paintEvent(self, event):
        try:
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            w, h = self.width(), self.height()
            r = 18

            # 裁剪圆角
            path = QPainterPath()
            path.addRoundedRect(QRectF(0, 0, w, h), r, r)
            p.setClipPath(path)

            base_c = QColor(25, 25, 38, 215)
            edge_c = QColor(25, 25, 38, 0)
            fade = 0.28

            # 基色填充
            p.setBrush(QBrush(base_c))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(QRectF(1, 1, w - 2, h - 2), r, r)

            # 四边渐变 fade-out
            for (x1, y1, x2, y2) in [
                (0, 0, 0, h * fade),
                (0, h * (1 - fade), 0, h),
                (0, 0, w * fade, 0),
                (w * (1 - fade), 0, w, 0),
            ]:
                g = QLinearGradient(x1, y1, x2, y2)
                g.setColorAt(0, edge_c)
                g.setColorAt(1, base_c)
                p.setBrush(QBrush(g))
                if x1 == x2:
                    p.drawRect(QRectF(0, y1, w, h * fade + 1))
                else:
                    p.drawRect(QRectF(x1, 0, w * fade + 1, h))

            # 细边框
            p.setClipping(False)
            p.setPen(QPen(QColor(255, 255, 255, 38), 1))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), r, r)

            # 分隔线 (输入框上方)
            div_y = h - self._input_h - 26
            if div_y > 10:
                g = QLinearGradient(w * 0.3, 0, w * 0.7, 0)
                g.setColorAt(0, QColor(255, 255, 255, 0))
                g.setColorAt(0.5, QColor(255, 255, 255, 32))
                g.setColorAt(1, QColor(255, 255, 255, 0))
                p.setPen(QPen(QBrush(g), 1))
                p.drawLine(QPointF(w * 0.3, div_y), QPointF(w * 0.7, div_y))

            # 消息气泡 (自下而上排列)
            msg_bottom = div_y - 14 if div_y > 10 else h - self._input_h - 32
            font = QFont("Microsoft YaHei", 12)
            font.setStyleHint(QFont.SansSerif)  # 确保字体回退
            p.setFont(font)

            drawn = 0
            for i in range(len(self.messages) - 1, -1, -1):
                text, age = self.messages[i]
                if msg_bottom < 5:
                    break

                alpha = max(30, 230 - age * 6)
                fm = p.fontMetrics()
                # width() 兼容所有 PyQt5 版本 (horizontalAdvance 需要 Qt ≥5.11)
                tw = fm.width(text)
                bw = max(tw + 30, 60)
                bx = (w - bw) / 2
                by = msg_bottom - self._bubble_h

                bc = QColor(255, 255, 255, min(alpha, 190))
                p.setBrush(QBrush(bc))
                p.setPen(QPen(QColor(255, 255, 255, min(alpha // 3, 50)), 1))
                p.drawRoundedRect(
                    QRectF(bx, by, bw, self._bubble_h),
                    self._bubble_h / 2, self._bubble_h / 2
                )

                tc = QColor(55, 55, 65)
                tc.setAlpha(alpha)
                p.setPen(QPen(tc))
                p.drawText(QRectF(bx, by, bw, self._bubble_h), Qt.AlignCenter, text)

                msg_bottom = by - self._gap
                drawn += 1

            if drawn > 0:
                _log(f"ChatOverlay.paint: 绘制了 {drawn} 个气泡, h={h}")

            if p.isActive():
                p.end()
        except Exception as e:
            _log(f"!!! ChatOverlay.paintEvent 异常: {e}\n{traceback.format_exc()}")

    # ---------- 窗口事件 ----------

    def showEvent(self, event):
        _log("ChatOverlay.showEvent 触发")
        try:
            super().showEvent(event)
            self.input_edit.setFocus()
            self.input_edit.clear()
            self._fade_timer.start(1000)
            self._outside_timer.stop()  # 显示时停止外部检测
            _log("ChatOverlay.showEvent 完成")
        except Exception as e:
            _log(f"!!! ChatOverlay.showEvent 异常: {e}\n{traceback.format_exc()}")
            raise

    def hideEvent(self, event):
        super().hideEvent(event)
        self._fade_timer.stop()
        self._outside_timer.stop()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.hide()
        super().keyPressEvent(event)

    def eventFilter(self, obj, event):
        """已废弃 — 改用 _on_focus_changed + _outside_timer"""
        return super().eventFilter(obj, event)

    def _on_focus_changed(self, old, new):
        """当焦点离开聊天框和输入框时启动外部检测"""
        if not self.isVisible():
            return
        # 如果新焦点既不是聊天框本身也不是其子控件(输入框)
        if new is None or (new is not self and new is not self.input_edit and not self.isAncestorOf(new)):
            _log(f"ChatOverlay 焦点转移: old={old} new={new}, 启动外部检测")
            self._outside_timer.start(200)

    def _check_outside_click(self):
        """定时检查：如果鼠标在聊天框和猫窗外，且左键按下 → 关闭"""
        if not self.isVisible():
            self._outside_timer.stop()
            return

        mouse = QCursor.pos()
        in_chat = self.geometry().contains(mouse)
        in_cat = self.cat.geometry().contains(mouse)

        if not in_chat and not in_cat:
            # 检测是否有鼠标按下 (通过 QApplication.mouseButtons)
            if QApplication.mouseButtons() & Qt.LeftButton:
                _log("ChatOverlay: 检测到外部点击, 关闭")
                self.hide()
                self._outside_timer.stop()
        else:
            # 鼠标回到聊天框或猫窗 → 停止检测
            self._outside_timer.stop()

    # ---------- 滚轮调整大小 ----------

    def wheelEvent(self, event):
        """Ctrl+滚轮 或 直接滚轮 调整控件宽度"""
        delta = event.angleDelta().y()
        step = 20
        new_w = self._W + (step if delta > 0 else -step)
        new_w = max(280, min(700, new_w))
        if new_w != self._W:
            self._W = new_w
            self.resize(self._W, self.height())
            self._relayout()
            self.update()
        event.accept()


# ======================== 窗口枚举与切换 ========================
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

# 程序员工具关键词优先级 (命中越靠前的排在程序列表越前面)
DEV_TOOL_KEYWORDS = [
    "visual studio", "devenv",                        # Visual Studio
    "code", "vscode",                                 # VS Code
    "cursor", "trae",
    "idea", "intellij", "pycharm", "webstorm", "clion",
    "rider", "goland", "datagrip", "phpstorm", "jetbrains",
    "sublime", "notepad++", "notepad3",
    "vim", "neovim", "gvim", "emacs",
    "atom", "eclipse", "hbuilder", "kdevelop", "qtcreator",
    "windowsterminal", "terminal",
    "powershell", "pwsh", "cmd", "conhost", "bash", "git-bash",
    "putty", "winscp", "xshell", "mobaxterm", "ftp",
    "git", "svn", "docker", "postman",
]

def _get_window_exe(hwnd):
    """通过窗口句柄取进程可执行名 (小写去扩展名); 失败返回空串"""
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return ""
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            name = os.path.basename(buf.value)
            return os.path.splitext(name)[0].lower()
        return ""
    finally:
        kernel32.CloseHandle(h)

def list_windows():
    """
    枚举所有有可见标题的顶层窗口。
    返回 [(hwnd, title, exe_name), ...]
    排序: 程序员工具按优先级排最前, 其余按标题字母序。
    """
    items = []
    seen = set()

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value.strip()
        if not title:
            return True
        exe = _get_window_exe(hwnd)
        key = (title.lower(), exe)
        if key in seen:
            return True
        seen.add(key)
        items.append((hwnd, title, exe))
        return True

    user32.EnumWindows(callback, 0)

    def rank(item):
        _hwnd, title, exe = item
        hay = (exe + " " + title).lower()
        for i, kw in enumerate(DEV_TOOL_KEYWORDS):
            if kw in hay:
                return (0, i, title.lower())
        return (1, 0, title.lower())

    items.sort(key=rank)
    return items

def _force_foreground(hwnd):
    """
    强制把窗口切到前台, 绕过 Windows 前台锁定保护。
    背景: 后台进程直接调 SetForegroundWindow 会被系统拒绝, 只会闪任务栏图标。
    技巧: 1) 模拟 Alt 键按下, 让系统认为是用户按键发起的切换
          2) AttachThreadInput 把当前线程挂到前台窗口线程, 获得 SetForegroundWindow 权限
          3) 兜底 SwitchToThisWindow (Win32 未公开 API, 对多窗口程序如 VS 特别有效)
    """
    try:
        import ctypes
        from ctypes import wintypes

        VK_MENU = 0x12
        KEYEVENTF_KEYUP = 0x0002

        # 方法1: 模拟 Alt 按下/抬起, 解除前台锁定
        ctypes.windll.user32.keybd_event(VK_MENU, 0, 0, 0)
        user32.SetForegroundWindow(hwnd)
        ctypes.windll.user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)

        # 验证是否成功
        if user32.GetForegroundWindow() == hwnd:
            return True

        # 方法2: 线程挂接
        fg = user32.GetForegroundWindow()      # 当前前台窗口
        fg_tid = user32.GetWindowThreadProcessId(fg, None)
        cur_tid = ctypes.windll.kernel32.GetCurrentThreadId()
        our_pid = wintypes.DWORD()
        our_tid = user32.GetWindowThreadProcessId(hwnd, ctypes.byref(our_pid))
        if fg_tid and fg_tid != cur_tid:
            if ctypes.windll.user32.AttachThreadInput(cur_tid, fg_tid, True):
                try:
                    if user32.IsIconic(hwnd):
                        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                    user32.BringWindowToTop(hwnd)
                    user32.SetForegroundWindow(hwnd)
                finally:
                    ctypes.windll.user32.AttachThreadInput(cur_tid, fg_tid, False)

        if user32.GetForegroundWindow() == hwnd:
            return True

        # 方法3: 兜底 SwitchToThisWindow (对 VS 这类多窗口程序有效)
        try:
            SwitchToThisWindow = ctypes.windll.user32.SwitchToThisWindow
            SwitchToThisWindow.argtypes = [wintypes.HWND, wintypes.BOOL]
            SwitchToThisWindow(hwnd, True)
        except Exception:
            pass

        return user32.GetForegroundWindow() == hwnd
    except Exception as e:
        _log(f"_force_foreground 异常: {e}")
        return False


def switch_to_target(title_keyword="", exe_keyword=""):
    """
    把匹配目标程序的窗口切到前台。
    匹配优先级: 可执行名精确 > 可执行名包含 > 标题包含。
    返回 (成功: bool, 消息: str)
    """
    title_keyword = (title_keyword or "").strip().lower()
    exe_keyword = (exe_keyword or "").strip().lower()
    if not title_keyword and not exe_keyword:
        return False, "未设置目标程序"

    try:
        best, best_score = None, -1
        for hwnd, title, exe in list_windows():
            score = 0
            if exe_keyword and exe_keyword == exe:
                score = 100
            elif exe_keyword and exe_keyword in exe:
                score = 60
            elif title_keyword and title_keyword in title.lower():
                score = 30
            if score > best_score:
                best_score, best = score, hwnd

        if best is None:
            return False, f"没有运行中的程序匹配 '{exe_keyword or title_keyword}'"

        if user32.IsIconic(best):
            user32.ShowWindow(best, 9)  # SW_RESTORE
        ok = _force_foreground(best)
        if not ok:
            _log("前台切换被系统拒绝(已尝试Alt模拟+线程挂接+SwitchToThisWindow)")
        return True, "切换成功" if ok else "已尝试切换(可能仍被系统限制)"
    except Exception as e:
        _log(f"switch_to_target 异常: {e}\n{traceback.format_exc()}")
        return False, str(e)


# ======================== 配置文件 ========================
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

DEFAULT_CONFIG = {
    "model": "hog",            # "hog" = HOG+Haar 传统检测, "yolo" = YOLOv26 深度学习
    "yolo_model": "yolo26n.pt",  # YOLO 权重文件 (ultralytics 会自动下载)
    "yolo_conf": 0.4,          # YOLO 置信度阈值
    "pose_kpt_conf": 0.5,      # pose 模型: 头部关键点(鼻/眼/耳)置信度阈值
    "dedup_iou": 0.55,         # 重复框合并: IoU/包含率超过该值的框视为同一人
    "trigger_count": 2,        # 检测到 >= 该人数(pose模型=头部数)时触发切换
    "sustain_sec": 1.5,        # 持续检出超过该秒数才触发 (0 = 立即)
    "cat_scale": 1.0,          # 小猫尺寸倍率 (0.6 ~ 2.0)
    "camera_index": 0,         # 摄像头编号
    "target_exe": "devenv",    # 目标程序可执行名关键字 (devenv=VS, Code=VSCode, idea64=IDEA...)
    "target_title": "visual studio",  # 目标程序窗口标题关键字
    "hotkey": "Ctrl+Alt+V",    # 全局快捷键 (快速切换到目标程序)
    "hotkey_enabled": True,    # 是否启用全局快捷键
    "chat_enabled": False,     # 聊天输入功能 (暂时禁用)
    "debug_save": False,       # 调试: 满足切换条件时保存标注检测图片到 debug_shots/
    "preview_scale": 1.0,      # 预览窗口缩放 (滚轮调整, 自动记忆)
    "cat_color": 0,            # 小猫颜色索引 (对应 COLORS 列表, 右键换颜色后自动记忆)
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


# ======================== 开机自启动 ========================
AUTOSTART_REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
AUTOSTART_REG_NAME = "CoolCat"

def _autostart_command():
    """构造注册表里写入的启动命令 (exe 模式直接 exe 路径; 源码模式用 pythonw)"""
    if getattr(sys, "frozen", False):
        # exe: "C:\...\CoolCat.exe"
        exe = os.path.abspath(sys.executable)
        return f'"{exe}"'
    # 源码: pythonw "...\main.py"
    py = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(py):
        py = sys.executable
    return f'"{py}" "{os.path.join(BASE_DIR, "main.py")}"'

def is_autostart_enabled():
    """读取注册表, 返回开机启动是否已开启"""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_REG_PATH, 0, winreg.KEY_READ) as key:
            val, _ = winreg.QueryValueEx(key, AUTOSTART_REG_NAME)
            return bool(val)
    except FileNotFoundError:
        return False
    except Exception as e:
        _log(f"读取开机启动状态失败: {e}")
        return False

def set_autostart(enabled):
    """写入/删除注册表项, 开启/关闭开机启动"""
    try:
        if enabled:
            cmd = _autostart_command()
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_REG_PATH, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, AUTOSTART_REG_NAME, 0, winreg.REG_SZ, cmd)
            _log(f"已开启开机启动: {cmd}")
        else:
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_REG_PATH, 0, winreg.KEY_SET_VALUE) as key:
                    winreg.DeleteValue(key, AUTOSTART_REG_NAME)
            except FileNotFoundError:
                pass
            _log("已关闭开机启动")
        return True
    except Exception as e:
        _log(f"设置开机启动失败: {e}")
        return False


# ======================== 全局快捷键 ========================
WM_HOTKEY = 0x0312
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN = 0x1, 0x2, 0x4, 0x8
HOTKEY_ID = 0xC47  # RegisterHotKey 自定义 ID

# 键名 → Windows 虚拟键码
VK_MAP = {chr(c): c for c in range(ord("A"), ord("Z") + 1)}
VK_MAP.update({str(d): 0x30 + d for d in range(10)})
VK_MAP.update({f"F{i}": 0x70 + i - 1 for i in range(1, 13)})

def parse_hotkey(text):
    """'Ctrl+Alt+V' → (mod_flags, vk); 解析失败返回 (0, 0)"""
    parts = [p.strip() for p in text.split("+") if p.strip()]
    mod, vk = 0, 0
    for p in parts:
        low = p.lower()
        if low in ("ctrl", "control"):
            mod |= MOD_CONTROL
        elif low == "alt":
            mod |= MOD_ALT
        elif low == "shift":
            mod |= MOD_SHIFT
        elif low == "win":
            mod |= MOD_WIN
        elif p.upper() in VK_MAP:
            vk = VK_MAP[p.upper()]
    return mod, vk

class HotkeyManager(QAbstractNativeEventFilter):
    """全局快捷键: 按下即回调 (用于快速切换到目标程序)"""

    def __init__(self, callback):
        super().__init__()
        self._callback = callback
        self._hwnd = None
        self._registered = False

    def register(self, hwnd, hotkey_text, enabled=True):
        self.unregister()
        if not enabled:
            return False
        mod, vk = parse_hotkey(hotkey_text)
        if not mod or not vk:
            _log(f"快捷键格式无效: {hotkey_text}")
            return False
        if user32.RegisterHotKey(hwnd, HOTKEY_ID, mod, vk):
            self._hwnd = hwnd
            self._registered = True
            _log(f"全局快捷键已注册: {hotkey_text}")
            return True
        _log(f"快捷键注册失败 (可能被占用): {hotkey_text}")
        return False

    def unregister(self):
        if self._registered and self._hwnd:
            user32.UnregisterHotKey(self._hwnd, HOTKEY_ID)
            _log("全局快捷键已注销")
        self._registered = False
        self._hwnd = None

    def nativeEventFilter(self, eventType, message):
        if eventType == "windows_generic_MSG":
            try:
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                    if self._callback:
                        self._callback()
            except Exception:
                pass
        return False, 0


# ======================== 摄像头检测线程 ========================
class CameraThread(QThread):
    """
    后台线程: 持续读取摄像头视频流并运行人体检测。
    支持两种模型:
      - "hog":  HOG 行人 + Haar 人脸 (传统检测, 无需额外依赖)
      - "yolo": YOLOv26 深度学习模型 (需要 ultralytics 包)
    每帧发射 frame_ready(QImage, list) 信号;
    人数变化时发射 person_count_changed(int) 信号。
    检测结果: [(x, y, w, h, is_main), ...]  is_main=True 为最大框(主人)
    """
    frame_ready = pyqtSignal(object, list, list, list, list)   # QImage, boxes, confs, skipped, kpts
    person_count_changed = pyqtSignal(int)
    camera_error = pyqtSignal(str)

    # 检测参数
    DETECT_WIDTH = 480        # 检测用缩放宽度 (越小越快)
    DETECT_INTERVAL = 3       # 每 N 帧检测一次
    MIN_BOX_AREA = 80 * 160   # 过滤太小的框 (HOG 模式)

    def __init__(self, camera_index=0, model="hog", yolo_model="yolo26n.pt",
                 yolo_conf=0.4, trigger_count=2, sustain_sec=1.5,
                 pose_kpt_conf=0.5, debug_save=False, dedup_iou=0.55):
        super().__init__()
        self.camera_index = camera_index
        self.model = model                       # "hog" / "yolo"
        self.yolo_model = yolo_model
        self.yolo_conf = yolo_conf
        self.pose_kpt_conf = max(0.05, min(0.95, float(pose_kpt_conf)))
        self.dedup_iou = max(0.2, min(0.95, float(dedup_iou)))  # 重复框合并阈值
        self.trigger_count = max(2, int(trigger_count))   # 触发人数阈值
        self.sustain_sec = max(0.0, float(sustain_sec))   # 持续秒数
        self.debug_save = bool(debug_save)       # 调试: 触发切换时保存标注图片

        self._running = False
        self._mutex = QMutex()

        # HOG 行人检测器 (全身, 适合站立的行人)
        self.hog = cv2.HOGDescriptor()
        self.hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

        # Haar 正脸检测器 (近距离坐着的上半身用户)
        cascade_path = os.path.join(
            cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
        self.face_cascade = cv2.CascadeClassifier(cascade_path)

        # YOLO 模型 (懒加载, run() 中初始化)
        self.yolo = None
        self.pose_mode = False   # True = pose 模型, 按"头部关键点"计数

        # 缓存最近一次检测结果 (供跳帧期间绘制)
        self._last_boxes = []
        self._last_confs = []    # 与 _last_boxes 对齐的置信度 (无则 -1)
        self._last_skipped = []  # pose 模式被头部阈值过滤掉的人 [(x,y,w,h,head_conf), ...]
        self._last_kpts = []     # pose 模式头部关键点 [(x, y, conf), ...] 原图坐标
        self._last_display = None   # 最近一帧标注后的图 (调试存图用)
        # 多人确认计时
        self._multi_since = None
        self._multi_emitted = False

    def _init_yolo(self):
        """加载 YOLO 模型; 失败时返回错误信息"""
        try:
            from ultralytics import YOLO
            # 依次尝试指定权重 → 常见回退权重
            # 优先从程序根目录 (exe 同目录) 加载
            candidates = [
                os.path.join(BASE_DIR, self.yolo_model),
                self.yolo_model, "yolo11n.pt", "yolov8n.pt",
            ]
            tried = []
            for name in candidates:
                if name in tried:
                    continue
                tried.append(name)
                try:
                    self.yolo = YOLO(name)
                    # 识别是否为 pose 模型 (任务类型或文件名判断)
                    task = getattr(self.yolo, "task", "") or ""
                    self.pose_mode = ("pose" in str(task).lower()
                                      or "pose" in os.path.basename(str(name)).lower())
                    mode_text = " [pose 模式: 按头部关键点计数]" if self.pose_mode else ""
                    _log(f"YOLO 模型加载成功: {name}{mode_text}")
                    return None
                except Exception as e:
                    _log(f"YOLO 权重 {name} 加载失败: {e}")
            return f"YOLO 模型均加载失败: {tried}"
        except ImportError:
            return "未安装 ultralytics 包 (pip install ultralytics)"
        except Exception as e:
            return f"YOLO 初始化异常: {e}"

    # ---------- 线程主循环 ----------

    def run(self):
        # YOLO 模式先加载模型
        if self.model == "yolo":
            err = self._init_yolo()
            if err:
                _log(f"YOLO 不可用, 回退到 HOG 模式: {err}")
                self.camera_error.emit(err + " | 已回退到 HOG 检测")
                self.model = "hog"

        cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap = cv2.VideoCapture(self.camera_index)
        if not cap.isOpened():
            self.camera_error.emit(f"无法打开摄像头 {self.camera_index}")
            return

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        _log(f"摄像头 {self.camera_index} 已打开")

        self._running = True
        frame_idx = 0

        while self._running:
            ret, frame = cap.read()
            if not ret or frame is None:
                continue

            # 水平镜像翻转 (前置摄像头自拍效果, 画面更直观)
            frame = cv2.flip(frame, 1)

            frame_idx += 1
            h, w = frame.shape[:2]

            # ---------- 检测 (每 DETECT_INTERVAL 帧一次) ----------
            need_report = False
            if frame_idx % self.DETECT_INTERVAL == 0:
                boxes = self._detect(frame, w, h)
                self._last_boxes = boxes
                need_report = True
            boxes = self._last_boxes

            # ---------- 绘制检测框并转 QImage ----------
            display = self._draw_boxes(frame.copy(), boxes, self._last_confs,
                                       self._last_skipped, self._last_kpts)
            self._last_display = display
            # 先画完本帧再上报人数, 保证触发时的调试存图
            # 与触发判断用的是同一帧 (含全部框/SKIP/关键点)
            if need_report:
                self._report_count(len(boxes))
            rgb = cv2.cvtColor(display, cv2.COLOR_BGR2RGB)
            qimg = QImage(rgb.data, rgb.shape[1], rgb.shape[0],
                          rgb.strides[0], QImage.Format_RGB888)
            # 拷贝一份, 防止底层缓冲被复用
            qimg = qimg.copy()
            self.frame_ready.emit(qimg, boxes, list(self._last_confs),
                                  list(self._last_skipped),
                                  list(self._last_kpts))

            self.msleep(33)  # ~30 FPS

        cap.release()
        _log("摄像头已释放")

    def stop(self):
        self._running = False
        self.wait(3000)

    # ---------- 检测逻辑 ----------

    def _detect(self, frame, orig_w, orig_h):
        """
        根据当前模型分发检测。
        内部返回 [(x, y, w, h, conf), ...]
        最终设置 self._last_confs 并返回 [(x, y, w, h, is_main), ...]
        """
        if self.model == "yolo" and self.yolo is not None:
            self._last_skipped = []
            self._last_kpts = []
            raw = self._detect_yolo(frame, orig_w, orig_h)
        else:
            self._last_skipped = []
            self._last_kpts = []
            raw = self._detect_hog(frame, orig_w, orig_h)

        # 同一人被识别成多个几乎重叠的框 → 合并去重
        raw = self._dedup_boxes(raw)

        if not raw:
            self._last_confs = []
            return []

        # 找最大面积框 → 主人(绿框)
        areas = [b[2] * b[3] for b in raw]
        main_idx = int(np.argmax(areas)) if raw else -1
        result = []
        confs = []
        for i, b in enumerate(raw):
            result.append((b[0], b[1], b[2], b[3], i == main_idx))
            c = b[4] if len(b) > 4 else -1.0
            confs.append(float(c) if c is not None else -1.0)
        self._last_confs = confs
        return result

    # ---------- 重复框合并 ----------

    @staticmethod
    def _iou(b1, b2):
        """两框 IoU + 包含率: 返回 max(IoU, 交集/较小框面积)
        后者用于捕获"嵌套框"(大框套小框, IoU 不高但明显是同一人)"""
        x1 = max(b1[0], b2[0]); y1 = max(b1[1], b2[1])
        x2 = min(b1[0] + b1[2], b2[0] + b2[2])
        y2 = min(b1[1] + b1[3], b2[1] + b2[3])
        if x2 <= x1 or y2 <= y1:
            return 0.0
        inter = (x2 - x1) * (y2 - y1)
        a1 = b1[2] * b1[3]; a2 = b2[2] * b2[3]
        union = a1 + a2 - inter
        return max(inter / union if union > 0 else 0.0,
                   inter / min(a1, a2) if min(a1, a2) > 0 else 0.0)

    def _dedup_boxes(self, boxes):
        """贪心去重: 按置信度降序保留, 与已保留框重叠率(IoU/包含率)
        >= dedup_iou 的框视为同一人, 丢弃。"""
        if len(boxes) <= 1:
            return boxes
        items = sorted(boxes, key=lambda b: (b[4] if len(b) > 4 else 0.0),
                       reverse=True)
        kept = []
        for b in items:
            if all(self._iou(b, k) < self.dedup_iou for k in kept):
                kept.append(b)
        return kept

    def _detect_yolo(self, frame, orig_w, orig_h):
        """YOLOv26 人体检测 (class 0 = person); pose 模型按头部关键点过滤"""
        try:
            scale = self.DETECT_WIDTH / orig_w
            small = cv2.resize(frame, (self.DETECT_WIDTH,
                                       int(orig_h * scale)))
            if self.pose_mode:
                return self._detect_yolo_pose(small, scale)
            results = self.yolo.predict(
                small, classes=[0], conf=self.yolo_conf,
                verbose=False, imgsz=self.DETECT_WIDTH
            )
            boxes = []
            for r in results:
                for b in r.boxes:
                    x1, y1, x2, y2 = b.xyxy[0].tolist()
                    conf = float(b.conf[0]) if b.conf is not None and len(b.conf) else -1.0
                    bx = int(x1 / scale)
                    by = int(y1 / scale)
                    bw = int((x2 - x1) / scale)
                    bh = int((y2 - y1) / scale)
                    if bw > 10 and bh > 10:
                        boxes.append([bx, by, bw, bh, conf])
            return boxes
        except Exception as e:
            _log(f"YOLO 检测异常: {e}")
            return self._last_boxes and [list(b[:4]) for b in self._last_boxes] or []

    # COCO 17 关键点中的头部点: 0=鼻, 1=左眼, 2=右眼, 3=左耳, 4=右耳
    HEAD_KPT_IDS = (0, 1, 2, 3, 4)

    def _detect_yolo_pose(self, small, scale):
        """
        pose 模型检测: 每个检出的人, 只有当其头部关键点(鼻/眼/耳)中
        置信度最高者 >= pose_kpt_conf 时才算一个"出现的头", 计入人数。
        身体被遮挡但头部可见的人也能被正确计数。
        """
        results = self.yolo.predict(
            small, conf=self.yolo_conf, verbose=False,
            imgsz=self.DETECT_WIDTH
        )
        boxes = []
        for r in results:
            kpts = getattr(r, "keypoints", None)
            n = len(r.boxes)
            for i in range(n):
                head_ok = False
                head_confs = []
                if kpts is not None and kpts.data is not None and len(kpts.data) > i:
                    try:
                        # data: (17, 3) 每行 [x, y, conf]
                        kdata = kpts.data[i]
                        if kdata.shape[0] >= 5:
                            head_confs = [float(kdata[k][2])
                                          for k in self.HEAD_KPT_IDS]
                            head_ok = (max(head_confs) >= self.pose_kpt_conf)
                    except Exception as e:
                        _log(f"关键点解析异常: {e}")
                        head_ok = False
                if not head_ok:
                    # 不计数, 但保留框用于调试绘制 (灰色 SKIP)
                    x1, y1, x2, y2 = r.boxes[i].xyxy[0].tolist()
                    sk = (int(x1 / scale), int(y1 / scale),
                          int((x2 - x1) / scale), int((y2 - y1) / scale),
                          max(head_confs) if head_confs else -1.0)
                    if sk[2] > 10 and sk[3] > 10:
                        self._last_skipped.append(sk)
                    continue   # 头部不可见/置信度低 → 不计数
                # 标注用置信度 = 头部关键点最高置信度 (更有参考意义)
                head_conf = max(head_confs) if head_confs else -1.0
                # 头部关键点 (原图坐标) 用于调试绘制
                for k in self.HEAD_KPT_IDS:
                    try:
                        kx = float(kdata[k][0]) / scale
                        ky = float(kdata[k][1]) / scale
                        kc = float(kdata[k][2])
                        if kc > 0.01 and 0 <= kx and 0 <= ky:
                            self._last_kpts.append((int(kx), int(ky), kc))
                    except Exception:
                        pass
                x1, y1, x2, y2 = r.boxes[i].xyxy[0].tolist()
                bx = int(x1 / scale)
                by = int(y1 / scale)
                bw = int((x2 - x1) / scale)
                bh = int((y2 - y1) / scale)
                if bw > 10 and bh > 10:
                    boxes.append([bx, by, bw, bh, head_conf])
        return boxes

    def _detect_hog(self, frame, orig_w, orig_h):
        """
        融合检测: HOG 全身行人 + Haar 正脸。
        脸落在 HOG 框内 → 同一个人; 框外的脸视为额外的人 (近距离坐姿用户)。
        """
        scale = self.DETECT_WIDTH / orig_w
        small = cv2.resize(frame, (self.DETECT_WIDTH,
                                   int(orig_h * scale)))
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

        boxes = []

        # ---------- HOG 全身行人 ----------
        try:
            rects, weights = self.hog.detectMultiScale(
                small, winStride=(8, 8), padding=(4, 4), scale=1.05
            )
            for (x, y, w, h), wt in zip(rects, weights):
                wt = float(wt)
                if wt < 0.3:   # 置信度过滤
                    continue
                bx, by = int(x / scale), int(y / scale)
                bw, bh = int(w / scale), int(h / scale)
                if bw * bh >= self.MIN_BOX_AREA:
                    boxes.append([bx, by, bw, bh, min(1.0, wt)])
        except cv2.error as e:
            _log(f"HOG 检测异常: {e}")

        # NMS 合并 HOG 重叠框
        boxes = self._nms(boxes, 0.4)

        # ---------- Haar 人脸 (补充近距离坐姿用户) ----------
        try:
            faces = self.face_cascade.detectMultiScale(
                gray, scaleFactor=1.15, minNeighbors=5, minSize=(36, 36)
            )
        except cv2.error:
            faces = []

        for (fx, fy, fw, fh) in faces:
            cx = fx + fw / 2
            cy = fy + fh / 2
            # 该脸的中心是否已落在某个 HOG 框内 (small 坐标系比较)
            inside = any(
                x <= cx <= x + w and y <= cy <= y + h
                for (x, y, w, h) in [
                    (b[0] * scale, b[1] * scale, b[2] * scale, b[3] * scale)
                    for b in boxes
                ]
            )
            if inside:
                continue
            # 框外的脸 → 独立的人, 估算上半身框 (脸向下扩展)
            ex = int((fx - fw * 0.5) / scale)
            ey = int((fy - fh * 0.3) / scale)
            ew = int(fw * 2.0 / scale)
            eh = int(fh * 3.0 / scale)
            # 限制在画面内
            ex = max(0, min(ex, orig_w - 1))
            ey = max(0, min(ey, orig_h - 1))
            ew = min(ew, orig_w - ex)
            eh = min(eh, orig_h - ey)
            boxes.append([ex, ey, ew, eh, -1.0])   # Haar 无置信度

        return boxes

    @staticmethod
    def _nms(boxes, threshold):
        """简单非极大值抑制"""
        if not boxes:
            return []
        arr = np.array(boxes, dtype=float)
        x1, y1 = arr[:, 0], arr[:, 1]
        x2, y2 = arr[:, 0] + arr[:, 2], arr[:, 1] + arr[:, 3]
        areas = arr[:, 2] * arr[:, 3]
        order = areas.argsort()[::-1]

        keep = []
        while order.size > 0:
            i = order[0]
            keep.append(i)
            xx1 = np.maximum(x1[i], x1[order[1:]])
            yy1 = np.maximum(y1[i], y1[order[1:]])
            xx2 = np.minimum(x2[i], x2[order[1:]])
            yy2 = np.minimum(y2[i], y2[order[1:]])
            inter = np.maximum(0, xx2 - xx1) * np.maximum(0, yy2 - yy1)
            iou = inter / (areas[i] + areas[order[1:]] - inter + 1e-6)
            order = order[1:][iou < threshold]

        return [list(boxes[int(i)]) for i in keep]

    # ---------- 人数上报 ----------

    def _report_count(self, count):
        now = datetime.now()
        if count >= self.trigger_count:
            if self.sustain_sec <= 0:
                # 立即触发模式
                if not self._multi_emitted:
                    self._multi_emitted = True
                    self._save_debug_shot(count)
                    self.person_count_changed.emit(count)
            else:
                if self._multi_since is None:
                    self._multi_since = now
                    self._multi_emitted = False
                elif (not self._multi_emitted and
                      (now - self._multi_since).total_seconds() >= self.sustain_sec):
                    # 确认多人 → 只发射一次
                    self._multi_emitted = True
                    self._save_debug_shot(count)
                    self.person_count_changed.emit(count)
        else:
            # 人离开 → 重置, 下次再次检出多人会重新触发
            if self._multi_since is not None or self._multi_emitted:
                self._multi_since = None
                self._multi_emitted = False
                self.person_count_changed.emit(count)

    # ---------- 调试存图 ----------

    def _save_debug_shot(self, count):
        """
        调试模式: 满足切换条件时, 把最近一帧 (已绘制检测框+置信度)
        保存到 debug_shots/ 目录, 文件名含时间戳和检出数量。
        """
        if not self.debug_save or self._last_display is None:
            return
        try:
            out_dir = os.path.join(BASE_DIR, "debug_shots")
            os.makedirs(out_dir, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
            unit = "head" if self.pose_mode else "person"
            path = os.path.join(out_dir, f"trigger_{ts}_{count}{unit}.jpg")
            ok, buf = cv2.imencode(".jpg", self._last_display,
                                   [cv2.IMWRITE_JPEG_QUALITY, 90])
            if ok:
                with open(path, "wb") as f:
                    f.write(buf.tobytes())
                _log(f"[调试] 已保存触发截图: {os.path.basename(path)}")
            else:
                _log("[调试] 截图编码失败")
        except Exception as e:
            _log(f"[调试] 保存触发截图失败: {e}")

    # ---------- 绘制 ----------

    @staticmethod
    def _draw_boxes(frame, boxes, confs=None, skipped=None, kpts=None):
        """
        主人体绿框, 其他红框; confs 对齐时显示置信度。
        skipped: pose 模式被过滤的人 → 灰色 SKIP 框 (head_conf)
        kpts:    pose 模式头部关键点 → 黄色圆点, 达阈值画实心
        """
        # 先画被过滤的 (底层), 再画计入的 (上层)
        if skipped:
            for (x, y, w, h, c) in skipped:
                cv2.rectangle(frame, (x, y), (x + w, y + h),
                              (160, 160, 160), 1)
                label = f"SKIP {c:.2f}" if c is not None and c >= 0 else "SKIP"
                cv2.putText(frame, label, (x + 3, y + 16),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (160, 160, 160), 1)
        for idx, (x, y, w, h, is_main) in enumerate(boxes):
            color = (0, 255, 0) if is_main else (0, 0, 255)  # BGR
            thickness = 3 if is_main else 2
            cv2.rectangle(frame, (x, y), (x + w, y + h), color, thickness)
            label = "MAIN" if is_main else "PERSON"
            if confs and idx < len(confs) and confs[idx] is not None and confs[idx] >= 0:
                label += f" {confs[idx]:.2f}"
            # 标签背景
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
            ty = y if y - th - 10 >= 0 else y + th + 10   # 贴顶时标签放框内下方
            cv2.rectangle(frame, (x, ty - th - 10), (x + tw + 10, ty), color, -1)
            cv2.putText(frame, label, (x + 5, ty - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)
        # 头部关键点: 黄色圆点 (实心=conf≥0.5, 空心=低置信度)
        if kpts:
            for (kx, ky, kc) in kpts:
                r, thick = (4, -1) if kc >= 0.5 else (4, 1)
                cv2.circle(frame, (kx, ky), r, (0, 255, 255), thick)
        return frame


# ======================== 摄像头预览悬浮窗 ========================
class CameraPreview(QWidget):
    """
    摄像头预览窗口 — 长按小猫时显示在旁边。
    滚轮缩放画面大小; 显示人体检测框(绿=主人/红=其他人)。
    """
    BASE_W, BASE_H = 480, 360   # 基准显示尺寸
    MIN_SCALE, MAX_SCALE = 0.5, 3.0

    def __init__(self, cat_window):
        super().__init__()
        self.cat = cat_window
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)

        # 从配置恢复上次的缩放 (记忆窗口大小)
        try:
            saved = self.cat.config.get("preview_scale", 1.0)
            self.scale = max(self.MIN_SCALE, min(self.MAX_SCALE, float(saved)))
        except Exception:
            self.scale = 1.0
        self.image = None       # QImage
        self.boxes = []
        self.confs = []
        self.skipped = []       # pose 模式被过滤的人
        self.kpts = []          # pose 模式头部关键点
        self.person_count = 0
        self._close_rect = None   # 关闭按钮区域 (paintEvent 中更新)

        self._apply_size()

    # ---------- 尺寸 / 缩放 ----------

    def _apply_size(self):
        w = int(self.BASE_W * self.scale)
        h = int(self.BASE_H * self.scale)
        self.resize(w, h + 34)  # 底部信息条 34px

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        step = 0.15
        new_scale = self.scale + (step if delta > 0 else -step)
        new_scale = max(self.MIN_SCALE, min(self.MAX_SCALE, new_scale))
        if new_scale != self.scale:
            self.scale = new_scale
            self._apply_size()
            self._save_scale()
            # 缩放后保持窗口在屏幕内
            self.cat._position_preview()
            self.update()
        event.accept()

    def _save_scale(self):
        """把当前缩放写入配置, 下次启动恢复同样大小"""
        try:
            self.cat.config["preview_scale"] = round(self.scale, 2)
            save_config(self.cat.config)
        except Exception as e:
            _log(f"保存预览窗口大小失败: {e}")

    # ---------- 数据更新 ----------

    def update_frame(self, qimg, boxes, confs=None, skipped=None, kpts=None):
        self.image = qimg
        self.boxes = boxes
        self.confs = confs or []
        self.skipped = skipped or []
        self.kpts = kpts or []
        self.person_count = len(boxes)
        if self.isVisible():
            self.update()

    # ---------- 绘制 ----------

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)

        w, h = self.width(), self.height()
        bar_h = 34

        # 背景
        p.setBrush(QBrush(QColor(20, 20, 30, 235)))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(0, 0, w, h), 12, 12)

        # 视频区域
        video_rect = QRectF(6, 6, w - 12, h - bar_h - 12)
        if self.image is not None and not self.image.isNull():
            pixmap = QPixmap.fromImage(self.image)
            scaled = pixmap.scaled(
                int(video_rect.width()), int(video_rect.height()),
                Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            vx = video_rect.x() + (video_rect.width() - scaled.width()) / 2
            vy = video_rect.y() + (video_rect.height() - scaled.height()) / 2
            p.drawPixmap(QPointF(vx, vy), scaled)

            # 检测框覆盖层 (与图像等比缩放)
            self._draw_overlay(p, QRectF(vx, vy, scaled.width(), scaled.height()))
        else:
            p.setPen(QPen(QColor(150, 150, 160)))
            font = QFont("Microsoft YaHei", 11)
            p.setFont(font)
            p.drawText(video_rect, Qt.AlignCenter,
                       "摄像头启动中..." if self.cat.cam_ok is None else "摄像头不可用")

        # 底部信息条
        self._draw_info_bar(p, w, h, bar_h)

        # 边框
        p.setPen(QPen(QColor(255, 255, 255, 40), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 12, 12)

        # 关闭按钮 (右上角)
        btn_r = 14
        bx, by = w - btn_r - 8, btn_r + 6
        self._close_rect = QRectF(bx, by, btn_r, btn_r)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(60, 60, 75, 220)))
        p.drawEllipse(self._close_rect)
        p.setPen(QPen(QColor(220, 220, 230), 2))
        m = 4
        p.drawLine(QPointF(bx + m, by + m), QPointF(bx + btn_r - m, by + btn_r - m))
        p.drawLine(QPointF(bx + btn_r - m, by + m), QPointF(bx + m, by + btn_r - m))

        p.end()

    def _draw_overlay(self, p, dst_rect):
        """在缩放后的视频上绘制检测框 (绿=主人 红=其他 灰=SKIP 黄点=头部关键点)"""
        if self.image is None:
            return
        if not self.boxes and not self.skipped and not self.kpts:
            return
        iw, ih = self.image.width(), self.image.height()
        sx = dst_rect.width() / iw
        sy = dst_rect.height() / ih

        # SKIP 框 (被头部阈值过滤的人)
        for (x, y, bw, bh, c) in self.skipped:
            color = QColor(160, 160, 160)
            p.setPen(QPen(color, 1))
            p.setBrush(Qt.NoBrush)
            p.drawRect(QRectF(dst_rect.x() + x * sx, dst_rect.y() + y * sy,
                              bw * sx, bh * sy))
            label = f"SKIP {c:.2f}" if c is not None and c >= 0 else "SKIP"
            font = QFont("Arial", max(7, int(8 * self.scale)), QFont.Normal)
            p.setFont(font)
            p.setPen(QPen(color))
            p.drawText(QPointF(dst_rect.x() + x * sx + 3,
                               dst_rect.y() + y * sy + 14), label)

        # 头部关键点 (黄点)
        for (kx, ky, kc) in self.kpts:
            color = QColor(255, 255, 0)
            p.setPen(QPen(color, 2))
            p.setBrush(color if kc >= 0.5 else Qt.NoBrush)
            p.drawEllipse(QPointF(dst_rect.x() + kx * sx,
                                  dst_rect.y() + ky * sy), 4, 4)

        for idx, (x, y, bw, bh, is_main) in enumerate(self.boxes):
            color = QColor(0, 230, 80) if is_main else QColor(255, 70, 70)
            pen_w = 3 if is_main else 2
            p.setPen(QPen(color, pen_w))
            p.setBrush(Qt.NoBrush)
            rx = dst_rect.x() + x * sx
            ry = dst_rect.y() + y * sy
            p.drawRect(QRectF(rx, ry, bw * sx, bh * sy))

            label = "MAIN" if is_main else "PERSON"
            if idx < len(self.confs) and self.confs[idx] is not None \
                    and self.confs[idx] >= 0:
                label += f" {self.confs[idx]:.2f}"
            font = QFont("Arial", max(8, int(9 * self.scale)), QFont.Bold)
            p.setFont(font)
            fm = p.fontMetrics()
            tw = fm.horizontalAdvance(label) + 8
            th = fm.height() + 2
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(color))
            p.drawRect(QRectF(rx, ry - th, tw, th))
            p.setPen(QPen(QColor(255, 255, 255)))
            p.drawText(QRectF(rx, ry - th, tw, th), Qt.AlignCenter, label)

    def _draw_info_bar(self, p, w, h, bar_h):
        y = h - bar_h
        p.setPen(QPen(QColor(255, 255, 255, 30), 1))
        p.drawLine(QPointF(10, y), QPointF(w - 10, y))

        font = QFont("Microsoft YaHei", 9)
        p.setFont(font)
        p.setPen(QPen(QColor(200, 200, 210)))

        if self.person_count == 0:
            status = "No person"
            color = QColor(160, 160, 170)
        elif self.person_count == 1:
            status = "1 person (main)"
            color = QColor(0, 230, 80)
        else:
            status = f"{self.person_count} persons - switching"
            color = QColor(255, 90, 90)

        p.setPen(QPen(color))
        p.drawText(QRectF(12, y, w - 120, bar_h),
                   Qt.AlignVCenter | Qt.AlignLeft, status)

        p.setPen(QPen(QColor(140, 140, 150)))
        p.drawText(QRectF(w - 110, y, 98, bar_h),
                   Qt.AlignVCenter | Qt.AlignRight,
                   f"zoom {self.scale:.1f}x")

    # ---------- 预览窗口自身可拖动 ----------
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # 点关闭按钮 → 隐藏预览
            if self._close_rect is not None and \
                    self._close_rect.contains(QPointF(event.pos())):
                self.hide()
                return
            self._drag_off = event.pos()
            self._dragging = True

    def mouseMoveEvent(self, event):
        if getattr(self, "_dragging", False):
            self.move(event.globalPos() - self._drag_off)

    def mouseReleaseEvent(self, event):
        self._dragging = False


# ======================== 设置对话框 ========================
class SettingsDialog(QDialog):
    """
    配置页面: 检测模型 / 触发规则 / 小猫尺寸 / 摄像头。
    保存后通过 get_config() 返回新配置, 由 CatWindow 应用并持久化。
    """
    STYLE = """
        QDialog {
            background: #1E1E2A;
            color: #E8E8F0;
            font-family: 'Microsoft YaHei';
            font-size: 13px;
        }
        QGroupBox {
            border: 1px solid #3A3A4E;
            border-radius: 8px;
            margin-top: 14px;
            padding: 14px 10px 10px 10px;
            font-weight: bold;
            color: #FFB347;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 12px;
            padding: 0 6px;
        }
        QLabel { color: #C8C8D4; }
        QComboBox, QSpinBox, QDoubleSpinBox {
            background: #2A2A3C;
            color: #FFFFFF;
            border: 1px solid #4A4A60;
            border-radius: 5px;
            padding: 4px 8px;
            min-width: 140px;
        }
        QLineEdit {
            background: #2A2A3C;
            color: #FFFFFF;
            border: 1px solid #4A4A60;
            border-radius: 5px;
            padding: 4px 8px;
            min-width: 140px;
        }
        QComboBox QAbstractItemView {
            background: #2A2A3C;
            color: #FFFFFF;
            selection-background-color: #4A5A80;
        }
        QSlider::groove:horizontal {
            height: 6px;
            background: #3A3A4E;
            border-radius: 3px;
        }
        QSlider::handle:horizontal {
            width: 16px; height: 16px;
            margin: -5px 0;
            border-radius: 8px;
            background: #FFB347;
        }
        QPushButton {
            background: #3A3A55;
            color: #FFFFFF;
            border: none;
            border-radius: 6px;
            padding: 8px 22px;
        }
        QPushButton:hover { background: #4A4A70; }
        QPushButton#okBtn {
            background: #E89530;
            font-weight: bold;
        }
        QPushButton#okBtn:hover { background: #FFB347; }
        QCheckBox { color: #C8C8D4; }
        QTabWidget::pane {
            border: 1px solid #3A3A4E;
            border-radius: 6px;
            top: -1px;
        }
        QTabBar::tab {
            background: #2A2A3C;
            color: #C8C8D4;
            padding: 7px 18px;
            margin-right: 3px;
            border-top-left-radius: 6px;
            border-top-right-radius: 6px;
        }
        QTabBar::tab:selected {
            background: #3A3A55;
            color: #FFB347;
            font-weight: bold;
        }
        QTabBar::tab:hover { background: #34344A; }
    """

    def __init__(self, cfg, yolo_available, parent=None):
        super().__init__(parent)
        self.setWindowTitle("小猫设置")
        self.setWindowFlags(Qt.Dialog | Qt.WindowStaysOnTopHint)
        self.setStyleSheet(self.STYLE)
        self.setMinimumWidth(420)
        self._yolo_available = yolo_available
        self._cfg = cfg   # 保存引用, get_config 时保留非 UI 项 (如 preview_scale)

        root = QVBoxLayout(self)

        # ---------- 分页容器 ----------
        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)

        # ========== Tab 1: 检测与触发 ==========
        page1 = QWidget()
        l1 = QVBoxLayout(page1)
        l1.setContentsMargins(8, 8, 8, 8)

        # ---------- 检测模型 ----------
        g1 = QGroupBox("检测模型")
        f1 = QFormLayout(g1)
        self.model_combo = QComboBox()
        self.model_combo.addItem("HOG+Haar 传统检测 (快速, 无额外依赖)", "hog")
        yolo_text = "YOLOv26 深度学习 (精准)" if yolo_available else \
                    "YOLOv26 深度学习 (未安装 ultralytics, 选中将回退)"
        self.model_combo.addItem(yolo_text, "yolo")
        f1.addRow("检测模型:", self.model_combo)

        self.yolo_model_combo = QComboBox()
        self.yolo_model_combo.setEditable(True)
        for name in ["yolo26n.pt", "yolo26n-pose.pt", "yolo26s.pt",
                     "yolo11n.pt", "yolo11n-pose.pt", "yolov8n-pose.pt"]:
            self.yolo_model_combo.addItem(name)
        f1.addRow("YOLO 权重:", self.yolo_model_combo)

        self.conf_spin = QDoubleSpinBox()
        self.conf_spin.setRange(0.05, 0.95)
        self.conf_spin.setSingleStep(0.05)
        f1.addRow("置信度阈值:", self.conf_spin)

        self.kpt_conf_spin = QDoubleSpinBox()
        self.kpt_conf_spin.setRange(0.1, 0.95)
        self.kpt_conf_spin.setSingleStep(0.05)
        self.kpt_conf_spin.setToolTip("pose 模型: 头部关键点(鼻/眼/耳)置信度达到该值才算一个出现的头部")
        f1.addRow("头部关键点置信度:", self.kpt_conf_spin)

        pose_hint = QLabel("提示: 权重名含 -pose 时为姿态模型, 触发按\"出现头部数\"计算 (身体被挡也能数到)")
        pose_hint.setStyleSheet("color: #8888A0; font-size: 11px; font-weight: normal;")
        pose_hint.setWordWrap(True)
        f1.addRow("", pose_hint)
        l1.addWidget(g1)

        # ---------- 触发规则 ----------
        g2 = QGroupBox("触发规则 (检测到多人时自动切换到目标程序)")
        f2 = QFormLayout(g2)
        self.count_spin = QSpinBox()
        self.count_spin.setRange(2, 10)
        self.count_spin.setSuffix(" 人")
        self.count_label = QLabel("触发人数 ≥:")
        f2.addRow(self.count_label, self.count_spin)

        self.sustain_spin = QDoubleSpinBox()
        self.sustain_spin.setRange(0.0, 10.0)
        self.sustain_spin.setSingleStep(0.5)
        self.sustain_spin.setSuffix(" 秒")
        self.sustain_spin.setSpecialValueText("立即触发 (0秒)")
        f2.addRow("持续检出时间:", self.sustain_spin)

        self.dedup_spin = QDoubleSpinBox()
        self.dedup_spin.setRange(0.2, 0.95)
        self.dedup_spin.setSingleStep(0.05)
        self.dedup_spin.setValue(0.55)
        f2.addRow("重复框合并阈值:", self.dedup_spin)
        dedup_hint = QLabel("重叠率超过该值的两个框视为同一人 (解决一人被识别成两人); 值越小合并越激进")
        dedup_hint.setStyleSheet("color: #8888A0; font-size: 11px; font-weight: normal;")
        dedup_hint.setWordWrap(True)
        f2.addRow("", dedup_hint)
        l1.addWidget(g2)
        l1.addStretch()
        self.tabs.addTab(page1, "检测与触发")

        # ========== Tab 2: 目标与快捷键 ==========
        page2 = QWidget()
        l2 = QVBoxLayout(page2)
        l2.setContentsMargins(8, 8, 8, 8)

        # ---------- 小猫尺寸 ----------
        g3 = QGroupBox("小猫尺寸")
        f3 = QFormLayout(g3)
        self.scale_slider = QSlider(Qt.Horizontal)
        self.scale_slider.setRange(60, 200)
        self.scale_slider.setTickInterval(10)
        self.scale_label = QLabel("100%")
        self.scale_label.setMinimumWidth(48)
        row = QHBoxLayout()
        row.addWidget(self.scale_slider)
        row.addWidget(self.scale_label)
        f3.addRow("大小:", row)
        hint = QLabel("提示: 也可以用右键菜单中的 +/- 快速调整")
        hint.setStyleSheet("color: #8888A0; font-size: 11px; font-weight: normal;")
        f3.addRow("", hint)
        l2.addWidget(g3)

        # ---------- 摄像头 ----------
        g4 = QGroupBox("摄像头")
        f4 = QFormLayout(g4)
        self.cam_spin = QSpinBox()
        self.cam_spin.setRange(0, 5)
        f4.addRow("摄像头编号:", self.cam_spin)

        self.debug_check = QCheckBox("调试模式: 满足切换条件时保存检测图片 (debug_shots/)")
        f4.addRow("", self.debug_check)
        dbg_hint = QLabel("图片带检测框和置信度标注, 用于排查误触发/漏检")
        dbg_hint.setStyleSheet("color: #8888A0; font-size: 11px; font-weight: normal;")
        dbg_hint.setWordWrap(True)
        f4.addRow("", dbg_hint)
        l2.addWidget(g4)
        l2.addStretch()
        self.tabs.addTab(page2, "小猫与摄像头")

        # ========== Tab 3: 目标程序与快捷键 ==========
        page3 = QWidget()
        l3 = QVBoxLayout(page3)
        l3.setContentsMargins(8, 8, 8, 8)

        # ---------- 目标程序切换 ----------
        g5 = QGroupBox("目标程序 (检测到多人自动切换 / 按快捷键手动切换)")
        f5 = QFormLayout(g5)

        self.target_combo = QComboBox()
        self.target_combo.setEditable(True)
        self.target_combo.lineEdit().setPlaceholderText("选择运行中的程序, 或手动输入程序名")
        f5.addRow("目标程序:", self.target_combo)

        refresh_btn = QPushButton("刷新程序列表")
        refresh_btn.clicked.connect(self._refresh_windows)
        f5.addRow("", refresh_btn)

        self.target_title_edit = QLineEdit()
        self.target_title_edit.setPlaceholderText("窗口标题关键字, 如 visual studio (可留空)")
        f5.addRow("标题关键字:", self.target_title_edit)

        hint2 = QLabel("列表中程序员工具 (VS/VSCode/IDEA 等) 已排在前面; 也可手动输入如 devenv / Code")
        hint2.setStyleSheet("color: #8888A0; font-size: 11px; font-weight: normal;")
        hint2.setWordWrap(True)
        f5.addRow("", hint2)
        l3.addWidget(g5)

        # ---------- 全局快捷键 ----------
        g6 = QGroupBox("全局快捷键 (任意界面按下 → 快速切换到目标程序)")
        f6 = QFormLayout(g6)
        hrow = QHBoxLayout()
        self.hk_ctrl = QCheckBox("Ctrl")
        self.hk_alt = QCheckBox("Alt")
        self.hk_shift = QCheckBox("Shift")
        self.hk_win = QCheckBox("Win")
        self.hk_key = QComboBox()
        for k in (list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
                  + [str(d) for d in range(10)]
                  + [f"F{i}" for i in range(1, 13)]):
            self.hk_key.addItem(k)
        self.hk_key.setMinimumWidth(70)
        hrow.addWidget(self.hk_ctrl)
        hrow.addWidget(self.hk_alt)
        hrow.addWidget(self.hk_shift)
        hrow.addWidget(self.hk_win)
        hrow.addSpacing(6)
        hrow.addWidget(self.hk_key)
        hrow.addStretch()
        f6.addRow("组合键:", hrow)

        self.hk_enabled = QCheckBox("启用全局快捷键")
        f6.addRow("", self.hk_enabled)
        l3.addWidget(g6)
        l3.addStretch()
        self.tabs.addTab(page3, "目标与快捷键")

        # ========== Tab 4: 安全 ==========
        page4 = QWidget()
        l4 = QVBoxLayout(page4)
        l4.setContentsMargins(8, 8, 8, 8)

        g7 = QGroupBox("设置页面密码 (打开设置需要输入)")
        f7 = QFormLayout(g7)
        self.pwd_old_edit = QLineEdit()
        self.pwd_old_edit.setEchoMode(QLineEdit.Password)
        self.pwd_old_edit.setPlaceholderText("留空表示不修改密码")
        f7.addRow("当前密码:", self.pwd_old_edit)
        self.pwd_new_edit = QLineEdit()
        self.pwd_new_edit.setEchoMode(QLineEdit.Password)
        self.pwd_new_edit.setPlaceholderText("留空表示不修改密码")
        f7.addRow("新密码:", self.pwd_new_edit)
        self.pwd_new2_edit = QLineEdit()
        self.pwd_new2_edit.setEchoMode(QLineEdit.Password)
        self.pwd_new2_edit.setPlaceholderText("再输入一遍新密码")
        f7.addRow("确认新密码:", self.pwd_new2_edit)
        pwd_hint = QLabel("修改后点击下方\"保存并应用\"生效; 密码以 SHA-256 哈希存储, 配置文件不含明文; 忘记密码可删除 config.json 中的 settings_password_hash 恢复默认")
        pwd_hint.setStyleSheet("color: #8888A0; font-size: 11px; font-weight: normal;")
        pwd_hint.setWordWrap(True)
        f7.addRow("", pwd_hint)
        l4.addWidget(g7)
        l4.addStretch()
        self.tabs.addTab(page4, "安全")

        # ---------- 按钮 ----------
        btns = QHBoxLayout()
        reset_btn = QPushButton("恢复默认")
        reset_btn.clicked.connect(self._reset)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        ok_btn = QPushButton("保存并应用")
        ok_btn.setObjectName("okBtn")
        ok_btn.clicked.connect(self.accept)
        btns.addWidget(reset_btn)
        btns.addStretch()
        btns.addWidget(cancel_btn)
        btns.addWidget(ok_btn)
        root.addLayout(btns)

        self.scale_slider.valueChanged.connect(
            lambda v: self.scale_label.setText(f"{v}%"))

        # ---------- 载入当前配置 ----------
        self.model_combo.setCurrentIndex(1 if cfg["model"] == "yolo" else 0)
        self.yolo_model_combo.setCurrentText(cfg["yolo_model"])
        self.conf_spin.setValue(cfg["yolo_conf"])
        self.kpt_conf_spin.setValue(cfg.get("pose_kpt_conf", 0.5))
        self.count_spin.setValue(cfg["trigger_count"])
        self.sustain_spin.setValue(cfg["sustain_sec"])
        self.dedup_spin.setValue(cfg.get("dedup_iou", 0.55))
        self.scale_slider.setValue(int(cfg["cat_scale"] * 100))
        self.cam_spin.setValue(cfg["camera_index"])
        self.debug_check.setChecked(bool(cfg.get("debug_save", False)))

        # pose 模型联动: 触发标签/单位改为"头部"
        self._update_count_label()
        self.yolo_model_combo.currentTextChanged.connect(
            lambda _t: self._update_count_label())

        # 目标程序
        self._refresh_windows()
        idx = self.target_combo.findData(cfg.get("target_exe", ""))
        if idx >= 0:
            self.target_combo.setCurrentIndex(idx)
        elif cfg.get("target_exe"):
            self.target_combo.setEditText(cfg["target_exe"])
        self.target_title_edit.setText(cfg.get("target_title", ""))

        # 快捷键
        mod, vk = parse_hotkey(cfg.get("hotkey", "Ctrl+Alt+V"))
        self.hk_ctrl.setChecked(bool(mod & MOD_CONTROL))
        self.hk_alt.setChecked(bool(mod & MOD_ALT))
        self.hk_shift.setChecked(bool(mod & MOD_SHIFT))
        self.hk_win.setChecked(bool(mod & MOD_WIN))
        key_text = next((name for name, code in VK_MAP.items() if code == vk), "V")
        ki = self.hk_key.findText(key_text)
        self.hk_key.setCurrentIndex(ki if ki >= 0 else self.hk_key.findText("V"))
        self.hk_enabled.setChecked(cfg.get("hotkey_enabled", True))

        # 密码: 当前密码引用 + 修改后的新密码 (None = 未修改)
        self._new_password = None

    def accept(self):
        """保存前校验密码修改输入"""
        old_pwd = self.pwd_old_edit.text()
        new_pwd = self.pwd_new_edit.text()
        new_pwd2 = self.pwd_new2_edit.text()
        if new_pwd or new_pwd2:
            cur_hash = self._cfg.get("settings_password_hash",
                                     DEFAULT_CONFIG["settings_password_hash"])
            if _hash_password(old_pwd) != cur_hash:
                QMessageBox.warning(self, "密码错误", "当前密码不正确!")
                self.tabs.setCurrentWidget(self.tabs.widget(3))
                self.pwd_old_edit.setFocus()
                return
            if new_pwd != new_pwd2:
                QMessageBox.warning(self, "密码不一致", "两次输入的新密码不一致!")
                self.tabs.setCurrentWidget(self.tabs.widget(3))
                self.pwd_new_edit.setFocus()
                return
            if not new_pwd:
                QMessageBox.warning(self, "密码为空", "新密码不能为空!")
                return
            self._new_password = new_pwd
        super().accept()

    def _update_count_label(self):
        """当前权重是否为 pose 模型 → 切换触发计数标签 (人数/头部数)"""
        if self.count_label is None:
            return
        text = self.yolo_model_combo.currentText().lower()
        if "pose" in text:
            self.count_label.setText("触发头部数 ≥:")
            self.count_spin.setSuffix(" 头")
        else:
            self.count_label.setText("触发人数 ≥:")
            self.count_spin.setSuffix(" 人")

    def _refresh_windows(self):
        """枚举当前运行的程序填充下拉框 (程序员工具优先)"""
        self.target_combo.blockSignals(True)
        try:
            self.target_combo.clear()
            for _hwnd, title, exe in list_windows():
                label = f"{exe or 'unknown'}  -  {title[:40]}"
                self.target_combo.addItem(label, exe)
        except Exception as e:
            _log(f"刷新程序列表失败: {e}")
        finally:
            self.target_combo.blockSignals(False)

    def _reset(self):
        self.model_combo.setCurrentIndex(0)
        self.yolo_model_combo.setCurrentText(DEFAULT_CONFIG["yolo_model"])
        self.conf_spin.setValue(DEFAULT_CONFIG["yolo_conf"])
        self.kpt_conf_spin.setValue(DEFAULT_CONFIG["pose_kpt_conf"])
        self.count_spin.setValue(DEFAULT_CONFIG["trigger_count"])
        self.sustain_spin.setValue(DEFAULT_CONFIG["sustain_sec"])
        self.dedup_spin.setValue(DEFAULT_CONFIG["dedup_iou"])
        self.scale_slider.setValue(100)
        self.cam_spin.setValue(0)
        self.debug_check.setChecked(DEFAULT_CONFIG["debug_save"])
        self.target_title_edit.setText(DEFAULT_CONFIG["target_title"])
        self.hk_ctrl.setChecked(True)
        self.hk_alt.setChecked(True)
        self.hk_shift.setChecked(False)
        self.hk_win.setChecked(False)
        self.hk_key.setCurrentIndex(self.hk_key.findText("V"))
        self.hk_enabled.setChecked(True)
        # 密码输入框清空 (不重置密码本身)
        self.pwd_old_edit.clear()
        self.pwd_new_edit.clear()
        self.pwd_new2_edit.clear()

    def get_config(self):
        # 目标程序: 优先取列表项数据, 手动输入则取输入内容
        exe = self.target_combo.currentData()
        if not exe:
            text = self.target_combo.currentText().strip()
            exe = text.split(" ")[0].lower() if text else ""
        # 快捷键
        mods = []
        if self.hk_ctrl.isChecked():
            mods.append("Ctrl")
        if self.hk_alt.isChecked():
            mods.append("Alt")
        if self.hk_shift.isChecked():
            mods.append("Shift")
        if self.hk_win.isChecked():
            mods.append("Win")
        hotkey = "+".join(mods + [self.hk_key.currentText()]) if mods else ""
        return {
            "model": self.model_combo.currentData(),
            "yolo_model": self.yolo_model_combo.currentText().strip() or "yolo26n.pt",
            "yolo_conf": round(self.conf_spin.value(), 2),
            "pose_kpt_conf": round(self.kpt_conf_spin.value(), 2),
            "trigger_count": self.count_spin.value(),
            "sustain_sec": round(self.sustain_spin.value(), 1),
            "dedup_iou": round(self.dedup_spin.value(), 2),
            "cat_scale": self.scale_slider.value() / 100.0,
            "camera_index": self.cam_spin.value(),
            "target_exe": (exe or "").lower(),
            "target_title": self.target_title_edit.text().strip(),
            "hotkey": hotkey or "Ctrl+Alt+V",
            "hotkey_enabled": self.hk_enabled.isChecked() and bool(mods),
            "chat_enabled": False,   # 聊天输入功能暂时禁用
            "debug_save": self.debug_check.isChecked(),
            # 非 UI 项原样保留 (预览窗口缩放等由滚轮实时修改)
            "preview_scale": self._cfg.get("preview_scale", 1.0),
            # 密码: 未修改则保留原哈希; 修改过则存新密码的哈希
            "settings_password_hash": _hash_password(self._new_password) if self._new_password
                else self._cfg.get("settings_password_hash",
                                   DEFAULT_CONFIG["settings_password_hash"]),
            "cat_color": self._cfg.get("cat_color", 0),
        }


# ======================== 小猫主窗口 ========================
class CatWindow(QWidget):
    """无边框透明置顶的小猫悬浮窗口"""

    # 状态枚举
    IDLE = "idle"
    HAPPY = "happy"
    SLEEP = "sleep"
    PLAY = "play"
    DRAG = "drag"

    def __init__(self):
        super().__init__()

        # ---------- 加载配置 ----------
        self.config = load_config()
        self.cat_scale = max(0.6, min(2.0, float(self.config["cat_scale"])))
        # 开机启动状态 (从注册表读取)
        self._autostart_on = is_autostart_enabled()

        self._setup_window()
        self._init_state()
        self.chat = ChatOverlay(self)
        self._setup_tray()
        self._apply_scale(self.cat_scale, keep_center=False)

        # ---------- 摄像头人体检测 ----------
        self.cam_ok = None                     # None=初始化中 True/False
        self.preview = CameraPreview(self)
        self.preview.hide()
        self.longpress_active = False           # 长按显示预览中
        self._multi_triggered = False           # 防止重复触发 VS 切换

        self._start_camera_thread()

        # 长按检测计时器 (500ms 未移动未释放 → 长按)
        self.press_timer = QTimer(self)
        self.press_timer.setSingleShot(True)
        self.press_timer.timeout.connect(self._on_long_press)

        # ---------- 全局快捷键 ----------
        self.hotkey_mgr = HotkeyManager(self._on_hotkey)
        QApplication.instance().installNativeEventFilter(self.hotkey_mgr)
        self._apply_hotkey()

        self._start_timer()

    # ---------- 全局快捷键 / 目标程序切换 ----------

    def _apply_hotkey(self):
        """按当前配置注册全局快捷键"""
        try:
            hwnd = int(self.winId())
            enabled = self.config.get("hotkey_enabled", True)
            ok = self.hotkey_mgr.register(
                hwnd, self.config.get("hotkey", "Ctrl+Alt+V"), enabled)
            if not ok and enabled:
                self._say("快捷键被占用了...")
        except Exception as e:
            _log(f"快捷键注册异常: {e}\n{traceback.format_exc()}")

    def _on_hotkey(self):
        """全局快捷键按下 → 立即切换到目标程序"""
        _log("全局快捷键触发")
        self._set_state(self.PLAY, 45)
        self._do_switch_target("切!")

    def _do_switch_target(self, tip=""):
        """执行切换到目标程序 (配置中的 target_exe / target_title)"""
        if tip:
            self._say(tip, 80)
        ok, msg = switch_to_target(
            title_keyword=self.config.get("target_title", ""),
            exe_keyword=self.config.get("target_exe", ""),
        )
        _log(f"切换目标程序: ok={ok} msg={msg}")
        if not ok:
            self._say(f"{msg[:16]}...", 120)

    # ---------- 摄像头线程管理 ----------

    def _start_camera_thread(self):
        """按当前配置创建并启动摄像头检测线程"""
        cfg = self.config
        self.camera_thread = CameraThread(
            camera_index=cfg["camera_index"],
            model=cfg["model"],
            yolo_model=cfg["yolo_model"],
            yolo_conf=cfg["yolo_conf"],
            pose_kpt_conf=cfg.get("pose_kpt_conf", 0.5),
            trigger_count=cfg["trigger_count"],
            sustain_sec=cfg["sustain_sec"],
            debug_save=cfg.get("debug_save", False),
            dedup_iou=cfg.get("dedup_iou", 0.55),
        )
        self.camera_thread.frame_ready.connect(self._on_camera_frame)
        self.camera_thread.person_count_changed.connect(self._on_person_count)
        self.camera_thread.camera_error.connect(self._on_camera_error)
        self.camera_thread.start()

    def _restart_camera_thread(self):
        """配置修改后重启检测线程"""
        try:
            if self.camera_thread is not None and self.camera_thread.isRunning():
                self.camera_thread.stop()
        except Exception:
            pass
        self._start_camera_thread()

    # ---------- 设置对话框 ----------

    def _open_settings(self):
        try:
            # ---------- 密码验证 (哈希比对) ----------
            cur_hash = self.config.get("settings_password_hash",
                                       DEFAULT_CONFIG["settings_password_hash"])
            pwd, ok = QInputDialog.getText(
                self, "身份验证", "请输入设置页面访问密码:",
                QLineEdit.Password)
            if not ok:
                return                      # 用户取消
            if _hash_password(pwd) != cur_hash:
                self._say("密码错误!", 90)
                QMessageBox.warning(self, "密码错误",
                                    "密码不正确, 无法打开设置页面!")
                return

            # 检查 ultralytics 是否可用 (用于对话框提示)
            yolo_ok = False
            try:
                import ultralytics  # noqa
                yolo_ok = True
            except Exception:
                # ImportError: 未安装; OSError/WinError 1114: DLL 加载失败
                pass

            dlg = SettingsDialog(self.config, yolo_ok, parent=self)
            if dlg.exec_() == QDialog.Accepted:
                new_cfg = dlg.get_config()
                old = dict(self.config)
                self.config = new_cfg
                save_config(new_cfg)

                # 应用小猫尺寸
                if new_cfg["cat_scale"] != old["cat_scale"]:
                    self._apply_scale(new_cfg["cat_scale"])

                # 模型/触发规则/摄像头变化 → 重启检测线程
                cam_keys = ("model", "yolo_model", "yolo_conf", "pose_kpt_conf",
                            "trigger_count", "sustain_sec", "camera_index",
                            "dedup_iou")
                if any(new_cfg[k] != old[k] for k in cam_keys):
                    model_name = "YOLOv26" if new_cfg["model"] == "yolo" else "HOG"
                    self._say(f"已切换 {model_name} 检测~")
                    self._restart_camera_thread()

                # 快捷键变化 → 重新注册
                if any(new_cfg[k] != old.get(k)
                       for k in ("hotkey", "hotkey_enabled")):
                    self._apply_hotkey()
                    hk = new_cfg["hotkey"] if new_cfg["hotkey_enabled"] else "快捷键已关闭"
                    self._say(f"{hk}~", 90)

                # 调试存图开关 → 直接热更新到检测线程 (无需重启)
                if new_cfg.get("debug_save", False) != old.get("debug_save", False):
                    self.camera_thread.debug_save = new_cfg["debug_save"]
                    self._say("调试存图已开启" if new_cfg["debug_save"] else "调试存图已关闭", 90)

                # 目标程序变化提示
                if any(new_cfg[k] != old.get(k) for k in ("target_exe", "target_title")):
                    name = new_cfg["target_exe"] or new_cfg["target_title"] or "未设置"
                    self._say(f"目标程序: {name}", 120)
        except Exception as e:
            _log(f"!!! 设置对话框异常: {e}\n{traceback.format_exc()}")

    # ---------- 小猫尺寸缩放 ----------

    def _apply_scale(self, scale, keep_center=True):
        """按倍率缩放小猫窗口 (绘制时用 painter 变换)"""
        scale = max(0.6, min(2.0, float(scale)))
        old_w, old_h = self.width(), self.height()
        # 以当前中心为锚点缩放
        cx = self.x() + old_w // 2
        cy = self.y() + old_h // 2
        new_w, new_h = int(W * scale), int(H * scale)
        self.cat_scale = scale
        self.resize(new_w, new_h)
        if keep_center:
            self.move(cx - new_w // 2, cy - new_h // 2)
        self.config["cat_scale"] = scale
        self.update()

    def _change_cat_size(self, delta):
        """右键菜单 +/- 快速调整尺寸 (每次 20%)"""
        new_scale = self.cat_scale + delta
        new_scale = max(0.6, min(2.0, new_scale))
        if abs(new_scale - self.cat_scale) > 0.001:
            self._apply_scale(new_scale)
            save_config(self.config)
            self._say(f"{int(self.cat_scale * 100)}% 大啦~", 90)

    # ---------- 摄像头回调 ----------

    def _on_camera_frame(self, qimg, boxes, confs=None, skipped=None, kpts=None):
        self.cam_ok = True
        self.preview.update_frame(qimg, boxes, confs, skipped, kpts)

    def _on_camera_error(self, msg):
        self.cam_ok = False
        _log(f"摄像头错误: {msg}")
        if "YOLO" in msg or "ultralytics" in msg:
            self._say("YOLO不可用, 用HOG检测~")
        else:
            self._say("摄像头打不开...")

    def _on_person_count(self, count):
        _log(f"人数变化: {count}")
        threshold = self.config.get("trigger_count", 2)
        if count >= threshold:
            if not self._multi_triggered:
                self._multi_triggered = True
                self._spawn_particles("sparkle", 5)
                self._do_switch_target("有别人来了! 切换!")
        else:
            # 人离开, 重置触发标记
            self._multi_triggered = False

    # ---------- 长按显示/隐藏预览 ----------

    def _on_long_press(self):
        """左键按住 500ms 且未拖动 → 显示摄像头预览"""
        if self.dragging and self.drag_distance < 8:
            self.longpress_active = True
            self._set_state(self.PLAY, 0)
            self._say("看看谁在偷看~")
            self._show_preview()

    def _show_preview(self):
        self._position_preview()
        self.preview.show()
        self.preview.raise_()

    def _hide_preview(self):
        self.preview.hide()
        self.longpress_active = False
        if self.state == self.PLAY:
            self._set_state(self.IDLE, 0)

    def _position_preview(self):
        """将预览窗口放到小猫旁边 (优先右侧, 空间不足放左侧)"""
        pw, ph = self.preview.width(), self.preview.height()
        screen = QApplication.primaryScreen().geometry()
        margin = 16

        px = self.x() + self.width() + margin
        if px + pw > screen.width():
            px = self.x() - pw - margin
        py = self.y() - (ph - self.height()) // 2
        py = max(8, min(screen.height() - ph - 8, py))
        px = max(8, px)
        self.preview.move(px, py)

    # ---------- 初始化 ----------

    def _setup_window(self):
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)
        sw = int(W * self.cat_scale)
        sh = int(H * self.cat_scale)
        self.resize(sw, sh)
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() - sw - 60, screen.height() - sh - 40)

    def _init_state(self):
        self.state = self.IDLE
        self.prev_state = self.IDLE
        # 颜色从配置读取 (上次选的), 越界则回退橘猫
        idx = int(self.config.get("cat_color", 0))
        self.color_idx = idx if 0 <= idx < len(COLORS) else 0
        self.c = COLORS[self.color_idx]

        self.frame = 0
        self.state_frame = 0
        self._state_duration = 0

        # 眨眼
        self.blink_cd = random.randint(120, 300)
        self.blink_left = 0

        # 眼睛跟随鼠标
        self.eye_x = 0.0
        self.eye_y = 0.0
        self.eye_tx = 0.0
        self.eye_ty = 0.0

        # 弹跳
        self.bounce = 0.0

        # 尾巴
        self.tail_phase = 0.0
        self.tail_speed = 0.04

        # 粒子
        self.particles = []

        # 对话
        self.speech = ""
        self.speech_left = 0
        self.speech_cd = random.randint(400, 800)

        # 拖拽
        self.dragging = False
        self.drag_start = QPoint(0, 0)
        self.drag_offset = QPoint(0, 0)
        self.drag_distance = 0.0
        self.shake = 0

        # 跟随鼠标
        self.follow = False

        # 闲置计时
        self.idle_time = 0

        # 贴边吸附
        self.snap_edge = None       # None / "left" / "right" / "top" / "bottom"
        self.snap_anim = 1.0        # 0=隐藏 1=完全可见
        self.snap_target = 1.0      # 动画目标值
        self.snap_pos = 0           # 吸附时的次要坐标 (左右吸附记录Y, 上下吸附记录X)
        self.peek_size = 55         # 兜底探出像素 (实际由 _peek_amount() 动态计算)

    def _peek_amount(self):
        """
        贴边隐藏时露出的条带宽度: 只够显示"眼睛+耳朵"特效,
        猫身完全藏到屏幕外。特效用固定尺寸, 不随猫身缩放。
        """
        if self.snap_edge in ("left", "right"):
            return 60   # 竖条带: 一对眼睛并排 + 耳朵
        if self.snap_edge in ("top", "bottom"):
            return 72   # 横条带: 耳朵(26) + 眼睛(12) + 边距
        return 60

    def _setup_tray(self):
        """系统托盘图标"""
        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(QIcon(self._make_tray_icon()))
        self.tray.setToolTip("桌面小猫 - 双击图标显示")
        self.tray.show()

        menu = QMenu()
        menu.addAction("显示小猫", self.show_cat)
        menu.addAction("摸摸猫", self._pet)
        menu.addAction("玩耍", lambda: self._set_state(self.PLAY, 180))
        menu.addAction("睡觉/起床", self._toggle_sleep)
        menu.addAction("跟随鼠标", self._toggle_follow)
        menu.addAction("换颜色", self._change_color)
        menu.addAction("设置...", self._open_settings)
        # 开机启动 (勾选状态在弹出时刷新)
        self._tray_autostart_act = menu.addAction("开机启动")
        self._tray_autostart_act.setCheckable(True)
        self._tray_autostart_act.setChecked(self._autostart_on)
        self._tray_autostart_act.triggered.connect(self._toggle_autostart)
        menu.aboutToShow.connect(
            lambda: self._tray_autostart_act.setChecked(self._autostart_on))
        menu.addSeparator()
        menu.addAction("退出", self._quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)

    def _make_tray_icon(self):
        """生成托盘图标 pixmap"""
        pix = QPixmap(64, 64)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        # 耳朵
        p.setBrush(QBrush(QColor("#FFB347")))
        p.setPen(Qt.NoPen)
        ear_l = QPainterPath()
        ear_l.moveTo(14, 22)
        ear_l.lineTo(18, 4)
        ear_l.lineTo(28, 18)
        ear_l.closeSubpath()
        p.drawPath(ear_l)
        ear_r = QPainterPath()
        ear_r.moveTo(50, 22)
        ear_r.lineTo(46, 4)
        ear_r.lineTo(36, 18)
        ear_r.closeSubpath()
        p.drawPath(ear_r)
        # 头
        p.drawEllipse(QRectF(10, 16, 44, 44))
        # 眼睛
        p.setBrush(QBrush(QColor("#2C2C2C")))
        p.drawEllipse(QRectF(22, 30, 7, 10))
        p.drawEllipse(QRectF(35, 30, 7, 10))
        # 高光
        p.setBrush(QBrush(QColor(255, 255, 255, 220)))
        p.drawEllipse(QRectF(23, 31, 2.5, 3))
        p.drawEllipse(QRectF(36, 31, 2.5, 3))
        # 鼻子
        p.setBrush(QBrush(QColor("#FF6B9D")))
        nose = QPainterPath()
        nose.moveTo(29, 40)
        nose.lineTo(35, 40)
        nose.lineTo(32, 44)
        nose.closeSubpath()
        p.drawPath(nose)
        p.end()
        return pix

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_cat()

    def show_cat(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def _quit(self):
        # 注销全局快捷键
        try:
            self.hotkey_mgr.unregister()
        except Exception:
            pass
        # 停止摄像头线程
        if self.camera_thread is not None and self.camera_thread.isRunning():
            self.camera_thread.stop()
        self.preview.hide()
        self.tray.hide()
        QApplication.quit()

    # ---------- 状态管理 ----------

    def _toggle_autostart(self, checked):
        """右键菜单: 开启/取消开机启动 (写注册表 HKCU Run)"""
        ok = set_autostart(bool(checked))
        if ok:
            self._autostart_on = bool(checked)
            self._say("开机启动已开启~" if checked else "开机启动已取消", 120)
        else:
            # 失败则回滚菜单勾选状态
            self._autostart_on = is_autostart_enabled()
            self._say("设置开机启动失败!", 120)

    def _set_state(self, state, duration=0):
        """切换状态, duration>0 表示持续时间(帧)后自动回到IDLE"""
        if state == self.state and duration == 0:
            return
        self.prev_state = self.state
        self.state = state
        self.state_frame = 0
        self._state_duration = duration
        self.idle_time = 0

    def _say(self, text, duration=150):
        self.speech = text
        self.speech_left = duration

    def _spawn_particles(self, kind, count, x=None, y=None):
        px = x if x is not None else CX
        py = y if y is not None else CY - 10
        for _ in range(count):
            self.particles.append(Particle(
                px + random.uniform(-25, 25),
                py + random.uniform(-15, 5),
                kind
            ))

    def _pet(self):
        self._set_state(self.HAPPY, 120)
        self._spawn_particles("heart", 6)
        self._say(random.choice(SPEECHES["happy"]), 120)

    def _toggle_follow(self):
        self.follow = not self.follow
        if self.follow:
            self._say("来追我呀~")
        else:
            self._say("不追了~")

    def _toggle_chat(self):
        # 聊天输入功能暂时禁用 (chat_enabled 配置控制, 恢复设 True 即可)
        if not self.config.get("chat_enabled", False):
            if self.chat.isVisible():
                self.chat.hide()
            self._say("聊天功能暂停中~", 90)
            return
        _log(f"_toggle_chat 调用, chat.isVisible={self.chat.isVisible()}")
        try:
            if self.chat.isVisible():
                self.chat.hide()
                _log("_toggle_chat: 隐藏聊天框")
            else:
                self.chat.messages.clear()
                self.chat.show()
                _log("_toggle_chat: 显示聊天框")
        except Exception as e:
            _log(f"!!! _toggle_chat 异常: {e}\n{traceback.format_exc()}")

    def _toggle_sleep(self):
        if self.state == self.SLEEP:
            self._set_state(self.IDLE, 0)
            self._say("醒啦~")
        else:
            self._set_state(self.SLEEP, 0)
            self._say("晚安~")

    def _change_color(self):
        self.color_idx = (self.color_idx + 1) % len(COLORS)
        self.c = COLORS[self.color_idx]
        # 写入配置, 下次启动生效
        try:
            self.config["cat_color"] = self.color_idx
            save_config(self.config)
        except Exception as e:
            _log(f"保存颜色失败: {e}")
        self._say("我是" + self.c["name"] + "!", 120)
        self._spawn_particles("sparkle", 8)

    # ---------- 动画循环 ----------

    def _start_timer(self):
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(1000 // FPS)

    def _tick(self):
        try:
            self.frame += 1
            self.state_frame += 1

            # 自动状态回归
            if self._state_duration > 0 and self.state_frame >= self._state_duration:
                self._set_state(self.IDLE, 0)

            self._update_blink()
            self._update_eyes()
            self._update_bounce()
            self.tail_phase += self.tail_speed
            self._update_particles()
            self._update_speech()

            if self.follow:
                self._update_follow()

            # 闲置自动睡觉 (40秒)
            if self.state == self.IDLE:
                self.idle_time += 1
                if self.idle_time > 2400:
                    self._set_state(self.SLEEP, 0)
            else:
                self.idle_time = 0

            # 睡觉时产�� Z 粒子
            if self.state == self.SLEEP and self.frame % 50 == 0:
                self.particles.append(Particle(CX + 30, CY - 20, "z"))

            # 玩耍时产生星星粒子
            if self.state == self.PLAY and self.frame % 12 == 0:
                self.particles.append(Particle(
                    CX + random.uniform(-35, 35),
                    CY + random.uniform(-25, 25),
                    random.choice(["star", "sparkle"])
                ))

            if self.shake > 0:
                self.shake -= 1

            self._update_snap()
            self._check_snap_hover()

            self.update()
        except Exception as e:
            _log(f"!!! CatWindow._tick 异常 (frame={self.frame}): {e}\n{traceback.format_exc()}")

    def _update_blink(self):
        if self.state == self.SLEEP:
            return
        if self.blink_left > 0:
            self.blink_left -= 1
        else:
            self.blink_cd -= 1
            if self.blink_cd <= 0:
                self.blink_left = 8
                self.blink_cd = random.randint(120, 360)

    def _update_eyes(self):
        if self.state in (self.SLEEP, self.HAPPY):
            return
        mouse = self.mapFromGlobal(QCursor.pos())
        # 屏幕坐标 → 逻辑画布坐标 (除以缩放倍率)
        mx = mouse.x() / self.cat_scale
        my = mouse.y() / self.cat_scale
        dx = mx - CX
        dy = my - CY
        dist = max(1.0, math.sqrt(dx * dx + dy * dy))
        max_off = 4.0
        self.eye_tx = (dx / dist) * min(max_off, dist / 20)
        self.eye_ty = (dy / dist) * min(max_off, dist / 20)
        self.eye_x += (self.eye_tx - self.eye_x) * 0.15
        self.eye_y += (self.eye_ty - self.eye_y) * 0.15

    def _update_bounce(self):
        if self.state == self.HAPPY:
            self.bounce = abs(math.sin(self.frame * 0.18)) * 10
            self.tail_speed = 0.12
        elif self.state == self.PLAY:
            self.bounce = abs(math.sin(self.frame * 0.22)) * 16
            self.tail_speed = 0.15
        elif self.state == self.SLEEP:
            self.bounce = math.sin(self.frame * 0.025) * 2
            self.tail_speed = 0.01
        elif self.state == self.DRAG:
            self.bounce = math.sin(self.frame * 0.4) * 3
            self.tail_speed = 0.08
        else:
            self.bounce = math.sin(self.frame * 0.04) * 1.5
            self.tail_speed = 0.04

    def _update_particles(self):
        self.particles = [p for p in self.particles if p.alive]
        for p in self.particles:
            p.update()

    def _update_speech(self):
        if self.speech_left > 0:
            self.speech_left -= 1
        else:
            self.speech = ""
        if not self.speech:
            self.speech_cd -= 1
            if self.speech_cd <= 0:
                if self.state in SPEECHES:
                    self._say(random.choice(SPEECHES[self.state]), 120)
                self.speech_cd = random.randint(500, 1200)

    def _update_follow(self):
        mouse = QCursor.pos()
        win_w, win_h = self.width(), self.height()
        target_x = mouse.x() - win_w // 2
        target_y = mouse.y() - win_h // 2
        cx, cy = self.x(), self.y()
        dx = target_x - cx
        dy = target_y - cy
        dist = math.sqrt(dx * dx + dy * dy)
        if dist > 5:
            speed = min(dist * 0.06, 12)
            new_x = int(cx + dx / dist * speed)
            new_y = int(cy + dy / dist * speed)
            screen = QApplication.primaryScreen().geometry()
            new_x = max(-50, min(screen.width() - win_w + 50, new_x))
            new_y = max(-50, min(screen.height() - win_h + 50, new_y))
            self.move(new_x, new_y)

    # ======================== 贴边吸附 ========================

    def _check_snap(self):
        """拖拽释放时检测是否应该吸附到屏幕边缘"""
        screen = QApplication.primaryScreen().geometry()
        x, y = self.x(), self.y()
        win_w, win_h = self.width(), self.height()
        threshold = 80

        snap_to = None
        if x < threshold:
            snap_to = "left"
            self.snap_pos = y
        elif x + win_w > screen.width() - threshold:
            snap_to = "right"
            self.snap_pos = y
        elif y < threshold:
            snap_to = "top"
            self.snap_pos = x
        elif y + win_h > screen.height() - threshold:
            snap_to = "bottom"
            self.snap_pos = x

        if snap_to:
            self.snap_edge = snap_to
            self.snap_anim = 1.0
            self.snap_target = 0.0  # 开始向边缘缩入
            self._say("嗖~", 80)
        else:
            self.snap_edge = None
            self.snap_anim = 1.0
            self.snap_target = 1.0

    def _update_snap(self):
        """贴边吸附动画更新"""
        if self.snap_edge is None:
            return

        # 平滑动画
        speed = 0.12
        self.snap_anim += (self.snap_target - self.snap_anim) * speed

        screen = QApplication.primaryScreen().geometry()
        win_w, win_h = self.width(), self.height()

        if self.snap_edge == "left":
            full_x = 0
            hidden_x = self._peek_amount() - win_w
            new_x = hidden_x + (full_x - hidden_x) * self.snap_anim
            self.move(int(new_x), self.snap_pos)

        elif self.snap_edge == "right":
            full_x = screen.width() - win_w
            hidden_x = screen.width() - self._peek_amount()
            new_x = hidden_x + (full_x - hidden_x) * self.snap_anim
            self.move(int(new_x), self.snap_pos)

        elif self.snap_edge == "top":
            full_y = 0
            hidden_y = self._peek_amount() - win_h
            new_y = hidden_y + (full_y - hidden_y) * self.snap_anim
            self.move(self.snap_pos, int(new_y))

        elif self.snap_edge == "bottom":
            full_y = screen.height() - win_h
            hidden_y = screen.height() - self._peek_amount()
            new_y = hidden_y + (full_y - hidden_y) * self.snap_anim
            self.move(self.snap_pos, int(new_y))

    def _check_snap_hover(self):
        """检测鼠标是否悬停到吸附的猫上，悬停时弹出"""
        if self.snap_edge is None:
            return
        if self.dragging:
            return

        mouse = QCursor.pos()
        # 扩展检测区域，方便触发
        rect = self.geometry().adjusted(-15, -15, 15, 15)
        if rect.contains(mouse):
            self.snap_target = 1.0  # 弹出
            if self.snap_anim > 0.9 and random.random() < 0.005:
                self._say("喵~", 60)
        else:
            self.snap_target = 0.0  # 缩入

    # ======================== 绘制 ========================

    def paintEvent(self, event):
        try:
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            p.setRenderHint(QPainter.SmoothPixmapTransform)

            sx = sy = 0
            if self.shake > 0:
                sx = random.uniform(-3, 3)
                sy = random.uniform(-3, 3)
            p.save()
            p.translate(sx, sy)
            # 尺寸缩放变换: 所有绘制仍用逻辑坐标 (W×H 画布)
            p.scale(self.cat_scale, self.cat_scale)

            # 贴边完全缩入后: 不画猫身, 只画"猫眼+耳朵"贴边特效
            edge_face = self.snap_edge is not None and self.snap_anim < 0.3
            if not edge_face:
                self._draw_shadow(p)
                self._draw_tail(p)
                self._draw_body(p)
                self._draw_head(p)

                for prt in self.particles:
                    prt.draw(p)

                if self.speech:
                    self._draw_speech(p)

            p.restore()

            if edge_face:
                # 眨巴的猫眼 + 微摆的耳朵 (像素坐标绘制)
                self._draw_edge_face(p)
            elif self.snap_edge and self.snap_anim < 0.9:
                # 缩入过程中: 贴边视觉指示器
                self._draw_snap_indicator(p)

            if p.isActive():
                p.end()
        except Exception as e:
            _log(f"!!! CatWindow.paintEvent 异常: {e}\n{traceback.format_exc()}")

    def _draw_shadow(self, p):
        """地面阴影"""
        p.setBrush(QBrush(QColor(0, 0, 0, 40)))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(CX, BODY_CY + BODY_RY + 25), 42, 7)

    def _draw_tail(self, p):
        """尾巴 - 摆动曲线"""
        wag = math.sin(self.tail_phase) * (8 if self.state != self.SLEEP else 2)
        wag2 = math.sin(self.tail_phase + 1.5) * (10 if self.state != self.SLEEP else 3)

        start_x = BODY_CX + BODY_RX - 5
        start_y = BODY_CY + 5
        path = QPainterPath()
        path.moveTo(start_x, start_y)
        path.cubicTo(
            start_x + 25, start_y + 5 + wag,
            start_x + 38, start_y - 30 + wag2,
            start_x + 28, start_y - 72 + wag2
        )
        pen = QPen(QColor(self.c["body"]), 11, Qt.SolidLine, Qt.RoundCap)
        p.setPen(pen)
        p.drawPath(path)

        # 尾巴尖端深色圆
        p.setBrush(QBrush(QColor(self.c["dark"])))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(start_x + 28, start_y - 72 + wag2), 6, 6)

    def _draw_body(self, p):
        """身体 + 肚子 + 前爪"""
        breath = 1.0 + math.sin(self.frame * 0.04) * 0.025
        by = BODY_CY - self.bounce

        # 身体
        grad = QRadialGradient(BODY_CX - 8, by - 8, BODY_RX * 2)
        grad.setColorAt(0, QColor(self.c["body"]))
        grad.setColorAt(1, QColor(self.c["dark"]))
        p.setBrush(QBrush(grad))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(BODY_CX, by), BODY_RX * breath, BODY_RY * breath)

        # 肚子
        p.setBrush(QBrush(QColor(self.c["belly"])))
        p.drawEllipse(QPointF(BODY_CX, by + 5), BODY_RX * 0.6, BODY_RY * 0.65)

        # 前爪
        paw_y = by + BODY_RY - 3
        p.setBrush(QBrush(QColor(self.c["body"])))
        p.drawEllipse(QPointF(BODY_CX - 16, paw_y), 10, 7)
        p.drawEllipse(QPointF(BODY_CX + 16, paw_y), 10, 7)
        # 爪垫
        p.setBrush(QBrush(QColor(self.c["ear"])))
        p.drawEllipse(QPointF(BODY_CX - 16, paw_y + 1), 4, 3)
        p.drawEllipse(QPointF(BODY_CX + 16, paw_y + 1), 4, 3)

    def _draw_head(self, p):
        """头部 + 耳朵 + 五官"""
        hy = CY - self.bounce

        self._draw_ears(p, hy)

        # 头部
        grad = QRadialGradient(CX - 10, hy - 10, HEAD_R * 2)
        grad.setColorAt(0, QColor(self.c["body"]))
        grad.setColorAt(1, QColor(self.c["dark"]))
        p.setBrush(QBrush(grad))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(CX, hy), HEAD_R, HEAD_R)

        self._draw_eyes(p, hy)
        self._draw_face(p, hy)
        self._draw_whiskers(p, hy)

        # 腮红 (开心/玩耍时)
        if self.state in (self.HAPPY, self.PLAY):
            blush = QColor(255, 150, 160, 120)
            p.setBrush(QBrush(blush))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(CX - 28, hy + 8), 8, 5)
            p.drawEllipse(QPointF(CX + 28, hy + 8), 8, 5)

    def _draw_ears(self, p, hy):
        # 左耳外
        path = QPainterPath()
        path.moveTo(CX - 40, hy - 30)
        path.lineTo(CX - 48, hy - 72)
        path.lineTo(CX - 14, hy - 42)
        path.closeSubpath()
        p.setBrush(QBrush(QColor(self.c["body"])))
        p.setPen(Qt.NoPen)
        p.drawPath(path)
        # 左耳内
        inner = QPainterPath()
        inner.moveTo(CX - 38, hy - 35)
        inner.lineTo(CX - 44, hy - 64)
        inner.lineTo(CX - 22, hy - 44)
        inner.closeSubpath()
        p.setBrush(QBrush(QColor(self.c["ear"])))
        p.drawPath(inner)

        # 右耳外
        path = QPainterPath()
        path.moveTo(CX + 40, hy - 30)
        path.lineTo(CX + 48, hy - 72)
        path.lineTo(CX + 14, hy - 42)
        path.closeSubpath()
        p.setBrush(QBrush(QColor(self.c["body"])))
        p.drawPath(path)
        # 右耳内
        inner = QPainterPath()
        inner.moveTo(CX + 38, hy - 35)
        inner.lineTo(CX + 44, hy - 64)
        inner.lineTo(CX + 22, hy - 44)
        inner.closeSubpath()
        p.setBrush(QBrush(QColor(self.c["ear"])))
        p.drawPath(inner)

    def _draw_eyes(self, p, hy):
        """根据状态绘制不同眼睛"""
        eye_y = hy - 2
        lex = CX - 15
        rex = CX + 15

        if self.state == self.HAPPY:
            # ^ ^ 开心眯眼
            pen = QPen(QColor("#2C2C2C"), 2.5)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            for ex in (lex, rex):
                path = QPainterPath()
                path.moveTo(ex - 7, eye_y + 3)
                path.quadTo(ex, eye_y - 5, ex + 7, eye_y + 3)
                p.drawPath(path)

        elif self.state == self.SLEEP:
            # ︶ ︶ 闭眼
            pen = QPen(QColor("#2C2C2C"), 2.5)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            for ex in (lex, rex):
                path = QPainterPath()
                path.moveTo(ex - 7, eye_y - 3)
                path.quadTo(ex, eye_y + 5, ex + 7, eye_y - 3)
                p.drawPath(path)

        elif self.state == self.DRAG:
            # O O 惊讶大眼
            p.setBrush(QBrush(QColor("#2C2C2C")))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(lex, eye_y), 7, 9)
            p.drawEllipse(QPointF(rex, eye_y), 7, 9)
            p.setBrush(QBrush(QColor(255, 255, 255, 220)))
            p.drawEllipse(QPointF(lex - 2, eye_y - 3), 2, 3)
            p.drawEllipse(QPointF(rex - 2, eye_y - 3), 2, 3)

        elif self.state == self.PLAY:
            # 星星眼
            p.setBrush(QBrush(QColor("#2C2C2C")))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(lex, eye_y), 8, 10)
            p.drawEllipse(QPointF(rex, eye_y), 8, 10)
            p.setBrush(QBrush(QColor(255, 220, 80)))
            for ex in (lex, rex):
                sp = QPainterPath()
                s = 3.5
                for i in range(4):
                    a1 = math.radians(i * 90 - 90)
                    a2 = math.radians(i * 90 - 45)
                    x1, y1 = math.cos(a1) * s, math.sin(a1) * s
                    x2, y2 = math.cos(a2) * s * 0.4, math.sin(a2) * s * 0.4
                    if i == 0:
                        sp.moveTo(ex + x1, eye_y + y1)
                    else:
                        sp.lineTo(ex + x1, eye_y + y1)
                    sp.lineTo(ex + x2, eye_y + y2)
                sp.closeSubpath()
                p.drawPath(sp)

        else:
            # IDLE: 圆眼跟随鼠标 + 眨眼
            blinking = self.blink_left > 0
            if blinking:
                pen = QPen(QColor("#2C2C2C"), 2.5)
                p.setPen(pen)
                p.setBrush(Qt.NoBrush)
                for ex in (lex, rex):
                    path = QPainterPath()
                    path.moveTo(ex - 7, eye_y)
                    path.lineTo(ex + 7, eye_y)
                    p.drawPath(path)
            else:
                p.setBrush(QBrush(QColor("#2C2C2C")))
                p.setPen(Qt.NoPen)
                p.drawEllipse(QPointF(lex + self.eye_x, eye_y + self.eye_y), 7, 9)
                p.drawEllipse(QPointF(rex + self.eye_x, eye_y + self.eye_y), 7, 9)
                # 高光
                p.setBrush(QBrush(QColor(255, 255, 255, 230)))
                p.drawEllipse(QPointF(lex + self.eye_x - 2, eye_y + self.eye_y - 3), 2.5, 3.5)
                p.drawEllipse(QPointF(rex + self.eye_x - 2, eye_y + self.eye_y - 3), 2.5, 3.5)

    def _draw_face(self, p, hy):
        """鼻子和嘴巴"""
        nose_y = hy + 12

        # 鼻子
        p.setBrush(QBrush(QColor("#FF6B9D")))
        p.setPen(Qt.NoPen)
        nose = QPainterPath()
        nose.moveTo(CX - 4, nose_y)
        nose.lineTo(CX + 4, nose_y)
        nose.lineTo(CX, nose_y + 5)
        nose.closeSubpath()
        p.drawPath(nose)

        mouth_y = nose_y + 5
        pen = QPen(QColor("#5C3D2E"), 1.8)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)

        if self.state == self.HAPPY:
            # 大笑 + 舌头
            path = QPainterPath()
            path.moveTo(CX, mouth_y)
            path.quadTo(CX - 4, mouth_y + 8, CX - 10, mouth_y + 5)
            path.moveTo(CX, mouth_y)
            path.quadTo(CX + 4, mouth_y + 8, CX + 10, mouth_y + 5)
            p.drawPath(path)
            p.setBrush(QBrush(QColor("#FF9999")))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(CX, mouth_y + 6), 4, 3)

        elif self.state == self.SLEEP:
            # 小o嘴 (呼吸)
            breath = 1.0 + math.sin(self.frame * 0.04) * 0.3
            p.setBrush(QBrush(QColor("#5C3D2E")))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(CX, mouth_y + 3), 3 * breath, 4 * breath)

        elif self.state == self.PLAY:
            # 开心张嘴
            path = QPainterPath()
            path.moveTo(CX, mouth_y)
            path.quadTo(CX - 5, mouth_y + 10, CX - 12, mouth_y + 6)
            path.moveTo(CX, mouth_y)
            path.quadTo(CX + 5, mouth_y + 10, CX + 12, mouth_y + 6)
            p.drawPath(path)

        elif self.state == self.DRAG:
            # O嘴
            p.setBrush(QBrush(QColor("#5C3D2E")))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(CX, mouth_y + 4), 4, 5)

        else:
            # 正常猫嘴 :3
            path = QPainterPath()
            path.moveTo(CX, mouth_y)
            path.quadTo(CX - 3, mouth_y + 5, CX - 7, mouth_y + 3)
            path.moveTo(CX, mouth_y)
            path.quadTo(CX + 3, mouth_y + 5, CX + 7, mouth_y + 3)
            p.drawPath(path)

    def _draw_whiskers(self, p, hy):
        """胡须"""
        pen = QPen(QColor(255, 255, 255, 180), 1.2)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)

        wy = hy + 14
        for i, (dy, length) in enumerate([(0, 28), (5, 30), (10, 26)]):
            # 左
            path = QPainterPath()
            path.moveTo(CX - 28, wy + dy)
            path.lineTo(CX - 28 - length, wy + dy - 3 + i * 2)
            p.drawPath(path)
            # 右
            path = QPainterPath()
            path.moveTo(CX + 28, wy + dy)
            path.lineTo(CX + 28 + length, wy + dy - 3 + i * 2)
            p.drawPath(path)

    def _draw_speech(self, p):
        """对话气泡"""
        font = QFont("Microsoft YaHei", 9, QFont.Medium)
        p.setFont(font)
        fm = p.fontMetrics()
        text_w = fm.horizontalAdvance(self.speech)
        text_h = fm.height()

        bw = text_w + 24
        bh = text_h + 12
        bx = CX - bw / 2
        by = CY - HEAD_R - bh - 25

        bx = max(5, min(W - bw - 5, bx))
        by = max(5, by)

        # 气泡背景
        p.setBrush(QBrush(QColor(255, 255, 255, 235)))
        p.setPen(QPen(QColor(200, 200, 200, 150), 1))
        p.drawRoundedRect(QRectF(bx, by, bw, bh), 10, 10)

        # 气泡尾巴
        tail_x = max(bx + 10, min(bx + bw - 10, CX))
        tail_path = QPainterPath()
        tail_path.moveTo(tail_x - 6, by + bh)
        tail_path.lineTo(tail_x + 6, by + bh)
        tail_path.lineTo(tail_x, by + bh + 8)
        tail_path.closeSubpath()
        p.setBrush(QBrush(QColor(255, 255, 255, 235)))
        p.drawPath(tail_path)

        # 文字
        p.setPen(QPen(QColor(80, 80, 80)))
        p.drawText(QRectF(bx, by, bw, bh), Qt.AlignCenter, self.speech)

    def _draw_edge_face(self, p):
        """
        贴边隐藏特效: 猫身完全藏到屏幕外, 只露一双猫眼贴边眨巴
        + 一对耳朵左右微摆。
        """
        t = time.time()
        s = 1.0  # 特效固定尺寸, 不随猫身缩放 (缩放后眼睛太小看不清)
        win_w, win_h = self.width(), self.height()
        peek = self._peek_amount()

        # 渐入: anim 从 0.3 → 0, alpha 从 0 → 255
        fade = (0.3 - self.snap_anim) / 0.3
        alpha = int(max(0.0, min(1.0, fade)) * 255)

        # 眨眼: 周期 3.6s, 闭眼 0.18s (三角波: 睁→闭→睁)
        ph = t % 3.6
        blink = 0.0
        if ph < 0.18:
            blink = 1.0 - abs(ph - 0.09) / 0.09

        # 耳朵左右微摆 (两耳相位错开, 更生动)
        ang_l = math.sin(t * 2.3) * 8
        ang_r = math.sin(t * 2.3 + 2.4) * 8

        body_c = QColor(self.c["body"]); body_c.setAlpha(alpha)
        ear_c = QColor(self.c["ear"]); ear_c.setAlpha(alpha)
        line_c = QColor(44, 44, 44, alpha)
        white_c = QColor(255, 252, 245, alpha)

        def draw_ear(cx_, cy_, ang, flip=1.0):
            """三角耳朵, 绕底部中心摆动; flip=-1 表示倒挂朝下"""
            bw, eh = 8.5 * s, 24 * s
            p.save()
            p.translate(cx_, cy_)
            p.rotate(ang)
            path = QPainterPath()
            path.moveTo(-bw, 0)
            path.lineTo(0, -eh * flip)
            path.lineTo(bw, 0)
            path.closeSubpath()
            p.setBrush(body_c)
            p.setPen(Qt.NoPen)
            p.drawPath(path)
            # 内耳
            path = QPainterPath()
            path.moveTo(-bw * 0.55, 0)
            path.lineTo(0, -eh * 0.6 * flip)
            path.lineTo(bw * 0.55, 0)
            path.closeSubpath()
            p.setBrush(ear_c)
            p.drawPath(path)
            p.restore()

        def draw_eye(cx_, cy_):
            """猫眼: 白眼底 + 竖瞳孔, 眨眼时收成弧线"""
            if blink > 0.75:
                pen = QPen(line_c, 2.2 * s)
                p.setPen(pen)
                p.setBrush(Qt.NoBrush)
                path = QPainterPath()
                path.moveTo(cx_ - 7 * s, cy_)
                path.quadTo(cx_, cy_ + 4 * s, cx_ + 7 * s, cy_)
                p.drawPath(path)
            else:
                ry = max(1.5, 10 * s * (1.0 - 0.92 * blink))
                p.setPen(Qt.NoPen)
                p.setBrush(QBrush(white_c))
                p.drawEllipse(QPointF(cx_, cy_), 8 * s, ry)
                p.setBrush(QBrush(line_c))
                p.drawEllipse(QPointF(cx_, cy_), 2.8 * s, max(1.0, ry * 0.72))

        gap = 13 * s      # 双眼半间距
        ear_dy = 26 * s   # 耳朵底到眼睛中心的距离

        if self.snap_edge in ("left", "right"):
            cy = CY * s
            if self.snap_edge == "left":
                cx0 = (win_w - peek) + peek * 0.5   # 条带中心
            else:
                cx0 = peek * 0.5
            draw_ear(cx0 - gap, cy - ear_dy, ang_l)
            draw_ear(cx0 + gap, cy - ear_dy, ang_r)
            draw_eye(cx0 - gap, cy)
            draw_eye(cx0 + gap, cy)
        else:
            cx = CX * s
            if self.snap_edge == "bottom":
                # 从底边向上探头: 耳朵在上, 眼睛贴底边
                eye_y = peek - 12 * s
                draw_ear(cx - gap, eye_y - ear_dy, ang_l)
                draw_ear(cx + gap, eye_y - ear_dy, ang_r)
                draw_eye(cx - gap, eye_y)
                draw_eye(cx + gap, eye_y)
            else:
                # 顶边倒挂: 眼睛贴顶边, 耳朵在下方
                top_edge = win_h - peek
                eye_y = top_edge + 12 * s
                draw_ear(cx - gap, eye_y + ear_dy, ang_l, flip=-1)
                draw_ear(cx + gap, eye_y + ear_dy, ang_r, flip=-1)
                draw_eye(cx - gap, eye_y)
                draw_eye(cx + gap, eye_y)

    def _draw_snap_indicator(self, p):
        """贴边隐藏时在可见边缘绘制猫色提示条"""
        alpha = int((1.0 - self.snap_anim) * 220)
        if alpha <= 0:
            return

        # 用实际窗口像素尺寸 (逻辑 W/H × cat_scale), 否则缩放后画到窗口外
        win_w, win_h = self.width(), self.height()

        color = QColor(self.c["body"])
        color.setAlpha(alpha)
        gradient_color = QColor(self.c["dark"])
        gradient_color.setAlpha(0)

        if self.snap_edge == "left":
            # 右侧可见，在右边缘画提示条
            bar_x = win_w - 8
            grad = QRadialGradient(bar_x, win_h // 2, 40)
            grad.setColorAt(0, color)
            grad.setColorAt(1, gradient_color)
            p.setBrush(QBrush(grad))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(QRectF(bar_x - 5, win_h // 2 - 35, 10, 70), 5, 5)

        elif self.snap_edge == "right":
            # 左侧可见，在左边缘画提示条
            grad = QRadialGradient(8, win_h // 2, 40)
            grad.setColorAt(0, color)
            grad.setColorAt(1, gradient_color)
            p.setBrush(QBrush(grad))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(QRectF(-5, win_h // 2 - 35, 10, 70), 5, 5)

        elif self.snap_edge == "top":
            # 下边缘可见
            bar_y = win_h - 8
            grad = QRadialGradient(win_w // 2, bar_y, 40)
            grad.setColorAt(0, color)
            grad.setColorAt(1, gradient_color)
            p.setBrush(QBrush(grad))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(QRectF(win_w // 2 - 35, bar_y - 5, 70, 10), 5, 5)

        elif self.snap_edge == "bottom":
            # 上边缘可见
            grad = QRadialGradient(win_w // 2, 8, 40)
            grad.setColorAt(0, color)
            grad.setColorAt(1, gradient_color)
            p.setBrush(QBrush(grad))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(QRectF(win_w // 2 - 35, -5, 70, 10), 5, 5)

    # ======================== 鼠标交互 ========================

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.drag_start = QPoint(event.globalPos())
            self.drag_offset = QPoint(event.pos())
            self.drag_distance = 0.0
            # 启动长按计时器: 500ms 内未拖动未释放 → 长按显示摄像头
            if not self.longpress_active:
                self.press_timer.start(500)
            # 如果处于吸附状态，拖拽时先弹出再拖动
            if self.snap_edge:
                self.snap_target = 1.0
                self.snap_anim = 1.0
                self.snap_edge = None
            if self.state != self.SLEEP:
                self._set_state(self.DRAG, 0)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.press_timer.stop()

            # 长按预览状态 → 松开隐藏预览, 不触发点击逻辑
            if self.longpress_active:
                self._hide_preview()
                self.dragging = False
                if self.state == self.DRAG:
                    self._set_state(self.IDLE, 0)
                return

            was_dragging = self.dragging
            self.dragging = False
            if self.state == self.DRAG:
                self._set_state(self.IDLE, 0)
            # 短距离释放 = 点击
            if was_dragging and self.drag_distance < 8:
                # 判断点击位置：头部附近 → 聊天框，身体 → 摸猫
                # 屏幕坐标 → 逻辑画布坐标 (除以缩放倍率)
                click_x = event.pos().x() / self.cat_scale
                click_y = event.pos().y() / self.cat_scale
                dx = click_x - CX
                dy = click_y - (CY - self.bounce)
                dist = math.sqrt(dx * dx + dy * dy)
                _log(f"点击检测: pos=({click_x},{click_y}) dist_to_head={dist:.1f} head_r*1.15={HEAD_R * 1.15}")
                if dist < HEAD_R * 1.15:
                    _log("→ 判定为猫头点击, 调用 _toggle_chat")
                    self._toggle_chat()
                else:
                    _log("→ 判定为身体点击, 调用 _pet")
                    self._pet()
            elif was_dragging and self.drag_distance >= 8:
                # 拖拽释放后检查贴边吸附
                self._check_snap()

    def mouseMoveEvent(self, event):
        if self.dragging:
            dx = event.globalPos().x() - self.drag_start.x()
            dy = event.globalPos().y() - self.drag_start.y()
            self.drag_distance = math.sqrt(dx * dx + dy * dy)
            # 拖动超过阈值 → 取消长按判定 (是拖拽不是长按)
            if self.drag_distance >= 8 and not self.longpress_active:
                self.press_timer.stop()
            if not self.longpress_active:
                new_pos = QPoint(event.globalPos() - self.drag_offset)
                self.move(new_pos)
                self.shake = 3
                # 预览显示中则跟随小猫移动
                if self.preview.isVisible():
                    self._position_preview()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._toggle_sleep()

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: white;
                border: 1px solid #ccc;
                border-radius: 8px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 30px 6px 20px;
                border-radius: 4px;
                font-size: 13px;
            }
            QMenu::item:selected {
                background: #FFE0B0;
            }
            QMenu::separator {
                height: 1px;
                background: #e0e0e0;
                margin: 4px 8px;
            }
        """)

        state_names = {
            "idle": "闲逛中", "happy": "开心",
            "sleep": "睡觉中", "play": "玩耍中", "drag": "被抓住"
        }
        header = menu.addAction(self.c["name"] + " (" + state_names.get(self.state, "") + ")")
        header.setEnabled(False)
        menu.addSeparator()
        menu.addAction("摸摸猫", self._pet)
        menu.addAction("玩耍", lambda: self._set_state(self.PLAY, 180))
        menu.addAction("睡觉/起床", self._toggle_sleep)
        menu.addAction("换颜色", self._change_color)
        follow_text = "取消跟随" if self.follow else "跟随鼠标"
        menu.addAction(follow_text, self._toggle_follow)
        cam_text = "隐藏摄像头预览" if self.preview.isVisible() else "摄像头预览 (或长按小猫)"
        menu.addAction(cam_text, self._toggle_preview)
        menu.addSeparator()
        model_text = "YOLOv26" if self.config.get("model") == "yolo" else "HOG+Haar"
        cfg_header = menu.addAction(
            f"检测: {model_text} | 触发: ≥{self.config.get('trigger_count')}人/{self.config.get('sustain_sec')}秒")
        cfg_header.setEnabled(False)
        target_name = self.config.get("target_exe") or self.config.get("target_title") or "未设置"
        hk_text = self.config.get("hotkey") if self.config.get("hotkey_enabled") else "已关闭"
        target_header = menu.addAction(f"目标程序: {target_name} | 快捷键: {hk_text}")
        target_header.setEnabled(False)
        menu.addAction("切换到目标程序", lambda: self._do_switch_target("切!"))
        menu.addAction("放大 (+20%)", lambda: self._change_cat_size(0.2))
        menu.addAction("缩小 (-20%)", lambda: self._change_cat_size(-0.2))
        menu.addAction("设置...", self._open_settings)
        menu.addSeparator()
        # 开机启动 (带勾选状态, 点击切换)
        autostart_act = menu.addAction("开机启动")
        autostart_act.setCheckable(True)
        autostart_act.setChecked(self._autostart_on)
        autostart_act.triggered.connect(self._toggle_autostart)
        menu.addSeparator()
        menu.addAction("退出", self._quit)
        menu.exec_(event.globalPos())

    def _toggle_preview(self):
        """手动切换摄像头预览显示状态"""
        if self.preview.isVisible():
            self.preview.hide()
            self.longpress_active = False
        else:
            self.longpress_active = False
            self._show_preview()

    # ======================== 窗口事件 ========================

    def closeEvent(self, event):
        event.ignore()
        self.hide()
        self.tray.showMessage(
            "桌面小猫",
            "小猫藏在系统托盘里啦~ 双击图标重新显示",
            QSystemTrayIcon.Information, 2000
        )


# ======================== 入口 ========================
def _preload_yolo():
    """
    在主线程预加载 torch/ultralytics。
    Windows 上 torch 的 DLL (c10.dll 等) 必须在主线程首次加载,
    否则在工作线程内 import 会报 WinError 1114 动态链接库初始化失败。
    """
    try:
        import torch  # noqa: F401
        import ultralytics  # noqa: F401
        _log("torch/ultralytics 主线程预加载成功")
        return True
    except Exception as e:
        _log(f"torch/ultralytics 预加载失败 (YOLO 将不可用): {e}")
        return False


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    cfg = load_config()
    if cfg.get("model") == "yolo":
        _preload_yolo()
    cat = CatWindow()
    cat.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
