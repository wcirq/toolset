from ..common import *
from PyQt5.QtWidgets import QScrollArea


TRANSLATION_LANGUAGES = (
    ("汉语普通话", "cn"), ("英语", "en"), ("彝语", "ii"),
    ("广东话", "yue"), ("日语", "ja"), ("俄语", "ru"),
    ("法语", "fr"), ("西班牙语", "es"), ("阿拉伯语", "ar"),
    ("意大利语", "it"), ("土耳其语", "tr"), ("越南语", "vi"),
    ("泰语", "th"), ("韩语", "ko"), ("德语", "de"),
    ("哈萨克语", "kka"), ("南非荷兰语", "af"), ("阿姆哈拉语", "am"),
    ("阿塞拜疆语", "az"), ("孟加拉语", "bn"), ("加泰罗尼亚语", "ca"),
    ("捷克语", "cs"), ("丹麦语", "da"), ("希腊语", "el"),
    ("波斯语", "fa"), ("芬兰语", "fi"), ("希伯来语", "he"),
    ("印地语", "hi"), ("克罗地亚语", "hr"), ("匈牙利语", "hu"),
    ("亚美尼亚语", "hy"), ("印尼语", "id"), ("冰岛语", "is"),
    ("塔加路语（菲律宾）", "tl"), ("罗马尼亚语", "ro"),
    ("格鲁吉亚语", "ka"), ("高棉语", "km"), ("老挝语", "lo"),
    ("立陶宛语", "lt"), ("拉脱维亚语", "lv"), ("马拉雅拉姆语", "ml"),
    ("马拉地语", "mr"), ("博克马尔挪威语", "nb"), ("尼泊尔语", "ne"),
    ("荷兰语", "nl"), ("波兰语", "pl"), ("葡萄牙语", "pt"),
    ("僧伽罗语", "si"), ("斯洛伐克语", "sk"), ("斯洛文尼亚语", "sl"),
    ("塞尔维亚语", "sr"), ("巽他语", "su"), ("瑞典语", "sv"),
    ("斯瓦希里语", "sw"), ("泰米尔语", "ta"), ("泰卢固语", "te"),
    ("爪哇语", "jv"), ("马来语", "ms"), ("乌克兰语", "uk"),
    ("乌尔都语", "ur"), ("南非祖鲁语", "zu"), ("内蒙语", "mn"),
    ("缅甸语", "my"), ("外蒙语", "nm"), ("普什图语", "ps"),
    ("豪萨语", "ha"), ("乌兹别克语", "uz"), ("土库曼语", "tk"),
    ("塔吉克语", "tg"), ("保加利亚语", "bg"),
)


