"""Version-specific read-only Qt row geometry. No injection or send capability."""
import ctypes as c
from ctypes import wintypes as w
import hashlib
import struct
import time
from pathlib import Path

from .chat_backend import Session


FINGERPRINT = 'e3240bf8a4d00593a4b3e6ce6c8b6ac26897622c27f410f6655c4eee17cb3b6d'
VTABLES = {0: 0x8e64c78, 0x10: 0x8e64e78, 0x30: 0x8e64eb8,
           0x70: 0x8e64ef8, 0xa8: 0x8e64f38}


class Region(c.Structure):
    _fields_ = [('base', c.c_void_p), ('allocation', c.c_void_p),
                ('allocation_protect', w.DWORD), ('partition', w.WORD),
                ('size', c.c_size_t), ('state', w.DWORD),
                ('protect', w.DWORD), ('kind', w.DWORD)]


def clip_rect(rect, clip):
    box = (max(rect[0], clip[0]), max(rect[1], clip[1]),
           min(rect[2], clip[2]), min(rect[3], clip[3]))
    return box if box[2] > box[0] and box[3] > box[1] else None


class QtChatRows:
    def __init__(self, messages=False):
        self.messages = messages
        self.key = None
        self.candidates = []
        self.next_scan = 0
        self.verified_file = None

    def physical_rows(self, hwnd, pid):
        api = c.WinDLL('user32', use_last_error=True)
        api.SetThreadDpiAwarenessContext.argtypes = [c.c_void_p]
        api.SetThreadDpiAwarenessContext.restype = c.c_void_p
        api.GetDpiForWindow.argtypes = [w.HWND]
        api.ClientToScreen.argtypes = [w.HWND, c.POINTER(w.POINT)]
        api.GetClientRect.argtypes = [w.HWND, c.POINTER(w.RECT)]
        api.GetWindowThreadProcessId.argtypes = [w.HWND, c.POINTER(w.DWORD)]
        old = api.SetThreadDpiAwarenessContext(c.c_void_p(-4))
        if not old:
            raise RuntimeError('无法读取物理屏幕坐标')
        def frame():
            owner, origin, rect = w.DWORD(), w.POINT(), w.RECT()
            api.GetWindowThreadProcessId(hwnd, c.byref(owner))
            if owner.value != pid or not api.ClientToScreen(hwnd, c.byref(origin)) or not api.GetClientRect(hwnd, c.byref(rect)):
                raise RuntimeError('目标窗口已失效')
            return origin.x, origin.y, rect.right, rect.bottom, api.GetDpiForWindow(hwnd)
        try:
            before = frame()
            rows = self.read(hwnd, pid)
            if frame() != before or not before[4]:
                raise RuntimeError('窗口移动或缩放中，等待坐标稳定')
            x, y, width, height, dpi = before
            scale = dpi / 96
            result = []
            for session, rect in rows:
                physical = tuple(round(v * scale) + (x if i % 2 == 0 else y) for i, v in enumerate(rect))
                physical = clip_rect(physical, (x, y, x + width, y + height))
                if physical:
                    result.append((session, physical))
            return result
        finally:
            api.SetThreadDpiAwarenessContext(old)

    def read(self, hwnd, pid):
        api = c.WinDLL('kernel32', use_last_error=True)
        api.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
        api.OpenProcess.restype = w.HANDLE
        api.CloseHandle.argtypes = [w.HANDLE]
        api.ReadProcessMemory.argtypes = [w.HANDLE, c.c_void_p, c.c_void_p, c.c_size_t, c.POINTER(c.c_size_t)]
        api.VirtualQueryEx.argtypes = [w.HANDLE, c.c_void_p, c.POINTER(Region), c.c_size_t]
        api.VirtualQueryEx.restype = c.c_size_t
        api.GetProcessTimes.argtypes = [w.HANDLE] + [c.POINTER(w.FILETIME)] * 4
        handle = api.OpenProcess(0x410, False, pid)
        if not handle:
            raise RuntimeError('无法只读访问微信进程：%s' % c.WinError(c.get_last_error()))
        try:
            def read(address, length):
                if not address or length <= 0 or length > 1024 * 1024:
                    return b''
                data, count = c.create_string_buffer(length), c.c_size_t()
                if not api.ReadProcessMemory(handle, address, data, length, c.byref(count)) or count.value != length:
                    return b''
                return data.raw
            def ptr(address):
                data = read(address, 8)
                return struct.unpack('<Q', data)[0] if data else 0
            ps = c.WinDLL('psapi', use_last_error=True)
            ps.EnumProcessModulesEx.argtypes = [w.HANDLE, c.POINTER(w.HMODULE), w.DWORD, c.POINTER(w.DWORD), w.DWORD]
            ps.GetModuleFileNameExW.argtypes = [w.HANDLE, w.HMODULE, w.LPWSTR, w.DWORD]
            modules, needed = (w.HMODULE * 2048)(), w.DWORD()
            if not ps.EnumProcessModulesEx(handle, modules, c.sizeof(modules), c.byref(needed), 3):
                raise RuntimeError('无法枚举微信模块')
            base, binary = 0, None
            for module in modules[:min(needed.value // c.sizeof(w.HMODULE), 2048)]:
                path = c.create_unicode_buffer(32768)
                if ps.GetModuleFileNameExW(handle, module, path, len(path)) and Path(path.value).name.lower() == 'weixin.dll':
                    base, binary = int(module), Path(path.value)
                    break
            if not base:
                raise RuntimeError('未找到 Weixin.dll')
            stamp = binary.stat()
            file_key = (str(binary), stamp.st_size, stamp.st_mtime_ns)
            if file_key != self.verified_file:
                with binary.open('rb') as stream:
                    if hashlib.file_digest(stream, 'sha256').hexdigest() != FINGERPRINT:
                        raise RuntimeError('聊天行内存定位只支持已核对的微信 4.1.13.12 安装包')
                self.verified_file = file_key
            times = [w.FILETIME() for _ in range(4)]
            if not api.GetProcessTimes(handle, *[c.byref(t) for t in times]):
                raise RuntimeError('无法核对进程生命周期')
            key = (pid, times[0].dwHighDateTime, times[0].dwLowDateTime, base)
            if key != self.key:
                self.key, self.candidates, self.next_scan = key, [], 0

            tables = ({0: 0x8efbed8, 0x10: 0x8efc118, 0x30: 0x8efc158, 0x68: 0x8efc188}
                      if self.messages else VTABLES)
            list_name = 'chat_message_list' if self.messages else 'session_list'
            def valid(obj):
                return all(ptr(obj + offset) == base + rva for offset, rva in tables.items())
            def name(obj):
                private = ptr(obj + 8)
                if not private or ptr(private + 8) != obj:
                    return ''
                extra = ptr(private + 0x30)
                string = ptr(extra + 0x28) if extra else 0
                header = read(string, 24)
                if not header:
                    return ''
                size, displacement = struct.unpack_from('<i', header, 4)[0], struct.unpack_from('<q', header, 16)[0]
                if not 12 <= size <= 256 or not 0 < displacement < 4096:
                    return ''
                text = read(string + displacement, size * 2).decode('utf-16-le', 'replace')
                return text if (text in ('session_list', 'chat_message_list') or
                                text.startswith('session_item_') or 'chat_bubble_item_view' in text) else ''
            def geometry(obj):
                chain, visited = [], set()
                while obj and obj not in visited and len(chain) < 32:
                    visited.add(obj)
                    private = ptr(obj + 8)
                    if not private or ptr(private + 8) != obj:
                        return None
                    raw = read(ptr(obj + 0x28), 36)
                    if not raw or not struct.unpack_from('<I', raw, 8)[0] & 0x8000:
                        return None
                    rect = struct.unpack_from('<4i', raw, 20)
                    if not 0 < rect[2] - rect[0] + 1 <= 32768 or not 0 < rect[3] - rect[1] + 1 <= 32768:
                        return None
                    parent = ptr(private + 0x10)
                    chain.append(rect)
                    if not parent:
                        if struct.unpack_from('<Q', raw)[0] != hwnd:
                            return None
                        x = sum(r[0] for r in chain[:-1])
                        y = sum(r[1] for r in chain[:-1])
                        first = chain[0]
                        return (x, y, x + first[2] - first[0] + 1, y + first[3] - first[1] + 1)
                    obj = parent
                return None

            if time.monotonic() >= self.next_scan:
                self.candidates = []
                marker, address, total = struct.pack('<Q', base + tables[0]), 0, 0
                deadline = time.monotonic() + 3
                while total < 512 * 1024 * 1024 and time.monotonic() < deadline:
                    region = Region()
                    if not api.VirtualQueryEx(handle, address, c.byref(region), c.sizeof(region)):
                        break
                    end = (region.base or 0) + region.size
                    if end <= address:
                        break
                    if region.state == 0x1000 and region.kind == 0x20000 and region.protect in (4, 8, 0x40, 0x80):
                        offset = 0
                        while offset < region.size and total < 512 * 1024 * 1024 and time.monotonic() < deadline:
                            length = min(1024 * 1024, region.size - offset)
                            data = read(address + offset, length)
                            index = data.find(marker)
                            while index >= 0:
                                obj = address + offset + index
                                if obj % 8 == 0 and valid(obj) and name(obj) == list_name:
                                    self.candidates.append(obj)
                                index = data.find(marker, index + 1)
                            offset += length
                            total += length
                    address = end
                self.next_scan = time.monotonic() + 10
            lists = [(obj, geometry(obj)) for obj in self.candidates if valid(obj) and name(obj) == list_name]
            lists = [(obj, rect) for obj, rect in lists if rect]
            if len(lists) != 1:
                raise RuntimeError('无法唯一定位当前可见聊天列表')
            listing, clip = lists[0]
            if self.messages:
                return self._messages(read, ptr, name, geometry, valid, base, key, listing, clip)
            rows, stack, visited = [], [listing], set()
            while stack and len(visited) < 500:
                obj = stack.pop()
                if obj in visited:
                    continue
                visited.add(obj)
                private = ptr(obj + 8)
                if not private or ptr(private + 8) != obj:
                    continue
                identity = name(obj)
                if identity.startswith('session_item_'):
                    original = geometry(obj)
                    box = original
                    if box:
                        box = clip_rect(box, clip)
                    if box and name(obj) == identity and geometry(obj) == original:
                        rows.append((Session(identity, key + (listing, obj), identity[13:]), box))
                children = ptr(private + 0x18)
                header = read(children, 16)
                if header:
                    _, allocated, begin, end = struct.unpack('<4i', header)
                    if 0 <= begin <= end <= allocated <= 4096:
                        for index in range(begin, min(end, begin + 200)):
                            child = ptr(children + 16 + index * 8)
                            if child and ptr(ptr(child + 8) + 0x10) == obj:
                                stack.append(child)
            if not valid(listing) or geometry(listing) != clip:
                raise RuntimeError('列表在读取时变化，请稍后重试')
            return [row for row in rows if sum(s.automation_id == row[0].automation_id for s, _ in rows) == 1]
        finally:
            api.CloseHandle(handle)

    @staticmethod
    def _messages(read, ptr, name, geometry, valid, base, key, listing, clip):
        groups, visited, stack = {}, set(), [(listing, None)]
        deadline = time.monotonic() + 2
        while stack and len(visited) < 5000 and time.monotonic() < deadline:
            obj, bubble = stack.pop()
            if obj in visited:
                continue
            visited.add(obj)
            private = ptr(obj + 8)
            if not private or ptr(private + 8) != obj:
                continue
            identity = name(obj)
            box = geometry(obj)
            if box and clip_rect(box, clip) and 'chat_bubble_item_view' in identity:
                bubble = obj
                groups.setdefault(bubble, {'rect': box, 'parts': [], 'kind': 'message'})
            # Confirm the actual XTextView static meta-object before reading
            # the Text getter's storage chain. No virtual function invocation.
            method = ptr(ptr(obj))
            code = read(method, 32)
            index = code.find(b'\x48\x8d\x05')
            meta = (method + index + 7 + struct.unpack_from('<i', code, index + 3)[0]
                    if 0 <= index <= 24 else 0)
            if box and (bubble in groups or clip_rect(box, clip)) and meta == base + 0x8b54db8:
                engine = ptr(ptr(obj + 0x3e0))
                if engine and ptr(ptr(engine) + 0x150) == base + 0x2370fe0:
                    header = read(engine + 0x90, 32)
                    if len(header) == 32:
                        size, capacity = struct.unpack_from('<2Q', header, 16)
                        if 0 < size <= 65536 and size <= capacity <= 1048576:
                            source = engine + 0x90 if capacity < 16 else struct.unpack_from('<Q', header)[0]
                            raw = read(source, size)
                            if len(raw) != size or read(engine + 0x90, 32) != header or geometry(obj) != box:
                                raise RuntimeError('消息读取时发生变化，请重新读取')
                            value = raw.decode('utf-8', 'strict').strip()
                            if value:
                                group = bubble if bubble in groups else obj
                                entry = groups.setdefault(group, {'rect': box, 'parts': [], 'kind': 'label'})
                                entry['parts'].append((box[1], box[0], value))
            children = ptr(private + 0x18)
            header = read(children, 16)
            if header:
                _, allocated, begin, end = struct.unpack('<4i', header)
                if 0 <= begin <= end <= allocated <= 4096:
                    for index in range(begin, end):
                        child = ptr(children + 16 + 8 * index)
                        if child and ptr(ptr(child + 8) + 0x10) == obj:
                            stack.append((child, bubble))
        if stack:
            raise RuntimeError('消息控件超过读取上限，本次未作为完整页面返回')
        if not valid(listing) or geometry(listing) != clip:
            raise RuntimeError('消息列表读取期间发生变化')
        records, record_keys, record_rects = [], [], []
        for obj, group in sorted(groups.items(), key=lambda item: (item[1]['rect'][1], item[1]['rect'][0])):
            if geometry(obj) != group['rect']:
                raise RuntimeError('消息位置读取期间发生变化')
            text = '\n'.join(part[2] for part in sorted(group['parts'])) or '[非文本消息或暂不支持的消息类型]'
            records.append((group['kind'], text))
            # A short-lived overlap token, not a business message ID. Reuse
            # is checked against full text by the adjacent-page merger.
            record_keys.append(key + (listing, obj))
            record_rects.append(group['rect'])
        return {'identity': key + (listing,), 'rect': clip, 'records': records,
                'record_keys': record_keys, 'record_rects': record_rects}
