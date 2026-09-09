"""Read-only, version-locked candidate scan; outputs pointers, never chat data."""
import ctypes as c
from ctypes import wintypes as w
import hashlib
import json
from pathlib import Path
import struct
import time


class Region(c.Structure):
    _fields_ = [('base', c.c_void_p), ('allocation', c.c_void_p),
                ('allocation_protect', w.DWORD), ('partition', w.WORD),
                ('size', c.c_size_t), ('state', w.DWORD),
                ('protect', w.DWORD), ('kind', w.DWORD)]


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--base', type=lambda s: int(s, 0), required=True)
    parser.add_argument('--messages', action='store_true', help='Inspect message-list objects, not session-list objects')
    parser.add_argument('--text-fields', action='store_true', help='Inspect bounded QString candidates in message text controls')
    args = parser.parse_args()
    target_name = 'chat_message_list' if args.messages else 'session_list'
    binary = Path(r'C:\Program Files\Tencent\Weixin\4.1.13.12\Weixin.dll')
    with binary.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    if digest != 'e3240bf8a4d00593a4b3e6ce6c8b6ac26897622c27f410f6655c4eee17cb3b6d':
        raise RuntimeError('Unsupported binary fingerprint')
    api = c.WinDLL('kernel32', use_last_error=True)
    api.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    api.OpenProcess.restype = w.HANDLE
    api.CloseHandle.argtypes = [w.HANDLE]
    api.VirtualQueryEx.argtypes = [w.HANDLE, c.c_void_p, c.POINTER(Region), c.c_size_t]
    api.VirtualQueryEx.restype = c.c_size_t
    api.ReadProcessMemory.argtypes = [w.HANDLE, c.c_void_p, c.c_void_p, c.c_size_t, c.POINTER(c.c_size_t)]
    handle = api.OpenProcess(0x410, False, args.pid)
    if not handle:
        raise c.WinError(c.get_last_error())
    def read(address, length):
        buffer = c.create_string_buffer(length)
        count = c.c_size_t()
        if not api.ReadProcessMemory(handle, address, buffer, length, c.byref(count)):
            return b''
        return buffer.raw[:count.value]
    found = []
    def pointer(address):
        data = read(address, 8)
        return struct.unpack('<Q', data)[0] if len(data) == 8 else 0

    def name_matches(candidate):
        # Candidate storage chain derived from RVA 0x26bf80, not a general
        # QObject ABI. Compare only one fixed identifier; never print text.
        private = pointer(candidate + 8)
        extra = pointer(private + 0x30) if private else 0
        string = pointer(extra + 0x28) if extra else 0
        header = read(string, 24) if string else b''
        if len(header) != 24:
            return False
        size = struct.unpack_from('<i', header, 4)[0]
        displacement = struct.unpack_from('<q', header, 16)[0]
        if size != len(target_name) or not 0 < displacement < 4096:
            return False
        return read(string + displacement, size * 2) == target_name.encode('utf-16-le')

    def ancestry(candidate):
        # Qt 5 QObjectData hypothesis; require q_ptr back-reference at each
        # level. Return only addresses and ownership evidence, not names.
        result = []
        visited = set()
        while candidate and candidate not in visited and len(result) < 32:
            visited.add(candidate)
            private = pointer(candidate + 8)
            if not private or pointer(private + 8) != candidate:
                result.append({'address': hex(candidate), 'q_ptr_verified': False})
                break
            parent = pointer(private + 0x10)
            geometry = {}
            # QWidget::data at +0x28 is a layout hypothesis, not yet an API.
            widget_data = pointer(candidate + 0x28)
            raw = read(widget_data, 36) if widget_data else b''
            if len(raw) == 36:
                geometry = {'hwnd_candidate': hex(struct.unpack_from('<Q', raw)[0]),
                            'attributes_candidate': hex(struct.unpack_from('<I', raw, 8)[0]),
                            'rect_candidate': struct.unpack_from('<4i', raw, 20)}
            result.append({'address': hex(candidate), 'q_ptr_verified': True,
                           'parent': hex(parent),
                           'geometry_candidate': geometry,
                           'parent_owns_at_1d0': bool(parent and pointer(parent + 0x1d0) == candidate),
                           'parent_owns_at_210': bool(parent and pointer(parent + 0x210) == candidate)})
            candidate = parent
        return result

    def rows_under(candidate):
        result, stack, visited, types = [], [(candidate, 0)], set(), {}
        while stack and len(visited) < 500:
            obj, depth = stack.pop()
            if obj in visited or depth > 16:
                continue
            visited.add(obj)
            private = pointer(obj + 8)
            if not private or pointer(private + 8) != obj:
                continue
            if args.messages:
                # Inspect static Qt class metadata, without executing virtual methods.
                method = pointer(pointer(obj))
                code = read(method, 32)
                at = code.find(b'\x48\x8d\x05')
                if 0 <= at <= 24 and len(code) >= at + 7:
                    meta = method + at + 7 + struct.unpack_from('<i', code, at + 3)[0]
                    strings = pointer(meta + 8)
                    info = read(strings, 24) if strings else b''
                    if len(info) == 24:
                        size = struct.unpack_from('<i', info, 4)[0]
                        offset = struct.unpack_from('<q', info, 16)[0]
                        if 0 < size < 160 and 0 < offset < 65536:
                            label = read(strings + offset, size).decode('ascii', 'replace')
                            if label and all(ch.isalnum() or ch in ':_' for ch in label):
                                entry = types.setdefault(label, {'count': 0, 'examples': [],
                                    'meta_rva': hex(meta - args.base),
                                    'metacall_rva': hex(pointer(meta + 24) - args.base)})
                                entry['count'] += 1
                                if len(entry['examples']) < 2:
                                    entry['examples'].append(hex(obj))
                                if label == 'mmui::XTextView':
                                    engine = pointer(pointer(obj + 0x3e0))
                                    getter = pointer(pointer(engine) + 0x150) if engine else 0
                                    if getter:
                                        entry.setdefault('text_getter_rvas', [])
                                        rva = hex(getter - args.base)
                                        if rva not in entry['text_getter_rvas']:
                                            entry['text_getter_rvas'].append(rva)
                                        if args.text_fields and getter == args.base + 0x2370fe0:
                                            header = read(engine + 0x90, 32)
                                            if len(header) == 32:
                                                size, capacity = struct.unpack_from('<2Q', header, 16)
                                                if 0 < size <= 16384 and size <= capacity <= 1048576:
                                                    source = engine + 0x90 if capacity < 16 else struct.unpack_from('<Q', header)[0]
                                                    raw = read(source, size)
                                                    if len(raw) == size and read(engine + 0x90, 32) == header:
                                                        try:
                                                            text = raw.decode('utf-8')
                                                            chain = ancestry(obj)
                                                            visible = all(int(e.get('geometry_candidate', {}).get('attributes_candidate', '0'), 16) & 0x8000 for e in chain)
                                                            if visible:
                                                                entry.setdefault('verified_getter_texts', []).append({'object': hex(obj), 'text': text[:500]})
                                                        except UnicodeError:
                                                            pass
                                if args.text_fields and label == 'mmui::XTextView':
                                    matches = []
                                    for field in range(0x30, 0x300, 8):
                                        header = read(obj + field, 32)
                                        if len(header) != 32:
                                            continue
                                        size, capacity = struct.unpack_from('<2Q', header, 16)
                                        if not 2 <= size <= 2048 or not size <= capacity <= 65535:
                                            continue
                                        address = obj + field if capacity < 16 else struct.unpack_from('<Q', header)[0]
                                        raw = read(address, size + 1)
                                        if len(raw) != size + 1 or raw[-1] != 0:
                                            continue
                                        try:
                                            value = raw[:-1].decode('utf-8')
                                        except UnicodeError:
                                            continue
                                        if all(ord(ch) >= 32 or ch in '\r\n\t' for ch in value):
                                            matches.append({'offset': hex(field), 'storage_candidate': 'std_string', 'text': value[:300]})
                                    for field in range(0x30, 0x300, 8):
                                        storage = pointer(obj + field)
                                        info = read(storage, 24) if storage else b''
                                        if len(info) != 24:
                                            continue
                                        refs, size, alloc = struct.unpack_from('<3i', info)
                                        displacement = struct.unpack_from('<q', info, 16)[0]
                                        if not 1 <= size <= 2048 or not -1 <= refs <= 10000 or not 0 < displacement < 4096:
                                            continue
                                        if alloc != 0 and (alloc & 0x7fffffff) < size:
                                            continue
                                        raw = read(storage + displacement, size * 2 + 2)
                                        if len(raw) != size * 2 + 2 or raw[-2:] != b'\x00\x00':
                                            continue
                                        try:
                                            value = raw[:-2].decode('utf-16-le')
                                        except UnicodeError:
                                            continue
                                        if any(ord(ch) < 32 and ch not in '\r\n\t' for ch in value):
                                            continue
                                        matches.append({'offset': hex(field), 'text': value[:300]})
                                    if matches:
                                        entry.setdefault('text_candidates', []).append({'object': hex(obj), 'fields': matches})
            extra = pointer(private + 0x30)
            string = pointer(extra + 0x28) if extra else 0
            header = read(string, 24) if string else b''
            if len(header) == 24:
                size = struct.unpack_from('<i', header, 4)[0]
                displacement = struct.unpack_from('<q', header, 16)[0]
                if 13 <= size <= 256 and 0 < displacement < 4096:
                    prefix = read(string + displacement, size * 2).decode('utf-16-le', 'replace')
                    if (('chat_bubble_item_view' in prefix) if args.messages else prefix.startswith('session_item_')):
                        result.append({'address': hex(obj), 'depth': depth,
                                       'row_prefix_match': True,
                                       'ancestry': ancestry(obj)})
            children = pointer(private + 0x18)
            data = read(children, 16) if children else b''
            if len(data) != 16:
                continue
            _, allocated, begin, end = struct.unpack('<4i', data)
            if not 0 <= begin <= end <= allocated <= 4096:
                continue
            for index in range(begin, min(end, begin + 200)):
                child = pointer(children + 16 + 8 * index)
                if child and pointer(pointer(child + 8) + 0x10) == obj:
                    stack.append((child, depth + 1))
        return {'visited': len(visited), 'rows': result, 'types': types}
    total = 0
    started = time.monotonic()
    address = 0
    expected = {0: 0x8e64c78, 0x10: 0x8e64e78, 0x30: 0x8e64eb8,
                0x70: 0x8e64ef8, 0xa8: 0x8e64f38}
    if args.messages:
        expected = {0: 0x8efbed8, 0x10: 0x8efc118, 0x30: 0x8efc158, 0x68: 0x8efc188}
    marker = struct.pack('<Q', args.base + expected[0])
    try:
        if read(args.base, 2) != b'MZ':
            raise RuntimeError('Module base is invalid')
        while total < 512 * 1024 * 1024 and time.monotonic() - started < 25:
            region = Region()
            if not api.VirtualQueryEx(handle, address, c.byref(region), c.sizeof(region)):
                break
            next_address = (region.base or 0) + region.size
            if next_address <= address:
                break
            if region.state == 0x1000 and region.kind == 0x20000 and region.protect in (4, 8, 0x40, 0x80):
                offset = 0
                while offset < region.size and total < 512 * 1024 * 1024 and time.monotonic() - started < 25:
                    length = min(1024 * 1024, region.size - offset)
                    chunk = read(address + offset, length)
                    total += length
                    index = chunk.find(marker)
                    while index >= 0:
                        candidate = address + offset + index
                        if candidate % 8 == 0:
                            header = read(candidate, 0xb0)
                            if len(header) == 0xb0 and all(struct.unpack_from('<Q', header, field)[0] == args.base + rva for field, rva in expected.items()):
                                found.append({'address': hex(candidate),
                                              'session_list_name_match': name_matches(candidate),
                                              'ancestry_candidate': ancestry(candidate),
                                              'descendants': rows_under(candidate)})
                        index = chunk.find(marker, index + 1)
                    offset += length
            address = next_address
        def summarize_chain(chain):
            geos = [entry.get('geometry_candidate', {}) for entry in chain]
            rects = [g.get('rect_candidate') for g in geos]
            complete = bool(chain and chain[-1].get('parent') == '0x0' and all(rects))
            return {'complete': complete, 'local': rects[0] if rects else None,
                    'ancestor_hwnd': geos[-1].get('hwnd_candidate') if geos else None,
                    'visible_bits': [bool(int(g.get('attributes_candidate', '0'), 16) & 0x8000) for g in geos],
                    'offset_to_window': [sum(r[0] for r in rects[:-1]), sum(r[1] for r in rects[:-1])] if complete else None}
        compact = [{'address': item['address'], 'name_match': item['session_list_name_match'],
                    'geometry': summarize_chain(item['ancestry_candidate']),
                    'visited': item['descendants']['visited'],
                    'types': item['descendants']['types'],
                    'rows': [{'address': row['address'], 'geometry': summarize_chain(row['ancestry'])}
                             for row in item['descendants']['rows']]} for item in found]
        print(json.dumps({'pid': args.pid, 'module_base': hex(args.base),
                          'scanned_bytes': total, 'seconds': round(time.monotonic() - started, 2),
                          'candidate_instances': compact,
                          'note': 'Matching vtables only; lifetime and window ownership are unverified.'}))
    finally:
        api.CloseHandle(handle)


if __name__ == '__main__':
    main()
