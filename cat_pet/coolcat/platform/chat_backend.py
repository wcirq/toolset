"""UIA session operations. Tokens are valid only for the current UI lifetime."""
from dataclasses import dataclass

from .wechat import _with_uia, _draft_identity, _read_window


@dataclass(frozen=True)
class Session:
    automation_id: str
    runtime_id: tuple
    name: str


def require_backend(config):
    mode = config.get('wechat_backend', 'uia')
    if mode == 'native':
        raise RuntimeError('进程内模式尚未完成当前安装版本的收发函数和参数结构适配，暂不可用。')
    if mode != 'uia':
        raise RuntimeError('未知聊天后端：' + str(mode))


def _items(automation, hwnd):
    root = automation.ElementFromHandle(int(hwnd))
    listing = root.FindFirst(4, automation.CreatePropertyCondition(30011, 'session_list'))
    if not listing:
        raise RuntimeError('客户端未暴露 session_list；不使用 OCR 回退。')
    items = listing.FindAll(4, automation.CreatePropertyCondition(30003, 50007))
    result = []
    for index in range(items.Length):
        item = items.GetElement(index)
        aid = str(item.CurrentAutomationId or '')
        if aid.startswith('session_item_') and not item.CurrentIsOffscreen:
            result.append((Session(aid, tuple(item.GetRuntimeId()), aid[len('session_item_'):]), item))
    return result


def list_sessions(hwnd):
    return _with_uia(lambda automation, uia: [s for s, _ in _items(automation, hwnd)])


def require_selected_session(hwnd, session):
    """Validate a bound row even when its token came from the Qt reader."""
    def check(automation, uia):
        matches = [(s, item) for s, item in _items(automation, hwnd)
                   if s.automation_id == session.automation_id]
        if len(matches) != 1:
            raise RuntimeError('无法确认吸附会话，请打开绑定的聊天后重试。')
        current, item = matches[0]
        pattern = item.GetCurrentPattern(10010).QueryInterface(uia.IUIAutomationSelectionItemPattern)
        if not pattern.CurrentIsSelected:
            raise RuntimeError('当前打开的聊天不是吸附会话，请切回「%s」后重试。' % session.name)
        identity = _draft_identity(automation, uia, hwnd)[2]
        if identity[2] != session.name:
            raise RuntimeError('聊天标题与吸附会话不一致，已停止读取。')
        return current.runtime_id, identity
    try:
        return _with_uia(check)
    except Exception as exc:
        raise RuntimeError('吸附会话核对失败，未读取其他聊天：%s' % exc) from exc


def session_rectangles(hwnd):
    """Return only realized, uniquely named rows, clipped to the session list."""
    def read(automation, uia):
        root = automation.ElementFromHandle(int(hwnd))
        listing = root.FindFirst(4, automation.CreatePropertyCondition(30011, 'session_list'))
        if not listing:
            raise RuntimeError('客户端没有暴露 session_list，无法定位聊天行。')
        clip = listing.CurrentBoundingRectangle
        items = _items(automation, hwnd)
        result = []
        for session, item in items:
            if sum(s.automation_id == session.automation_id for s, _ in items) != 1:
                continue
            rect = item.CurrentBoundingRectangle
            bounds = (max(rect.left, clip.left), max(rect.top, clip.top),
                      min(rect.right, clip.right), min(rect.bottom, clip.bottom))
            if bounds[2] > bounds[0] and bounds[3] > bounds[1]:
                result.append((session, bounds))
        return result
    return _with_uia(read)


def _resolve(automation, hwnd, session):
    items = _items(automation, hwnd)
    matches = [(s, item) for s, item in items if s.automation_id == session.automation_id]
    if len(matches) != 1 or matches[0][0] != session:
        raise RuntimeError('会话绑定失效、滚出可见列表或存在同名项，请重新绑定。')
    return matches[0][1]


def _selected(automation, uia, hwnd, session):
    item = _resolve(automation, hwnd, session)
    pattern = item.GetCurrentPattern(10010).QueryInterface(uia.IUIAutomationSelectionItemPattern)
    if not pattern.CurrentIsSelected:
        raise RuntimeError('用户已切换会话，本次操作取消。')
    root, field, identity, draft = _draft_identity(automation, uia, hwnd)
    if identity[2] != session.name:
        raise RuntimeError('聊天标题与绑定会话不一致，等待页面加载后重试。')
    return root, field, identity, draft


def select_session(hwnd, session):
    def select(automation, uia):
        if _draft_identity(automation, uia, hwnd)[3]:
            raise RuntimeError('当前输入框有草稿，暂停切换。')
        item = _resolve(automation, hwnd, session)
        item.GetCurrentPattern(10010).QueryInterface(uia.IUIAutomationSelectionItemPattern).Select()
    return _with_uia(select)


def read_session(hwnd, session):
    def read(automation, uia):
        before = _selected(automation, uia, hwnd, session)
        if before[3]:
            raise RuntimeError('会话已有草稿，暂停处理。')
        snapshot = _read_window(automation, uia, hwnd, 'conversation')
        after = _selected(automation, uia, hwnd, session)
        if before[2:] != after[2:]:
            raise RuntimeError('读取时会话发生变化。')
        return before[2], snapshot
    return _with_uia(read)


def fill_reply(hwnd, session, identity, conversation, reply):
    if not reply.strip() or len(reply) > 4000:
        raise RuntimeError('模型回复为空或过长。')
    def fill(automation, uia):
        root, field, current, draft = _selected(automation, uia, hwnd, session)
        if current != identity or draft:
            raise RuntimeError('会话或草稿已变化，未填写。')
        if _read_window(automation, uia, hwnd, 'conversation').conversation != conversation:
            raise RuntimeError('消息已更新，请重新生成回复。')
        value = field.GetCurrentPattern(10002).QueryInterface(uia.IUIAutomationValuePattern)
        if value.CurrentIsReadOnly or not field.CurrentIsEnabled:
            raise RuntimeError('输入框不支持 UIA 写入。')
        _selected(automation, uia, hwnd, session)
        value.SetValue(reply)
        if _draft_identity(automation, uia, hwnd)[2:] != (identity, reply):
            raise RuntimeError('填写结果无法确认，请检查输入框；不会重试。')
    return _with_uia(fill)
