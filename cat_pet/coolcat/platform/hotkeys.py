from ..runtime import *
from .windows import user32

# ======================== 全局快捷键 ========================
WM_HOTKEY = 0x0312
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN = 0x1, 0x2, 0x4, 0x8
MOD_NOREPEAT = 0x4000  # 按住时不重复发送 WM_HOTKEY
HOTKEY_ID = 0xC47  # RegisterHotKey 自定义 ID
MONITOR_HOTKEY_ID = 0xC48
SCREENSHOT_HOTKEY_ID = 0xC49

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

    def __init__(self, callback, hotkey_id=HOTKEY_ID, label="全局快捷键"):
        super().__init__()
        self._callback = callback
        self._hotkey_id = hotkey_id
        self._label = label
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
        if user32.RegisterHotKey(hwnd, self._hotkey_id, mod | MOD_NOREPEAT, vk):
            self._hwnd = hwnd
            self._registered = True
            _log(f"{self._label}已注册: {hotkey_text}")
            return True
        _log(f"快捷键注册失败 (可能被占用): {hotkey_text}")
        return False

    def unregister(self):
        if self._registered and self._hwnd:
            user32.UnregisterHotKey(self._hwnd, self._hotkey_id)
            _log(f"{self._label}已注销")
        self._registered = False
        self._hwnd = None

    def nativeEventFilter(self, eventType, message):
        if eventType == "windows_generic_MSG":
            try:
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == WM_HOTKEY and msg.wParam == self._hotkey_id:
                    if self._callback:
                        self._callback()
            except Exception:
                pass
        return False, 0

__all__ = [name for name in globals() if not name.startswith('__')]
