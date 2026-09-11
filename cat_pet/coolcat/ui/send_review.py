"""Attached-window keyboard/mouse send review, with asynchronous UIA and model operations."""
import threading
import time
from PyQt5.QtCore import QObject, QTimer, pyqtSignal
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QApplication
from ..platform.send_guard import SendGuard
from ..platform.wechat import focused_chat_input, capture_send_draft, send_original_draft, send_guard_state
from .wechat_assistant import analyze_wechat_text


class SendReview(QObject):
    focus_ready = pyqtSignal(int, object, float)
    result_ready = pyqtSignal(int, object, str, str, str)
    sent_ready = pyqtSignal(int, str)

    def __init__(self, attachment):
        super().__init__(attachment)
        self.attachment = attachment
        self.guard = SendGuard(self)
        self.guard.close_requested.connect(self.intercepted)
        self.guard.click_requested.connect(lambda hwnd, pid: self.intercepted(hwnd, pid, 'mouse'))
        self.hwnd = self.pid = self.generation = 0
        self.enabled = True
        self.ctrl = False
        self.dialog = None
        self.checking = False
        self.mouse_ready = False
        self.probed_at = 0.0
        self.pending = False
        self.closed = False
        self.bound_session = None
        self.focus_ready.connect(self._focused)
        self.result_ready.connect(self._result)
        self.sent_ready.connect(self._sent)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._poll)
        self.timer.start(100)

    def sync(self):
        attachment = self.attachment
        target = attachment.target
        hwnd = target.hwnd if self.enabled and attachment._is_wechat_target() else 0
        pid = target.pid if hwnd else 0
        session = getattr(getattr(attachment, 'chat_anchor', None), 'session', None)
        if (hwnd, pid, session) == (self.hwnd, self.pid, self.bound_session):
            return
        self.bound_session = session
        self.generation += 1
        self.guard.uninstall()
        self.hwnd, self.pid = hwnd, pid
        self.mouse_ready = False
        self.pending = False
        if self.dialog:
            self.dialog.close()
            self.dialog.deleteLater()
            self.dialog = None
        if hwnd and not self.guard.install(hwnd, pid):
            attachment.pet._say('发送检查未启用：' + self.guard.error, 200)

    def _poll(self):
        if self.closed:
            return
        self.sync()
        if self.pending:
            self.guard.pulse(False, self.ctrl)
            self.guard.mouse_region()
            return
        if not self.hwnd or not self.guard._hook or self.checking:
            return
        self.checking = True
        hwnd, generation = self.hwnd, self.generation
        session = self.bound_session
        started = time.monotonic()
        def run():
            try:
                if session:
                    from ..platform.chat_backend import require_selected_session
                    require_selected_session(hwnd, session)
                state = send_guard_state(hwnd)
                if session:
                    require_selected_session(hwnd, session)
            except Exception:
                state = (False, None, None)
            if not self.closed:
                self.focus_ready.emit(generation, state, started)
        threading.Thread(target=run, daemon=True).start()

    def _focused(self, generation, state, started):
        self.checking = False
        if generation == self.generation and not self.closed and not self.pending:
            focused, bounds, frame = state
            fresh = time.monotonic() - started < .3
            self.guard.pulse(focused and fresh, self.ctrl)
            posted = self.guard.mouse_region(bounds if fresh else None, frame if fresh else None)
            self.mouse_ready = bool(posted and fresh and bounds is not None and frame is not None)
            self.probed_at = time.monotonic()

    def intercepted(self, hwnd, pid, source='keyboard'):
        if (hwnd, pid) != (self.hwnd, self.pid) or self.pending:
            return
        self.pending = True
        self.generation += 1
        generation = self.generation
        session = self.bound_session
        self.guard.pulse(False, self.ctrl)
        self.guard.mouse_region()
        config = dict(getattr(self.attachment.pet, 'config', {}))
        dialog = QDialog(self.attachment.pet)
        dialog.setWindowTitle('发送前检查 · 发送已拦截')
        dialog.resize(620, 470)
        layout = QVBoxLayout(dialog)
        dialog.status = QLabel('正在读取草稿并生成建议，本次操作尚未发送。')
        dialog.status.setWordWrap(True)
        layout.addWidget(dialog.status)
        dialog.draft = QPlainTextEdit()
        dialog.draft.setReadOnly(True)
        dialog.draft.setMaximumHeight(110)
        layout.addWidget(dialog.draft)
        dialog.advice = QPlainTextEdit()
        dialog.advice.setReadOnly(True)
        layout.addWidget(dialog.advice)
        row = QHBoxLayout()
        copy = QPushButton('复制建议')
        copy.clicked.connect(lambda: QApplication.clipboard().setText(dialog.advice.toPlainText()))
        dialog.submitted = False
        dialog.send = QPushButton('发送原文')
        dialog.send.setEnabled(False)
        dialog.send.setAutoDefault(False)
        dialog.send.clicked.connect(self._send)
        cancel = QPushButton('取消 / 返回编辑')
        cancel.setAutoDefault(False)
        cancel.clicked.connect(dialog.reject)
        for button in (copy, dialog.send, cancel):
            button.setAutoDefault(False)
            row.addWidget(button)
        layout.addLayout(row)
        dialog.finished.connect(lambda _: self._dismiss(generation))
        self.dialog = dialog
        # Read before opening the dialog so UIA focus can be revalidated.
        def run():
            identity, draft, advice, error = None, '', '', ''
            try:
                if session:
                    from ..platform.chat_backend import require_selected_session
                    require_selected_session(hwnd, session)
                if source == 'keyboard' and not focused_chat_input(hwnd):
                    raise RuntimeError('输入焦点已变化，本次未发送；请返回输入框重试')
                identity, draft = capture_send_draft(hwnd)
                if not self.closed:
                    self.result_ready.emit(generation, identity, draft, '', '正在生成建议；可取消或明确选择发送原文。')
                advice = analyze_wechat_text(config, '', draft, 'draft')
            except Exception as exc:
                error = str(exc)
            if not self.closed:
                self.result_ready.emit(generation, identity, draft, advice, error)
        threading.Thread(target=run, daemon=True).start()
        # Do not steal UIA focus until the capture has finished.
        self.attachment.pet._say('发送已拦截，正在检查草稿…', 120)

    def _result(self, generation, identity, draft, advice, error):
        if generation != self.generation or not self.pending or not self.dialog:
            return
        dialog = self.dialog
        if dialog.submitted:
            return
        dialog.identity, dialog.original = identity, draft
        dialog.draft.setPlainText(draft)
        dialog.advice.setPlainText(advice)
        dialog.status.setText(error or '请核对建议。发送原文会发送上方草稿；采用建议请复制后返回编辑。')
        dialog.send.setEnabled(identity is not None and bool(draft))
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _send(self):
        dialog = self.dialog
        if not dialog or not dialog.send.isEnabled():
            return
        dialog.send.setEnabled(False)
        dialog.submitted = True
        hwnd, generation = self.hwnd, self.generation
        identity, draft = dialog.identity, dialog.original
        session = self.bound_session
        # GUI state cannot change between these checks and spawning the worker.
        current_session = getattr(getattr(self.attachment, 'chat_anchor', None), 'session', None)
        if (not self.enabled or not self.attachment.target or self.attachment.target.hwnd != hwnd
                or current_session != session):
            dialog.status.setText('绑定已变化，本次未发送')
            return
        dialog.status.setText('正在提交一次发送请求…')
        # Release the intercepted input state and disarm before Invoke can
        # synthesize a click; polling remains disarmed while pending.
        self.guard.pulse(False, self.ctrl)
        self.guard.mouse_region()
        self.guard.cancel_close()
        def run():
            error = ''
            try:
                if session:
                    from ..platform.chat_backend import require_selected_session
                    require_selected_session(hwnd, session)
                send_original_draft(hwnd, identity, draft)
            except Exception as exc:
                error = '发送未完成或结果未知，请在客户端核对，勿重复提交：' + str(exc)
            if not self.closed:
                self.sent_ready.emit(generation, error)
        threading.Thread(target=run, daemon=True).start()

    def _sent(self, generation, error):
        if generation != self.generation or not self.dialog:
            return
        if error:
            self.dialog.status.setText(error)
        else:
            self.dialog.accept()

    def _dismiss(self, generation):
        if generation == self.generation:
            self.pending = False
            self.guard.cancel_close()
            if self.dialog:
                self.dialog.deleteLater()
            self.dialog = None

    def close(self):
        self.closed = True
        self.generation += 1
        self.timer.stop()
        self.guard.close()
        if self.dialog:
            self.dialog.close()
            self.dialog.deleteLater()
            self.dialog = None
