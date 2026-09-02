from ..common import *

# ======================== 摄像头预览悬浮窗 ========================
class CameraPreview(QWidget):
    """
    摄像头预览窗口 — 长按小猫时显示在旁边。
    滚轮缩放画面大小; 显示人体检测框(绿=主人/红=其他人)。
    """
    BASE_W, BASE_H = 480, 360   # 基准显示尺寸
    MIN_SCALE, MAX_SCALE = 0.5, 3.0

    def __init__(self, cat_window):
        super().__init__()
        self.cat = cat_window
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)

        # 从配置恢复上次的缩放 (记忆窗口大小)
        try:
            saved = self.cat.config.get("preview_scale", 1.0)
            self.scale = max(self.MIN_SCALE, min(self.MAX_SCALE, float(saved)))
        except Exception:
            self.scale = 1.0
        def read_opacity(key, default):
            try:
                return max(0.0, min(1.0, float(self.cat.config.get(key, default))))
            except Exception:
                return default
        self.window_opacity = read_opacity("preview_window_opacity", 0.85)
        self.video_opacity = read_opacity("preview_video_opacity", 0.85)
        self.overlay_opacity = read_opacity("preview_overlay_opacity", 1.0)
        self.image = None       # QImage
        self.boxes = []
        self.confs = []
        self.skipped = []       # pose 模式被过滤的人
        self.kpts = []          # pose 模式头部关键点
        self.person_count = 0
        self._close_rect = None   # 关闭按钮区域 (paintEvent 中更新)

        self._apply_size()

    # ---------- 尺寸 / 缩放 ----------

    def _apply_size(self):
        w = int(self.BASE_W * self.scale)
        h = int(self.BASE_H * self.scale)
        self.resize(w, h + 34)  # 底部信息条 34px

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        step = 0.15
        new_scale = self.scale + (step if delta > 0 else -step)
        new_scale = max(self.MIN_SCALE, min(self.MAX_SCALE, new_scale))
        if new_scale != self.scale:
            self.scale = new_scale
            self._apply_size()
            self._save_scale()
            # 缩放后保持窗口在屏幕内
            self.cat._position_preview()
            self.update()
        event.accept()

    def _save_scale(self):
        """把当前缩放写入配置, 下次启动恢复同样大小"""
        try:
            self.cat.config["preview_scale"] = round(self.scale, 2)
            save_config(self.cat.config)
        except Exception as e:
            _log(f"保存预览窗口大小失败: {e}")

    # ---------- 数据更新 ----------

    def update_frame(self, qimg, boxes, confs=None, skipped=None, kpts=None):
        self.image = qimg
        self.boxes = boxes
        self.confs = confs or []
        self.skipped = skipped or []
        self.kpts = kpts or []
        self.person_count = len(boxes)
        if self.isVisible():
            self.update()

    # ---------- 绘制 ----------

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)

        w, h = self.width(), self.height()
        bar_h = 34

        # 窗口层: 背景使用独立透明度
        p.save()
        p.setOpacity(self.window_opacity)
        p.setBrush(QBrush(QColor(20, 20, 30, 235)))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(0, 0, w, h), 12, 12)
        p.restore()

        # 视频区域
        video_rect = QRectF(6, 6, w - 12, h - bar_h - 12)
        if self.image is not None and not self.image.isNull():
            pixmap = QPixmap.fromImage(self.image)
            scaled = pixmap.scaled(
                int(video_rect.width()), int(video_rect.height()),
                Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            vx = video_rect.x() + (video_rect.width() - scaled.width()) / 2
            vy = video_rect.y() + (video_rect.height() - scaled.height()) / 2
            p.save()
            p.setOpacity(self.video_opacity)
            p.drawPixmap(QPointF(vx, vy), scaled)
            p.restore()

            # 检测框覆盖层 (与图像等比缩放)
            p.save()
            p.setOpacity(self.overlay_opacity)
            self._draw_overlay(p, QRectF(vx, vy, scaled.width(), scaled.height()))
            p.restore()
        else:
            p.save()
            p.setOpacity(self.overlay_opacity)
            p.setPen(QPen(QColor(150, 150, 160)))
            font = QFont("Microsoft YaHei", 11)
            p.setFont(font)
            p.drawText(video_rect, Qt.AlignCenter,
                       "摄像头启动中..." if self.cat.cam_ok is None else "摄像头不可用")
            p.restore()

        # 窗口层: 底部信息条、边框和关闭按钮
        p.save()
        p.setOpacity(self.window_opacity)
        self._draw_info_bar(p, w, h, bar_h)

        # 边框
        p.setPen(QPen(QColor(255, 255, 255, 40), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 12, 12)

        # 关闭按钮 (右上角)
        btn_r = 14
        bx, by = w - btn_r - 8, btn_r + 6
        self._close_rect = QRectF(bx, by, btn_r, btn_r)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(60, 60, 75, 220)))
        p.drawEllipse(self._close_rect)
        p.setPen(QPen(QColor(220, 220, 230), 2))
        m = 4
        p.drawLine(QPointF(bx + m, by + m), QPointF(bx + btn_r - m, by + btn_r - m))
        p.drawLine(QPointF(bx + btn_r - m, by + m), QPointF(bx + m, by + btn_r - m))
        p.restore()

        p.end()

    def _draw_overlay(self, p, dst_rect):
        """在缩放后的视频上绘制检测框 (绿=主人 红=其他 灰=SKIP 黄点=头部关键点)"""
        if self.image is None:
            return
        if not self.boxes and not self.skipped and not self.kpts:
            return
        iw, ih = self.image.width(), self.image.height()
        sx = dst_rect.width() / iw
        sy = dst_rect.height() / ih

        # SKIP 框 (被头部阈值过滤的人)
        for (x, y, bw, bh, c) in self.skipped:
            color = QColor(160, 160, 160)
            p.setPen(QPen(color, 1))
            p.setBrush(Qt.NoBrush)
            p.drawRect(QRectF(dst_rect.x() + x * sx, dst_rect.y() + y * sy,
                              bw * sx, bh * sy))
            label = f"SKIP {c:.2f}" if c is not None and c >= 0 else "SKIP"
            font = QFont("Arial", max(7, int(8 * self.scale)), QFont.Normal)
            p.setFont(font)
            p.setPen(QPen(color))
            p.drawText(QPointF(dst_rect.x() + x * sx + 3,
                               dst_rect.y() + y * sy + 14), label)

        # 头部关键点 (黄点)
        for (kx, ky, kc) in self.kpts:
            color = QColor(255, 255, 0)
            p.setPen(QPen(color, 2))
            p.setBrush(color if kc >= 0.5 else Qt.NoBrush)
            p.drawEllipse(QPointF(dst_rect.x() + kx * sx,
                                  dst_rect.y() + ky * sy), 4, 4)

        for idx, (x, y, bw, bh, is_main) in enumerate(self.boxes):
            color = QColor(0, 230, 80) if is_main else QColor(255, 70, 70)
            pen_w = 3 if is_main else 2
            p.setPen(QPen(color, pen_w))
            p.setBrush(Qt.NoBrush)
            rx = dst_rect.x() + x * sx
            ry = dst_rect.y() + y * sy
            p.drawRect(QRectF(rx, ry, bw * sx, bh * sy))

            label = "MAIN" if is_main else "PERSON"
            if idx < len(self.confs) and self.confs[idx] is not None \
                    and self.confs[idx] >= 0:
                label += f" {self.confs[idx]:.2f}"
            font = QFont("Arial", max(8, int(9 * self.scale)), QFont.Bold)
            p.setFont(font)
            fm = p.fontMetrics()
            tw = fm.horizontalAdvance(label) + 8
            th = fm.height() + 2
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(color))
            p.drawRect(QRectF(rx, ry - th, tw, th))
            p.setPen(QPen(QColor(255, 255, 255)))
            p.drawText(QRectF(rx, ry - th, tw, th), Qt.AlignCenter, label)

    def _draw_info_bar(self, p, w, h, bar_h):
        y = h - bar_h
        # 信息栏保持不透明, 避免文字随画面透明度变淡
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(0, 0, w, h), 12, 12)
        p.save()
        p.setClipPath(clip)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(20, 20, 30, 235)))
        p.drawRect(QRectF(0, y, w, bar_h))
        p.restore()
        p.setPen(QPen(QColor(255, 255, 255, 30), 1))
        p.drawLine(QPointF(10, y), QPointF(w - 10, y))

        font = QFont("Microsoft YaHei", 9)
        p.setFont(font)
        p.setPen(QPen(QColor(200, 200, 210)))

        if self.person_count == 0:
            status = "No person"
            color = QColor(160, 160, 170)
        elif self.person_count == 1:
            status = "1 person (main)"
            color = QColor(0, 230, 80)
        else:
            status = f"{self.person_count} persons - switching"
            color = QColor(255, 90, 90)

        p.setPen(QPen(color))
        p.drawText(QRectF(12, y, w - 120, bar_h),
                   Qt.AlignVCenter | Qt.AlignLeft, status)

        p.setPen(QPen(QColor(140, 140, 150)))
        p.drawText(QRectF(w - 110, y, 98, bar_h),
                   Qt.AlignVCenter | Qt.AlignRight,
                   f"zoom {self.scale:.1f}x")

    # ---------- 预览窗口自身可拖动 ----------
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # 点关闭按钮 → 隐藏预览
            if self._close_rect is not None and \
                    self._close_rect.contains(QPointF(event.pos())):
                self.hide()
                return
            self._drag_off = event.pos()
            self._dragging = True

    def mouseMoveEvent(self, event):
        if getattr(self, "_dragging", False):
            self.move(event.globalPos() - self._drag_off)

    def mouseReleaseEvent(self, event):
        self._dragging = False
