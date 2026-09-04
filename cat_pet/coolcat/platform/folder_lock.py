"""Best-effort Explorer tab directory lock (navigation rollback, not access control).

COM objects and the captured tab identity stay on one worker thread. We never
retarget a different tab by its title, directory, or the top-level HWND alone.
"""
from dataclasses import dataclass
import ntpath
import gc
import threading
import time

from PyQt5.QtCore import QObject, pyqtSignal
from .explorer import active_tab_hwnd, browser_is_active


@dataclass
class Tab:
    identity: object
    visible: object
    path: str
    navigate: object


def same_path(left, right):
    return bool(left and right and ntpath.normcase(ntpath.normpath(left)) ==
                ntpath.normcase(ntpath.normpath(right)))


def is_same_or_descendant(path, root):
    """Lexical Windows directory-tree check; different drives/shares are outside."""
    if not path or not root:
        return False
    path = ntpath.normcase(ntpath.normpath(path))
    root = ntpath.normcase(ntpath.normpath(root))
    try:
        return ntpath.commonpath((path, root)) == root
    except ValueError:
        return False


class LockPolicy:
    """Small testable policy; identity is a canonical COM IUnknown in production."""
    def __init__(self, tabs):
        active = [tab for tab in tabs if tab.visible is True]
        if len(active) != 1 or not active[0].path:
            raise ValueError('无法确认当前标签页的真实文件夹，未启用锁定')
        self.identity = active[0].identity
        self.path = active[0].path
        self.next_restore = 0.0
        self.attempts = 0

    def step(self, tabs, now, cancelled):
        matches = [tab for tab in tabs if tab.identity == self.identity]
        if len(matches) != 1:
            raise ValueError('原标签页已关闭或无法识别，目录锁定已解除')
        tab = matches[0]
        if tab.visible is not True or sum(t.visible is True for t in tabs) != 1:
            return 'paused'
        if is_same_or_descendant(tab.path, self.path):
            self.attempts = 0
            return 'locked'
        if now < self.next_restore:
            return 'restoring'
        if self.attempts >= 3:
            raise ValueError('无法恢复锁定目录，已解除锁定；请检查目录是否仍可访问')
        if cancelled.is_set():
            return 'cancelled'
        # Recheck cancellation immediately before the only external write.
        # A navigation already dispatched to Explorer cannot be retracted.
        if tab.navigate(self.path) is False:
            return 'paused'
        self.attempts += 1
        self.next_restore = now + 2.0
        return 'restoring'


def explorer_tabs(hwnd, is_visible):
    import pythoncom
    import win32com.client
    from win32com.shell import shell

    tabs = []
    active_tab = active_tab_hwnd(hwnd)
    for window in win32com.client.Dispatch('Shell.Application').Windows():
        if int(window.HWND) != hwnd:
            continue
        identity = window._oleobj_.QueryInterface(pythoncom.IID_IUnknown)
        provider = window._oleobj_.QueryInterface(pythoncom.IID_IServiceProvider)
        browser = provider.QueryService(shell.SID_STopLevelBrowser, shell.IID_IShellBrowser)
        visible = browser_is_active(hwnd, browser, is_visible, active_tab)
        item = window.Document.Folder.Self
        path = str(item.Path) if item.IsFileSystem else ''
        # The bound method retains exactly this tab, never the active tab of
        # some other window. All wrappers are released before CoUninitialize.
        tabs.append(Tab(identity, visible, path, tab_navigator(hwnd, window, browser, is_visible)))
    if active_tab_hwnd(hwnd) != active_tab:
        # A switch during enumeration is not evidence that the locked tab died.
        for tab in tabs:
            tab.visible = None
    return tabs


def tab_navigator(hwnd, window, browser, is_visible):
    def navigate(path):
        # Recheck immediately before mutation: the user may have switched tabs
        # while ShellWindows enumeration / property reads were in progress.
        if not browser_is_active(hwnd, browser, is_visible, active_tab_hwnd(hwnd)):
            return False
        window.Navigate2(path)
        return True
    return navigate


def monitor_folder(hwnd, is_visible, cancelled, report, interval=.5):
    policy = LockPolicy(explorer_tabs(hwnd, is_visible))
    if cancelled.is_set():
        return
    report('locked', policy.path)
    previous = 'locked'
    while not cancelled.wait(interval):
        state = policy.step(explorer_tabs(hwnd, is_visible), time.monotonic(), cancelled)
        if state == 'cancelled':
            return
        if state != previous:
            report(state, policy.path)
            previous = state


class ExplorerFolderLock(QObject):
    changed = pyqtSignal(int, str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.token = 0
        self.cancelled = None

    def stop(self):
        self.token += 1
        if self.cancelled:
            self.cancelled.set()
        self.cancelled = None

    def start(self, hwnd, is_visible):
        self.stop()
        token = self.token
        cancelled = self.cancelled = threading.Event()

        def report(state, detail):
            if not cancelled.is_set():
                try:
                    self.changed.emit(token, state, detail)
                except RuntimeError:
                    cancelled.set()

        def work():
            try:
                import pythoncom
                pythoncom.CoInitialize()
                try:
                    # The inner function owns all COM references.
                    try:
                        monitor_folder(hwnd, is_visible, cancelled, report)
                    except ValueError as exc:
                        report('error', str(exc))
                    except Exception:
                        report('error', '资源管理器接口不可用，目录锁定已解除')
                    # Exception tracebacks (which can retain COM wrappers) have
                    # also been cleared when their handlers finish here.
                finally:
                    gc.collect()
                    pythoncom.CoUninitialize()
            except ImportError:
                report('error', '锁定目录需要安装 pywin32')
            except Exception:
                report('error', '资源管理器接口不可用，目录锁定已解除')
        threading.Thread(target=work, name='ExplorerFolderLock', daemon=True).start()
        return token
