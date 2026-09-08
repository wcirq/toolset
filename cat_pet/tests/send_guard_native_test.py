"""Native integration test using ONLY a local dummy window. Never sends chats."""
import ctypes
from ctypes import wintypes
import os
import sys
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PyQt5.QtWidgets import QApplication, QLineEdit
from coolcat.platform.send_guard import SendGuard

app = QApplication([])
u = ctypes.WinDLL('user32', use_last_error=True)
u.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
u.GetForegroundWindow.restype = wintypes.HWND
u.SetForegroundWindow.argtypes = [wintypes.HWND]
u.SetFocus.argtypes = [wintypes.HWND]
u.SetFocus.restype = wintypes.HWND
class Target(QLineEdit):
    def __init__(self):
        super().__init__()
        self.keys = []
    def nativeEvent(self, kind, pointer):
        msg = wintypes.MSG.from_address(int(pointer))
        if msg.message in (0x100, 0x101) and msg.wParam == 13:
            self.keys.append(msg.message)
            return True, 0
        return super().nativeEvent(kind, pointer)

def pump(seconds=.06):
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        app.processEvents()
        time.sleep(.002)

def modifier(vk, pressed):
    keys = (ctypes.c_ubyte * 256)()
    assert u.GetKeyboardState(keys)
    keys[vk] = 0x80 if pressed else 0
    assert u.SetKeyboardState(keys)

def enter(target):
    u.PostMessageW(int(target.winId()), 0x100, 13, 1)
    u.PostMessageW(int(target.winId()), 0x101, 13, 0xC0000001)
    pump()

u.GetKeyboardLayout.argtypes = [wintypes.DWORD]
u.GetKeyboardLayout.restype = wintypes.HANDLE
u.LoadKeyboardLayoutW.argtypes = [wintypes.LPCWSTR, wintypes.UINT]
u.LoadKeyboardLayoutW.restype = wintypes.HANDLE
u.ActivateKeyboardLayout.argtypes = [wintypes.HANDLE, wintypes.UINT]
u.ActivateKeyboardLayout.restype = wintypes.HANDLE
previous_layout = u.GetKeyboardLayout(0)
# Applies only to this test thread, not the user's language preferences.
english_layout = u.LoadKeyboardLayoutW('00000409', 0)
u.ActivateKeyboardLayout(english_layout, 0)
target = Target()
target.setWindowTitle('CoolCat local hook test — no messages sent')
target.resize(350, 90)
target.show()
guard = SendGuard()
requests = []
guard.close_requested.connect(lambda h, p: requests.append((h, p)))
try:
    u.SetForegroundWindow(int(target.winId()))
    u.SetFocus(int(target.winId()))
    pump()
    print('Waiting up to 45 seconds for the local test window to receive focus...', flush=True)
    deadline = time.monotonic() + 45
    while u.GetForegroundWindow() != int(target.winId()) and time.monotonic() < deadline:
        pump(.05)
    assert u.GetForegroundWindow() == int(target.winId()), 'Cannot foreground local test window'
    u.SetFocus(int(target.winId()))
    assert guard.install(int(target.winId()), os.getpid()), guard.error
    pump()
    assert guard.ready, 'Native install acknowledgement missing'
    print('foreground after install:', u.GetForegroundWindow(), 'target:', int(target.winId()), 'layout:', u.GetKeyboardLayout(0), flush=True)
    u.SetForegroundWindow(int(target.winId()))
    u.SetFocus(int(target.winId()))
    u.ActivateKeyboardLayout(english_layout, 0)
    guard.pulse(True)
    pump()
    enter(target)
    assert len(requests) == 1 and target.keys == [], (requests, target.keys, guard._library.CoolCatSendReadiness())
    enter(target)
    assert len(requests) == 1 and target.keys == [], 'Repeated pending Enter leaked'
    guard.cancel_close()
    u.ActivateKeyboardLayout(english_layout, 0)
    guard.pulse(True)
    pump()
    enter(target)
    assert len(requests) == 2, 'Cancel failed to reset request'
    modifier(0x10, True)
    guard.pulse(True)
    pump()
    enter(target)
    modifier(0x10, False)
    assert target.keys == [0x100, 0x101], 'Shift+Enter was swallowed'
    target.keys.clear()
    guard.pulse(False)
    pump()
    enter(target)
    assert target.keys == [0x100, 0x101], 'Disarmed Enter did not pass through'
    target.keys.clear()
    guard.pulse(True, ctrl=True)
    pump()
    enter(target)
    assert target.keys == [0x100, 0x101], 'Ctrl+Enter mode swallowed plain Enter'
    target.keys.clear()
    guard.cancel_close()
    modifier(0x11, True)
    guard.pulse(True, ctrl=True)
    pump()
    enter(target)
    modifier(0x11, False)
    assert len(requests) == 3 and target.keys == [], 'Ctrl+Enter was not intercepted'
    guard.pulse(True)
    pump(.55)
    target.keys.clear()
    enter(target)
    assert target.keys == [0x100, 0x101], 'Expired heartbeat did not fail open'
    print('PASS: native acknowledgement, Enter interception, pending deduplication, cancel, disarm, Shift+Enter, Ctrl+Enter, heartbeat expiry')
finally:
    modifier(0x10, False)
    modifier(0x11, False)
    u.ActivateKeyboardLayout(previous_layout, 0)
    guard.close()
    pump(.3)
    target.close()
