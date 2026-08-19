#!/usr/bin/env python3
"""
生成小猫图标 cat.ico
使用 QPainter 绘制一个可爱的小猫头像并保存为 ICO 格式
"""
import sys
import math
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QPainter, QPixmap, QColor, QBrush, QPainterPath, QPen
from PyQt5.QtCore import Qt, QRectF, QPointF


def make_icon(path="cat.ico"):
    size = 256
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)

    cx, cy = size // 2, size // 2 + 10
    r = 78

    # ---- 耳朵 ----
    p.setBrush(QBrush(QColor("#FFB347")))
    p.setPen(Qt.NoPen)

    # 左耳
    left_ear = QPainterPath()
    left_ear.moveTo(cx - r * 0.8, cy - r * 0.6)
    left_ear.lineTo(cx - r * 0.95, cy - r * 1.45)
    left_ear.lineTo(cx - r * 0.28, cy - r * 0.85)
    left_ear.closeSubpath()
    p.drawPath(left_ear)

    # 右耳
    right_ear = QPainterPath()
    right_ear.moveTo(cx + r * 0.8, cy - r * 0.6)
    right_ear.lineTo(cx + r * 0.95, cy - r * 1.45)
    right_ear.lineTo(cx + r * 0.28, cy - r * 0.85)
    right_ear.closeSubpath()
    p.drawPath(right_ear)

    # 内耳
    p.setBrush(QBrush(QColor("#FF9999")))
    li = QPainterPath()
    li.moveTo(cx - r * 0.76, cy - r * 0.66)
    li.lineTo(cx - r * 0.88, cy - r * 1.28)
    li.lineTo(cx - r * 0.44, cy - r * 0.82)
    li.closeSubpath()
    p.drawPath(li)

    ri = QPainterPath()
    ri.moveTo(cx + r * 0.76, cy - r * 0.66)
    ri.lineTo(cx + r * 0.88, cy - r * 1.28)
    ri.lineTo(cx + r * 0.44, cy - r * 0.82)
    ri.closeSubpath()
    p.drawPath(ri)

    # ---- 头部 ----
    p.setBrush(QBrush(QColor("#FFB347")))
    p.drawEllipse(QPointF(cx, cy), r, r)

    # 脸部浅色区域
    p.setBrush(QBrush(QColor("#FFE0B0")))
    p.drawEllipse(QPointF(cx, cy + 12), r * 0.7, r * 0.55)

    # ---- 眼睛 ----
    eye_y = cy - 5
    eye_offset = 28
    eye_w, eye_h = 14, 20

    p.setBrush(QBrush(QColor("#2C2C2C")))
    p.setPen(Qt.NoPen)
    p.drawEllipse(QPointF(cx - eye_offset, eye_y), eye_w / 2, eye_h / 2)
    p.drawEllipse(QPointF(cx + eye_offset, eye_y), eye_w / 2, eye_h / 2)

    # 高光
    p.setBrush(QBrush(QColor(255, 255, 255, 230)))
    p.drawEllipse(QPointF(cx - eye_offset - 3, eye_y - 4), 4, 6)
    p.drawEllipse(QPointF(cx + eye_offset - 3, eye_y - 4), 4, 6)

    # ---- 鼻子 ----
    p.setBrush(QBrush(QColor("#FF6B9D")))
    nose = QPainterPath()
    nose.moveTo(cx - 6, cy + 18)
    nose.lineTo(cx + 6, cy + 18)
    nose.lineTo(cx, cy + 27)
    nose.closeSubpath()
    p.drawPath(nose)

    # ---- 嘴巴 ----
    p.setPen(QPen(QColor("#5C3D2E"), 2.5))
    p.setBrush(Qt.NoBrush)
    mouth = QPainterPath()
    mouth.moveTo(cx, cy + 27)
    mouth.quadTo(cx - 6, cy + 38, cx - 14, cy + 33)
    mouth.moveTo(cx, cy + 27)
    mouth.quadTo(cx + 6, cy + 38, cx + 14, cy + 33)
    p.drawPath(mouth)

    # ---- 胡须 ----
    p.setPen(QPen(QColor(255, 255, 255, 200), 1.5))
    whisker_y = cy + 20
    for i in range(3):
        dy = i * 7
        # 左
        p.drawLine(cx - 40, whisker_y + dy, cx - 72, whisker_y + dy - 5 + i * 4)
        # 右
        p.drawLine(cx + 40, whisker_y + dy, cx + 72, whisker_y + dy - 5 + i * 4)

    # ---- 腮红 ----
    blush = QColor(255, 150, 160, 100)
    p.setBrush(QBrush(blush))
    p.setPen(Qt.NoPen)
    p.drawEllipse(QPointF(cx - 42, cy + 10), 12, 8)
    p.drawEllipse(QPointF(cx + 42, cy + 10), 12, 8)

    p.end()

    if pix.save(path, "ICO"):
        print("图标已保存: " + path)
    else:
        print("保存ICO失败, 尝试PNG...")
        png_path = path.replace(".ico", ".png")
        pix.save(png_path, "PNG")
        print("图标已保存: " + png_path)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    make_icon("cat.ico")
