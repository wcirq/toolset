"""Read current Weixin text through UI Automation; never capture pixels."""
from dataclasses import dataclass, field


@dataclass
class WeChatSnapshot:
    conversation: str = ''
    input_text: str = ''
    readable: bool = False
    error: str = ''
    pages_read: int = 1
    warning: str = ''
    messages_read: int = 0
    messages: list = field(default_factory=list)
    conversation_title_candidate: str = ''


def is_wechat_window(title='', kind='', executable=''):
    value = ('%s %s %s' % (title, kind, executable)).lower()
    return any(token in value for token in
               ('微信', 'wechat', 'weixin.exe', 'wechat.exe', 'weixin'))


def _read_input(element, uia):
    # Name is the conversation title, not the draft.
    for pattern_id, interface, getter in (
        (10014, uia.IUIAutomationTextPattern,
         lambda p: p.DocumentRange.GetText(-1)),
        (10002, uia.IUIAutomationValuePattern, lambda p: p.CurrentValue),
    ):
        try:
            pattern = element.GetCurrentPattern(pattern_id).QueryInterface(interface)
            return str(getter(pattern) or '')
        except Exception:
            continue
    raise RuntimeError('输入框未暴露可读取的文本接口')


def _read_window(automation, uia, hwnd, mode):
    root = automation.ElementFromHandle(int(hwnd))

    def find(automation_id):
        return root.FindFirst(4, automation.CreatePropertyCondition(30011, automation_id))

    draft = ''
    if mode in ('draft', 'read'):
        field = find('chat_input_field')
        if not field:
            raise RuntimeError('未找到当前聊天输入框，请先打开一个会话')
        draft = _read_input(field, uia)
    lines = []
    if mode != 'draft':
        messages = find('chat_message_list')
        if not messages:
            raise RuntimeError('未找到当前消息列表；当前客户端版本可能需要适配')
        items = messages.FindAll(4, automation.CreatePropertyCondition(30003, 50007))
        for index in range(items.Length):
            text = str(items.GetElement(index).CurrentName or '').strip()
            if text:
                lines.append(text)
    conversation = '\n'.join(lines)
    return WeChatSnapshot(conversation, draft, bool(conversation or draft))


def read_wechat_window(hwnd, mode='conversation'):
    """Worker entry point; COM objects stay on their owning thread."""
    if mode not in ('conversation', 'draft', 'read'):
        return WeChatSnapshot(error='不支持的微信读取模式')
    try:
        import comtypes
        from comtypes.client import CreateObject, GetModule
        comtypes.CoInitializeEx()
        try:
            uia = GetModule('UIAutomationCore.dll')
            automation = CreateObject(uia.CUIAutomation, interface=uia.IUIAutomation)
            return _read_window(automation, uia, hwnd, mode)
        finally:
            comtypes.CoUninitialize()
    except Exception as exc:
        return WeChatSnapshot(error='无法通过 UI Automation 读取聊天文本：%s' % exc)


__all__ = ['WeChatSnapshot', 'is_wechat_window', 'read_wechat_window']


def _with_uia(callback):
    import comtypes
    from comtypes.client import CreateObject, GetModule
    comtypes.CoInitializeEx()
    try:
        uia = GetModule('UIAutomationCore.dll')
        return callback(CreateObject(uia.CUIAutomation, interface=uia.IUIAutomation), uia)
    finally:
        comtypes.CoUninitialize()


def _input_focused(automation, root):
    field = root.FindFirst(4, automation.CreatePropertyCondition(30011, 'chat_input_field'))
    focused = automation.GetFocusedElement()
    for _ in range(8):
        if not focused:
            break
        if field and automation.CompareElements(field, focused):
            return True
        focused = automation.ControlViewWalker.GetParentElement(focused)
    return False


def focused_chat_input(hwnd):
    try:
        return _with_uia(lambda automation, uia:
                         _input_focused(automation, automation.ElementFromHandle(int(hwnd))))
    except Exception:
        return False


