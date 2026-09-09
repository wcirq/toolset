import unittest
from unittest.mock import patch
from coolcat.platform.qt_history import read_qt_history
from coolcat.platform.chat_backend import Session
from coolcat.ui.wechat_assistant import WeChatAnalysisWorker


class BoundReadTests(unittest.TestCase):
    @patch('coolcat.platform.chat_backend.require_selected_session')
    @patch('coolcat.ui.wechat_assistant.read_wechat_window')
    def test_wrong_chat_never_reads(self, read, selected):
        selected.side_effect = RuntimeError('wrong chat')
        worker = WeChatAnalysisWorker(1, {}, 'read', session=Session('a', (1,), 'a'))
        results = []
        worker.completed.connect(lambda *args: results.append(args))
        worker.run()
        read.assert_not_called()
        self.assertFalse(results[0][0])

    @patch('coolcat.platform.qt_history.time.sleep')
    @patch('coolcat.platform.qt_history.QtChatRows')
    @patch('coolcat.platform.qt_history.HistoryWindow')
    def test_switch_during_history_discards_partial_result(self, window, reader, sleep):
        window.return_value.input_token.return_value = 1
        reader.return_value.read.return_value = {'identity': (1,), 'rect': (0, 0, 100, 100),
                                               'records': [('message', 'bound')]}
        calls = 0
        def validate():
            nonlocal calls
            calls += 1
            if calls == 4:
                raise RuntimeError('switched')
        with self.assertRaisesRegex(RuntimeError, 'switched'):
            read_qt_history(1, max_messages=10, validate_session=validate)


if __name__ == '__main__':
    unittest.main()
