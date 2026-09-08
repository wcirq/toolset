"""Target GUI-thread keyboard and mouse send hook. UIA polling and model calls live elsewhere."""
import ctypes
from ctypes import wintypes
import os
import sys

from PyQt5.QtCore import QObject, QTimer, Qt, pyqtSignal
from PyQt5.QtWidgets import QWidget


MESSAGE_NAMES = {
    'install': 'CoolCat.SendGuard.Install.v1',
    'uninstall': 'CoolCat.SendGuard.Uninstall.v1',
    'request': 'CoolCat.SendGuard.Request.v1',
    'ready': 'CoolCat.SendGuard.Ready.v1',
    'pulse': 'CoolCat.SendGuard.Pulse.v1',
    'cancel': 'CoolCat.SendGuard.Cancel.v1',
    'click': 'CoolCat.SendGuard.Click.v1',
    'button': 'CoolCat.SendGuard.Button.v1',
    'frame': 'CoolCat.SendGuard.Frame.v1',
    'mouse': 'CoolCat.SendGuard.Mouse.v1',
}


class _MessageWindow(QWidget):
    ready = pyqtSignal(object, object)
    click_requested = pyqtSignal(object, object)
    close_requested = pyqtSignal(object, object)

    def __init__(self, request_message, ready_message, click_message):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint)
        self.request_message = request_message
        self.ready_message = ready_message
        self.click_message = click_message
        self.setAttribute(Qt.WA_DontShowOnScreen)
        self.resize(1, 1)
        self.winId()  # Materialize a native HWND without showing the widget.

    def nativeEvent(self, event_type, message):
        if sys.platform == 'win32':
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == self.ready_message:
                hwnd, pid = int(msg.wParam), int(msg.lParam)
                QTimer.singleShot(0, lambda: self.ready.emit(hwnd, pid))
                return True, 0
            if msg.message == self.click_message:
                hwnd, pid = int(msg.wParam), int(msg.lParam)
                QTimer.singleShot(0, lambda: self.click_requested.emit(hwnd, pid))
                return True, 0
            if msg.message == self.request_message:
                hwnd, pid = int(msg.wParam), int(msg.lParam)
                QTimer.singleShot(0, lambda: self.close_requested.emit(hwnd, pid))
                return True, 0
        return super().nativeEvent(event_type, message)


