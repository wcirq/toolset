"""Click-through, geometry-only annotations for the page being read."""
import time
from types import SimpleNamespace
from PyQt5.QtCore import Qt, QRectF, QTimer
from PyQt5.QtGui import QColor, QFont, QPainter, QPen
from PyQt5.QtWidgets import QWidget


class MessageReadOverlay(QWidget):
    def __init__(self, backend, hwnd, parent=None):
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint |
                         Qt.WindowStaysOnTopHint | Qt.WindowTransparentForInput |
                         Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.backend, self.hwnd = backend, hwnd
        self.boxes = []
        self.numbers, self.parts = [], []
        self.provisional = False
        self.expires = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.expire)
        self.timer.start(100)

    def expire(self):
        if time.monotonic() > self.expires or not self.target_active():
            self.hide()

    def target_active(self):
        foreground = self.backend.api.GetForegroundWindow()
        # Opening the pet's own menu can give its window foreground ownership.
        parent = self.parentWidget()
        return foreground == self.hwnd or (parent is not None and
                                            foreground == int(parent.window().winId()))

    def display(self, data):
        if not data or not self.target_active():
            self.hide()
            return
        def logical(bounds):
            return self.backend.logical_rect(self.hwnd, SimpleNamespace(
                **dict(zip(('left', 'top', 'right', 'bottom'), bounds))))
        clip = logical(data['clip'])
        if clip.isEmpty():
            return
        if self.geometry() != clip:
            self.setGeometry(clip)
        self.boxes = []
        self.numbers, self.parts = [], []
        self.provisional = bool(data.get('provisional', False))
        for index, box in enumerate(data['boxes']):
            rect = logical(box).intersected(clip)
            if not rect.isEmpty():
                rect.translate(-clip.x(), -clip.y())
                self.boxes.append(QRectF(rect))
                numbers = data.get('numbers', [])
                self.numbers.append(numbers[index] if index < len(numbers) else None)
        for part in data.get('parts', []):
            rect = logical(part['rect']).intersected(clip)
            if not rect.isEmpty():
                rect.translate(-clip.x(), -clip.y())
                self.parts.append((part['kind'], QRectF(rect)))
        self.expires = time.monotonic() + .8
        self.show()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setFont(QFont('Segoe UI', 9, QFont.Bold))
        for number, box in zip(self.numbers, self.boxes):
            rect = box.adjusted(2, 2, -2, -2)
            alpha = 145 if self.provisional else 210
            painter.setPen(QPen(QColor(70, 215, 195, alpha), 1.5))
            painter.setBrush(QColor(70, 215, 195, 15))
            painter.drawRoundedRect(rect, 9, 9)
            if number is None:
                continue
            badge = QRectF(rect.left()+7, rect.top()+5, max(28, len(str(number))*9+12), 22)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(20, 120, 112, 235))
            painter.drawRoundedRect(badge, 7, 7)
            painter.setPen(QColor('white'))
            painter.drawText(badge, Qt.AlignCenter, str(number).zfill(2))
        styles = {'avatar': ('#a78bfa', 2, Qt.SolidLine, '头像'),
                  'nickname': ('#f472b6', 1.5, Qt.DashLine, '昵称候选'),
                  'image': ('#fb923c', 2, Qt.SolidLine, '图片区域'),
                  'time': ('#fbbf24', 1, Qt.DashLine, '时间'),
                  'link': ('#60a5fa', 2, Qt.DashLine, '链接'),
                  'text': ('#67e8f9', 1, Qt.DotLine, '文本')}
        painter.setFont(QFont('Microsoft YaHei', 8))
        for kind, box in self.parts:
            color, width, line, label = styles.get(kind, styles['text'])
            painter.setPen(QPen(QColor(color), width, line))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(box.adjusted(1, 1, -1, -1), 4, 4)
            painter.drawText(box.adjusted(3, 1, -3, -1), Qt.AlignRight | Qt.AlignTop, label)
