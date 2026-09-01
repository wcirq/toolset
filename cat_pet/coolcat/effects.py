from .common import *


class MonitorEdgeEffect(QWidget):
    """不抢焦点、鼠标穿透的全屏边缘状态特效。"""

    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool |
                         Qt.WindowStaysOnTopHint | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self._enabled = True
        self._extent = 220
        self._started_at = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)

    def flash(self, enabled, extent=None):
        self._enabled = bool(enabled)
        if extent is not None:
            self._extent = max(80, min(600, int(extent)))
        self._started_at = time.monotonic()
        screen = QApplication.primaryScreen()
        area = screen.geometry() if screen else QRectF(0, 0, 1920, 1080).toRect()
        self.setGeometry(area.left(), area.top(), self._extent, self._extent)
        self.show()
        self.raise_()
        self._timer.start()
        self.update()

    def _tick(self):
        duration = 1.35 if self._enabled else 0.95
        if time.monotonic() - self._started_at >= duration:
            self._timer.stop()
            self.hide()
            return
        self.update()

    def paintEvent(self, _event):
        elapsed = time.monotonic() - self._started_at
        if self._enabled:
            # 启用：三次柔和扩散的青绿脉冲。
            phase = min(1.0, elapsed / 1.35)
            pulse = (0.5 + 0.5 * math.sin(elapsed * math.pi * 4.5))
            alpha = int(145 * (1.0 - phase) * (0.55 + 0.45 * pulse))
            width = int(16 + 20 * phase)
            inner = QColor(40, 255, 175, alpha)
            outer = QColor(0, 185, 255, 0)
            label, label_color = "监控已启用  ●", QColor(55, 255, 180, min(245, alpha + 35))
        else:
            # 禁用：两次急促的红橙告警闪烁，中间有明显断层。
            on = ((0.00 <= elapsed < 0.20) or (0.34 <= elapsed < 0.62))
            fade = 1.0 if on else 0.08
            alpha = int(170 * fade * max(0.0, 1.0 - elapsed / 1.15))
            width = 32 if elapsed < 0.62 else 22
            inner = QColor(255, 45, 45, alpha)
            outer = QColor(255, 155, 20, 0)
            label, label_color = "监控已禁用  ✕", QColor(255, 70, 45, min(255, alpha + 20))

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        edges = [
            (QRectF(0, 0, w, width), QPointF(0, 0), QPointF(0, width)),
            (QRectF(0, 0, width, h), QPointF(0, 0), QPointF(width, 0)),
        ]
        for rect, start, end in edges:
            grad = QLinearGradient(start, end)
            grad.setColorAt(0.0, inner)
            grad.setColorAt(1.0, outer)
            p.fillRect(rect, grad)
        p.setPen(label_color)
        p.setFont(QFont("微软雅黑", 11, QFont.Bold))
        p.drawText(QRectF(16, 14, max(1, w - 22), 30),
                   Qt.AlignLeft | Qt.AlignVCenter, label)
        p.end()

# ======================== 粒子效果 ========================
class Particle:
    """单个粒子，用于爱心、星星、Z等视觉效果"""

    def __init__(self, x, y, kind="heart"):
        self.x = float(x)
        self.y = float(y)
        self.vx = random.uniform(-1.5, 1.5)
        self.vy = random.uniform(-3.5, -1.5)
        self.life = 1.0
        self.decay = random.uniform(0.012, 0.025)
        self.size = random.uniform(12, 20)
        self.kind = kind
        self.rot = random.uniform(0, 360)
        self.rot_spd = random.uniform(-4, 4)
        self.gravity = 0.06

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.vy += self.gravity
        self.life -= self.decay
        self.rot += self.rot_spd

    @property
    def alive(self):
        return self.life > 0

    def draw(self, painter):
        if self.life <= 0:
            return
        painter.save()
        painter.translate(self.x, self.y)
        painter.rotate(self.rot)
        painter.setOpacity(max(0.0, min(1.0, self.life)))
        if self.kind == "heart":
            self._draw_heart(painter)
        elif self.kind == "star":
            self._draw_star(painter)
        elif self.kind == "z":
            self._draw_z(painter)
        elif self.kind == "sparkle":
            self._draw_sparkle(painter)
        painter.restore()

    def _draw_heart(self, p):
        p.setBrush(QBrush(QColor(255, 85, 120)))
        p.setPen(Qt.NoPen)
        s = self.size / 2
        path = QPainterPath()
        path.moveTo(0, s * 0.35)
        path.cubicTo(-s * 0.2, -s * 0.1, -s, -s * 0.3, -s * 0.5, -s * 0.6)
        path.cubicTo(-s * 0.2, -s * 0.8, 0, -s * 0.6, 0, -s * 0.3)
        path.cubicTo(0, -s * 0.6, s * 0.2, -s * 0.8, s * 0.5, -s * 0.6)
        path.cubicTo(s, -s * 0.3, s * 0.2, -s * 0.1, 0, s * 0.35)
        p.drawPath(path)

    def _draw_star(self, p):
        p.setBrush(QBrush(QColor(255, 210, 70)))
        p.setPen(Qt.NoPen)
        s = self.size / 2
        path = QPainterPath()
        for i in range(5):
            a1 = math.radians(i * 72 - 90)
            a2 = math.radians(i * 72 - 54)
            x1, y1 = math.cos(a1) * s, math.sin(a1) * s
            x2, y2 = math.cos(a2) * s * 0.4, math.sin(a2) * s * 0.4
            if i == 0:
                path.moveTo(x1, y1)
            else:
                path.lineTo(x1, y1)
            path.lineTo(x2, y2)
        path.closeSubpath()
        p.drawPath(path)

    def _draw_z(self, p):
        font = QFont("Arial", int(self.size), QFont.Bold)
        p.setFont(font)
        p.setPen(QPen(QColor(100, 150, 255)))
        r = QRectF(-self.size, -self.size, self.size * 2, self.size * 2)
        p.drawText(r, Qt.AlignCenter, "Z")

    def _draw_sparkle(self, p):
        c = QColor(255, 255, 200)
        c.setAlpha(200)
        p.setBrush(QBrush(c))
        p.setPen(Qt.NoPen)
        s = self.size / 3
        path = QPainterPath()
        path.moveTo(0, -s)
        path.cubicTo(s * 0.3, -s * 0.3, s * 0.3, -s * 0.3, s, 0)
        path.cubicTo(s * 0.3, s * 0.3, s * 0.3, s * 0.3, 0, s)
        path.cubicTo(-s * 0.3, s * 0.3, -s * 0.3, s * 0.3, -s, 0)
        path.cubicTo(-s * 0.3, -s * 0.3, -s * 0.3, -s * 0.3, 0, -s)
        p.drawPath(path)
