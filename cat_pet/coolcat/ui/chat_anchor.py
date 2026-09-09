"""Asynchronous UIA row geometry cache; all pet movement stays on the GUI thread."""
import threading
import time
from types import SimpleNamespace

from PyQt5.QtCore import QObject, QPoint, pyqtSignal

from ..platform.chat_backend import session_rectangles


class ChatAnchor(QObject):
    completed = pyqtSignal(object, object, object)

    def __init__(self, attachment):
        super().__init__(attachment)
        self.attachment = attachment
        self.key = None
        self.rows = []
        self.at = 0
        self.busy = False
        self.session = None
        self.error = ''
        from ..platform.qt_chat_rows import QtChatRows
        self.native_rows = QtChatRows()
        self.completed.connect(self.receive)

    def clear(self):
        self.session = None
        self.key = None
        self.rows = []
        self.at = 0

    def refresh(self, target):
        key = (target.hwnd, target.pid)
        if self.key != key:
            self.rows = []
            self.at = 0
            self.key = key
        if self.busy or time.monotonic() - self.at < .25:
            return
        self.busy = True
        frame = (target.rect.x(), target.rect.y(), target.rect.width(), target.rect.height())
        def work():
            try:
                try:
                    rows = session_rectangles(target.hwnd)
                except Exception:
                    rows = []
                if not rows:
                    rows = self.native_rows.physical_rows(target.hwnd, target.pid)
            except Exception as exc:
                rows = str(exc)
            try:
                self.completed.emit(key, frame, rows)
            except RuntimeError:
                pass  # Owner was destroyed while a bounded read was finishing.
        threading.Thread(target=work, daemon=True).start()

    def receive(self, key, frame, rows):
        self.busy = False
        if key != self.key:
            return
        target = self.attachment.backend.get(key[0])
        if not target or target.pid != key[1]:
            return
        current = (target.rect.x(), target.rect.y(), target.rect.width(), target.rect.height())
        self.rows = []
        self.at = time.monotonic()
        self.error = rows if isinstance(rows, str) else ''
        if self.error:
            return
        if current != frame:
            return
        self.frame = frame
        for session, bounds in rows:
            rect = SimpleNamespace(**dict(zip(('left', 'top', 'right', 'bottom'), bounds)))
            self.rows.append((session, self.attachment.backend.logical_rect(key[0], rect)))

    def visible_rows(self, target):
        self.refresh(target)
        frame = (target.rect.x(), target.rect.y(), target.rect.width(), target.rect.height())
        if time.monotonic() - self.at > .8 or getattr(self, 'frame', None) != frame:
            return []
        return self.rows

    def hit(self, target, cursor):
        rows = self.visible_rows(target)
        return next(((s, r) for s, r in rows if r.contains(cursor)), None)

    def position(self, target):
        rect = next((r for s, r in self.visible_rows(target) if s == self.session), None)
        if rect is None:
            return None
        pet = self.attachment.pet
        return QPoint(rect.right() + 1 - pet.width() // 2,
                      rect.center().y() - pet.height() // 2)
