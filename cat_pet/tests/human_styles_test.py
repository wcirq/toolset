# -*- coding: utf-8 -*-
"""离屏验证全部人类形象均可绘制，且三种表现层级和六套主题色完整。"""
import os
import sys
from types import SimpleNamespace

os.environ["QT_QPA_PLATFORM"] = "offscreen"
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage, QPainter
from PyQt5.QtWidgets import QApplication

from coolcat.cat_window import CatWindow
from coolcat.runtime import HUMAN_PALETTES, HUMAN_STYLES, H, W


app = QApplication.instance() or QApplication([])
assert len(HUMAN_STYLES) == len(HUMAN_PALETTES) == 6
assert {style["render"] for style in HUMAN_STYLES} == {
    "portrait", "cartoon", "abstract"
}

for style in HUMAN_STYLES:
    palette = HUMAN_PALETTES[style["palette"]]
    subject = SimpleNamespace(
        style=style, c=palette, bounce=0, blink_left=0,
        eye_x=0.0, eye_y=0.0,
    )
    image = QImage(W, H, QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    CatWindow._draw_human_character(subject, painter)
    painter.end()
    visible = sum(
        image.pixelColor(x, y).alpha() > 0
        for y in range(H) for x in range(W)
    )
    assert visible > 2500, (style["name"], visible)
    for mood in ('angry', 'happy'):
        subject._tab_mood = mood
        expression = QImage(W, H, QImage.Format_ARGB32_Premultiplied)
        expression.fill(Qt.transparent)
        painter = QPainter(expression)
        CatWindow._draw_human_character(subject, painter)
        painter.end()
        assert expression != image, (style['name'], mood, 'expression did not change')
print("PASS: 6 human styles, 6 linked palettes, 3 render levels")
