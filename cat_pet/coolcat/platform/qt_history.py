"""Visible Qt message pages with bounded, user-cancellable upward scrolling."""
import ctypes as c
from ctypes import wintypes as w
import time

from .qt_chat_rows import QtChatRows
from .wechat import WeChatSnapshot


def merge_older(older, accumulated):
    """Only merge a unique >=2-record overlap; preserve duplicate messages."""
    # Labels may scroll off-screen while their message bubbles remain visible.
    # They are display context, not message identity or overlap anchors.
    if older and accumulated and isinstance(older[0], tuple):
        old_messages = [record for record in older if record[0] == 'message']
        new_positions = [i for i, record in enumerate(accumulated) if record[0] == 'message']
        new_messages = [accumulated[i] for i in new_positions]
        matches = [n for n in range(2, min(len(old_messages), len(new_messages)) + 1)
                   if old_messages[-n:] == new_messages[:n] and
                   sum(record[1] != '[非文本消息或暂不支持的消息类型]'
                       for record in new_messages[:n]) >= 2]
        if len(matches) != 1:
            return None
        return older + accumulated[new_positions[matches[0] - 1] + 1:]
    matches = [n for n in range(2, min(len(older), len(accumulated)) + 1)
               if older[-n:] == accumulated[:n]]
    if len(matches) != 1:
        return None
    return older[:-matches[0]] + accumulated


def merge_pages(older, records, keys, previous=None):
    """Match transient bubble identity AND full text across adjacent reads."""
    old_keys = older.get('record_keys', [])
    old = older['records']
    if len(old_keys) == len(old) and len(keys) == len(records):
        # Time/retraction labels can be the only surviving controls. Match
        # their object tokens AND text AND consistent upward-scroll geometry;
        # equal time strings alone never establish continuity.
        if previous:
            before_boxes = dict(zip(previous.get('record_keys', []), previous.get('record_rects', [])))
            after_boxes = dict(zip(old_keys, older.get('record_rects', [])))
            left_all, right_all = list(zip(old_keys, old)), list(zip(keys, records))
            overlaps = []
            for n in range(1, min(len(left_all), len(right_all)) + 1):
                if left_all[-n:] != right_all[:n] or any(token is None for token, _ in left_all[-n:]):
                    continue
                shifts = []
                for token, record in left_all[-n:]:
                    a, b = before_boxes.get(token), after_boxes.get(token)
                    if not a or not b or (a[0], a[2], a[3]-a[1]) != (b[0], b[2], b[3]-b[1]):
                        break
                    shifts.append(b[1]-a[1])
                if len(shifts) == n and min(shifts) > 0 and max(shifts)-min(shifts) <= 1:
                    overlaps.append(n)
            if len(overlaps) == 1:
                cut = overlaps[0]
                return old + records[cut:], old_keys + keys[cut:]
        oi = [i for i, r in enumerate(old) if r[0] == 'message']
        ni = [i for i, r in enumerate(records) if r[0] == 'message']
        left = [(old_keys[i], old[i]) for i in oi]
        right = [(keys[i], records[i]) for i in ni]
        def position_confirms(n):
            if not previous:
                return False
            before = dict(zip(previous.get('record_keys', []), previous.get('record_rects', [])))
            after = dict(zip(old_keys, older.get('record_rects', [])))
            shifts = []
            for token, _ in left[-n:]:
                a, b = before.get(token), after.get(token)
                if not a or not b or (a[0], a[2], a[3]-a[1]) != (b[0], b[2], b[3]-b[1]):
                    return False
                shifts.append(b[1]-a[1])
            return bool(shifts) and min(shifts) > 0 and max(shifts)-min(shifts) <= 1
        matches = [n for n in range(1, min(len(left), len(right)) + 1)
                   if left[-n:] == right[:n] and all(token is not None for token, _ in left[-n:]) and
                   (any(r[1][1] != '[非文本消息或暂不支持的消息类型]' for r in right[:n])
                    or position_confirms(n))]
        if len(matches) == 1:
            cut = ni[matches[0] - 1] + 1
            return old + records[cut:], old_keys + keys[cut:]
    merged = merge_older(old, records)
    if merged is not None:
        # The text merger prepends the new page and retains an exact suffix.
        # Keep the new page's tokens so the NEXT page can use geometry again.
        # Dropping all tokens here permanently disabled that fallback.
        tail_length = len(merged) - len(old)
        tail_keys = (keys[-tail_length:] if tail_length and len(keys) == len(records)
                     else [None] * tail_length)
        return merged, (old_keys if len(old_keys) == len(old) else [None] * len(old)) + tail_keys
    return None, []


