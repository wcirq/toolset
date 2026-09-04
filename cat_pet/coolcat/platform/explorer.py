"""Explorer COM queries run off the GUI thread; never guess an ambiguous tab."""
import threading
from PyQt5.QtCore import QObject, pyqtSignal


def select_folder(matches):
    confirmed = [item for item in matches if item[0] is True]
    if len(confirmed) == 1:
        _, name, path = confirmed[0]
        return name, path
    return '当前标签页无法确认', ''


def active_tab_hwnd(hwnd):
    import win32gui
    # Windows 11 keeps inactive tab views WS_VISIBLE too. The selected
    # ShellTabWindowClass is first in child Z-order (also used by QuickLook).
    # This is Explorer-specific, not a public tab-selection API.
    return win32gui.FindWindowEx(hwnd, 0, 'ShellTabWindowClass', None)


def browser_is_active(hwnd, browser, is_visible, active_tab):
    if active_tab and int(browser.GetWindow()) != active_tab:
        return False
    return bool(is_visible(browser.QueryActiveShellView().GetWindow()))


def read_folder(hwnd, is_visible):
    import pythoncom
    pythoncom.CoInitialize()
    try:
        # All COM wrappers live in the inner function and are released BEFORE
        # CoUninitialize; releasing them afterwards can cause native exceptions.
        return _read_initialized_folder(hwnd, is_visible)
    finally:
        pythoncom.CoUninitialize()


def _read_initialized_folder(hwnd, is_visible):
    import pythoncom
    import win32com.client
    from win32com.shell import shell

    matches = []
    active_tab = active_tab_hwnd(hwnd)
    for window in win32com.client.Dispatch('Shell.Application').Windows():
        try:
            if int(window.HWND) != hwnd:
                continue
            visible = None
            try:
                provider = window._oleobj_.QueryInterface(pythoncom.IID_IServiceProvider)
                browser = provider.QueryService(shell.SID_STopLevelBrowser, shell.IID_IShellBrowser)
                visible = browser_is_active(hwnd, browser, is_visible, active_tab)
            except Exception:
                pass
            item = window.Document.Folder.Self
            matches.append((visible, str(item.Name), str(item.Path) if item.IsFileSystem else ''))
        except Exception:
            continue
    # A single shell registration is not proof of the active Windows 11 tab.
    if active_tab_hwnd(hwnd) != active_tab:
        return '标签页正在切换，请稍后重试', ''
    return select_folder(matches)


class ExplorerReader(QObject):
    ready = pyqtSignal(int, int, str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.busy = False
        self.closed = False
        self.ready.connect(self._finished)

    def _finished(self, *_):
        self.busy = False

    def request(self, hwnd, generation, is_visible):
        if self.busy or self.closed:
            return
        self.busy = True

        def work():
            try:
                name, path = read_folder(hwnd, is_visible)
            except ImportError:
                name, path = '读取目录需要安装 pywin32（requirements.txt）', ''
            except Exception:
                name, path = '目录暂不可用', ''
            if not self.closed:
                try:
                    self.ready.emit(hwnd, generation, name, path)
                except RuntimeError:
                    pass
        # A hung Explorer COM server must not block dragging or application exit.
        threading.Thread(target=work, name='ExplorerFolderReader', daemon=True).start()
