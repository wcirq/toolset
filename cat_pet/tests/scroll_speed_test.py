import unittest
from unittest.mock import patch
from coolcat.platform.qt_history import read_qt_history


class SpeedTests(unittest.TestCase):
    @patch('coolcat.platform.qt_history.time.sleep')
    @patch('coolcat.platform.qt_history.QtChatRows')
    @patch('coolcat.platform.qt_history.HistoryWindow')
    def test_uniform_mode_uses_one_notch_per_page(self, window, reader, sleep):
        def page(texts):
            return {'identity': (1,), 'rect': (0, 0, 100, 100),
                    'records': [('message', text) for text in texts]}
        initial, older = page(['b', 'c', 'd']), page(['a', 'b', 'c'])
        reader.return_value.read.side_effect = [initial, initial, older, older]
        result = read_qt_history(1, max_messages=4, scroll_speed=4)
        self.assertEqual(result.messages_read, 4)
        window.return_value.wheel.assert_called_once_with((0, 0, 100, 100), 120)
