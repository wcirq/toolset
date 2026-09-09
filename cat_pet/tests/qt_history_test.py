import unittest
from unittest.mock import patch

from coolcat.platform.qt_history import merge_older, merge_pages, read_qt_history, newest_messages, message_count, measured_scroll, scroll_delta, scroll_distance


class MergeTests(unittest.TestCase):
    def test_text_fallback_keeps_tokens_for_following_page(self):
        records = [('message', 'a'), ('message', 'b'), ('message', 'c')]
        older = {'records': [('message', 'old'), ('message', 'a'), ('message', 'b')],
                 'record_keys': [(10,), (11,), (12,)]}
        merged, keys = merge_pages(older, records, [(1,), (2,), (3,)])
        self.assertEqual(keys, [(10,), (11,), (12,), (3,)])
        following = {'records': [('message', 'older'), ('message', 'old')],
                     'record_keys': [(20,), (10,)]}
        combined, tokens = merge_pages(following, merged, keys)
        self.assertEqual([text for _, text in combined], ['older', 'old', 'a', 'b', 'c'])

    @patch('coolcat.platform.qt_history.time.sleep')
    @patch('coolcat.platform.qt_history.QtChatRows')
    @patch('coolcat.platform.qt_history.HistoryWindow')
    def test_transient_gap_retries_without_scrolling_farther(self, window, reader, sleep):
        def page(texts):
            return {'identity': (1,), 'rect': (0, 0, 100, 100),
                    'records': [('message', text) for text in texts]}
        initial, transient, loaded = page(['a', 'b', 'c']), page(['loading']), page(['old', 'a', 'b'])
        reader.return_value.read.side_effect = [initial, initial, transient, transient, loaded]
        snapshot = read_qt_history(1, max_messages=4)
        self.assertEqual(snapshot.messages_read, 4)
        self.assertEqual(window.return_value.wheel.call_count, 1)

    def test_time_only_overlap_requires_object_and_geometry(self):
        before = {'records': [('label', '10:00'), ('label', '10:00'), ('message', 'new')],
                  'record_keys': [(1,), (2,), (3,)],
                  'record_rects': [(0, 0, 80, 20), (0, 40, 80, 60), (0, 80, 80, 120)]}
        older = {'records': [('label', '撤回了一条消息'), ('label', '10:00'), ('label', '10:00')],
                 'record_keys': [(0,), (1,), (2,)],
                 'record_rects': [(0, 0, 80, 20), (0, 40, 80, 60), (0, 80, 80, 100)]}
        merged, keys = merge_pages(older, before['records'], before['record_keys'], before)
        self.assertEqual(merged, older['records'] + [('message', 'new')])
        self.assertEqual(message_count(merged), 1)
        older['record_keys'] = [(7,), (8,), (9,)]
        self.assertIsNone(merge_pages(older, before['records'], before['record_keys'], before)[0])

    @patch('coolcat.platform.qt_history.time.sleep')
    @patch('coolcat.platform.qt_history.QtChatRows')
    @patch('coolcat.platform.qt_history.HistoryWindow')
    def test_label_only_page_does_not_end_history(self, window, reader, sleep):
        def page(items, positions):
            return {'identity': (1,), 'rect': (0, 0, 100, 200),
                    'records': [r for _, r in items], 'record_keys': [(k,) for k, _ in items],
                    'record_rects': [(0, y, 100, y+20) for y in positions]}
        label = ('label', '10:00')
        a = page([(1, label), (2, ('message', 'new'))], [0, 100])
        b = page([(0, label), (1, label)], [0, 100])
        c = page([(-1, ('message', 'old')), (0, label)], [0, 100])
        reader.return_value.read.side_effect = [a, a, b, b, b, c, c]
        result = read_qt_history(1, max_messages=2)
        self.assertEqual(result.messages_read, 2)
        self.assertEqual(result.pages_read, 3)
        self.assertNotIn('无法确认连续性', result.warning)

    @patch('coolcat.platform.qt_history.QtChatRows')
    @patch('coolcat.platform.qt_history.HistoryWindow')
    def test_external_viewport_movement_stops_before_next_scroll(self, window, reader):
        page = {'identity': (1,), 'rect': (0, 0, 100, 100),
                'records': [('message', 'one')], 'record_keys': [(1,)],
                'record_rects': [(0, 0, 100, 50)]}
        reader.return_value.read.side_effect = [page, dict(page, record_rects=[(0, 20, 100, 70)])]
        result = read_qt_history(1, max_messages=10)
        window.return_value.wheel.assert_not_called()
        self.assertIn('消息区域', result.warning)

    @patch('coolcat.platform.qt_history.QtChatRows')
    @patch('coolcat.platform.qt_history.HistoryWindow')
    def test_explicit_cancel_is_still_honored(self, window, reader):
        with self.assertRaisesRegex(RuntimeError, '取消'):
            read_qt_history(1, cancelled=lambda: True, max_messages=10)
        window.return_value.wheel.assert_not_called()
        reader.return_value.read.assert_not_called()

    def test_scroll_calibrates_then_keeps_page_overlap(self):
        before = {'rect': (0, 0, 600, 500), 'records': [('message', 'a')],
                  'record_keys': [(1,)], 'record_rects': [(0, 0, 600, 100)]}
        after = dict(before, record_rects=[(0, 37, 600, 137)])
        self.assertEqual(scroll_delta(before, None), 120)
        measured = measured_scroll(before, after, 120)
        self.assertEqual(measured, 37)
        self.assertEqual(scroll_delta(after, measured), 960)
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
        self.assertEqual(scroll_distance(page), 325)
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
            reads.append(page(y-1))
            reads.extend([page(y)] * 2)
        reads.extend([page(4)] * 63)
        reader.return_value.read.side_effect = reads
        snapshot = read_qt_history(1, max_messages=20)
        self.assertEqual(window.return_value.wheel.call_count, 5)
        self.assertEqual(snapshot.messages_read, 1)
        self.assertIn('位置和内容经复核仍未变化', snapshot.warning)

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
    def test_one_scroll_with_stationary_confirmation_stops(self, window, reader, sleep):
        window.return_value.input_token.return_value = 1
        reader.return_value.read.return_value = {'identity': (1,), 'rect': (0, 0, 100, 100),
            'records': [('message', 'only')]}
        snapshot = read_qt_history(1, max_messages=20)
        self.assertEqual(window.return_value.wheel.call_count, 1)
        self.assertEqual(snapshot.messages_read, 1)
        self.assertIn('位置和内容经复核仍未变化', snapshot.warning)
        self.assertEqual(reader.return_value.read.call_count, 4)

    @patch('coolcat.platform.qt_history.time.sleep')
    @patch('coolcat.platform.qt_history.QtChatRows')
    @patch('coolcat.platform.qt_history.HistoryWindow')
    def test_message_limit_overrides_legacy_page_limit(self, window, reader, sleep):
        window.return_value.input_token.return_value = 1
        def page(texts):
            return {'identity': (1,), 'rect': (0, 0, 100, 100),
                    'records': [('message', text) for text in texts]}
        older = page(['a', 'b', 'c'])
        reader.return_value.read.side_effect = [page(['b', 'c', 'd']), page(['b', 'c', 'd']), older, older]
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
    def test_unrelated_user_input_does_not_prevent_scroll(self, window, reader, sleep):
        window.return_value.input_token.side_effect = [1, 1, 1, 2]
        reader.return_value.read.return_value = {'identity': (1,), 'rect': (0, 0, 100, 100),
                                               'records': [('message', 'one')]}
        snapshot = read_qt_history(1, 5)
        self.assertEqual(snapshot.pages_read, 1)
        self.assertEqual(window.return_value.wheel.call_count, 1)
        self.assertNotIn('用户操作', snapshot.warning)

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
