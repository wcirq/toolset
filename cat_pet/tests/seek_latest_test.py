import unittest
from unittest.mock import Mock, patch
from coolcat.platform.qt_history import seek_latest


def page(y, identity=(1,)):
    return {'identity': identity, 'rect': (0, 0, 100, 100),
            'records': [('message', 'same text')], 'record_keys': [(1,)],
            'record_rects': [(0, y, 100, y+60)]}


class SeekTests(unittest.TestCase):
    @patch('coolcat.platform.qt_history.time.sleep')
    def test_already_bottom_only_probes_once(self, sleep):
        window, reader = Mock(), Mock()
        reader.read.return_value = page(0)
        result = seek_latest(window, reader, page(0), lambda: None)
        self.assertEqual(result, page(0))
        self.assertEqual(window.wheel.call_count, 1)
        self.assertEqual(window.wheel.call_args.args, ((0, 0, 100, 100), -14400))
        self.assertTrue(callable(window.wheel.call_args.kwargs['before_batch']))

    @patch('coolcat.platform.qt_history.time.sleep')
    def test_previously_scrolled_history_returns_to_bottom(self, sleep):
        window, reader = Mock(), Mock()
        reader.read.side_effect = [page(-20), page(-20), page(-60), page(-60), page(-60), page(-60)]
        result = seek_latest(window, reader, page(0), lambda: None)
        self.assertEqual(result, page(-60))
        self.assertEqual(window.wheel.call_count, 3)
        self.assertTrue(all(call.args[1] == -14400 for call in window.wheel.call_args_list))

    @patch('coolcat.platform.qt_history.time.sleep')
    def test_switch_during_seek_aborts(self, sleep):
        window, reader = Mock(), Mock()
        reader.read.return_value = page(0, (2,))
        with self.assertRaisesRegex(RuntimeError, '会话发生变化'):
            seek_latest(window, reader, page(0), lambda: None)

    def test_cancel_before_seek_does_not_scroll(self):
        window = Mock()
        with self.assertRaisesRegex(RuntimeError, 'cancel'):
            seek_latest(window, Mock(), page(0), Mock(side_effect=RuntimeError('cancel')))
        window.wheel.assert_not_called()