def physical_window_rect(hwnd):
    """Match UIA physical coordinates, independent of the caller's DPI mode."""
    import ctypes
    from ctypes import wintypes
    api = ctypes.WinDLL('user32', use_last_error=True)
    api.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    api.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
    api.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    old = api.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
    if not old:
        raise OSError('无法读取物理窗口坐标')
    try:
        rect = wintypes.RECT()
        if not api.GetWindowRect(int(hwnd), ctypes.byref(rect)):
            raise OSError('窗口已失效')
        return rect.left, rect.top, rect.right, rect.bottom
    finally:
        api.SetThreadDpiAwarenessContext(old)


def send_guard_state(hwnd):
    """Read focus and the unique enabled Send button without reading any text."""
    def inspect(automation, uia):
        before = physical_window_rect(hwnd)
        root = automation.ElementFromHandle(int(hwnd))
        focused = _input_focused(automation, root)
        field = root.FindFirst(4, automation.CreatePropertyCondition(30011, 'chat_input_field'))
        if not field:
            return False, None, None
        buttons = root.FindAll(4, automation.CreateAndCondition(
            automation.CreatePropertyCondition(30003, 50000),
            automation.CreatePropertyCondition(30005, '发送')))
        if buttons.Length != 1:
            return focused, None, None
        button = buttons.GetElement(0)
        if not button.CurrentIsEnabled or button.CurrentIsOffscreen:
            return focused, None, None
        rect = button.CurrentBoundingRectangle
        bounds = (int(rect.left), int(rect.top), int(rect.right), int(rect.bottom))
        after = physical_window_rect(hwnd)
        l, t, r, b = bounds
        if (before != after or r <= l or b <= t or
                not (after[0] <= l < r <= after[2] and after[1] <= t < b <= after[3])):
            return focused, None, None
        return focused, bounds, after
    try:
        return _with_uia(inspect)
    except Exception:
        return False, None, None


def _draft_identity(automation, uia, hwnd):
    root = automation.ElementFromHandle(int(hwnd))
    field = root.FindFirst(4, automation.CreatePropertyCondition(30011, 'chat_input_field'))
    if not field:
        raise RuntimeError('当前会话输入框已不可用')
    # RuntimeId also detects a destroyed/recreated editor with the same title.
    identity = (tuple(root.GetRuntimeId()), tuple(field.GetRuntimeId()),
                str(field.CurrentName or ''))
    return root, field, identity, _read_input(field, uia)


def capture_send_draft(hwnd):
    def capture(automation, uia):
        _, _, identity, draft = _draft_identity(automation, uia, hwnd)
        if not draft.strip():
            raise RuntimeError('输入框为空，已取消本次发送')
        return identity, draft
    return _with_uia(capture)


def send_original_draft(hwnd, identity, draft):
    """Only called after an explicit Send original click; never retries Invoke."""
    def send(automation, uia):
        root, field, current_identity, current_draft = _draft_identity(automation, uia, hwnd)
        if current_identity != identity or current_draft != draft:
            raise RuntimeError('会话或草稿已变化，本次未发送；请重新检查')
        condition = automation.CreateAndCondition(
            automation.CreatePropertyCondition(30003, 50000),
            automation.CreatePropertyCondition(30005, '发送'))
        buttons = root.FindAll(4, condition)
        if buttons.Length != 1:
            raise RuntimeError('无法唯一确定发送按钮，本次未发送')
        button = buttons.GetElement(0)
        if not button.CurrentIsEnabled:
            raise RuntimeError('发送按钮不可用')
        # Recheck immediately before the one-shot action.
        if _draft_identity(automation, uia, hwnd)[2:] != (identity, draft):
            raise RuntimeError('会话或草稿已变化，本次未发送')
        button.GetCurrentPattern(10000).QueryInterface(uia.IUIAutomationInvokePattern).Invoke()
    return _with_uia(send)
