import unittest
from unittest.mock import Mock, patch
from coolcat.platform.message_details import describe_message, enrich_messages, nickname_candidate
from coolcat.platform.chat_backend import Session, require_selected_session


class DetailTests(unittest.TestCase):
    def test_at_nickname_and_split_suffix_over_image(self):
        avatar, rect = [(10, 10, 50, 50)], (0, 0, 600, 250)
        whole = {'text': '郑红润@湾流畅游', 'rect': (60, 10, 210, 28), 'object': 1}
        image = [(60, 40, 260, 240)]
        self.assertEqual(nickname_candidate(rect, avatar, [whole], image)['text'], '郑红润@湾流畅游')
        parts = [{'text': '郑红润', 'rect': (60, 10, 110, 28), 'object': 1},
                 {'text': '@湾流畅游', 'rect': (112, 10, 210, 28), 'object': 2}]
        result = nickname_candidate(rect, avatar, parts, image)
        self.assertEqual(result['text'], '郑红润@湾流畅游')
        self.assertEqual(result['objects'], [1, 2])
        self.assertIsNone(nickname_candidate(rect, avatar, parts))

    def test_nickname_requires_separate_body_below_avatar_label(self):
        avatar = [(10, 10, 50, 50)]
        nickname = {'text': '小王', 'rect': (60, 10, 110, 28), 'object': 1}
        body = {'text': '下午见', 'rect': (60, 38, 160, 68), 'object': 2}
        self.assertIs(nickname_candidate((0, 0, 600, 100), avatar, [nickname, body]), nickname)
        self.assertIsNone(nickname_candidate((0, 0, 600, 100), avatar, [nickname]))
        self.assertIsNone(nickname_candidate((0, 0, 600, 100), [(550, 10, 590, 50)], [nickname, body]))

    def test_time_context_and_numbering_do_not_invent_sender_or_date(self):
        records = [('label', '昨天 10:30'), ('message', 'old'),
                   ('label', '撤回了一条消息'), ('message', 'https://example.com/a'),
                   ('label', '11:00'), ('message', 'new')]
        details = [describe_message(text, (0, 0, 0, 0), [])
                   for kind, text in records if kind == 'message']
        result = enrich_messages(records, details)
        self.assertEqual([m['number'] for m in result], [3, 2, 1])
        self.assertEqual([m['displayed_time'] for m in result], ['昨天 10:30', '昨天 10:30', '11:00'])
        self.assertEqual(result[1]['links'], ['https://example.com/a'])
        self.assertTrue(all(m['timestamp'] is None and m['sender_id'] is None for m in result))
        self.assertNotIn('number', details[0])

    def test_position_is_not_sender_identity(self):
        detail = describe_message('text', (0, 0, 600, 100), [(550, 10, 590, 50)])
        self.assertEqual(detail['layout_side'], 'right')
        self.assertEqual(detail['direction'], 'outgoing')
        self.assertEqual(detail['direction_basis'], 'user_confirmed_layout')
        self.assertIsNone(detail['sender_name'])
        ambiguous = describe_message('text', (0, 0, 600, 100),
                                     [(10, 10, 50, 50), (550, 10, 590, 50)])
        self.assertEqual(ambiguous['layout_side'], 'unknown')

    @patch('coolcat.platform.chat_backend._items')
    @patch('coolcat.platform.chat_backend._with_uia')
    @patch('coolcat.platform.chat_backend._draft_identity')
    def test_identity_check_does_not_read_draft(self, draft, with_uia, items):
        automation, uia = Mock(), Mock()
        with_uia.side_effect = lambda fn: fn(automation, uia)
        session = Session('session_item_A', (10,), 'A')
        item = Mock()
        item.GetRuntimeId.return_value = (10,)
        item.GetCurrentPattern.return_value.QueryInterface.return_value.CurrentIsSelected = True
        items.return_value = [(session, item)]
        root = automation.ElementFromHandle.return_value
        root.GetRuntimeId.return_value = (1,)
        field = root.FindFirst.return_value
        field.GetRuntimeId.return_value = (2,)
        field.CurrentName = 'A'
        self.assertEqual(require_selected_session(1, session), ((10,), ((1,), (2,), 'A')))
        draft.assert_not_called()
        items.return_value = [(Session('session_item_A', (99,), 'A'), item)]
        with self.assertRaisesRegex(RuntimeError, '重新绑定'):
            require_selected_session(1, session)


if __name__ == '__main__':
    unittest.main()
