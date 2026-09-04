"""Read-only native window tracking. Coordinates exposed to Qt are logical pixels."""
import ctypes
from ctypes import wintypes as w
from dataclasses import dataclass
import os

from PyQt5.QtCore import QPoint, QRect
from PyQt5.QtWidgets import QApplication


@dataclass
class Target:
    hwnd: int
    pid: int
    title: str
    kind: str
    rect: QRect
    visible: bool = True


class NativeWindows:
    def __init__(self):
        self.api = ctypes.WinDLL('user32', use_last_error=True)
        self.dwm = ctypes.WinDLL('dwmapi')
        self.callback = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
        signatures = {
            'IsWindow': ([w.HWND], w.BOOL),
            'IsWindowVisible': ([w.HWND], w.BOOL),
            'IsIconic': ([w.HWND], w.BOOL),
            'GetWindowRect': ([w.HWND, ctypes.POINTER(w.RECT)], w.BOOL),
            'GetWindowThreadProcessId': ([w.HWND, ctypes.POINTER(w.DWORD)], w.DWORD),
            'GetWindowTextW': ([w.HWND, w.LPWSTR, ctypes.c_int], ctypes.c_int),
            'GetClassNameW': ([w.HWND, w.LPWSTR, ctypes.c_int], ctypes.c_int),
            'GetForegroundWindow': ([], w.HWND),
            'GetAncestor': ([w.HWND, w.UINT], w.HWND),
            'GetWindowLongW': ([w.HWND, ctypes.c_int], w.LONG),
            'EnumWindows': ([self.callback, w.LPARAM], w.BOOL),
            'MonitorFromWindow': ([w.HWND, w.DWORD], w.HMONITOR),
            'GetMonitorInfoW': ([w.HMONITOR, ctypes.c_void_p], w.BOOL),
            'GetAsyncKeyState': ([ctypes.c_int], ctypes.c_short),
        }
        for name, (args, result) in signatures.items():
            fn = getattr(self.api, name)
            fn.argtypes, fn.restype = args, result
        self.dwm.DwmGetWindowAttribute.argtypes = [w.HWND, w.DWORD, ctypes.c_void_p, w.DWORD]
        self.dwm.DwmGetWindowAttribute.restype = ctypes.c_long

    def pid(self, hwnd):
        pid = w.DWORD()
        self.api.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return pid.value

    def logical_rect(self, hwnd, rect):
        class MonitorInfo(ctypes.Structure):
            _fields_ = [('size', w.DWORD), ('monitor', w.RECT),
                        ('work', w.RECT), ('flags', w.DWORD), ('device', w.WCHAR * 32)]
        info = MonitorInfo()
        info.size = ctypes.sizeof(info)
        monitor = self.api.MonitorFromWindow(hwnd, 2)
        if self.api.GetMonitorInfoW(monitor, ctypes.byref(info)):
            for screen in QApplication.screens():
                if screen.name().lower() == info.device.lower():
                    scale = screen.devicePixelRatio()
                    origin = screen.geometry().topLeft()
                    return QRect(origin.x() + round((rect.left - info.monitor.left) / scale),
                                 origin.y() + round((rect.top - info.monitor.top) / scale),
                                 round((rect.right - rect.left) / scale),
                                 round((rect.bottom - rect.top) / scale))
        return QRect(rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)

    def get(self, hwnd):
        if not hwnd or not self.api.IsWindow(hwnd):
            return None
        pid = self.pid(hwnd)
        if not pid or pid == os.getpid():
            return None
        title, kind = ctypes.create_unicode_buffer(1024), ctypes.create_unicode_buffer(256)
        self.api.GetWindowTextW(hwnd, title, len(title))
        self.api.GetClassNameW(hwnd, kind, len(kind))
        if (not title.value or kind.value in ('Progman', 'WorkerW', 'Shell_TrayWnd',
                                              'Shell_SecondaryTrayWnd')
                or self.api.GetWindowLongW(hwnd, -20) & 0x80):  # WS_EX_TOOLWINDOW
            return None
        rect = w.RECT()
        if not self.api.GetWindowRect(hwnd, ctypes.byref(rect)):
            return None
        self.dwm.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(rect), ctypes.sizeof(rect))
        cloaked = w.DWORD()
        self.dwm.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
        visible = bool(self.api.IsWindowVisible(hwnd) and not self.api.IsIconic(hwnd)
                       and not cloaked.value)
        return Target(int(hwnd), pid, title.value, kind.value, self.logical_rect(hwnd, rect), visible)

    def all(self):
        targets = []
        @self.callback
        def collect(hwnd, _):
            try:
                target = self.get(hwnd)
                if target and target.visible and not target.rect.isEmpty():
                    targets.append(target)
            except Exception:
                pass  # Exceptions must never escape a ctypes callback.
            return True
        self.api.EnumWindows(collect, 0)
        return targets  # Z-order, not title-deduplicated.

    def active(self, target):
        foreground = self.api.GetForegroundWindow()
        return bool(foreground and (self.pid(foreground) == os.getpid()
                    or self.api.GetAncestor(foreground, 3) == target.hwnd))

    def escape_pressed(self):
        return bool(self.api.GetAsyncKeyState(0x1B) & 0x8000)