class SendGuard(QObject):
    """Install one WH_GETMESSAGE hook for the currently attached GUI thread."""
    close_requested = pyqtSignal(object, object)
    click_requested = pyqtSignal(object, object)

    def __init__(self, parent=None, api=None, dll_path=None):
        super().__init__(parent)
        self.available = False
        self.error = ''
        self.ready = False
        self.target_hwnd = 0
        self.target_pid = 0
        self._hook = None
        self._library = None
        self._api = api
        self._explicit_dll_path = dll_path
        self._messages = {}
        self._receiver = None
        if sys.platform == 'win32':
            self._initialize()

    @staticmethod
    def _candidate_paths():
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        base = getattr(sys, '_MEIPASS', project_root)
        executable_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else project_root
        return [
            os.path.join(executable_dir, 'CoolCatSendGuardV2_64.dll'),
            os.path.join(base, 'CoolCatSendGuardV2_64.dll'),
            os.path.join(project_root, 'native', 'send_guard', 'bin', 'x64',
                         'Release', 'CoolCatSendGuardV2_64.dll'),
        ]

    def _initialize(self):
        try:
            self._api = self._api or ctypes.WinDLL('user32', use_last_error=True)
            self._api.RegisterWindowMessageW.argtypes = [wintypes.LPCWSTR]
            self._api.RegisterWindowMessageW.restype = wintypes.UINT
            self._api.GetWindowThreadProcessId.argtypes = [wintypes.HWND,
                                                            ctypes.POINTER(wintypes.DWORD)]
            self._api.GetWindowThreadProcessId.restype = wintypes.DWORD
            self._api.SetWindowsHookExW.argtypes = [ctypes.c_int, ctypes.c_void_p,
                                                     wintypes.HINSTANCE, wintypes.DWORD]
            self._api.SetWindowsHookExW.restype = wintypes.HANDLE
            self._api.UnhookWindowsHookEx.argtypes = [wintypes.HANDLE]
            self._api.UnhookWindowsHookEx.restype = wintypes.BOOL
            self._api.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                                wintypes.WPARAM, wintypes.LPARAM]
            self._api.PostMessageW.restype = wintypes.BOOL
            self._messages = {key: int(self._api.RegisterWindowMessageW(value))
                              for key, value in MESSAGE_NAMES.items()}
            if not all(self._messages.values()):
                raise OSError('无法注册发送检查消息')
            path = self._explicit_dll_path or next(
                (item for item in self._candidate_paths() if os.path.isfile(item)), '')
            if not path:
                raise FileNotFoundError('缺少 CoolCatSendGuardV2_64.dll')
            self._library = ctypes.WinDLL(path)
            self._hook_proc = getattr(self._library, 'CoolCatSendHook')
            self.available = True
        except Exception as exc:
            self.error = str(exc)
            self.available = False

    def install(self, hwnd, pid=0):
        self.uninstall()
        if not self.available or not hwnd:
            return False
        process_id = wintypes.DWORD()
        thread_id = int(self._api.GetWindowThreadProcessId(
            wintypes.HWND(hwnd), ctypes.byref(process_id)))
        if not thread_id or (pid and process_id.value != pid):
            self.error = '目标窗口已失效'
            return False
        hook = self._api.SetWindowsHookExW(
            3, ctypes.cast(self._hook_proc, ctypes.c_void_p),
            wintypes.HINSTANCE(self._library._handle), thread_id)  # WH_GETMESSAGE
        if not hook:
            code = ctypes.get_last_error()
            self.error = '无法挂接目标窗口（Windows 错误 %d）' % code
            return False
        self._hook = hook
        self._receiver = _MessageWindow(self._messages['request'], self._messages['ready'], self._messages['click'])
        self._receiver.ready.connect(self._ready)
        self._receiver.click_requested.connect(self.click_requested)
        self._receiver.close_requested.connect(self.close_requested)
        self.target_hwnd, self.target_pid = int(hwnd), int(process_id.value)
        if not self._post('install', int(self._receiver.winId()), 0):
            self._release_hook()
            self.target_hwnd = self.target_pid = 0
            self._destroy_receiver()
            return False
        self.error = ''
        return True

    def _ready(self, hwnd, pid):
        if (hwnd, pid) == (self.target_hwnd, self.target_pid):
            self.ready = True

    def _post(self, name, wparam=0, lparam=0):
        if not self.target_hwnd:
            return False
        return bool(self._api.PostMessageW(
            wintypes.HWND(self.target_hwnd), self._messages[name],
            wintypes.WPARAM(wparam), wintypes.LPARAM(lparam)))

    def _destroy_receiver(self):
        if self._receiver:
            receiver = self._receiver
            self._receiver = None
            receiver.close()
            receiver.destroy(True, True)
            receiver.deleteLater()

    def pulse(self, armed, ctrl=False):
        return self._post('pulse', int(self._receiver.winId()) if self._receiver else 0,
                          int(bool(armed)) | (int(bool(ctrl)) << 1))

    @staticmethod
    def _pack_point(x, y):
        if not (-2**31 <= x < 2**31 and -2**31 <= y < 2**31):
            raise ValueError('鼠标坐标超出范围')
        return (x & 0xffffffff) | ((y & 0xffffffff) << 32)

    def mouse_region(self, bounds=None, frame=None):
        # Three value-only messages: no pointer crosses process boundaries.
        if bounds is None or frame is None:
            return self._post('mouse', int(self._receiver.winId()) if self._receiver else 0, 0)
        try:
            for name, rect in (('button', bounds), ('frame', frame)):
                if not self._post(name, self._pack_point(*rect[:2]), self._pack_point(*rect[2:])):
                    self.mouse_region()
                    return False
            return self._post('mouse', int(self._receiver.winId()) if self._receiver else 0, 1)
        except (TypeError, ValueError):
            self.mouse_region()
            return False

    def cancel_close(self):
        return self._post('cancel')

    def uninstall(self):
        self.ready = False
        if self.target_hwnd and self.available:
            self._post('uninstall')
        self.target_hwnd = self.target_pid = 0
        # A unique receiver HWND makes stale hooks fail open if teardown is delayed.
        self._destroy_receiver()
        if self._hook:
            hook = self._hook
            self._hook = None
            # Let the target process the uninstall message and release mouse capture.
            QTimer.singleShot(250, lambda: self._unhook_value(hook))

    def _unhook_value(self, hook):
        try:
            self._api.UnhookWindowsHookEx(hook)
        except Exception:
            pass

    def _release_hook(self):
        if self._hook:
            self._unhook_value(self._hook)
            self._hook = None

    def close(self):
        self.uninstall()
        self._release_hook()
