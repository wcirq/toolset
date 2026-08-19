from ..runtime import *

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


def switch_to_target(title_keyword="", exe_keyword="", maximize=False):
    """
    把匹配目标程序的窗口切到前台; maximize=True 时同时最大化。
    匹配优先级: 可执行名精确 > 可执行名包含 > 标题包含。
    返回 (成功: bool, 消息: str)
    """
    title_keyword = (title_keyword or "").strip().lower()
    exe_keyword = (exe_keyword or "").strip().lower()
    if not title_keyword and not exe_keyword:
        return False, "未设置目标程序"

    try:
        best, best_score = None, 0
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

        if maximize:
            user32.ShowWindow(best, 3)  # SW_MAXIMIZE
        elif user32.IsIconic(best):
            user32.ShowWindow(best, 9)  # SW_RESTORE
        ok = _force_foreground(best)
        if not ok:
            _log("前台切换被系统拒绝(已尝试Alt模拟+线程挂接+SwitchToThisWindow)")
        return True, "切换成功" if ok else "已尝试切换(可能仍被系统限制)"
    except Exception as e:
        _log(f"switch_to_target 异常: {e}\n{traceback.format_exc()}")
        return False, str(e)


def is_foreground_fullscreen(exclude_hwnd=0):
    """当前前台窗口是否覆盖其所在显示器; 排除桌面、任务栏和本程序。"""
    try:
        hwnd = user32.GetForegroundWindow()
        if not hwnd or hwnd == exclude_hwnd or not user32.IsWindowVisible(hwnd):
            return False
        class_buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, class_buf, len(class_buf))
        if class_buf.value in ("Progman", "WorkerW", "Shell_TrayWnd"):
            return False

        rect = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return False

        class MONITORINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD),
                        ("rcMonitor", wintypes.RECT),
                        ("rcWork", wintypes.RECT),
                        ("dwFlags", wintypes.DWORD)]

        monitor = user32.MonitorFromWindow(hwnd, 2)  # MONITOR_DEFAULTTONEAREST
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(info)
        if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            return False
        mr = info.rcMonitor
        tolerance = 2
        return (rect.left <= mr.left + tolerance and
                rect.top <= mr.top + tolerance and
                rect.right >= mr.right - tolerance and
                rect.bottom >= mr.bottom - tolerance)
    except Exception as e:
        _log(f"检测全屏窗口失败: {e}")
        return False

__all__ = [name for name in globals() if not name.startswith('__')]