class ApiConfigTestWorker(QThread):
    completed = pyqtSignal(str, bool, float, str)

    def __init__(self, kind, config, text, pixmap=None, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.config = dict(config)
        self.text = text
        self.pixmap = QPixmap(pixmap) if pixmap is not None else QPixmap()

    def run(self):
        started = time.perf_counter()
        try:
            from .screenshot import (call_openai_compatible,
                                     call_translation_lines, call_umi_ocr)
            if self.kind == "ocr":
                provider = self.config.get(
                    "screenshot_ocr_provider", "rapidocr_local")
                if provider == "openai_compatible":
                    result = call_openai_compatible(
                        self.config, self.pixmap, translate=False)
                else:
                    result = call_umi_ocr(self.config, self.pixmap)
            else:
                result = "\n".join(call_translation_lines(
                    self.config, [self.text]))
            self.completed.emit(
                self.kind, True, time.perf_counter() - started, str(result))
        except Exception as exc:
            self.completed.emit(
                self.kind, False, time.perf_counter() - started, str(exc))

# ======================== 无边框对话框标题栏 ========================
class DialogTitleBar(QWidget):
    """统一的自绘标题栏: 支持拖动窗口和关闭。"""
    def __init__(self, title, dialog):
        super().__init__(dialog)
        self.dialog = dialog
        self._drag_offset = None
        self.setFixedHeight(38)
        self.setStyleSheet("background: transparent;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 4, 6, 2)
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet(
            "color: #B8B8C8; font-size: 12px; font-weight: bold;")
        layout.addWidget(self.title_label)
        layout.addStretch()

        close_btn = QPushButton("×")
        close_btn.setFixedSize(30, 28)
        close_btn.setToolTip("关闭")
        close_btn.setStyleSheet("""
            QPushButton {
                background: transparent; color: #A8A8B8;
                border: none; border-radius: 6px;
                padding: 0; font-size: 20px; font-weight: normal;
            }
            QPushButton:hover { background: #D94B5B; color: white; }
            QPushButton:pressed { background: #B83B49; }
        """)
        close_btn.clicked.connect(dialog.reject)
        layout.addWidget(close_btn)

    def setTitle(self, title):
        self.title_label.setText(title)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_offset = event.globalPos() - self.dialog.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.dialog.move(event.globalPos() - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_offset = None
        event.accept()


# ======================== 统一消息对话框 ========================
class StyledMessageDialog(QDialog):
    """替代 QMessageBox 的无边框中文提示/确认窗口。"""
    STYLE = """
        QDialog {
            background: #1E1E2A; color: #EEEEF4;
            border: 1px solid #3B3B50; border-radius: 11px;
            font-family: 'Microsoft YaHei'; font-size: 13px;
        }
        QLabel#message { color: #D8D8E2; font-size: 14px; }
        QLabel#mark {
            background: #3A3040; color: #FFB347;
            border-radius: 20px; font-size: 22px; font-weight: bold;
        }
        QPushButton {
            background: #343449; color: #E8E8EF;
            border: none; border-radius: 7px; padding: 8px 20px;
            min-width: 72px;
        }
        QPushButton:hover { background: #45455D; }
        QPushButton#primary { background: #E89530; color: white; font-weight: bold; }
        QPushButton#primary:hover { background: #FFB347; }
        QPushButton#danger { background: #56313A; color: #FFB1B8; }
        QPushButton#danger:hover { background: #70404B; }
    """

    def __init__(self, title, message, buttons, parent=None, mark="!"):
        super().__init__(parent)
        self.choice = None
        self._cancel_key = next((key for _text, key, _kind in buttons
                                 if key == "cancel"), buttons[0][1])
        self.setWindowFlags(
            Qt.Dialog | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setFixedWidth(390)
        self.setStyleSheet(self.STYLE)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 6, 14, 18)
        root.setSpacing(12)
        root.addWidget(DialogTitleBar(title, self))

        content = QHBoxLayout()
        content.setContentsMargins(12, 8, 12, 8)
        badge = QLabel(mark)
        badge.setObjectName("mark")
        badge.setAlignment(Qt.AlignCenter)
        badge.setFixedSize(42, 42)
        content.addWidget(badge, 0, Qt.AlignTop)
        label = QLabel(message)
        label.setObjectName("message")
        label.setWordWrap(True)
        label.setMinimumHeight(44)
        content.addWidget(label, 1)
        root.addLayout(content)

        row = QHBoxLayout()
        row.addStretch()
        for text, key, kind in buttons:
            btn = QPushButton(text)
            if kind in ("primary", "danger"):
                btn.setObjectName(kind)
            btn.clicked.connect(lambda _checked=False, k=key: self._choose(k))
            row.addWidget(btn)
        root.addLayout(row)

    def _choose(self, key):
        self.choice = key
        super().accept()

    def reject(self):
        self.choice = self._cancel_key
        super().reject()

    @classmethod
    def warning(cls, parent, title, message):
        dlg = cls(title, message, [("知道了", "ok", "primary")], parent, "!")
        dlg.exec_()

    @classmethod
    def ask_save(cls, parent, message):
        buttons = [
            ("取消", "cancel", "normal"),
            ("不保存", "discard", "danger"),
            ("保存", "save", "primary"),
        ]
        dlg = cls("未保存的设置", message, buttons, parent, "?")
        dlg.exec_()
        return dlg.choice or "cancel"


# ======================== 设置身份验证 ========================
class AuthDialog(QDialog):
    """与小猫设置页统一风格的密码验证窗口。"""
    STYLE = """
        QDialog {
            background: #1E1E2A;
            color: #F4F4F8;
            border: 1px solid #3B3B50;
            border-radius: 12px;
            font-family: 'Microsoft YaHei';
            font-size: 13px;
        }
        QLabel#badge {
            background: #343044;
            color: #FFB347;
            border: 1px solid #4A445B;
            border-radius: 25px;
            font-size: 25px;
        }
        QLabel#title {
            color: #FFFFFF;
            font-size: 20px;
            font-weight: bold;
        }
        QLabel#subtitle { color: #9999AA; font-size: 12px; }
        QLabel#error {
            color: #FF7B86;
            background: #3A252F;
            border-radius: 5px;
            padding: 6px 10px;
        }
        QLineEdit {
            background: #29293A;
            color: #FFFFFF;
            border: 1px solid #48485D;
            border-radius: 8px;
            padding: 10px 12px;
            font-size: 14px;
            selection-background-color: #E89530;
        }
        QLineEdit:focus { border: 1px solid #FFB347; }
        QCheckBox { color: #AAAABB; spacing: 7px; }
        QPushButton {
            background: #343449;
            color: #E8E8EF;
            border: none;
            border-radius: 7px;
            padding: 9px 22px;
        }
        QPushButton:hover { background: #414159; }
        QPushButton#unlock {
            background: #E89530;
            color: #FFFFFF;
            font-weight: bold;
        }
        QPushButton#unlock:hover { background: #FFB347; }
        QPushButton#unlock:pressed { background: #D78128; }
    """

    def __init__(self, expected_hash, parent=None):
        super().__init__(parent)
        self.expected_hash = expected_hash
        self.setWindowTitle("身份验证")
        self.setWindowFlags(
            Qt.Dialog | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setFixedWidth(420)
        self.setStyleSheet(self.STYLE)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 6, 20, 24)
        root.setSpacing(12)

        self.title_bar = DialogTitleBar("身份验证", self)
        root.addWidget(self.title_bar)

        badge = QLabel("♥")
        badge.setObjectName("badge")
        badge.setAlignment(Qt.AlignCenter)
        badge.setFixedSize(52, 52)
        root.addWidget(badge, 0, Qt.AlignHCenter)

        title = QLabel("进入小猫设置")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignCenter)
        root.addWidget(title)

        subtitle = QLabel("设置中包含摄像头检测与目标程序配置\n请输入访问密码继续")
        subtitle.setObjectName("subtitle")
        subtitle.setAlignment(Qt.AlignCenter)
        root.addWidget(subtitle)
        root.addSpacing(4)

        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.password_edit.setPlaceholderText("输入设置访问密码")
        self.password_edit.returnPressed.connect(self.accept)
        self.password_edit.textChanged.connect(self._clear_error)
        self.password_visible = False
        self.toggle_password_action = QAction(self)
        self.toggle_password_action.setToolTip("显示密码")
        self.toggle_password_action.setIcon(self._make_eye_icon(False))
        self.toggle_password_action.triggered.connect(self._toggle_password)
        self.password_edit.addAction(
            self.toggle_password_action, QLineEdit.TrailingPosition)
        root.addWidget(self.password_edit)

        self.error_label = QLabel("")
        self.error_label.setObjectName("error")
        self.error_label.setAlignment(Qt.AlignCenter)
        self.error_label.hide()
        root.addWidget(self.error_label)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        unlock_btn = QPushButton("解锁设置")
        unlock_btn.setObjectName("unlock")
        unlock_btn.setDefault(True)
        unlock_btn.clicked.connect(self.accept)
        buttons.addWidget(cancel_btn)
        buttons.addWidget(unlock_btn)
        root.addLayout(buttons)

        self.password_edit.setFocus()

    @staticmethod
    def _make_eye_icon(opened):
        """绘制密码框右侧的睁眼/闭眼图标。"""
        pix = QPixmap(24, 24)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor("#B8B8C8"), 1.8, Qt.SolidLine, Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        if opened:
            eye = QPainterPath()
            eye.moveTo(3, 12)
            eye.quadTo(12, 4, 21, 12)
            eye.quadTo(12, 20, 3, 12)
            p.drawPath(eye)
            p.setBrush(QBrush(QColor("#B8B8C8")))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(12, 12), 3.2, 3.2)
        else:
            lid = QPainterPath()
            lid.moveTo(3, 10)
            lid.quadTo(12, 17, 21, 10)
            p.drawPath(lid)
            p.drawLine(QPointF(5, 6), QPointF(19, 19))
        p.end()
        return QIcon(pix)

    def _toggle_password(self):
        self.password_visible = not self.password_visible
        self.password_edit.setEchoMode(
            QLineEdit.Normal if self.password_visible else QLineEdit.Password)
        self.toggle_password_action.setIcon(
            self._make_eye_icon(self.password_visible))
        self.toggle_password_action.setToolTip(
            "隐藏密码" if self.password_visible else "显示密码")

    def _clear_error(self):
        if self.error_label.isVisible():
            self.error_label.hide()
            self.password_edit.setStyleSheet("")

    def accept(self):
        if _hash_password(self.password_edit.text()) != self.expected_hash:
            self.error_label.setText("密码不正确, 请重新输入")
            self.error_label.show()
            self.password_edit.setStyleSheet("border: 1px solid #FF6575;")
            self.password_edit.selectAll()
            self.password_edit.setFocus()
            return
        super().accept()


# ======================== 设置对话框 ========================
SETTINGS_HINT_STYLE = (
    "color: #C7D0E5; font-size: 12px; font-weight: 400; padding: 3px 0;"
)


class SettingsDialog(QDialog):
    """
    配置页面: 检测模型 / 触发规则 / 形象尺寸 / 摄像头。
    保存后通过 get_config() 返回新配置, 由 CatWindow 应用并持久化。
    """
    STYLE = """
        QDialog {
            background: #1E1E2A;
            color: #E8E8F0;
            border: 1px solid #3B3B50;
            border-radius: 10px;
            font-family: 'Microsoft YaHei';
            font-size: 13px;
        }
        QGroupBox {
            border: 1px solid #3A3A4E;
            border-radius: 8px;
            margin-top: 14px;
            padding: 14px 10px 10px 10px;
            font-weight: bold;
            color: #FFB347;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 12px;
            padding: 0 6px;
        }
        QLabel { color: #C8C8D4; }
        QComboBox, QSpinBox, QDoubleSpinBox {
            background: #2A2A3C;
            color: #FFFFFF;
            border: 1px solid #4A4A60;
            border-radius: 5px;
            padding: 4px 8px;
            min-width: 140px;
        }
        QLineEdit {
            background: #2A2A3C;
            color: #FFFFFF;
            border: 1px solid #4A4A60;
            border-radius: 5px;
            padding: 4px 8px;
            min-width: 140px;
        }
        QComboBox QAbstractItemView {
            background: #2A2A3C;
            color: #FFFFFF;
            selection-background-color: #4A5A80;
        }
        QSlider::groove:horizontal {
            height: 6px;
            background: #3A3A4E;
            border-radius: 3px;
        }
        QSlider::handle:horizontal {
            width: 16px; height: 16px;
            margin: -5px 0;
            border-radius: 8px;
            background: #FFB347;
        }
        QPushButton {
            background: #3A3A55;
            color: #FFFFFF;
            border: none;
            border-radius: 6px;
            padding: 8px 22px;
        }
        QPushButton:hover { background: #4A4A70; }
        QPushButton#okBtn {
            background: #E89530;
            font-weight: bold;
        }
        QPushButton#okBtn:hover { background: #FFB347; }
        QCheckBox { color: #C8C8D4; }
        QTabWidget::pane {
            border: 1px solid #3A3A4E;
            border-radius: 6px;
            top: -1px;
        }
        QTabBar::tab {
            background: #2A2A3C;
            color: #C8C8D4;
            padding: 7px 18px;
            margin-right: 3px;
            border-top-left-radius: 6px;
            border-top-right-radius: 6px;
        }
        QTabBar::tab:selected {
            background: #3A3A55;
            color: #FFB347;
            font-weight: bold;
        }
        QTabBar::tab:hover { background: #34344A; }
    """

    def __init__(self, cfg, yolo_available, parent=None):
        super().__init__(parent)
        self.setWindowTitle("小猫设置")
        self.setWindowFlags(
            Qt.Dialog | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setStyleSheet(self.STYLE)
        self.setMinimumWidth(420)
        self._yolo_available = yolo_available
        self._cfg = dict(cfg)   # 上次已保存的配置快照
        self._preview_was_visible = bool(
            parent and hasattr(parent, "preview") and parent.preview.isVisible())

        root = QVBoxLayout(self)

        self.title_bar = DialogTitleBar("小猫设置", self)
        root.addWidget(self.title_bar)

        # ---------- 分页容器 ----------
        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)

        # ========== Tab 1: 检测与触发 ==========
        page1 = QWidget()
        l1 = QVBoxLayout(page1)
        l1.setContentsMargins(8, 8, 8, 8)

        # ---------- 检测模型 ----------
        g1 = QGroupBox("检测模型")
        f1 = QFormLayout(g1)
        self.model_combo = QComboBox()
        self.model_combo.addItem("HOG+Haar 传统检测 (快速, 无额外依赖)", "hog")
        yolo_text = "YOLOv26 深度学习 (精准)" if yolo_available else \
                    "YOLOv26 ONNX (未安装 onnxruntime, 选中将回退)"
        self.model_combo.addItem(yolo_text, "yolo")
        f1.addRow("检测模型:", self.model_combo)

        self.yolo_model_combo = QComboBox()
        self.yolo_model_combo.setEditable(True)
        for name in ["yolo26n.onnx", "yolo26n-pose.onnx"]:
            self.yolo_model_combo.addItem(name)
        f1.addRow("YOLO 权重:", self.yolo_model_combo)

        self.conf_spin = QDoubleSpinBox()
        self.conf_spin.setRange(0.05, 0.95)
        self.conf_spin.setSingleStep(0.05)
        f1.addRow("置信度阈值:", self.conf_spin)

        self.kpt_conf_spin = QDoubleSpinBox()
        self.kpt_conf_spin.setRange(0.1, 0.95)
        self.kpt_conf_spin.setSingleStep(0.05)
        self.kpt_conf_spin.setToolTip("pose 模型: 头部关键点(鼻/眼/耳)置信度达到该值才算一个出现的头部")
        f1.addRow("头部关键点置信度:", self.kpt_conf_spin)

        pose_hint = QLabel("权重文件名包含 -pose 时使用姿态模型，触发人数按可见头部计算。")
        pose_hint.setStyleSheet(SETTINGS_HINT_STYLE)
        pose_hint.setWordWrap(True)
        f1.addRow("", pose_hint)
        l1.addWidget(g1)

        # ---------- 触发规则 ----------
        g2 = QGroupBox("触发规则 (检测到多人时自动切换到目标程序)")
        f2 = QFormLayout(g2)
        self.count_spin = QSpinBox()
        self.count_spin.setRange(2, 10)
        self.count_spin.setSuffix(" 人")
        self.count_label = QLabel("触发人数 ≥:")
        f2.addRow(self.count_label, self.count_spin)

        self.sustain_spin = QDoubleSpinBox()
        self.sustain_spin.setRange(0.0, 10.0)
        self.sustain_spin.setSingleStep(0.5)
        self.sustain_spin.setSuffix(" 秒")
        self.sustain_spin.setSpecialValueText("立即触发 (0秒)")
        f2.addRow("持续检出时间:", self.sustain_spin)

        self.cooldown_spin = QDoubleSpinBox()
        self.cooldown_spin.setRange(0.0, 3600.0)
        self.cooldown_spin.setSingleStep(1.0)
        self.cooldown_spin.setSuffix(" 秒")
        self.cooldown_spin.setSpecialValueText("不冷却 (0秒)")
        self.cooldown_spin.setToolTip("自动触发切换后, 在该时间内忽略新的多人触发")
        f2.addRow("触发冷却时间:", self.cooldown_spin)

        self.auto_pause_fullscreen_check = QCheckBox(
            "全屏游戏、会议、演示时自动暂停监控")
        self.auto_pause_fullscreen_check.setToolTip(
            "当前台程序覆盖整个显示器时释放摄像头; 退出全屏后自动恢复")
        f2.addRow("", self.auto_pause_fullscreen_check)

        self.dedup_spin = QDoubleSpinBox()
        self.dedup_spin.setRange(0.2, 0.95)
        self.dedup_spin.setSingleStep(0.05)
        self.dedup_spin.setValue(0.55)
        f2.addRow("重复框合并阈值:", self.dedup_spin)
        dedup_hint = QLabel("重叠率超过该值的两个框视为同一人 (解决一人被识别成两人); 值越小合并越激进")
        dedup_hint.setStyleSheet(SETTINGS_HINT_STYLE)
        dedup_hint.setWordWrap(True)
        f2.addRow("", dedup_hint)
        l1.addWidget(g2)
        l1.addStretch()
        self.tabs.addTab(page1, "检测与触发")

        # ========== Tab 2: 目标与快捷键 ==========
        page2 = QWidget()
        l2 = QVBoxLayout(page2)
        l2.setContentsMargins(8, 8, 8, 8)

        # ---------- 形象尺寸 ----------
        g3 = QGroupBox("形象尺寸")
        f3 = QFormLayout(g3)
        self.scale_slider = QSlider(Qt.Horizontal)
        # 1% 仅用于避免零尺寸窗口；产品层面不再设置最小尺寸限制。
        self.scale_slider.setRange(1, 200)
        self.scale_slider.setTickInterval(10)
        self.scale_label = QLabel("100%")
        self.scale_label.setMinimumWidth(48)
        row = QHBoxLayout()
        row.addWidget(self.scale_slider)
        row.addWidget(self.scale_label)
        f3.addRow("大小:", row)

        self.character_category_combo = QComboBox()
        self.character_category_combo.addItem("猫类", "cat")
        self.character_category_combo.addItem("人类", "human")
        f3.addRow("形象类别:", self.character_category_combo)

        self.cat_style_combo = QComboBox()
        f3.addRow("具体形象:", self.cat_style_combo)

        self.locked_tab_behavior_combo = QComboBox()
        self.locked_tab_behavior_combo.addItem("切走生气，返回开心", "emotion")
        self.locked_tab_behavior_combo.addItem("切走隐藏，返回显示", "hide")
        self.locked_tab_behavior_combo.addItem("不改变角色表现", "none")
        self.locked_tab_behavior_combo.setToolTip("仅在启用资源管理器标签页目录锁定后生效；返回开心表情持续约 2.5 秒。")
        f3.addRow("锁定标签页切换:", self.locked_tab_behavior_combo)
        self.attached_focus_behavior_combo = QComboBox()
        self.attached_focus_behavior_combo.addItem("失焦隐藏，返回显示", "hide")
        self.attached_focus_behavior_combo.addItem("失焦生气，返回开心", "emotion")
        self.attached_focus_behavior_combo.addItem("保持显示，不改变表情", "none")
        self.attached_focus_behavior_combo.setToolTip(
            "对所有吸附窗口生效。最小化/隐藏仍隐藏宠物；任一切换规则要求隐藏时优先隐藏，生气优先于开心。")
        f3.addRow("吸附软件焦点切换:", self.attached_focus_behavior_combo)

        self.attached_roam_check = QCheckBox("吸附后自主活动")
        self.attached_roam_check.setToolTip(
            "宠物会沿窗口边缘散步，偶尔探头、翻身或睡觉；最大化时改为沿屏幕边缘活动。")
        f3.addRow("", self.attached_roam_check)

        self.screen_edge_intent_spin = QSpinBox()
        self.screen_edge_intent_spin.setRange(1, 50)
        self.screen_edge_intent_spin.setSuffix(" px")
        self.screen_edge_intent_spin.setToolTip(
            "最大化软件与屏幕边缘重合时，鼠标距屏幕边缘小于此值才判定为屏幕贴边。")
        f3.addRow("屏幕边缘判定:", self.screen_edge_intent_spin)

        self.cat_color_combo = QComboBox()
        for i, color in enumerate(COLORS):
            self.cat_color_combo.addItem(color["name"], i)
        f3.addRow("配色:", self.cat_color_combo)
        l2.addWidget(g3)

        # ---------- 摄像头 ----------
        g4 = QGroupBox("摄像头")
        f4 = QFormLayout(g4)
        self.cam_spin = QSpinBox()
        self.cam_spin.setRange(0, 5)
        f4.addRow("摄像头编号:", self.cam_spin)

        self.debug_check = QCheckBox("调试模式: 满足切换条件时保存检测图片 (debug_shots/)")
        f4.addRow("", self.debug_check)
        dbg_hint = QLabel("图片按天分目录保存, 自动保留最近 3 天; 默认关闭")
        dbg_hint.setStyleSheet(SETTINGS_HINT_STYLE)
        dbg_hint.setWordWrap(True)
        f4.addRow("", dbg_hint)

        def add_opacity_row(title, initial):
            slider = QSlider(Qt.Horizontal)
            slider.setRange(0, 100)
            slider.setTickInterval(10)
            label = QLabel(f"{initial}%")
            label.setMinimumWidth(48)
            row = QHBoxLayout()
            row.addWidget(slider)
            row.addWidget(label)
            f4.addRow(title, row)
            slider.valueChanged.connect(lambda v, out=label: out.setText(f"{v}%"))
            return slider

        self.preview_window_opacity_slider = add_opacity_row("窗口透明度:", 85)
        self.preview_video_opacity_slider = add_opacity_row("摄像头画面:", 85)
        self.preview_overlay_opacity_slider = add_opacity_row("检测标注:", 100)
        opacity_hint = QLabel("窗口、视频画面、人体框/关键点/标签可分别调整")
        opacity_hint.setStyleSheet(SETTINGS_HINT_STYLE)
        opacity_hint.setWordWrap(True)
        f4.addRow("", opacity_hint)
        l2.addWidget(g4)
        l2.addStretch()
        self.tabs.addTab(page2, "形象与摄像头")

        # ========== Tab 3: 目标程序与快捷键 ==========
        page3 = QWidget()
        l3 = QVBoxLayout(page3)
        l3.setContentsMargins(8, 8, 8, 8)

        # ---------- 目标程序切换 ----------
        g5 = QGroupBox("目标程序 (检测到多人自动切换 / 按快捷键手动切换)")
        f5 = QFormLayout(g5)

        self.target_combo = QComboBox()
        self.target_combo.setEditable(True)
        self.target_combo.lineEdit().setPlaceholderText("选择运行中的程序, 或手动输入程序名")
        f5.addRow("目标程序:", self.target_combo)

        refresh_btn = QPushButton("刷新程序列表")
        refresh_btn.clicked.connect(self._refresh_windows)
        f5.addRow("", refresh_btn)

        self.target_title_edit = QLineEdit()
        self.target_title_edit.setPlaceholderText("窗口标题关键字, 如 visual studio (可留空)")
        f5.addRow("标题关键字:", self.target_title_edit)

        self.maximize_target_check = QCheckBox("切换时最大化目标程序")
        f5.addRow("", self.maximize_target_check)

        self.auto_return_check = QCheckBox("人员离开后自动切回原窗口")
        f5.addRow("", self.auto_return_check)
        self.auto_return_delay_spin = QDoubleSpinBox()
        self.auto_return_delay_spin.setRange(1.0, 300.0)
        self.auto_return_delay_spin.setSingleStep(1.0)
        self.auto_return_delay_spin.setSuffix(" 秒")
        self.auto_return_delay_spin.setToolTip(
            "人数低于触发阈值后等待该时间再切回; 再次检测到人员会取消")
        f5.addRow("离开后等待:", self.auto_return_delay_spin)

        hint2 = QLabel("列表中程序员工具 (VS/VSCode/IDEA 等) 已排在前面; 也可手动输入如 devenv / Code")
        hint2.setStyleSheet(SETTINGS_HINT_STYLE)
        hint2.setWordWrap(True)
        f5.addRow("", hint2)
        l3.addWidget(g5)

        # ---------- 全局快捷键 ----------
        g6 = QGroupBox("全局快捷键 (任意界面按下 → 快速切换到目标程序)")
        f6 = QFormLayout(g6)
        hrow = QHBoxLayout()
        self.hk_ctrl = QCheckBox("Ctrl")
        self.hk_alt = QCheckBox("Alt")
        self.hk_shift = QCheckBox("Shift")
        self.hk_win = QCheckBox("Win")
        self.hk_key = QComboBox()
        for k in (list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
                  + [str(d) for d in range(10)]
                  + [f"F{i}" for i in range(1, 13)]):
            self.hk_key.addItem(k)
        self.hk_key.setMinimumWidth(70)
        hrow.addWidget(self.hk_ctrl)
        hrow.addWidget(self.hk_alt)
        hrow.addWidget(self.hk_shift)
        hrow.addWidget(self.hk_win)
        hrow.addSpacing(6)
        hrow.addWidget(self.hk_key)
        hrow.addStretch()
        f6.addRow("组合键:", hrow)

        self.hk_enabled = QCheckBox("启用全局快捷键")
        f6.addRow("", self.hk_enabled)
        l3.addWidget(g6)

        # ---------- 监控启用/禁用快捷键 ----------
        g6_monitor = QGroupBox("监控开关快捷键 (任意界面按下 → 启用/禁用摄像头监控)")
        f6_monitor = QFormLayout(g6_monitor)
        mhrow = QHBoxLayout()
        self.monitor_hk_ctrl = QCheckBox("Ctrl")
        self.monitor_hk_alt = QCheckBox("Alt")
        self.monitor_hk_shift = QCheckBox("Shift")
        self.monitor_hk_win = QCheckBox("Win")
        self.monitor_hk_key = QComboBox()
        for k in (list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
                  + [str(d) for d in range(10)]
                  + [f"F{i}" for i in range(1, 13)]):
            self.monitor_hk_key.addItem(k)
        self.monitor_hk_key.setMinimumWidth(70)
        for control in (self.monitor_hk_ctrl, self.monitor_hk_alt,
                        self.monitor_hk_shift, self.monitor_hk_win):
            mhrow.addWidget(control)
        mhrow.addSpacing(6)
        mhrow.addWidget(self.monitor_hk_key)
        mhrow.addStretch()
        f6_monitor.addRow("组合键:", mhrow)
        self.monitor_hk_enabled = QCheckBox("启用监控开关快捷键")
        self.monitor_hk_enabled.setToolTip(
            "启用时显示青绿渐变脉冲，禁用时显示红橙告警双闪")
        f6_monitor.addRow("", self.monitor_hk_enabled)
        effect_row = QHBoxLayout()
        self.monitor_effect_size_slider = QSlider(Qt.Horizontal)
        self.monitor_effect_size_slider.setRange(80, 600)
        self.monitor_effect_size_slider.setSingleStep(10)
        self.monitor_effect_size_slider.setPageStep(50)
        self.monitor_effect_size_label = QLabel("220 px")
        self.monitor_effect_size_label.setMinimumWidth(55)
        effect_row.addWidget(self.monitor_effect_size_slider, 1)
        effect_row.addWidget(self.monitor_effect_size_label)
        f6_monitor.addRow("闪烁范围:", effect_row)
        effect_hint = QLabel("拖动滑块可实时预览左上角提示范围")
        effect_hint.setStyleSheet(SETTINGS_HINT_STYLE)
        f6_monitor.addRow("", effect_hint)
        l3.addWidget(g6_monitor)

        # ---------- 截图快捷键与第三方 OCR ----------
        g6_screenshot = QGroupBox("截图与贴图")
        f6_screenshot = QFormLayout(g6_screenshot)
        shrow = QHBoxLayout()
        self.screenshot_hk_ctrl = QCheckBox("Ctrl")
        self.screenshot_hk_alt = QCheckBox("Alt")
        self.screenshot_hk_shift = QCheckBox("Shift")
        self.screenshot_hk_win = QCheckBox("Win")
        self.screenshot_hk_key = QComboBox()
        for k in (list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
                  + [str(d) for d in range(10)]
                  + [f"F{i}" for i in range(1, 13)]):
            self.screenshot_hk_key.addItem(k)
        self.screenshot_hk_key.setMinimumWidth(70)
        for control in (self.screenshot_hk_ctrl, self.screenshot_hk_alt,
                        self.screenshot_hk_shift, self.screenshot_hk_win):
            shrow.addWidget(control)
        shrow.addSpacing(6); shrow.addWidget(self.screenshot_hk_key); shrow.addStretch()
        f6_screenshot.addRow("截图快捷键:", shrow)
        self.screenshot_hk_enabled = QCheckBox("启用全局截图快捷键")
        f6_screenshot.addRow("", self.screenshot_hk_enabled)

        self.screenshot_ocr_group = QGroupBox("OCR 配置")
        f6_ocr = QFormLayout(self.screenshot_ocr_group)
        self.screenshot_ocr_form_layout = f6_ocr
        self.screenshot_provider_combo = QComboBox()
        self.screenshot_provider_combo.addItem(
            "本地 RapidOCR SMALL（进程内推理）", "rapidocr_local")
        self.screenshot_provider_combo.addItem(
            "OpenAI-compatible 第三方接口", "openai_compatible")
        f6_ocr.addRow("OCR 服务:", self.screenshot_provider_combo)
        self.screenshot_endpoint_edit = QLineEdit()
        self.screenshot_endpoint_edit.setPlaceholderText(
            "https://服务地址/v1/chat/completions")
        f6_ocr.addRow("OCR 接口地址:", self.screenshot_endpoint_edit)
        self.screenshot_api_key_edit = QLineEdit()
        self.screenshot_api_key_edit.setEchoMode(QLineEdit.Password)
        self.screenshot_api_key_edit.setPlaceholderText("Bearer API Key（保存在本机配置）")
        f6_ocr.addRow("OCR API Key:", self.screenshot_api_key_edit)
        self.screenshot_model_edit = QLineEdit()
        self.screenshot_model_edit.setPlaceholderText("支持图片输入的模型名称")
        f6_ocr.addRow("OCR 模型:", self.screenshot_model_edit)
        self.screenshot_ocr_test_input = QLineEdit()
        self.screenshot_ocr_test_input.setPlaceholderText("输入用于生成测试图片的文字")
        self.screenshot_ocr_test_button = QPushButton("测试 OCR")
        self.screenshot_ocr_test_container = QWidget()
        ocr_test_row = QHBoxLayout(self.screenshot_ocr_test_container)
        ocr_test_row.setContentsMargins(0, 0, 0, 0)
        ocr_test_row.addWidget(self.screenshot_ocr_test_input, 1)
        ocr_test_row.addWidget(self.screenshot_ocr_test_button)
        f6_ocr.addRow("接口测试:", self.screenshot_ocr_test_container)
        self.screenshot_ocr_test_result = QLabel("尚未测试")
        self.screenshot_ocr_test_result.setWordWrap(True)
        self.screenshot_ocr_test_result.setTextInteractionFlags(
            Qt.TextSelectableByMouse)
        f6_ocr.addRow("测试结果:", self.screenshot_ocr_test_result)
        f6_screenshot.addRow(self.screenshot_ocr_group)

        self.screenshot_translate_group = QGroupBox("翻译配置")
        f6_translate = QFormLayout(self.screenshot_translate_group)
        self.screenshot_translate_form_layout = f6_translate
        self.screenshot_translate_provider_combo = QComboBox()
        self.screenshot_translate_provider_combo.addItem("关闭翻译", "disabled")
        self.screenshot_translate_provider_combo.addItem(
            "OpenAI-compatible 翻译接口", "openai_compatible")
        self.screenshot_translate_provider_combo.addItem(
            "讯飞机器翻译 WebAPI（旧版 v2）", "xfyun")
        self.screenshot_translate_provider_combo.addItem(
            "讯飞机器翻译 2.0（新版 v1）", "xfyun_v1")
        f6_translate.addRow("翻译服务:", self.screenshot_translate_provider_combo)
        self.screenshot_result_mode_combo = QComboBox()
        self.screenshot_result_mode_combo.addItem(
            "在原图上擦除并重绘文字（默认）", "image")
        self.screenshot_result_mode_combo.addItem(
            "弹出文字结果窗口", "popup")
        f6_translate.addRow("翻译结果显示:", self.screenshot_result_mode_combo)
        self.screenshot_translate_endpoint_edit = QLineEdit()
        self.screenshot_translate_endpoint_edit.setPlaceholderText(
            "https://翻译服务地址/v1/chat/completions")
        f6_translate.addRow("翻译接口地址:", self.screenshot_translate_endpoint_edit)
        self.screenshot_translate_api_key_edit = QLineEdit()
        self.screenshot_translate_api_key_edit.setEchoMode(QLineEdit.Password)
        self.screenshot_translate_api_key_edit.setPlaceholderText(
            "翻译服务 Bearer API Key（保存在本机）")
        f6_translate.addRow("翻译 API Key:", self.screenshot_translate_api_key_edit)
        self.screenshot_translate_model_edit = QLineEdit()
        self.screenshot_translate_model_edit.setPlaceholderText("翻译模型名称")
        f6_translate.addRow("翻译模型:", self.screenshot_translate_model_edit)
        self.screenshot_xfyun_endpoint_edit = QLineEdit()
        self.screenshot_xfyun_endpoint_edit.setPlaceholderText(
            "https://itrans.xfyun.cn/v2/its")
        f6_translate.addRow("讯飞接口地址:", self.screenshot_xfyun_endpoint_edit)
        self.screenshot_xfyun_v1_endpoint_edit = QLineEdit()
        self.screenshot_xfyun_v1_endpoint_edit.setPlaceholderText(
            "https://itrans.xf-yun.com/v1/its")
        f6_translate.addRow(
            "讯飞 2.0 接口地址:", self.screenshot_xfyun_v1_endpoint_edit)
        self.screenshot_xfyun_res_id_edit = QLineEdit()
        self.screenshot_xfyun_res_id_edit.setPlaceholderText(
            "可选，如：its_en_cn_word")
        f6_translate.addRow("术语资源 RES_ID:", self.screenshot_xfyun_res_id_edit)
        self.screenshot_xfyun_app_id_edit = QLineEdit()
        f6_translate.addRow("旧版 APPID:", self.screenshot_xfyun_app_id_edit)
        self.screenshot_xfyun_api_key_edit = QLineEdit()
        self.screenshot_xfyun_api_key_edit.setEchoMode(QLineEdit.Password)
        f6_translate.addRow("旧版 API Key:", self.screenshot_xfyun_api_key_edit)
        self.screenshot_xfyun_api_secret_edit = QLineEdit()
        self.screenshot_xfyun_api_secret_edit.setEchoMode(QLineEdit.Password)
        f6_translate.addRow("旧版 API Secret:", self.screenshot_xfyun_api_secret_edit)
        self.screenshot_xfyun_v1_app_id_edit = QLineEdit()
        f6_translate.addRow("2.0 APPID:", self.screenshot_xfyun_v1_app_id_edit)
        self.screenshot_xfyun_v1_api_key_edit = QLineEdit()
        self.screenshot_xfyun_v1_api_key_edit.setEchoMode(QLineEdit.Password)
        f6_translate.addRow("2.0 API Key:", self.screenshot_xfyun_v1_api_key_edit)
        self.screenshot_xfyun_v1_api_secret_edit = QLineEdit()
        self.screenshot_xfyun_v1_api_secret_edit.setEchoMode(QLineEdit.Password)
        f6_translate.addRow(
            "2.0 API Secret:", self.screenshot_xfyun_v1_api_secret_edit)
        self.screenshot_xfyun_from_combo = QComboBox()
        for label, code in TRANSLATION_LANGUAGES:
            self.screenshot_xfyun_from_combo.addItem(f"{label} ({code})", code)
        f6_translate.addRow("源语言:", self.screenshot_xfyun_from_combo)
        self.screenshot_language_combo = QComboBox()
        for label, code in TRANSLATION_LANGUAGES:
            self.screenshot_language_combo.addItem(f"{label} ({code})", code)
        # 保留旧属性名，避免外部插件访问设置窗口时失效。
        self.screenshot_language_edit = self.screenshot_language_combo
        f6_translate.addRow("目标语言:", self.screenshot_language_combo)
        self.screenshot_translate_test_input = QLineEdit()
        self.screenshot_translate_test_input.setPlaceholderText("输入需要翻译的测试文本")
        self.screenshot_translate_test_button = QPushButton("测试翻译")
        self.screenshot_translate_test_container = QWidget()
        translate_test_row = QHBoxLayout(self.screenshot_translate_test_container)
        translate_test_row.setContentsMargins(0, 0, 0, 0)
        translate_test_row.addWidget(self.screenshot_translate_test_input, 1)
        translate_test_row.addWidget(self.screenshot_translate_test_button)
        f6_translate.addRow("接口测试:", self.screenshot_translate_test_container)
        self.screenshot_translate_test_result = QLabel("尚未测试")
        self.screenshot_translate_test_result.setWordWrap(True)
        self.screenshot_translate_test_result.setTextInteractionFlags(
            Qt.TextSelectableByMouse)
        f6_translate.addRow("测试结果:", self.screenshot_translate_test_result)
        f6_screenshot.addRow(self.screenshot_translate_group)
        self._config_test_workers = []
        self.screenshot_ocr_test_button.clicked.connect(
            lambda: self._start_api_config_test("ocr"))
        self.screenshot_translate_test_button.clicked.connect(
            lambda: self._start_api_config_test("translate"))
        self.screenshot_provider_combo.currentIndexChanged.connect(
            self._update_ocr_provider_fields)
        self.screenshot_translate_provider_combo.currentIndexChanged.connect(
            self._update_translation_provider_fields)
        self._update_ocr_provider_fields()
        self._update_translation_provider_fields()
        screenshot_hint = QLabel(
            "OCR 始终弹出文字结果；翻译可在原图重绘或弹窗显示。"
            "RapidOCR SMALL 模型直接在当前进程离线识别，无需 EXE 或本地服务；"
            "OCR 与翻译服务相互独立，可分别启用和配置。")
        screenshot_hint.setWordWrap(True)
        screenshot_hint.setStyleSheet(SETTINGS_HINT_STYLE)
        f6_screenshot.addRow("", screenshot_hint)
        l3.addStretch()
        self.tabs.addTab(page3, "目标与快捷键")

        screenshot_page = QWidget()
        screenshot_page.setObjectName("screenshotPage")
        screenshot_page.setStyleSheet("QWidget#screenshotPage{background:#1E1E2A;}")
        screenshot_layout = QVBoxLayout(screenshot_page)
        screenshot_layout.setContentsMargins(8, 8, 8, 8)
        screenshot_scroll = QScrollArea()
        self.screenshot_scroll = screenshot_scroll
        screenshot_scroll.setObjectName("screenshotScroll")
        screenshot_scroll.setWidgetResizable(True)
        screenshot_scroll.setFrameShape(QScrollArea.NoFrame)
        screenshot_scroll.setFixedHeight(520)
        screenshot_scroll.setStyleSheet(
            "QScrollArea#screenshotScroll{background:#1E1E2A;border:none;}"
            "QScrollArea#screenshotScroll QWidget#qt_scrollarea_viewport{background:#1E1E2A;}")
        screenshot_content = QWidget()
        screenshot_content.setObjectName("screenshotContent")
        screenshot_content.setStyleSheet(
            "QWidget#screenshotContent{background:#1E1E2A;}")
        screenshot_content_layout = QVBoxLayout(screenshot_content)
        screenshot_content_layout.setContentsMargins(0, 0, 6, 0)
        screenshot_content_layout.addWidget(g6_screenshot)
        screenshot_content_layout.addStretch()
        screenshot_scroll.setWidget(screenshot_content)
        screenshot_layout.addWidget(screenshot_scroll)
        self.tabs.addTab(screenshot_page, "截图与贴图")

        # ========== Tab 5: 安全 ==========
        page4 = QWidget()
        l4 = QVBoxLayout(page4)
        l4.setContentsMargins(8, 8, 8, 8)

        g7 = QGroupBox("设置页面密码 (打开设置需要输入)")
        f7 = QFormLayout(g7)
        self.pwd_old_edit = QLineEdit()
        self.pwd_old_edit.setEchoMode(QLineEdit.Password)
        has_password = bool(str(cfg.get("settings_password_hash", "")).strip())
        self.pwd_old_edit.setEnabled(has_password)
        self.pwd_old_edit.setPlaceholderText(
            "输入当前密码" if has_password else "尚未设置密码，无需填写")
        f7.addRow("当前密码:", self.pwd_old_edit)
        self.pwd_new_edit = QLineEdit()
        self.pwd_new_edit.setEchoMode(QLineEdit.Password)
        self.pwd_new_edit.setPlaceholderText("留空表示不修改密码")
        f7.addRow("新密码:", self.pwd_new_edit)
        self.pwd_new2_edit = QLineEdit()
        self.pwd_new2_edit.setEchoMode(QLineEdit.Password)
        self.pwd_new2_edit.setPlaceholderText("再输入一遍新密码")
        f7.addRow("确认新密码:", self.pwd_new2_edit)
        pwd_hint = QLabel("首次设置密码无需填写当前密码；已有密码时修改密码才需验证当前密码。修改后点击下方\"保存并应用\"生效；配置文件只保存 SHA-256 哈希，不保存明文。")
        pwd_hint.setStyleSheet(SETTINGS_HINT_STYLE)
        pwd_hint.setWordWrap(True)
        f7.addRow("", pwd_hint)
        l4.addWidget(g7)
        l4.addStretch()
        self.tabs.addTab(page4, "安全")

        # ---------- 按钮 ----------
        btns = QHBoxLayout()
        reset_btn = QPushButton("恢复默认")
        reset_btn.clicked.connect(self._reset)
        exit_btn = QPushButton("退出设置")
        exit_btn.clicked.connect(self.reject)
        ok_btn = QPushButton("保存并应用")
        ok_btn.setObjectName("okBtn")
        ok_btn.clicked.connect(self._save_and_apply)
        btns.addWidget(reset_btn)
        btns.addStretch()
        btns.addWidget(ok_btn)
        btns.addWidget(exit_btn)
        root.addLayout(btns)

        self.scale_slider.valueChanged.connect(
            lambda v: self.scale_label.setText(f"{v}%"))

        # ---------- 载入当前配置 ----------
        self.model_combo.setCurrentIndex(1 if cfg["model"] == "yolo" else 0)
        self.yolo_model_combo.setCurrentText(cfg["yolo_model"])
        self.conf_spin.setValue(cfg["yolo_conf"])
        self.kpt_conf_spin.setValue(cfg.get("pose_kpt_conf", 0.5))
        self.count_spin.setValue(cfg["trigger_count"])
        self.sustain_spin.setValue(cfg["sustain_sec"])
        self.cooldown_spin.setValue(cfg.get("trigger_cooldown_sec", 10.0))
        self.auto_pause_fullscreen_check.setChecked(
            bool(cfg.get("auto_pause_fullscreen", False)))
        self.dedup_spin.setValue(cfg.get("dedup_iou", 0.55))
        self.scale_slider.setValue(int(cfg["cat_scale"] * 100))
        behavior_index = self.locked_tab_behavior_combo.findData(cfg.get("locked_tab_behavior", "emotion"))
        self.locked_tab_behavior_combo.setCurrentIndex(max(0, behavior_index))
        focus_index = self.attached_focus_behavior_combo.findData(cfg.get("attached_focus_behavior", "hide"))
        self.attached_focus_behavior_combo.setCurrentIndex(max(0, focus_index))
        self.attached_roam_check.setChecked(bool(cfg.get("attached_roam_enabled", True)))
        self.screen_edge_intent_spin.setValue(int(cfg.get("screen_edge_intent_px", 5)))
        category = cfg.get("character_category", "cat")
        category_idx = self.character_category_combo.findData(category)
        self.character_category_combo.setCurrentIndex(
            category_idx if category_idx >= 0 else 0)
        self._update_character_styles()
        self.cat_style_combo.setCurrentIndex(max(0, min(
            self.cat_style_combo.count() - 1, int(cfg.get("cat_style", 0)))))
        self.cat_color_combo.setCurrentIndex(max(0, min(
            len(COLORS) - 1, int(cfg.get("cat_color", 0)))))
        self.cam_spin.setValue(cfg["camera_index"])
        self.debug_check.setChecked(bool(cfg.get("debug_save", False)))
        self.preview_window_opacity_slider.setValue(
            int(float(cfg.get("preview_window_opacity", 0.85)) * 100))
        self.preview_video_opacity_slider.setValue(
            int(float(cfg.get("preview_video_opacity",
                              cfg.get("preview_opacity", 0.85))) * 100))
        self.preview_overlay_opacity_slider.setValue(
            int(float(cfg.get("preview_overlay_opacity", 1.0)) * 100))

        # pose 模型联动: 触发标签/单位改为"头部"
        self._update_count_label()
        self.yolo_model_combo.currentTextChanged.connect(
            lambda _t: self._update_count_label())

        # 目标程序
        self._refresh_windows()
        idx = self.target_combo.findData(cfg.get("target_exe", ""))
        if idx >= 0:
            self.target_combo.setCurrentIndex(idx)
        elif cfg.get("target_exe"):
            self.target_combo.setEditText(cfg["target_exe"])
        self.target_title_edit.setText(cfg.get("target_title", ""))
        self.maximize_target_check.setChecked(bool(cfg.get("maximize_target", False)))
        self.auto_return_check.setChecked(bool(cfg.get("auto_return_enabled", False)))
        self.auto_return_delay_spin.setValue(
            float(cfg.get("auto_return_delay_sec", 10.0)))

        # 快捷键
        mod, vk = parse_hotkey(cfg.get("hotkey", "Ctrl+Alt+V"))
        self.hk_ctrl.setChecked(bool(mod & MOD_CONTROL))
        self.hk_alt.setChecked(bool(mod & MOD_ALT))
        self.hk_shift.setChecked(bool(mod & MOD_SHIFT))
        self.hk_win.setChecked(bool(mod & MOD_WIN))
        key_text = next((name for name, code in VK_MAP.items() if code == vk), "V")
        ki = self.hk_key.findText(key_text)
        self.hk_key.setCurrentIndex(ki if ki >= 0 else self.hk_key.findText("V"))
        self.hk_enabled.setChecked(cfg.get("hotkey_enabled", True))

        monitor_mod, monitor_vk = parse_hotkey(
            cfg.get("monitor_hotkey", "Ctrl+Alt+M"))
        self.monitor_hk_ctrl.setChecked(bool(monitor_mod & MOD_CONTROL))
        self.monitor_hk_alt.setChecked(bool(monitor_mod & MOD_ALT))
        self.monitor_hk_shift.setChecked(bool(monitor_mod & MOD_SHIFT))
        self.monitor_hk_win.setChecked(bool(monitor_mod & MOD_WIN))
        monitor_key_text = next(
            (name for name, code in VK_MAP.items() if code == monitor_vk), "M")
        monitor_ki = self.monitor_hk_key.findText(monitor_key_text)
        self.monitor_hk_key.setCurrentIndex(
            monitor_ki if monitor_ki >= 0 else self.monitor_hk_key.findText("M"))
        self.monitor_hk_enabled.setChecked(
            cfg.get("monitor_hotkey_enabled", True))
        self.monitor_effect_size_slider.setValue(
            int(cfg.get("monitor_effect_size", 220)))
        self.monitor_effect_size_label.setText(
            f"{self.monitor_effect_size_slider.value()} px")
        self.monitor_effect_size_slider.valueChanged.connect(
            self._preview_monitor_effect)

        screenshot_mod, screenshot_vk = parse_hotkey(
            cfg.get("screenshot_hotkey", "Alt+A"))
        self.screenshot_hk_ctrl.setChecked(bool(screenshot_mod & MOD_CONTROL))
        self.screenshot_hk_alt.setChecked(bool(screenshot_mod & MOD_ALT))
        self.screenshot_hk_shift.setChecked(bool(screenshot_mod & MOD_SHIFT))
        self.screenshot_hk_win.setChecked(bool(screenshot_mod & MOD_WIN))
        screenshot_key_text = next(
            (name for name, code in VK_MAP.items() if code == screenshot_vk), "A")
        screenshot_ki = self.screenshot_hk_key.findText(screenshot_key_text)
        self.screenshot_hk_key.setCurrentIndex(
            screenshot_ki if screenshot_ki >= 0 else self.screenshot_hk_key.findText("A"))
        self.screenshot_hk_enabled.setChecked(
            cfg.get("screenshot_hotkey_enabled", True))
        provider = cfg.get("screenshot_ocr_provider", "rapidocr_local")
        if provider == "umi_ocr":
            provider = "rapidocr_local"
        provider_idx = self.screenshot_provider_combo.findData(provider)
        self.screenshot_provider_combo.setCurrentIndex(provider_idx if provider_idx >= 0 else 0)
        result_mode_idx = self.screenshot_result_mode_combo.findData(
            cfg.get("screenshot_result_mode", "image"))
        self.screenshot_result_mode_combo.setCurrentIndex(
            result_mode_idx if result_mode_idx >= 0 else 0)
        self.screenshot_endpoint_edit.setText(cfg.get("screenshot_ocr_api_endpoint", ""))
        self.screenshot_api_key_edit.setText(cfg.get("screenshot_ocr_api_key", ""))
        self.screenshot_model_edit.setText(cfg.get("screenshot_ocr_api_model", ""))
        translate_provider_idx = self.screenshot_translate_provider_combo.findData(
            cfg.get("screenshot_translate_provider", "disabled"))
        self.screenshot_translate_provider_combo.setCurrentIndex(
            translate_provider_idx if translate_provider_idx >= 0 else 0)
        self.screenshot_translate_endpoint_edit.setText(
            cfg.get("screenshot_translate_api_endpoint", ""))
        self.screenshot_translate_api_key_edit.setText(
            cfg.get("screenshot_translate_api_key", ""))
        self.screenshot_translate_model_edit.setText(
            cfg.get("screenshot_translate_api_model", ""))
        self.screenshot_xfyun_endpoint_edit.setText(cfg.get(
            "screenshot_xfyun_endpoint", "https://itrans.xfyun.cn/v2/its"))
        self.screenshot_xfyun_v1_endpoint_edit.setText(cfg.get(
            "screenshot_xfyun_v1_endpoint", "https://itrans.xf-yun.com/v1/its"))
        self.screenshot_xfyun_res_id_edit.setText(
            cfg.get("screenshot_xfyun_res_id", ""))
        self.screenshot_xfyun_v1_app_id_edit.setText(
            cfg.get("screenshot_xfyun_v1_app_id", ""))
        self.screenshot_xfyun_v1_api_key_edit.setText(
            cfg.get("screenshot_xfyun_v1_api_key", ""))
        self.screenshot_xfyun_v1_api_secret_edit.setText(
            cfg.get("screenshot_xfyun_v1_api_secret", ""))
        self.screenshot_xfyun_app_id_edit.setText(
            cfg.get("screenshot_xfyun_app_id", ""))
        self.screenshot_xfyun_api_key_edit.setText(
            cfg.get("screenshot_xfyun_api_key", ""))
        self.screenshot_xfyun_api_secret_edit.setText(
            cfg.get("screenshot_xfyun_api_secret", ""))
        xfyun_from_idx = self.screenshot_xfyun_from_combo.findData(
            cfg.get("screenshot_xfyun_from", "cn"))
        self.screenshot_xfyun_from_combo.setCurrentIndex(
            xfyun_from_idx if xfyun_from_idx >= 0 else 0)
        target_language = cfg.get("screenshot_translate_language", "cn")
        target_idx = self.screenshot_language_combo.findData(target_language)
        if target_idx < 0:
            legacy_names = {"简体中文": "cn", "中文": "cn", "汉语": "cn",
                            "英文": "en", "English": "en", "日本語": "ja"}
            target_idx = self.screenshot_language_combo.findData(
                legacy_names.get(str(target_language), target_language))
        self.screenshot_language_combo.setCurrentIndex(
            target_idx if target_idx >= 0 else 0)

        self.character_category_combo.currentIndexChanged.connect(
            self._update_character_styles)

        # 密码: 当前密码引用 + 修改后的新密码 (None = 未修改)
        self._new_password = None

        # 外观和预览设置实时反映到主窗口
        for control in (
                self.scale_slider, self.character_category_combo,
                self.cat_style_combo, self.cat_color_combo,
                self.preview_window_opacity_slider,
                self.preview_video_opacity_slider,
                self.preview_overlay_opacity_slider):
            if isinstance(control, QSlider):
                control.valueChanged.connect(self._apply_live_preview)
            else:
                control.currentIndexChanged.connect(self._apply_live_preview)

    def _update_translation_provider_fields(self, _index=None):
        provider = self.screenshot_translate_provider_combo.currentData()
        enabled = provider in ("openai_compatible", "xfyun", "xfyun_v1")
        show_openai = provider == "openai_compatible"
        show_xfyun = provider in ("xfyun", "xfyun_v1")
        show_xfyun_old = provider == "xfyun"
        show_xfyun_v1 = provider == "xfyun_v1"
        for widget in (self.screenshot_result_mode_combo,
                       self.screenshot_language_combo,
                       self.screenshot_translate_test_container,
                       self.screenshot_translate_test_result):
            self._set_form_row_visible(
                self.screenshot_translate_form_layout, widget, enabled)
        for widget in (self.screenshot_translate_endpoint_edit,
                       self.screenshot_translate_api_key_edit,
                       self.screenshot_translate_model_edit):
            self._set_form_row_visible(
                self.screenshot_translate_form_layout, widget, show_openai)
        self._set_form_row_visible(
            self.screenshot_translate_form_layout,
            self.screenshot_xfyun_endpoint_edit, show_xfyun_old)
        for widget in (self.screenshot_xfyun_v1_endpoint_edit,
                       self.screenshot_xfyun_res_id_edit,
                       self.screenshot_xfyun_v1_app_id_edit,
                       self.screenshot_xfyun_v1_api_key_edit,
                       self.screenshot_xfyun_v1_api_secret_edit):
            self._set_form_row_visible(
                self.screenshot_translate_form_layout, widget, show_xfyun_v1)
        for widget in (self.screenshot_xfyun_app_id_edit,
                       self.screenshot_xfyun_api_key_edit,
                       self.screenshot_xfyun_api_secret_edit):
            self._set_form_row_visible(
                self.screenshot_translate_form_layout, widget, show_xfyun_old)
        self._set_form_row_visible(
            self.screenshot_translate_form_layout,
            self.screenshot_xfyun_from_combo, show_xfyun)

    def _start_api_config_test(self, kind):
        is_ocr = kind == "ocr"
        input_widget = (self.screenshot_ocr_test_input if is_ocr
                        else self.screenshot_translate_test_input)
        button = (self.screenshot_ocr_test_button if is_ocr
                  else self.screenshot_translate_test_button)
        result_label = (self.screenshot_ocr_test_result if is_ocr
                        else self.screenshot_translate_test_result)
        test_text = input_widget.text().strip()
        if not test_text:
            result_label.setText("请输入测试文本")
            return
        pixmap = None
        if is_ocr:
            pixmap = QPixmap(900, 150)
            pixmap.fill(QColor("#FFFFFF"))
            painter = QPainter(pixmap)
            painter.setPen(QColor("#111111"))
            painter.setFont(QFont("Microsoft YaHei UI", 30))
            painter.drawText(
                pixmap.rect().adjusted(24, 12, -24, -12),
                Qt.AlignLeft | Qt.AlignVCenter | Qt.TextWordWrap, test_text)
            painter.end()
        button.setEnabled(False)
        result_label.setText("测试中，请稍候…")
        worker = ApiConfigTestWorker(
            kind, self.get_config(), test_text, pixmap, self)
        self._config_test_workers.append(worker)
        worker.completed.connect(self._api_config_test_completed)
        worker.finished.connect(
            lambda: self._config_test_workers.remove(worker)
            if worker in self._config_test_workers else None)
        worker.start()

    def _api_config_test_completed(self, kind, success, elapsed, result):
        is_ocr = kind == "ocr"
        button = (self.screenshot_ocr_test_button if is_ocr
                  else self.screenshot_translate_test_button)
        result_label = (self.screenshot_ocr_test_result if is_ocr
                        else self.screenshot_translate_test_result)
        button.setEnabled(True)
        status = "成功" if success else "失败"
        result_label.setText(
            f"{status}｜耗时 {elapsed:.3f} 秒\n{result}")

    def _update_ocr_provider_fields(self, _index=None):
        show_api = self.screenshot_provider_combo.currentData() == "openai_compatible"
        for widget in (self.screenshot_endpoint_edit,
                       self.screenshot_api_key_edit,
                       self.screenshot_model_edit):
            self._set_form_row_visible(
                self.screenshot_ocr_form_layout, widget, show_api)

    @staticmethod
    def _set_form_row_visible(form_layout, widget, visible):
        widget.setVisible(visible)
        label = form_layout.labelForField(widget)
        if label is not None:
            label.setVisible(visible)

    def _update_character_styles(self, _index=None):
        category = self.character_category_combo.currentData() or "cat"
        styles = HUMAN_STYLES if category == "human" else CAT_STYLES
        previous = self.cat_style_combo.currentData()
        self.cat_style_combo.blockSignals(True)
        self.cat_style_combo.clear()
        for i, style in enumerate(styles):
            self.cat_style_combo.addItem(style["name"], i)
        idx = self.cat_style_combo.findData(previous)
        self.cat_style_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.cat_style_combo.blockSignals(False)
        self.cat_color_combo.setEnabled(category == "cat")
        self.cat_color_combo.setToolTip(
            "" if category == "cat" else "人类形象的主题色已与具体形象绑定")
        if hasattr(self, "_new_password"):
            self._apply_live_preview()

    def accept(self):
        """保留兼容: 等同于“保存并应用”, 但不关闭窗口。"""
        self._save_and_apply()

    def _validate_password_change(self):
        """保存前校验密码修改输入"""
        old_pwd = self.pwd_old_edit.text()
        new_pwd = self.pwd_new_edit.text()
        new_pwd2 = self.pwd_new2_edit.text()
        if new_pwd or new_pwd2:
            cur_hash = str(self._cfg.get(
                "settings_password_hash",
                DEFAULT_CONFIG["settings_password_hash"])).strip()
            if cur_hash and _hash_password(old_pwd) != cur_hash:
                StyledMessageDialog.warning(self, "密码错误", "当前密码不正确!")
                self.tabs.setCurrentWidget(self.tabs.widget(3))
                self.pwd_old_edit.setFocus()
                return False
            if new_pwd != new_pwd2:
                StyledMessageDialog.warning(self, "密码不一致", "两次输入的新密码不一致!")
                self.tabs.setCurrentWidget(self.tabs.widget(3))
                self.pwd_new_edit.setFocus()
                return False
            if not new_pwd:
                StyledMessageDialog.warning(self, "密码为空", "新密码不能为空!")
                return False
            self._new_password = new_pwd
        return True

    def _apply_live_preview(self, _value=None):
        cat = self.parent()
        if cat is None or not hasattr(cat, "_apply_visual_settings"):
            return
        cat._apply_visual_settings(self.get_config(), show_preview=True)

    def _preview_monitor_effect(self, value):
        self.monitor_effect_size_label.setText(f"{value} px")
        cat = self.parent()
        if cat is None or not hasattr(cat, "monitor_edge_effect"):
            return
        enabled = bool(getattr(cat, "_monitoring_requested", True))
        cat.monitor_edge_effect.flash(enabled, value)

    def _save_and_apply(self):
        if not self._validate_password_change():
            return False
        cfg = self.get_config()
        cat = self.parent()
        if cat is not None and hasattr(cat, "_apply_settings_config"):
            cat._apply_settings_config(cfg)
        else:
            save_config(cfg)
        self._cfg = dict(cfg)
        self._new_password = None
        self.pwd_old_edit.clear()
        self.pwd_new_edit.clear()
        self.pwd_new2_edit.clear()
        has_password = bool(str(cfg.get("settings_password_hash", "")).strip())
        self.pwd_old_edit.setEnabled(has_password)
        self.pwd_old_edit.setPlaceholderText(
            "输入当前密码" if has_password else "尚未设置密码，无需填写")
        self.title_bar.setTitle("小猫设置 — 已保存")
        QTimer.singleShot(1200, lambda: self.title_bar.setTitle("小猫设置"))
        return True

    def _has_unsaved_changes(self):
        current = self.get_config()
        changed = any(self._cfg.get(k, DEFAULT_CONFIG.get(k)) != v
                      for k, v in current.items())
        return changed or bool(self.pwd_old_edit.text() or
                               self.pwd_new_edit.text() or
                               self.pwd_new2_edit.text())

    def _finish_close(self):
        cat = self.parent()
        if cat is not None and hasattr(cat, "preview") and not self._preview_was_visible:
            cat.preview.hide()
        super().reject()

    def reject(self):
        if self._has_unsaved_changes():
            choice = StyledMessageDialog.ask_save(
                self, "设置已修改, 是否保存后退出?")
            if choice == "cancel":
                return
            if choice == "save":
                if not self._save_and_apply():
                    return
            else:
                cat = self.parent()
                if cat is not None and hasattr(cat, "_apply_visual_settings"):
                    cat._apply_visual_settings(self._cfg, show_preview=False)
        self._finish_close()

    def closeEvent(self, event):
        event.ignore()
        self.reject()

    def _update_count_label(self):
        """当前权重是否为 pose 模型 → 切换触发计数标签 (人数/头部数)"""
        if self.count_label is None:
            return
        text = self.yolo_model_combo.currentText().lower()
        if "pose" in text:
            self.count_label.setText("触发头部数 ≥:")
            self.count_spin.setSuffix(" 头")
        else:
            self.count_label.setText("触发人数 ≥:")
            self.count_spin.setSuffix(" 人")

    def _refresh_windows(self):
        """枚举当前运行的程序填充下拉框 (程序员工具优先)"""
        self.target_combo.blockSignals(True)
        try:
            self.target_combo.clear()
            for _hwnd, title, exe in list_windows():
                label = f"{exe or 'unknown'}  -  {title[:40]}"
                self.target_combo.addItem(label, exe)
        except Exception as e:
            _log(f"刷新程序列表失败: {e}")
        finally:
            self.target_combo.blockSignals(False)

    def _reset(self):
        self.model_combo.setCurrentIndex(0)
        self.yolo_model_combo.setCurrentText(DEFAULT_CONFIG["yolo_model"])
        self.conf_spin.setValue(DEFAULT_CONFIG["yolo_conf"])
        self.kpt_conf_spin.setValue(DEFAULT_CONFIG["pose_kpt_conf"])
        self.count_spin.setValue(DEFAULT_CONFIG["trigger_count"])
        self.sustain_spin.setValue(DEFAULT_CONFIG["sustain_sec"])
        self.cooldown_spin.setValue(DEFAULT_CONFIG["trigger_cooldown_sec"])
        self.auto_pause_fullscreen_check.setChecked(
            DEFAULT_CONFIG["auto_pause_fullscreen"])
        self.dedup_spin.setValue(DEFAULT_CONFIG["dedup_iou"])
        self.scale_slider.setValue(100)
        self.locked_tab_behavior_combo.setCurrentIndex(0)
        self.attached_focus_behavior_combo.setCurrentIndex(0)
        self.attached_roam_check.setChecked(DEFAULT_CONFIG["attached_roam_enabled"])
        self.screen_edge_intent_spin.setValue(DEFAULT_CONFIG["screen_edge_intent_px"])
        self.character_category_combo.setCurrentIndex(
            self.character_category_combo.findData("cat"))
        self.cat_style_combo.setCurrentIndex(DEFAULT_CONFIG["cat_style"])
        self.cat_color_combo.setCurrentIndex(DEFAULT_CONFIG["cat_color"])
        self.cam_spin.setValue(0)
        self.debug_check.setChecked(DEFAULT_CONFIG["debug_save"])
        self.preview_window_opacity_slider.setValue(
            int(DEFAULT_CONFIG["preview_window_opacity"] * 100))
        self.preview_video_opacity_slider.setValue(
            int(DEFAULT_CONFIG["preview_video_opacity"] * 100))
        self.preview_overlay_opacity_slider.setValue(
            int(DEFAULT_CONFIG["preview_overlay_opacity"] * 100))
        self.target_title_edit.setText(DEFAULT_CONFIG["target_title"])
        self.maximize_target_check.setChecked(DEFAULT_CONFIG["maximize_target"])
        self.auto_return_check.setChecked(DEFAULT_CONFIG["auto_return_enabled"])
        self.auto_return_delay_spin.setValue(DEFAULT_CONFIG["auto_return_delay_sec"])
        self.hk_ctrl.setChecked(True)
        self.hk_alt.setChecked(True)
        self.hk_shift.setChecked(False)
        self.hk_win.setChecked(False)
        self.hk_key.setCurrentIndex(self.hk_key.findText("V"))
        self.hk_enabled.setChecked(True)
        self.monitor_hk_ctrl.setChecked(True)
        self.monitor_hk_alt.setChecked(True)
        self.monitor_hk_shift.setChecked(False)
        self.monitor_hk_win.setChecked(False)
        self.monitor_hk_key.setCurrentIndex(self.monitor_hk_key.findText("M"))
        self.monitor_hk_enabled.setChecked(True)
        self.monitor_effect_size_slider.setValue(
            DEFAULT_CONFIG["monitor_effect_size"])
        self.screenshot_hk_ctrl.setChecked(False)
        self.screenshot_hk_alt.setChecked(True)
        self.screenshot_hk_shift.setChecked(False)
        self.screenshot_hk_win.setChecked(False)
        self.screenshot_hk_key.setCurrentIndex(
            self.screenshot_hk_key.findText("A"))
        self.screenshot_hk_enabled.setChecked(True)
        self.screenshot_provider_combo.setCurrentIndex(
            self.screenshot_provider_combo.findData("rapidocr_local"))
        self.screenshot_result_mode_combo.setCurrentIndex(0)
        self.screenshot_endpoint_edit.clear()
        self.screenshot_api_key_edit.clear()
        self.screenshot_model_edit.clear()
        self.screenshot_translate_provider_combo.setCurrentIndex(0)
        self.screenshot_translate_endpoint_edit.clear()
        self.screenshot_translate_api_key_edit.clear()
        self.screenshot_translate_model_edit.clear()
        self.screenshot_xfyun_endpoint_edit.setText(
            "https://itrans.xfyun.cn/v2/its")
        self.screenshot_xfyun_v1_endpoint_edit.setText(
            "https://itrans.xf-yun.com/v1/its")
        self.screenshot_xfyun_res_id_edit.clear()
        self.screenshot_xfyun_v1_app_id_edit.clear()
        self.screenshot_xfyun_v1_api_key_edit.clear()
        self.screenshot_xfyun_v1_api_secret_edit.clear()
        self.screenshot_xfyun_app_id_edit.clear()
        self.screenshot_xfyun_api_key_edit.clear()
        self.screenshot_xfyun_api_secret_edit.clear()
        self.screenshot_xfyun_from_combo.setCurrentIndex(0)
        self.screenshot_language_combo.setCurrentIndex(0)
        # 密码输入框清空 (不重置密码本身)
        self.pwd_old_edit.clear()
        self.pwd_new_edit.clear()
        self.pwd_new2_edit.clear()

    def get_config(self):
        # 目标程序: 优先取列表项数据, 手动输入则取输入内容
        exe = self.target_combo.currentData()
        if not exe:
            text = self.target_combo.currentText().strip()
            exe = text.split(" ")[0].lower() if text else ""
        # 快捷键
        mods = []
        if self.hk_ctrl.isChecked():
            mods.append("Ctrl")
        if self.hk_alt.isChecked():
            mods.append("Alt")
        if self.hk_shift.isChecked():
            mods.append("Shift")
        if self.hk_win.isChecked():
            mods.append("Win")
        hotkey = "+".join(mods + [self.hk_key.currentText()]) if mods else ""
        monitor_mods = []
        if self.monitor_hk_ctrl.isChecked():
            monitor_mods.append("Ctrl")
        if self.monitor_hk_alt.isChecked():
            monitor_mods.append("Alt")
        if self.monitor_hk_shift.isChecked():
            monitor_mods.append("Shift")
        if self.monitor_hk_win.isChecked():
            monitor_mods.append("Win")
        monitor_hotkey = "+".join(
            monitor_mods + [self.monitor_hk_key.currentText()]
        ) if monitor_mods else ""
        screenshot_mods = []
        if self.screenshot_hk_ctrl.isChecked():
            screenshot_mods.append("Ctrl")
        if self.screenshot_hk_alt.isChecked():
            screenshot_mods.append("Alt")
        if self.screenshot_hk_shift.isChecked():
            screenshot_mods.append("Shift")
        if self.screenshot_hk_win.isChecked():
            screenshot_mods.append("Win")
        screenshot_hotkey = "+".join(
            screenshot_mods + [self.screenshot_hk_key.currentText()]
        ) if screenshot_mods else ""
        return {
            "model": self.model_combo.currentData(),
            "yolo_model": self.yolo_model_combo.currentText().strip() or "yolo26n.onnx",
            "yolo_conf": round(self.conf_spin.value(), 2),
            "pose_kpt_conf": round(self.kpt_conf_spin.value(), 2),
            "trigger_count": self.count_spin.value(),
            "sustain_sec": round(self.sustain_spin.value(), 1),
            "trigger_cooldown_sec": round(self.cooldown_spin.value(), 1),
            "auto_pause_fullscreen": self.auto_pause_fullscreen_check.isChecked(),
            "dedup_iou": round(self.dedup_spin.value(), 2),
            "cat_scale": self.scale_slider.value() / 100.0,
            "locked_tab_behavior": self.locked_tab_behavior_combo.currentData(),
            "attached_focus_behavior": self.attached_focus_behavior_combo.currentData(),
            "attached_roam_enabled": self.attached_roam_check.isChecked(),
            "screen_edge_intent_px": self.screen_edge_intent_spin.value(),
            "character_category": self.character_category_combo.currentData() or "cat",
            "cat_style": self.cat_style_combo.currentData(),
            "cat_color": self.cat_color_combo.currentData(),
            "camera_index": self.cam_spin.value(),
            "target_exe": (exe or "").lower(),
            "target_title": self.target_title_edit.text().strip(),
            "maximize_target": self.maximize_target_check.isChecked(),
            "auto_return_enabled": self.auto_return_check.isChecked(),
            "auto_return_delay_sec": round(self.auto_return_delay_spin.value(), 1),
            "hotkey": hotkey or "Ctrl+Alt+V",
            "hotkey_enabled": self.hk_enabled.isChecked() and bool(mods),
            "monitor_hotkey": monitor_hotkey or "Ctrl+Alt+M",
            "monitor_hotkey_enabled": (
                self.monitor_hk_enabled.isChecked() and bool(monitor_mods)),
            "monitor_effect_size": self.monitor_effect_size_slider.value(),
            "screenshot_hotkey": screenshot_hotkey or "Alt+A",
            "screenshot_hotkey_enabled": (
                self.screenshot_hk_enabled.isChecked() and bool(screenshot_mods)),
            "screenshot_ocr_provider": (
                self.screenshot_provider_combo.currentData() or "rapidocr_local"),
            "screenshot_result_mode": (
                self.screenshot_result_mode_combo.currentData() or "image"),
            "screenshot_ocr_api_endpoint": self.screenshot_endpoint_edit.text().strip(),
            "screenshot_ocr_api_key": self.screenshot_api_key_edit.text().strip(),
            "screenshot_ocr_api_model": self.screenshot_model_edit.text().strip(),
            "screenshot_translate_provider": (
                self.screenshot_translate_provider_combo.currentData() or "disabled"),
            "screenshot_translate_api_endpoint": (
                self.screenshot_translate_endpoint_edit.text().strip()),
            "screenshot_translate_api_key": (
                self.screenshot_translate_api_key_edit.text().strip()),
            "screenshot_translate_api_model": (
                self.screenshot_translate_model_edit.text().strip()),
            "screenshot_xfyun_endpoint": (
                self.screenshot_xfyun_endpoint_edit.text().strip()
                or "https://itrans.xfyun.cn/v2/its"),
            "screenshot_xfyun_v1_endpoint": (
                self.screenshot_xfyun_v1_endpoint_edit.text().strip()
                or "https://itrans.xf-yun.com/v1/its"),
            "screenshot_xfyun_res_id": (
                self.screenshot_xfyun_res_id_edit.text().strip()),
            "screenshot_xfyun_v1_app_id": (
                self.screenshot_xfyun_v1_app_id_edit.text().strip()),
            "screenshot_xfyun_v1_api_key": (
                self.screenshot_xfyun_v1_api_key_edit.text().strip()),
            "screenshot_xfyun_v1_api_secret": (
                self.screenshot_xfyun_v1_api_secret_edit.text().strip()),
            "screenshot_xfyun_app_id": (
                self.screenshot_xfyun_app_id_edit.text().strip()),
            "screenshot_xfyun_api_key": (
                self.screenshot_xfyun_api_key_edit.text().strip()),
            "screenshot_xfyun_api_secret": (
                self.screenshot_xfyun_api_secret_edit.text().strip()),
            "screenshot_xfyun_from": (
                self.screenshot_xfyun_from_combo.currentData() or "cn"),
            "screenshot_translate_language": (
                self.screenshot_language_combo.currentData() or "cn"),
            "chat_enabled": False,   # 聊天输入功能暂时禁用
            "debug_save": self.debug_check.isChecked(),
            # 非 UI 项原样保留 (预览窗口缩放等由滚轮实时修改)
            "preview_scale": self._cfg.get("preview_scale", 1.0),
            "preview_window_opacity": self.preview_window_opacity_slider.value() / 100.0,
            "preview_video_opacity": self.preview_video_opacity_slider.value() / 100.0,
            "preview_overlay_opacity": self.preview_overlay_opacity_slider.value() / 100.0,
            # 密码: 未修改则保留原哈希; 修改过则存新密码的哈希
            "settings_password_hash": _hash_password(self._new_password) if self._new_password
                else self._cfg.get("settings_password_hash",
                                   DEFAULT_CONFIG["settings_password_hash"]),
        }