ANCHOR_NAMES = {
    'top-left': '左上角', 'top': '上边缘', 'top-right': '右上角',
    'left': '左边缘', 'right': '右边缘',
    'bottom-left': '左下角', 'bottom': '下边缘', 'bottom-right': '右下角',
}


def anchor_point(rect, anchor):
    x = rect.left() if anchor.endswith('left') or anchor == 'left' else (
        rect.right() + 1 if anchor.endswith('right') or anchor == 'right' else rect.center().x())
    y = rect.top() if anchor.startswith('top') or anchor == 'top' else (
        rect.bottom() + 1 if anchor.startswith('bottom') or anchor == 'bottom' else rect.center().y())
    return QPoint(x, y)


def anchor_placements(anchor):
    """Only positions across the frame or inside it; fully outside is excluded."""
    if '-' in anchor:
        xs = (0, 1) if anchor.endswith('left') else (-1, 0)
        ys = (0, 1) if anchor.startswith('top') else (-1, 0)
        return [(x, y) for y in ys for x in xs]  # 2 x 2 corner grid.
    if anchor in ('top', 'bottom'):
        return [(0, y) for y in ((0, 1) if anchor == 'top' else (-1, 0))]
    return [(x, 0) for x in ((0, 1) if anchor == 'left' else (-1, 0))]


def default_placement(anchor):
    return {
        'top-left': (1, 1), 'top': (0, 1), 'top-right': (-1, 1),
        'left': (1, 0), 'right': (-1, 0),
        'bottom-left': (1, -1), 'bottom': (0, -1), 'bottom-right': (-1, -1),
    }[anchor]


def attachment_position(rect, size, anchor, placement=None, gap=10, edge_ratio=None):
    """Place a pet outside/across/inside an exact window corner or edge midpoint."""
    placement = placement or default_placement(anchor)
    point = anchor_point(rect, anchor)
    xalign, yalign = placement
    x = point.x() - size.width() if xalign < 0 else (
        point.x() - size.width() // 2 if xalign == 0 else point.x())
    y = point.y() - size.height() if yalign < 0 else (
        point.y() - size.height() // 2 if yalign == 0 else point.y())
    if xalign:
        x += gap * xalign
    if yalign:
        y += gap * yalign
    if edge_ratio is not None and '-' not in anchor:
        ratio = max(0.0, min(1.0, float(edge_ratio)))
        if anchor in ('left', 'right'):
            y = rect.top() + round(max(0, rect.height() - size.height()) * ratio)
        else:
            x = rect.left() + round(max(0, rect.width() - size.width()) * ratio)
    return QPoint(x, y)


def corner_position(rect, size, corner, padding=10):
    """Compatibility wrapper for the original four inside-corner positions."""
    left = rect.x() + min(padding, max(0, rect.width() - size.width()))
    top = rect.y() + min(padding, max(0, rect.height() - size.height()))
    right = max(left, rect.x() + rect.width() - size.width() - padding)
    bottom = max(top, rect.y() + rect.height() - size.height() - padding)
    return QPoint(right if corner.endswith('right') else left,
                  bottom if corner.startswith('bottom') else top)
