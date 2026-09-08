"""Real message-loop tests against a LOCAL button, never a chat client."""
import ctypes
from ctypes import wintypes
import os
import sys
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PyQt5.QtWidgets import QApplication, QWidget, QPushButton, QLineEdit
from coolcat.platform.send_guard import SendGuard
from coolcat.platform.wechat import physical_window_rect

app = QApplication([])
u = ctypes.WinDLL('user32', use_last_error=True)
u.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
u.GetForegroundWindow.restype = wintypes.HWND
u.SetForegroundWindow.argtypes = [wintypes.HWND]

def pump(seconds=.04):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.002)

def post(widget, message, x=30, y=15):
    point = (x & 0xffff) | ((y & 0xffff) << 16)
    assert u.PostMessageW(int(widget.winId()), message, 1 if message in (0x201, 0x203) else 0, point)
    pump()

def click(down=0x201, release_x=30):
    post(button, down)
    post(button, 0x202, release_x)

target = QWidget()
target.setWindowTitle('CoolCat local mouse hook test - no chat messages')
target.resize(450, 220)
editor = QLineEdit(target)
editor.setGeometry(20, 20, 400, 60)
button = QPushButton('Local test send', target)
button.setGeometry(290, 140, 130, 50)
button.winId()
target.show()
guard = SendGuard()
reviews, sends = [], []
guard.click_requested.connect(lambda h, p: reviews.append((h, p)))
button.clicked.connect(lambda: sends.append(True))

def arm():
    assert guard.mouse_region(physical_window_rect(int(button.winId())),
                              physical_window_rect(int(target.winId())))
    pump()

try:
    target.activateWindow()
    # Temporarily join input queues only to foreground this owned test window.
    # No keys or mouse input are delivered to the existing foreground window.
    u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    u.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
    own_thread = ctypes.windll.kernel32.GetCurrentThreadId()
    foreground_thread = u.GetWindowThreadProcessId(u.GetForegroundWindow(), None)
    attached = foreground_thread != own_thread and u.AttachThreadInput(own_thread, foreground_thread, True)
    try:
        u.SetForegroundWindow(int(target.winId()))
    finally:
        if attached:
            u.AttachThreadInput(own_thread, foreground_thread, False)
    pump()
    print('Waiting for local test window focus...', flush=True)
    deadline = time.monotonic() + 30
    while u.GetForegroundWindow() != int(target.winId()) and time.monotonic() < deadline:
        pump()
    assert u.GetForegroundWindow() == int(target.winId()), 'Local test window needs foreground focus'
    assert guard.install(int(target.winId()), os.getpid()), guard.error
    pump()
    assert guard.ready, 'Hook acknowledgement missing'
    guard.pulse(False)  # Mouse guard works WITHOUT chat-input keyboard focus.
    arm()
    click()
    assert len(reviews) == 1 and sends == [], (reviews, sends)
    arm()
    click(0x203)
    assert len(reviews) == 1 and sends == [], 'Double click escaped/prompt duplicated'
    # Programmatic button action is deliberately separate from mouse messages.
    button.click()
    assert len(sends) == 1 and len(reviews) == 1, 'Confirmed action reentered mouse guard'
    sends.clear()
    guard.cancel_close()
    arm()
    click(release_x=180)
    assert len(reviews) == 1 and sends == [], 'Drag-out incorrectly sent or requested review'
    arm()
    post(target, 0x201, 10, 100)
    post(target, 0x202, 10, 100)
    assert len(reviews) == 1, 'Unrelated area was intercepted'
    arm()
    pump(.5)
    click()
    assert len(sends) == 1 and len(reviews) == 1, 'Expired region did not pass through'
    sends.clear()
    arm()
    target.move(target.x() + 20, target.y())
    pump()
    click()
    assert len(sends) == 1 and len(reviews) == 1, 'Stale window geometry was used'
    sends.clear()
    arm()
    click()
    assert len(reviews) == 2 and sends == [], 'New bounds after movement did not intercept'
    guard.cancel_close()
    guard.mouse_region()
    pump()
    click()
    assert len(sends) == 1 and len(reviews) == 2, 'Disabled mouse guard swallowed click'
    print('PASS: mouse interception, no input focus, double-click deduplication, programmatic send, drag-out, unrelated area, expiry, movement, disable')
finally:
    guard.close()
    pump(.3)
    target.close()
