"""Print only anonymous page signatures while validating upward scrolling."""
import hashlib
import sys
import time
from coolcat.platform.qt_history import HistoryWindow, merge_pages
from coolcat.platform.qt_chat_rows import QtChatRows

w = HistoryWindow(int(sys.argv[1]))
r = QtChatRows(messages=True)
def signature(p):
    return [(k, len(t), hashlib.sha256(t.encode()).hexdigest()[:8],
             hex(key[-1]), box) for (k, t), key, box in
            zip(p['records'], p['record_keys'], p['record_rects'])]
a = r.read(w.hwnd, w.pid)
print('before', signature(a))
for i in range(5):
    w.wheel(a['rect'])
    time.sleep(.8)
    b = r.read(w.hwnd, w.pid)
    print(i, signature(b))
    print('merge', merge_pages(b, a['records'], a['record_keys'], a)[0] is not None)
    a = b
