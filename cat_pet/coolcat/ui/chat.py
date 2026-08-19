from ..common import *

# ======================== 顶部聊天悬浮窗 ========================
class ChatOverlay(QWidget):
    """毛玻璃聊天框 — 顶部居中，四边渐变半透明，按回车发送气泡向上浮出"""

    def __init__(self, cat_window):
        _log("ChatOverlay.__init__ 开始")
        try:
            super().__init__()
            self.cat = cat_window
            self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
            self.setAttribute(Qt.WA_TranslucentBackground)
            _log("ChatOverlay 窗口属性已设置")

            self._W = 420
            self._min_h = 88
            self._max_h = 480
            self._pad = 16
            self._input_h = 50
            self._bubble_h = 34
            self._gap = 8
            _log(f"ChatOverlay 尺寸参数: W={self._W} min_h={self._min_h}")

            self.messages = []  # [(text, age_seconds)]

            screen = QApplication.primaryScreen().geometry()
            _log(f"屏幕尺寸: {screen.width()}x{screen.height()}")
            self.resize(self._W, self._min_h)
            self.move((screen.width() - self._W) // 2, 6)
            _log(f"ChatOverlay 已定位到 ({self.x()}, {self.y()})")

            # 输入框
            self.input_edit = QLineEdit(self)
            self.input_edit.setPlaceholderText("跟小猫说点什么...  ↵ 发送")
            self.input_edit.returnPressed.connect(self._send)
            self._style_input()
            self._relayout()
            _log("ChatOverlay input_edit 已创建")

            # 消息老化计时器
            self._fade_timer = QTimer(self)
            self._fade_timer.timeout.connect(self._age_messages)

            # 外部点击检测定时器 (每 200ms 检查鼠标是否在外面)
            self._outside_timer = QTimer(self)
            self._outside_timer.timeout.connect(self._check_outside_click)
            _log("ChatOverlay 定时器已创建")

            # 焦点变化 → 检测是否应该关闭
            QApplication.instance().focusChanged.connect(self._on_focus_changed)
            _log("ChatOverlay 焦点监听已连接")
            _log("ChatOverlay.__init__ 完成")
        except Exception as e:
            _log(f"!!! ChatOverlay.__init__ 异常: {e}\n{traceback.format_exc()}")
            raise

    # ---------- 布局 & 样式 ----------

    def _relayout(self):
        h = self.height()
        self.input_edit.setGeometry(
            self._pad, h - self._input_h - 14,
            self._W - 2 * self._pad, self._input_h
        )

    def _style_input(self):
        self.input_edit.setStyleSheet("""
            QLineEdit {
                background: rgba(255, 255, 255, 30);
                border: 1px solid rgba(255, 255, 255, 56);
                border-radius: 22px;
                padding: 8px 20px;
                color: #ffffff;
                font-size: 15px;
                font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif;
                selection-background-color: rgba(255, 180, 130, 89);
            }
            QLineEdit:focus {
                border: 1px solid rgba(255, 200, 150, 140);
                background: rgba(255, 255, 255, 46);
            }
            QLineEdit::placeholder {
                color: rgba(255, 255, 255, 89);
            }
        """)

    # ---------- 发送消息 ----------

    def _send(self):
        text = self.input_edit.text().strip()
        if not text:
            return
        _log(f"ChatOverlay._send: text='{text}'")
        self.messages.append((text, 0))
        _log(f"ChatOverlay._send: messages count={len(self.messages)}")
        self.input_edit.clear()

        # 小猫复读 + 爱心粒子
        self.cat._say(text, 180)
        self.cat._spawn_particles("heart", 3)

        # 延迟一帧调整高度，确保信号处理完成后再重绘
        QTimer.singleShot(10, self._adjust_height)

    def _adjust_height(self):
        n = len(self.messages)
        needed = self._min_h + n * (self._bubble_h + self._gap)
        new_h = min(needed, self._max_h)
        _log(f"ChatOverlay._adjust_height: n={n} old_h={self.height()} new_h={new_h}")
        self.resize(self._W, new_h)
        self._relayout()
        self.repaint()  # 强制立即重绘

    def _age_messages(self):
        """每秒老化消息，超过40秒的移除"""
        if not self.messages:
            if self.height() > self._min_h:
                self.resize(self._W, self._min_h)
                self._relayout()
                self.repaint()
            return

        changed = False
        new_msgs = []
        for text, age in self.messages:
            if age < 40:
                new_msgs.append((text, age + 1))
            else:
                changed = True

        if len(new_msgs) != len(self.messages):
            changed = True

        self.messages = new_msgs
        if changed:
            self._adjust_height()
        else:
            self.update()

    # ---------- 绘制 ----------

    def paintEvent(self, event):
        try:
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            w, h = self.width(), self.height()
            r = 18

            # 裁剪圆角
            path = QPainterPath()
            path.addRoundedRect(QRectF(0, 0, w, h), r, r)
            p.setClipPath(path)

            base_c = QColor(25, 25, 38, 215)
            edge_c = QColor(25, 25, 38, 0)
            fade = 0.28

            # 基色填充
            p.setBrush(QBrush(base_c))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(QRectF(1, 1, w - 2, h - 2), r, r)

            # 四边渐变 fade-out
            for (x1, y1, x2, y2) in [
                (0, 0, 0, h * fade),
                (0, h * (1 - fade), 0, h),
                (0, 0, w * fade, 0),
                (w * (1 - fade), 0, w, 0),
            ]:
                g = QLinearGradient(x1, y1, x2, y2)
                g.setColorAt(0, edge_c)
                g.setColorAt(1, base_c)
                p.setBrush(QBrush(g))
                if x1 == x2:
                    p.drawRect(QRectF(0, y1, w, h * fade + 1))
                else:
                    p.drawRect(QRectF(x1, 0, w * fade + 1, h))

            # 细边框
            p.setClipping(False)
            p.setPen(QPen(QColor(255, 255, 255, 38), 1))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), r, r)

            # 分隔线 (输入框上方)
            div_y = h - self._input_h - 26
            if div_y > 10:
                g = QLinearGradient(w * 0.3, 0, w * 0.7, 0)
                g.setColorAt(0, QColor(255, 255, 255, 0))
                g.setColorAt(0.5, QColor(255, 255, 255, 32))
                g.setColorAt(1, QColor(255, 255, 255, 0))
                p.setPen(QPen(QBrush(g), 1))
                p.drawLine(QPointF(w * 0.3, div_y), QPointF(w * 0.7, div_y))

            # 消息气泡 (自下而上排列)
            msg_bottom = div_y - 14 if div_y > 10 else h - self._input_h - 32
            font = QFont("Microsoft YaHei", 12)
            font.setStyleHint(QFont.SansSerif)  # 确保字体回退
            p.setFont(font)

            drawn = 0
            for i in range(len(self.messages) - 1, -1, -1):
                text, age = self.messages[i]
                if msg_bottom < 5:
                    break

                alpha = max(30, 230 - age * 6)
                fm = p.fontMetrics()
                # width() 兼容所有 PyQt5 版本 (horizontalAdvance 需要 Qt ≥5.11)
                tw = fm.width(text)
                bw = max(tw + 30, 60)
                bx = (w - bw) / 2
                by = msg_bottom - self._bubble_h

                bc = QColor(255, 255, 255, min(alpha, 190))
                p.setBrush(QBrush(bc))
                p.setPen(QPen(QColor(255, 255, 255, min(alpha // 3, 50)), 1))
                p.drawRoundedRect(
                    QRectF(bx, by, bw, self._bubble_h),
                    self._bubble_h / 2, self._bubble_h / 2
                )

                tc = QColor(55, 55, 65)
                tc.setAlpha(alpha)
                p.setPen(QPen(tc))
                p.drawText(QRectF(bx, by, bw, self._bubble_h), Qt.AlignCenter, text)

                msg_bottom = by - self._gap
                drawn += 1

            if drawn > 0:
                _log(f"ChatOverlay.paint: 绘制了 {drawn} 个气泡, h={h}")

            if p.isActive():
                p.end()
        except Exception as e:
            _log(f"!!! ChatOverlay.paintEvent 异常: {e}\n{traceback.format_exc()}")

    # ---------- 窗口事件 ----------

    def showEvent(self, event):
        _log("ChatOverlay.showEvent 触发")
        try:
            super().showEvent(event)
            self.input_edit.setFocus()
            self.input_edit.clear()
            self._fade_timer.start(1000)
            self._outside_timer.stop()  # 显示时停止外部检测
            _log("ChatOverlay.showEvent 完成")
        except Exception as e:
            _log(f"!!! ChatOverlay.showEvent 异常: {e}\n{traceback.format_exc()}")
            raise

    def hideEvent(self, event):
        super().hideEvent(event)
        self._fade_timer.stop()
        self._outside_timer.stop()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.hide()
        super().keyPressEvent(event)

    def eventFilter(self, obj, event):
        """已废弃 — 改用 _on_focus_changed + _outside_timer"""
        return super().eventFilter(obj, event)

    def _on_focus_changed(self, old, new):
        """当焦点离开聊天框和输入框时启动外部检测"""
        if not self.isVisible():
            return
        # 如果新焦点既不是聊天框本身也不是其子控件(输入框)
        if new is None or (new is not self and new is not self.input_edit and not self.isAncestorOf(new)):
            _log(f"ChatOverlay 焦点转移: old={old} new={new}, 启动外部检测")
            self._outside_timer.start(200)

    def _check_outside_click(self):
        """定时检查：如果鼠标在聊天框和猫窗外，且左键按下 → 关闭"""
        if not self.isVisible():
            self._outside_timer.stop()
            return

        mouse = QCursor.pos()
        in_chat = self.geometry().contains(mouse)
        in_cat = self.cat.geometry().contains(mouse)

        if not in_chat and not in_cat:
            # 检测是否有鼠标按下 (通过 QApplication.mouseButtons)
            if QApplication.mouseButtons() & Qt.LeftButton:
                _log("ChatOverlay: 检测到外部点击, 关闭")
                self.hide()
                self._outside_timer.stop()
        else:
            # 鼠标回到聊天框或猫窗 → 停止检测
            self._outside_timer.stop()

    # ---------- 滚轮调整大小 ----------

    def wheelEvent(self, event):
        """Ctrl+滚轮 或 直接滚轮 调整控件宽度"""
        delta = event.angleDelta().y()
        step = 20
        new_w = self._W + (step if delta > 0 else -step)
        new_w = max(280, min(700, new_w))
        if new_w != self._W:
            self._W = new_w
            self.resize(self._W, self.height())
            self._relayout()
            self.update()
        event.accept()
