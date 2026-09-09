"""Explicit UIA session selection and guarded reply filling."""
import threading

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QListWidget, QListWidgetItem, QPushButton, QPlainTextEdit)

from ..platform.chat_backend import (require_backend, list_sessions, select_session,
                                     read_session, fill_reply)
from .wechat_assistant import analyze_wechat_text


class ChatSessionsDialog(QDialog):
    completed = pyqtSignal(int, str, object)

    def __init__(self, attachment):
        super().__init__(attachment.pet)
        self.attachment = attachment
        self.hwnd = attachment.target.hwnd
        self.pid = attachment.target.pid
        self.config = dict(attachment.pet.config)
        self.generation = 0
        self.busy = False
        self.context = None
        self.cursor = -1
        self.setWindowTitle('会话绑定与回复填写（实验性）')
        self.resize(640, 560)
        layout = QVBoxLayout(self)
        note = QLabel('勾选当前列表中的会话，按“切换下一个”轮流打开。'
                      '切换后可生成回复并填写；填写不会发送。'
                      '此版本尚不支持后台监听或无人值守自动回复。')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.sessions = QListWidget()
        layout.addWidget(self.sessions)
        self.bind_button = QPushButton('将宠物吸附到列表中选中的聊天')
        self.bind_button.clicked.connect(self.bind_anchor)
        layout.addWidget(self.bind_button)
        row = QHBoxLayout()
        self.buttons = []
        for title, handler in [('刷新列表', self.refresh), ('切换下一个', self.select_next),
                               ('生成回复', self.generate), ('填写回复', self.fill)]:
            button = QPushButton(title)
            button.clicked.connect(handler)
            row.addWidget(button)
            self.buttons.append(button)
        layout.addLayout(row)
        self.reply = QPlainTextEdit()
        layout.addWidget(self.reply)
        self.status = QLabel('尚未绑定')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.completed.connect(self.result)
        self.refresh()

    def valid(self):
        target = self.attachment.target
        return (target and (target.hwnd, target.pid) == (self.hwnd, self.pid)
                and self.attachment.pet.config.get('wechat_backend', 'uia') ==
                self.config.get('wechat_backend', 'uia'))

    def bind_anchor(self):
        item = self.sessions.currentItem()
        if not item or not self.valid():
            self.status.setText('请先刷新列表并单击选中一条聊天。')
            return
        self.attachment.bind_chat_session(item.data(Qt.UserRole))
        self.status.setText('已绑定：' + item.data(Qt.UserRole).name + '；关闭此窗口查看宠物位置。')

    def run(self, operation, function):
        if self.busy:
            return
        if not self.valid():
            self.status.setText('吸附目标或后端已变化，请关闭并重新打开。')
            return
        try:
            require_backend(self.config)
        except Exception as exc:
            self.status.setText(str(exc))
            return
        self.busy = True
        self.generation += 1
        generation = self.generation
        for button in self.buttons:
            button.setEnabled(False)
        self.status.setText('正在处理…')
        def work():
            try:
                value = function()
                self.completed.emit(generation, operation, value)
            except Exception as exc:
                self.completed.emit(generation, 'error', str(exc))
        threading.Thread(target=work, daemon=True).start()

    def refresh(self):
        self.context = None
        self.run('list', lambda: list_sessions(self.hwnd))

    def select_next(self):
        selected = [self.sessions.item(i).data(Qt.UserRole)
                    for i in range(self.sessions.count())
                    if self.sessions.item(i).checkState() == Qt.Checked]
        if not selected:
            self.status.setText('请先勾选要绑定的会话。')
            return
        self.cursor = (self.cursor + 1) % len(selected)
        session = selected[self.cursor]
        self.context = None
        def select():
            select_session(self.hwnd, session)
            return session
        self.run('select', select)

    def generate(self):
        if not self.context:
            self.status.setText('请先切换到一个绑定会话。')
            return
        session = self.context[0]
        def generate():
            identity, snapshot = read_session(self.hwnd, session)
            if not snapshot.readable:
                raise RuntimeError('当前会话没有可读取内容。')
            reply = analyze_wechat_text(self.config, snapshot.conversation, mode='reply')
            return session, identity, snapshot.conversation, reply
        self.run('reply', generate)

    def fill(self):
        if not self.context or len(self.context) != 4:
            self.status.setText('请先生成回复。')
            return
        session, identity, conversation, _ = self.context
        reply = self.reply.toPlainText()
        self.run('fill', lambda: fill_reply(self.hwnd, session, identity, conversation, reply))

    def result(self, generation, operation, value):
        if generation != self.generation:
            return
        self.busy = False
        for button in self.buttons:
            button.setEnabled(True)
        if not self.valid():
            self.context = None
            self.status.setText('目标或后端已变化，结果已丢弃。')
            return
        if operation == 'list':
            self.sessions.clear()
            for session in value:
                item = QListWidgetItem(session.name)
                item.setData(Qt.UserRole, session)
                item.setCheckState(Qt.Unchecked)
                self.sessions.addItem(item)
            self.status.setText('已读取 %d 个可见会话；绑定仅在本次窗口生命周期有效。' % len(value))
        elif operation == 'select':
            self.context = (value,)
            self.reply.clear()
            self.status.setText('已请求切换到：' + value.name + '。页面加载后点击生成回复。')
        elif operation == 'reply':
            self.context = value
            self.reply.setPlainText(value[3])
            self.status.setText('回复已生成，可编辑后填写。')
        elif operation == 'fill':
            self.context = None
            self.status.setText('回复已填写，请在客户端检查并发送。')
        else:
            self.context = None
            self.status.setText(str(value))

    def closeEvent(self, event):
        if self.busy:
            self.status.setText('正在完成当前操作，请稍后关闭。')
            event.ignore()
            return
        super().closeEvent(event)
