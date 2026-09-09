"""Read-only bounded MSAA diagnostic. No actions, values or message text reads."""
import ctypes as c
from ctypes import wintypes as w
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import comtypes
from comtypes.client import GetModule
from comtypes.automation import VARIANT
from PyQt5.QtWidgets import QApplication
from coolcat.platform.attachment import NativeWindows
from coolcat.platform.wechat import is_wechat_window


def main():
    app = QApplication([])
    module = GetModule('oleacc.dll')
    interface = module.IAccessible
    api = c.OleDLL('oleacc')
    api.AccessibleObjectFromWindow.argtypes = [w.HWND, w.DWORD, c.POINTER(comtypes.GUID), c.POINTER(c.POINTER(interface))]
    api.AccessibleChildren.argtypes = [c.POINTER(interface), c.c_long, c.c_long, c.POINTER(VARIANT), c.POINTER(c.c_long)]
    native = NativeWindows()
    output = []
    root_start = 0
    def tree(obj, child=0, depth=0):
        if len(output) - root_start >= 500 or depth > 16:
            return
        entry = {'depth': depth, 'child': child}
        for key, getter in [('role', lambda: obj.accRole[child]),
                            ('state', lambda: obj.accState[child]),
                            ('rect', lambda: obj.accLocation(child))]:
            try:
                entry[key] = getter()
            except Exception as exc:
                entry[key + '_error'] = str(exc)
        # Only list and list-item names: do not collect arbitrary message labels.
        if entry.get('role') in (33, 34):
            try:
                entry['name'] = obj.accName[child]
            except Exception as exc:
                entry['name_error'] = str(exc)
        output.append(entry)
        if child:
            return
        try:
            count = min(int(obj.accChildCount), 100)
            entry['children'] = count
            if not count:
                return
            variants = (VARIANT * count)()
            obtained = c.c_long()
            api.AccessibleChildren(obj, 0, count, variants, c.byref(obtained))
            for value in variants[:obtained.value]:
                value = value.value
                if isinstance(value, int):
                    tree(obj, value, depth + 1)
                elif value:
                    tree(value.QueryInterface(interface), 0, depth + 1)
        except Exception as exc:
            entry['children_error'] = str(exc)
    for target in native.all():
        if not is_wechat_window(target.title, target.kind, native.process_executable(target.pid)):
            continue
        handles = [target.hwnd]
        callback_type = c.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
        callback = callback_type(lambda hwnd, _: handles.append(int(hwnd)) or True)
        user = c.WinDLL('user32')
        user.EnumChildWindows.argtypes = [w.HWND, callback_type, w.LPARAM]
        user.EnumChildWindows(target.hwnd, callback, 0)
        for hwnd in handles:
            for object_id in (-4, 0):
                output.append({'hwnd': hwnd, 'object_id': object_id})
                root_start = len(output)
                try:
                    obj = c.POINTER(interface)()
                    api.AccessibleObjectFromWindow(hwnd, object_id & 0xffffffff,
                                                   c.byref(interface._iid_), c.byref(obj))
                    if obj:
                        tree(obj)
                except Exception as exc:
                    output[-1]['error'] = str(exc)
    from collections import Counter
    print(json.dumps({'roots': [e for e in output if 'hwnd' in e],
                      'nodes': sum('depth' in e for e in output),
                      'roles': dict(Counter(str(e['role']) for e in output if 'role' in e)),
                      'lists': [e for e in output if e.get('role') in (33, 34)],
                      'errors': [e for e in output if any(k.endswith('error') for k in e)]},
                     ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
