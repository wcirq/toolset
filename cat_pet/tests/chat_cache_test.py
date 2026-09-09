import unittest
from unittest.mock import patch
from coolcat.platform.chat_cache import combine_cache, cache_context
from coolcat.platform.qt_history import read_qt_history


class CacheTests(unittest.TestCase):
    @patch('coolcat.platform.qt_history.QtChatRows')
    @patch('coolcat.platform.qt_history.HistoryWindow')
    def test_known_overlap_stops_old_history_scan(self, window, reader):
        reader.return_value.read.return_value = {'identity': (1,), 'rect': (0, 0, 100, 100),
            'records': [('message', 'b'), ('message', 'c'), ('message', 'd')]}
        snapshot = read_qt_history(1, max_messages=100, known_messages=self.messages('a', 'b', 'c'))
        self.assertIn('已衔接缓存', snapshot.warning)
        window.return_value.wheel.assert_not_called()

    def messages(self, *texts):
        return [{'text': text} for text in texts]

    def test_append_new_only_and_keep_numbered_evidence(self):
        cached, count = combine_cache(self.messages('a', 'b', 'c'), self.messages('b', 'c', 'd'))
        self.assertEqual([m['text'] for m in cached], ['a', 'b', 'c', 'd'])
        self.assertEqual(count, 1)
        self.assertIn('[#1]', cache_context(cached))

    def test_no_new_message_does_not_duplicate(self):
        cached, count = combine_cache(self.messages('a', 'b', 'c'), self.messages('b', 'c'))
        self.assertEqual(len(cached), 3)
        self.assertEqual(count, 0)

    def test_ambiguous_or_different_chat_rejected(self):
        for old, new in [(self.messages('a', 'b'), self.messages('c', 'd')),
                         (self.messages('x', 'x', 'x'), self.messages('x', 'x', 'x'))]:
            with self.assertRaises(RuntimeError):
                combine_cache(old, new)