class ReadNumbers:
    """Run-local discovery numbers; only accepted adjacent pages advance them."""
    def __init__(self):
        self.count = 0
        self.previous = {}

    def page(self, page, commit=False):
        result, current = [], {}
        for key, record in reversed(list(zip(page.get('record_keys', []), page['records']))):
            if record[0] != 'message':
                continue
            token = (key, record)
            number = self.previous.get(token)
            if number is None and commit:
                self.count += 1
                number = self.count
            result.append(number)
            if number is not None:
                current[token] = number
        if commit:
            self.previous = current
        return list(reversed(result))


class HistoryWindow:
    def __init__(self, hwnd):
        self.hwnd = hwnd
        self.api = c.WinDLL('user32', use_last_error=True)
        for name, args, result in [
            ('GetWindowThreadProcessId', [w.HWND, c.POINTER(w.DWORD)], w.DWORD),
            ('GetForegroundWindow', [], w.HWND),
            ('GetDpiForWindow', [w.HWND], w.UINT),
            ('ClientToScreen', [w.HWND, c.POINTER(w.POINT)], w.BOOL),
            ('GetClientRect', [w.HWND, c.POINTER(w.RECT)], w.BOOL),
            ('WindowFromPoint', [w.POINT], w.HWND),
            ('ScreenToClient', [w.HWND, c.POINTER(w.POINT)], w.BOOL),
            ('ChildWindowFromPointEx', [w.HWND, w.POINT, w.UINT], w.HWND),
            ('GetAncestor', [w.HWND, w.UINT], w.HWND),
            ('SendMessageTimeoutW', [w.HWND, w.UINT, w.WPARAM, w.LPARAM, w.UINT, w.UINT, c.POINTER(c.c_size_t)], w.LPARAM),
            ('SetThreadDpiAwarenessContext', [c.c_void_p], c.c_void_p),
        ]:
            function = getattr(self.api, name)
            function.argtypes, function.restype = args, result
        owner = w.DWORD()
        self.api.GetWindowThreadProcessId(hwnd, c.byref(owner))
        self.pid = owner.value
        if not self.pid:
            raise RuntimeError('微信窗口已关闭')

    def input_token(self):
        class Input(c.Structure):
            _fields_ = [('size', w.UINT), ('tick', w.DWORD)]
        value = Input(c.sizeof(Input), 0)
        if not self.api.GetLastInputInfo(c.byref(value)):
            raise RuntimeError('无法核对用户操作状态')
        return value.tick

    def annotation(self, page, numbers=None):
        old = self.api.SetThreadDpiAwarenessContext(c.c_void_p(-4))
        if not old:
            return None
        try:
            origin = w.POINT()
            if not self.api.ClientToScreen(self.hwnd, c.byref(origin)):
                return None
            scale = self.api.GetDpiForWindow(self.hwnd) / 96
            def physical(rect):
                return tuple(round(v * scale) + (origin.x if i % 2 == 0 else origin.y)
                             for i, v in enumerate(rect))
            return {'clip': physical(page['rect']), 'numbers': numbers or [],
                    'parts': [{'kind': part['kind'], 'rect': physical(part['rect'])}
                              for part in page.get('annotations', [])],
                    'boxes': [physical(rect)
                    for record, rect in zip(page['records'], page.get('record_rects', []))
                    if record[0] == 'message']}
        finally:
            self.api.SetThreadDpiAwarenessContext(old)

    def wheel(self, rect, delta=120, after_step=None):
        old = self.api.SetThreadDpiAwarenessContext(c.c_void_p(-4))
        if not old:
            raise RuntimeError('无法核对屏幕坐标')
        try:
            origin, client, pid = w.POINT(), w.RECT(), w.DWORD()
            self.api.GetWindowThreadProcessId(self.hwnd, c.byref(pid))
            if pid.value != self.pid or not self.api.ClientToScreen(self.hwnd, c.byref(origin)) or not self.api.GetClientRect(self.hwnd, c.byref(client)):
                raise RuntimeError('目标窗口已变化')
            scale = self.api.GetDpiForWindow(self.hwnd) / 96
            x = origin.x + round((rect[0] + rect[2]) * .5 * scale)
            y = origin.y + round((rect[1] + rect[3]) * .5 * scale)
            if not (origin.x <= x < origin.x + client.right and origin.y <= y < origin.y + client.bottom):
                raise RuntimeError('消息区域不在窗口内')
            # Hit-test inside the authorized HWND, not the desktop's topmost
            # window: our own progress/menu window must not stop scrolling.
            target = self.hwnd
            for _ in range(16):
                point = w.POINT(x, y)
                if not self.api.ScreenToClient(target, c.byref(point)):
                    raise RuntimeError('无法定位微信消息子窗口')
                child = self.api.ChildWindowFromPointEx(target, point, 7)
                if not child or child == target:
                    break
                target = child
            if self.api.GetAncestor(target, 2) != self.hwnd:
                raise RuntimeError('消息子窗口归属发生变化，已停止翻页')
            result = c.c_size_t()
            # This client caps a single large wheel delta. Send a bounded
            # burst of ordinary notches, then read one overlapping page.
            wheel_word = ((120 if delta > 0 else -120) & 0xffff) << 16
            for _ in range(max(1, min(12, abs(int(delta)) // 120))):
                if not self.api.SendMessageTimeoutW(target, 0x20a, wheel_word,
                        (x & 0xffff) | ((y & 0xffff) << 16), 2, 1000, c.byref(result)):
                    raise RuntimeError('滚动未确认，已停止，未重试')
                if after_step:
                    after_step()
        finally:
            self.api.SetThreadDpiAwarenessContext(old)


def message_count(records):
    return sum(kind == 'message' for kind, _ in records)


def page_state(page):
    # A tall bubble may occupy several scrolls without changing its text.
    # Coordinates and object tokens distinguish movement from an actual end.
    return (page['records'], page.get('record_keys'), page.get('record_rects'))


def measured_scroll(before, after, delta):
    """Estimate pixels per wheel notch from surviving, unchanged bubbles."""
    old = {key: (record, rect) for key, record, rect in zip(
        before.get('record_keys', []), before['records'], before.get('record_rects', []))}
    shifts = []
    for key, record, rect in zip(after.get('record_keys', []), after['records'], after.get('record_rects', [])):
        if key not in old or old[key][0] != record:
            continue
        prior = old[key][1]
        if (prior[0], prior[2], prior[3]-prior[1]) == (rect[0], rect[2], rect[3]-rect[1]) and rect[1] > prior[1]:
            shifts.append(rect[1]-prior[1])
    if not shifts or max(shifts)-min(shifts) > 2:
        return None
    return max(shifts) * 120 / delta


def scroll_delta(page, pixels_per_notch):
    if not pixels_per_notch:
        return 120  # Calibrate once instead of assuming system wheel settings.
    distance = scroll_distance(page)
    return 120 * max(1, min(12, int(distance / pixels_per_notch)))


def scroll_distance(page):
    """Keep the first two visible bubbles, allowing for a clipped tall one."""
    _, top, _, bottom = page['rect']
    height = max(1, bottom - top)
    bubbles = sorted((rect for record, rect in zip(page['records'], page.get('record_rects', []))
                      if record[0] == 'message' and rect[3] > top and rect[1] < bottom),
                     key=lambda rect: rect[1])
    if not bubbles:
        bubbles = sorted((rect for rect in page.get('record_rects', [])
                          if rect[3] > top and rect[1] < bottom), key=lambda rect: rect[1])
        if not bubbles:
            return height * .55
    # Retain at least 24 logical pixels of the second bubble. If only one
    # large bubble fills the viewport, retain that bubble instead.
    anchor = bubbles[min(1, len(bubbles)-1)]
    margin = min(24, max(1, (anchor[3]-anchor[1]) / 2))
    safe = bottom - max(top, anchor[1]) - margin
    return max(1, min(height * .65, safe * .8))


def newest_messages(records, limit):
    """Keep the latest N bubbles and the labels immediately preceding them."""
    positions = [i for i, (kind, _) in enumerate(records) if kind == 'message']
    if len(positions) <= limit:
        return records
    start = positions[-limit]
    while start > 0 and records[start - 1][0] == 'label':
        start -= 1
    return records[start:]


def seek_latest(window, reader, page, check, progress=None):
    """Probe downward first; keep scrolling until the loaded viewport stops."""
    identity = page['identity']
    deadline = time.monotonic() + 120
    if progress:
        progress(None)
    for attempt in range(256):
        check()
        if time.monotonic() >= deadline:
            break
        window.wheel(page['rect'], -120 if attempt == 0 else -1440)
        candidate, stable = None, 0
        for poll in range(8):
            time.sleep(.1 if poll == 0 else .3)
            check()
            try:
                current = reader.read(window.hwnd, window.pid)
            except RuntimeError as exc:
                if '变化' not in str(exc):
                    raise
                candidate, stable = None, 0
                continue
            check()
            if current['identity'] != identity:
                raise RuntimeError('返回最新消息时会话发生变化，已停止')
            stable = stable + 1 if candidate and page_state(current) == page_state(candidate) else 0
            candidate = current
            if stable >= 1:
                break
        if stable < 1:
            raise RuntimeError('返回最新消息时页面尚未稳定，请重试')
        if page_state(candidate) == page_state(page):
            return candidate
        page = candidate
    raise RuntimeError('尚未确认到达最新消息，未开始历史读取，请手动回到底部后重试')


def read_qt_history(hwnd, pages=1, cancelled=lambda: False, max_messages=None, validate_session=None, progress=None, start_latest=False):
    limit = max(1, min(1000, int(max_messages))) if max_messages is not None else None
    window, reader = HistoryWindow(hwnd), QtChatRows(messages=True)
    session_error = None
    def check():
        nonlocal session_error
        if validate_session:
            try:
                validate_session()
            except Exception as exc:
                session_error = exc
                raise
        if cancelled():
            raise RuntimeError('已取消历史读取')
    check()
    page = reader.read(hwnd, window.pid)
    check()
    if start_latest:
        page = seek_latest(window, reader, page, check, progress)
    identity = page['identity']
    numbering = ReadNumbers()
    numbering.page(page, commit=True)
    if progress:
        progress(window.annotation(page, numbering.page(page)))
    records, count, note = page['records'], 1, '仅包含当前消息区域的可见文本；发送人和稳定消息 ID 尚未解析。'
    keys = page.get('record_keys', [])
    if not records:
        raise RuntimeError('当前会话没有可读取文本')
    deadline = time.monotonic() + (300 if limit else 30)
    pixels_per_notch = None
    for _ in range(1000 if limit else max(0, min(20, int(pages)) - 1)):
        try:
            check()
            if limit and message_count(records) >= limit:
                break
            if time.monotonic() > deadline:
                note += ' 已达到读取时限。'
                break
            # Input elsewhere is harmless. Only an actual change to our
            # message viewport between batches invalidates the next scroll.
            fresh = reader.read(hwnd, window.pid)
            check()
            if fresh['identity'] != identity:
                raise RuntimeError('消息列表身份变化，已停止读取')
            if page_state(fresh) != page_state(page):
                raise RuntimeError('消息区域在翻页间发生变化，已暂停，请重新读取')
            delta = scroll_delta(page, pixels_per_notch)
            def follow_boxes():
                if cancelled():
                    raise RuntimeError('已取消历史读取')
                try:
                    tracked = reader.track(hwnd, window.pid, page)
                    progress(window.annotation(tracked, numbering.page(tracked)))
                except Exception:
                    progress(None)
            if progress:
                window.wheel(page['rect'], delta, after_step=follow_boxes)
            else:
                window.wheel(page['rect'], delta)
            previous = page
            # Wait for scrolling/loading to settle; no additional scroll while waiting.
            stable, candidate = 0, None
            # Compare the viewport after one scroll, then confirm once after
            # a short loading grace period. Geometry is part of page_state:
            # unchanged text in a moving tall bubble cannot signal the end.
            for poll in range(8):
                delay = .075 if poll == 0 else .3
                if progress:
                    until = time.monotonic() + delay
                    while time.monotonic() < until:
                        follow_boxes()
                        time.sleep(.03)
                else:
                    time.sleep(delay)
                check()
                try:
                    current = reader.read(hwnd, window.pid)
                except RuntimeError as exc:
                    if '变化' not in str(exc):
                        raise
                    stable, candidate = 0, None
                    continue  # Scroll animation may invalidate one snapshot.
                check()
                if current['identity'] != identity:
                    raise RuntimeError('消息列表身份变化，已停止读取')
                if progress:
                    progress(window.annotation(current, numbering.page(current)))
                stable = stable + 1 if candidate and page_state(candidate) == page_state(current) else 0
                candidate = current
                if stable >= 1:
                    break
            if stable < 1:
                raise RuntimeError('页面尚未稳定，已停止读取')
            if progress:
                progress(window.annotation(candidate, numbering.page(candidate)))
            if page_state(candidate) == page_state(previous):
                note += ' 向上滚动后，消息控件位置和内容经复核仍未变化，已结束读取；若历史延迟加载，可再次读取。'
                break
            measured = measured_scroll(previous, candidate, delta)
            if measured:
                # Partial motion at the history boundary must not cause the
                # next batch to grow dramatically. Increase speed gradually.
                pixels_per_notch = max(measured, pixels_per_notch * .85) if pixels_per_notch else measured
            else:
                # Reflow/changed heights invalidate the previous calibration.
                pixels_per_notch = None
            if (candidate['records'] == previous['records'] and
                    candidate.get('record_keys') == previous.get('record_keys')):
                page = candidate
                continue
            merged, merged_keys = merge_pages(candidate, records, keys, previous)
            if merged is None:
                # Recycled bubbles and late-loaded cards may temporarily
                # change text/labels after their positions have settled.
                # Retry this position, never scroll farther across a gap.
                for retry in range(2):
                    time.sleep(.2)
                    check()
                    refreshed = reader.read(hwnd, window.pid)
                    check()
                    if refreshed['identity'] != identity:
                        raise RuntimeError('消息列表身份变化，已停止读取')
                    merged, merged_keys = merge_pages(refreshed, records, keys, previous)
                    if merged is not None:
                        candidate = refreshed
                        pixels_per_notch = None
                        break
                if merged is None:
                    note += ' 当前页复核后仍缺少可靠重叠，已停止合并以避免漏记或重复。'
                    break
            records, page, count = merged, candidate, count + 1
            keys = merged_keys
            numbering.page(page, commit=True)
            if progress:
                progress(window.annotation(page, numbering.page(page)))
        except Exception as exc:
            note += ' ' + str(exc)
            break
    else:
        if limit:
            note += ' 已达到滚动次数保护上限。'
    # Never return even a partial result if its bound conversation changed.
    if session_error is not None:
        raise session_error
    if validate_session:
        validate_session()
    if limit:
        records = newest_messages(records, limit)
        found = message_count(records)
        note += ' 已读取 %d/%d 条消息（时间标签不计数）。' % (found, limit)
        if found >= limit:
            note += ' 已达到指定消息条数。'
    content = '\n\n'.join(text for _, text in records)
    return WeChatSnapshot(conversation=content, readable=bool(content), pages_read=count,
                          warning=note + (' 页面停留在本次读取位置。' if limit or pages > 1 else ''),
                          messages_read=message_count(records))
