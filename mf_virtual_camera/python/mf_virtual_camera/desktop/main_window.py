from __future__ import annotations

import uuid

import cv2
from PyQt5.QtCore import Qt, QPoint
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QMainWindow, QMessageBox,
    QPlainTextEdit, QPushButton, QSpinBox, QTabWidget, QVBoxLayout, QWidget,
)

from .camera_manager import CameraManager
from .plugin_host import EXAMPLE_PLUGIN, validate_in_subprocess
from .sender import SenderConfig, SenderThread
from .theme import STYLESHEET


class TitleBar(QFrame):
    def __init__(self, window):
        super().__init__(); self.window = window; self._offset = QPoint()
        row = QHBoxLayout(self); row.setContentsMargins(18, 8, 8, 8)
        brand = QLabel("●  SSKJ CAMERA STUDIO"); brand.setObjectName("title"); row.addWidget(brand)
        row.addStretch(); minimize = QPushButton("—"); close = QPushButton("×")
        minimize.setFixedWidth(42); close.setFixedWidth(42); close.setObjectName("danger")
        minimize.clicked.connect(window.showMinimized); close.clicked.connect(window.close)
        row.addWidget(minimize); row.addWidget(close)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton: self._offset = event.globalPos() - self.window.pos()
    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton: self.window.move(event.globalPos() - self._offset)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__(); self.manager = CameraManager(); self.sender = None; self.plugin_valid = False
        self.setWindowTitle("SSKJ Camera Studio"); self.resize(1120, 760)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        root = QWidget(); root.setObjectName("root"); self.setCentralWidget(root)
        layout = QVBoxLayout(root); layout.setContentsMargins(10, 10, 10, 10)
        layout.addWidget(TitleBar(self)); self.tabs = QTabWidget(); layout.addWidget(self.tabs)
        self.tabs.addTab(self._studio_page(), "直播工作台")
        self.tabs.addTab(self._devices_page(), "虚拟相机")
        self.tabs.addTab(self._plugin_page(), "帧插件")
        self.tabs.addTab(self._log_page(), "运行日志")
        self.setStyleSheet(STYLESHEET); self.refresh_devices()

    def _card(self):
        frame = QFrame(); frame.setObjectName("card"); return frame

    def _studio_page(self):
        page = QWidget(); outer = QHBoxLayout(page)
        left = self._card(); form = QFormLayout(left); form.setContentsMargins(22, 22, 22, 22)
        self.source_type = QComboBox(); self.source_type.addItems(["图片或视频", "物理摄像头", "网络流", "测试画面"])
        self.source = QLineEdit(); browse = QPushButton("选择文件"); browse.clicked.connect(self.choose_source)
        source_row = QWidget(); sr = QHBoxLayout(source_row); sr.setContentsMargins(0,0,0,0); sr.addWidget(self.source); sr.addWidget(browse)
        self.camera_index = QSpinBox(); self.camera_index.setRange(0, 32)
        self.fps = QDoubleSpinBox(); self.fps.setRange(1, 120); self.fps.setValue(30); self.fps.setSuffix(" FPS")
        self.loop = QCheckBox("循环播放"); self.loop.setChecked(True)
        self.mirror = QCheckBox("水平镜像")
        self.output_size = QComboBox(); self.output_size.addItems(["1280×720 IPC（应用可协商 1080p/720p/480p）"])
        form.addRow("视频源类型", self.source_type); form.addRow("文件 / URL", source_row)
        form.addRow("摄像头索引", self.camera_index); form.addRow("发送帧率", self.fps)
        form.addRow("输出", self.output_size); form.addRow("播放", self.loop); form.addRow("画面", self.mirror)
        buttons = QWidget(); br = QHBoxLayout(buttons); br.setContentsMargins(0,8,0,0)
        self.start_button = QPushButton("开始发送"); self.start_button.setObjectName("primary")
        stop = QPushButton("停止"); self.start_button.clicked.connect(self.start_sender); stop.clicked.connect(self.stop_sender)
        br.addWidget(self.start_button); br.addWidget(stop); form.addRow(buttons)
        self.status = QLabel("准备就绪"); self.status.setObjectName("muted"); form.addRow("状态", self.status)
        right = self._card(); rv = QVBoxLayout(right); rv.setContentsMargins(16,16,16,16)
        self.preview = QLabel("预览将在开始发送后显示"); self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(600, 420); self.preview.setStyleSheet("background:#070B14;border-radius:10px;color:#52627E")
        rv.addWidget(self.preview); outer.addWidget(left, 4); outer.addWidget(right, 7); return page

    def _devices_page(self):
        page = QWidget(); layout = QHBoxLayout(page)
        card = self._card(); cv = QVBoxLayout(card); cv.setContentsMargins(22,22,22,22)
        title = QLabel("系统摄像头"); title.setObjectName("title"); cv.addWidget(title)
        self.devices = QListWidget(); cv.addWidget(self.devices)
        row = QHBoxLayout(); install = QPushButton("安装默认相机"); install.setObjectName("primary")
        uninstall = QPushButton("删除正式相机"); uninstall.setObjectName("danger"); refresh = QPushButton("刷新列表")
        remove_test = QPushButton("删除企微测试相机"); remove_test.setObjectName("danger")
        install.clicked.connect(self.install); uninstall.clicked.connect(self.uninstall)
        remove_test.clicked.connect(self.remove_wecom_test); refresh.clicked.connect(self.refresh_devices)
        row.addWidget(install); row.addWidget(uninstall); row.addWidget(remove_test); row.addWidget(refresh); cv.addLayout(row)
        custom = self._card(); form = QFormLayout(custom); form.setContentsMargins(22,22,22,22)
        heading = QLabel("自定义实例"); heading.setObjectName("title"); self.camera_name = QLineEdit("我的虚拟摄像头")
        self.instance_id = QLineEdit("{" + str(uuid.uuid4()).upper() + "}")
        add = QPushButton("创建实例"); add.setObjectName("primary"); remove = QPushButton("移除实例")
        add.clicked.connect(self.add_instance); remove.clicked.connect(self.remove_instance)
        form.addRow(heading); form.addRow("相机名称", self.camera_name); form.addRow("实例 GUID", self.instance_id)
        form.addRow(add); form.addRow(remove); layout.addWidget(card, 3); layout.addWidget(custom, 2); return page

    def _plugin_page(self):
        page = QWidget(); layout = QVBoxLayout(page); card = self._card(); cv = QVBoxLayout(card); cv.setContentsMargins(22,22,22,22)
        heading = QLabel("Python 帧处理插件"); heading.setObjectName("title"); hint = QLabel("定义 process(frame, context)。验证成功后，下次开始发送立即生效。仅运行可信代码。")
        hint.setObjectName("muted"); self.editor = QPlainTextEdit(EXAMPLE_PLUGIN); self.editor.setTabStopDistance(28)
        row = QHBoxLayout(); validate = QPushButton("验证并启用"); validate.setObjectName("primary"); disable = QPushButton("停用插件")
        validate.clicked.connect(self.validate_plugin); disable.clicked.connect(self.disable_plugin); row.addWidget(validate); row.addWidget(disable); row.addStretch()
        self.plugin_result = QPlainTextEdit(); self.plugin_result.setReadOnly(True); self.plugin_result.setMaximumHeight(150)
        cv.addWidget(heading); cv.addWidget(hint); cv.addWidget(self.editor, 1); cv.addLayout(row); cv.addWidget(self.plugin_result)
        layout.addWidget(card); return page

    def _log_page(self):
        page = QWidget(); layout = QVBoxLayout(page); self.log = QPlainTextEdit(); self.log.setReadOnly(True); layout.addWidget(self.log); return page

    def write_log(self, text): self.log.appendPlainText(text)
    def choose_source(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择图片或视频", "", "媒体文件 (*.jpg *.jpeg *.png *.bmp *.mp4 *.avi *.mkv *.mov);;所有文件 (*)")
        if path: self.source.setText(path)

    def start_sender(self):
        self.stop_sender(); labels = ["file", "camera", "stream", "pattern"]; kind = labels[self.source_type.currentIndex()]
        value = str(self.camera_index.value()) if kind == "camera" else self.source.text().strip()
        if kind == "pattern": value = "clock"
        if not value: QMessageBox.warning(self, "缺少视频源", "请选择文件或填写网络流地址。"); return
        config = SenderConfig(kind, value, self.fps.value(), self.loop.isChecked(), self.mirror.isChecked(),
                              self.editor.toPlainText() if self.plugin_valid else "")
        self.sender = SenderThread(config, self); self.sender.preview.connect(self.show_preview)
        self.sender.status.connect(self.status.setText); self.sender.failed.connect(self.on_error); self.sender.start()

    def stop_sender(self):
        if self.sender and self.sender.isRunning(): self.sender.stop()
        self.sender = None
    def show_preview(self, frame):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB); h,w,c = rgb.shape
        image = QImage(rgb.data, w, h, c*w, QImage.Format_RGB888).copy()
        self.preview.setPixmap(QPixmap.fromImage(image).scaled(self.preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
    def on_error(self, message): self.write_log(message); QMessageBox.critical(self, "运行错误", message[-2000:])
    def validate_plugin(self):
        result = validate_in_subprocess(self.editor.toPlainText()); self.plugin_valid = bool(result["ok"])
        self.plugin_result.setPlainText(result["message"]); self.write_log("插件：" + result["message"])
    def disable_plugin(self): self.plugin_valid = False; self.plugin_result.setPlainText("插件已停用")
    def install(self): self._admin(self.manager.install_primary, "默认相机安装完成。")
    def uninstall(self): self._admin(self.manager.uninstall_primary, "正式相机删除完成。")
    def remove_wecom_test(self): self._admin(self.manager.remove_wecom_test, "企微测试相机删除完成。")
    def add_instance(self): self._admin(lambda: self.manager.add_instance(self.camera_name.text(), self.instance_id.text()), "自定义相机创建完成。")
    def remove_instance(self): self._admin(lambda: self.manager.remove_instance(self.camera_name.text(), self.instance_id.text()), "自定义相机删除完成。")
    def _admin(self, action, message):
        try:
            detail = action(); self.write_log(message + ("\n" + detail if detail else ""))
            self.status.setText(message); self.refresh_devices()
        except Exception as exc: self.on_error(str(exc))
    def refresh_devices(self):
        self.devices.clear(); items = self.manager.list_system(); self.devices.addItems(items or ["未找到探针结果；安装后点击刷新"])
    def closeEvent(self, event): self.stop_sender(); event.accept()
