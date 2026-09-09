import unittest
from unittest.mock import patch

from coolcat.platform.qt_history import merge_older, merge_pages, read_qt_history, newest_messages, message_count, measured_scroll, scroll_delta, scroll_distance


class MergeTests(unittest.TestCase):
    def test_scroll_calibrates_then_keeps_page_overlap(self):
        before = {'rect': (0, 0, 600, 500), 'records': [('message', 'a')],
                  'record_keys': [(1,)], 'record_rects': [(0, 0, 600, 100)]}
        after = dict(before, record_rects=[(0, 37, 600, 137)])
        self.assertEqual(scroll_delta(before, None), 120)
        measured = measured_scroll(before, after, 120)
        self.assertEqual(measured, 37)
        self.assertEqual(scroll_delta(after, measured), 1200)
        self.assertLessEqual(scroll_delta(after, measured)/120*measured, scroll_distance(after))
        self.assertIsNone(measured_scroll(before, dict(after, records=[('message', 'changed')]), 120))

    def test_geometry_retains_second_bubble_and_ignores_time_label(self):
        page = {'rect': (0, 0, 600, 500),
                'records': [('message', 'a'), ('label', 'time'), ('message', 'b')],
                'record_rects': [(0, -20, 600, 60), (0, 60, 600, 80), (0, 100, 600, 180)]}
        distance = scroll_distance(page)
        self.assertGreater(distance, 500*.55)
        self.assertLess(100+distance+24, 500)
        page['record_rects'][2] = (0, 400, 600, 480)
        self.assertLess(scroll_distance(page), 100)

    def test_tall_bubble_and_reflow(self):
        page = {'rect': (0, 0, 600, 500), 'records': [('message', 'a')],
                'record_keys': [(1,)], 'record_rects': [(0, -1000, 600, 800)]}
        self.assertEqual(scroll_distance(page), 400)
        changed = dict(page, record_rects=[(0, -900, 600, 1000)])
        self.assertIsNone(measured_scroll(page, changed, 120))

    def test_nontext_anchor_requires_continuous_geometry(self):
        record = ('message', '[非文本消息或暂不支持的消息类型]')
        previous = {'records': [record], 'record_keys': [(1,)],
                    'record_rects': [(0, 0, 100, 200)]}
        older = {'records': [record, record], 'record_keys': [(2,), (1,)],
                 'record_rects': [(0, -160, 100, 40), (0, 40, 100, 240)]}
        self.assertIsNone(merge_pages(older, previous['records'], previous['record_keys'])[0])
        self.assertEqual(len(merge_pages(older, previous['records'], previous['record_keys'], previous)[0]), 2)
        older['record_rects'][1] = (0, 40, 100, 300)
        self.assertIsNone(merge_pages(older, previous['records'], previous['record_keys'], previous)[0])

    def test_recycled_object_with_different_text_is_not_anchor(self):
        older = {'records': [('message', 'different')], 'record_keys': [(1,)]}
        self.assertIsNone(merge_pages(older, [('message', 'original')], [(1,)])[0])

    @patch('coolcat.platform.qt_history.time.sleep')
    @patch('coolcat.platform.qt_history.QtChatRows')
    @patch('coolcat.platform.qt_history.HistoryWindow')
    def test_tall_bubble_movement_does_not_trigger_end(self, window, reader, sleep):
        window.return_value.input_token.return_value = 1
        def page(y):
            return {'identity': (1,), 'rect': (0, 0, 100, 100),
                    'records': [('message', 'tall')], 'record_keys': [(1,)],
                    'record_rects': [(0, y, 100, y+1000)]}
        reads = [page(0)]
        for y in range(1, 5):
            reads.extend([page(y)] * 2)
        reads.extend([page(4)] * 60)
        reader.return_value.read.side_effect = reads
        snapshot = read_qt_history(1, max_messages=20)
        self.assertEqual(window.return_value.wheel.call_count, 7)
        self.assertEqual(snapshot.messages_read, 1)
        self.assertIn('连续三次', snapshot.warning)

    def test_nontext_inside_overlap_does_not_stop_history(self):
        placeholder = ('message', '[非文本消息或暂不支持的消息类型]')
        previous = [('message', 'a'), ('message', 'b'), placeholder]
        older = [placeholder] + previous
        self.assertEqual(merge_older(older, previous), older)

    def test_scrolled_time_labels_do_not_break_overlap(self):
        old = [('label', 'yesterday'), ('message', 'a'), ('message', 'b'), ('message', 'c')]
        new = [('message', 'b'), ('label', '09:00'), ('message', 'c'), ('message', 'd')]
        merged = merge_older(old, new)
        self.assertEqual([text for kind, text in merged if kind == 'message'], ['a', 'b', 'c', 'd'])

    def test_unsupported_placeholders_cannot_anchor_pages(self):
        records = [('message', '[非文本消息或暂不支持的消息类型]')] * 2
        self.assertIsNone(merge_older(records, records))

    def test_limit_excludes_labels_and_keeps_preceding_time(self):
        records = [('message', 'old'), ('label', 'yesterday'), ('message', 'same'),
                   ('message', 'same'), ('label', 'today'), ('message', 'new')]
        trimmed = newest_messages(records, 3)
        self.assertEqual(trimmed, records[1:])
        self.assertEqual(message_count(trimmed), 3)

    @patch('coolcat.platform.qt_history.QtChatRows')
    @patch('coolcat.platform.qt_history.HistoryWindow')
    def test_first_page_limit_never_scrolls(self, window, reader):
        window.return_value.input_token.return_value = 1
        reader.return_value.read.return_value = {'identity': (1,), 'rect': (0, 0, 100, 100),
            'records': [('message', 'old'), ('message', 'new')]}
        snapshot = read_qt_history(1, max_messages=1)
        self.assertEqual(snapshot.conversation, 'new')
        self.assertEqual(snapshot.messages_read, 1)
        window.return_value.wheel.assert_not_called()

    @patch('coolcat.platform.qt_history.time.sleep')
    @patch('coolcat.platform.qt_history.QtChatRows')
    @patch('coolcat.platform.qt_history.HistoryWindow')
    def test_three_unchanged_scrolls_stop(self, window, reader, sleep):
        window.return_value.input_token.return_value = 1
        reader.return_value.read.return_value = {'identity': (1,), 'rect': (0, 0, 100, 100),
            'records': [('message', 'only')]}
        snapshot = read_qt_history(1, max_messages=20)
        self.assertEqual(window.return_value.wheel.call_count, 3)
        self.assertEqual(snapshot.messages_read, 1)
        self.assertIn('连续三次', snapshot.warning)

    @patch('coolcat.platform.qt_history.time.sleep')
    @patch('coolcat.platform.qt_history.QtChatRows')
    @patch('coolcat.platform.qt_history.HistoryWindow')
    def test_message_limit_overrides_legacy_page_limit(self, window, reader, sleep):
        window.return_value.input_token.return_value = 1
        def page(texts):
            return {'identity': (1,), 'rect': (0, 0, 100, 100),
                    'records': [('message', text) for text in texts]}
        older = page(['a', 'b', 'c'])
        reader.return_value.read.side_effect = [page(['b', 'c', 'd']), older, older]
        snapshot = read_qt_history(1, pages=1, max_messages=4)
        self.assertEqual(snapshot.messages_read, 4)
        self.assertEqual(snapshot.pages_read, 2)
        self.assertEqual(snapshot.conversation, 'a\n\nb\n\nc\n\nd')
        self.assertEqual(window.return_value.wheel.call_count, 1)

    def test_preserves_repeated_messages(self):
        self.assertEqual(merge_older(['old', 'same', 'same', 'end'], ['same', 'end', 'new']),
                         ['old', 'same', 'same', 'end', 'new'])

    def test_ambiguous_overlap_rejected(self):
        self.assertIsNone(merge_older(['x'] * 4, ['x'] * 4))

    def test_no_overlap_rejected(self):
        self.assertIsNone(merge_older(['a', 'b'], ['c', 'd']))

    def test_single_record_overlap_insufficient(self):
        self.assertIsNone(merge_older(['a', 'b'], ['b', 'c']))

    @patch('coolcat.platform.qt_history.time.sleep')
    @patch('coolcat.platform.qt_history.QtChatRows')
    @patch('coolcat.platform.qt_history.HistoryWindow')
    def test_user_input_after_first_page_prevents_scroll(self, window, reader, sleep):
        window.return_value.input_token.side_effect = [1, 1, 1, 2]
        reader.return_value.read.return_value = {'identity': (1,), 'rect': (0, 0, 100, 100),
                                               'records': [('message', 'one')]}
        snapshot = read_qt_history(1, 5)
        self.assertEqual(snapshot.pages_read, 1)
        window.return_value.wheel.assert_not_called()
        self.assertIn('用户操作', snapshot.warning)

    @patch('coolcat.platform.qt_history.time.sleep')
    @patch('coolcat.platform.qt_history.QtChatRows')
    @patch('coolcat.platform.qt_history.HistoryWindow')
    def test_changed_identity_does_not_merge(self, window, reader, sleep):
        window.return_value.input_token.return_value = 1
        reader.return_value.read.side_effect = [
            {'identity': (1,), 'rect': (0, 0, 100, 100), 'records': [('message', 'one')]},
            {'identity': (2,), 'records': [('message', 'other chat')]}]
        snapshot = read_qt_history(1, 5)
        self.assertEqual(snapshot.conversation, 'one')
        self.assertIn('身份变化', snapshot.warning)


if __name__ == '__main__':
    unittest.main()
