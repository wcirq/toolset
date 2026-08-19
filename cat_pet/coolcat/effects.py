from .common import *

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
