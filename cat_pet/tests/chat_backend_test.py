import unittest
from unittest.mock import Mock, patch

from coolcat.platform import chat_backend as backend
from coolcat.platform.wechat import WeChatSnapshot


class ChatBackendTests(unittest.TestCase):
    def test_native_never_falls_back(self):
        with self.assertRaisesRegex(RuntimeError, '暂不可用'):
            backend.require_backend({'wechat_backend': 'native'})

    def test_duplicate_names_rejected(self):
        session = backend.Session('session_item_A', (1,), 'A')
        with patch.object(backend, '_items', return_value=[(session, Mock()), (session, Mock())]):
            with self.assertRaises(RuntimeError):
                backend._resolve(Mock(), 1, session)

    def test_recreated_row_rejected(self):
        session = backend.Session('session_item_A', (1,), 'A')
        replacement = backend.Session('session_item_A', (2,), 'A')
        with patch.object(backend, '_items', return_value=[(replacement, Mock())]):
            with self.assertRaises(RuntimeError):
                backend._resolve(Mock(), 1, session)

    def test_changed_draft_or_conversation_prevents_write(self):
        for draft, conversation in [('manual draft', 'old'), ('', 'new')]:
            field = Mock()
            with patch.object(backend, '_with_uia', side_effect=lambda f: f(Mock(), Mock())), \
                 patch.object(backend, '_selected', return_value=(Mock(), field, ('id',), draft)), \
                 patch.object(backend, '_read_window', return_value=WeChatSnapshot(conversation)):
                with self.assertRaises(RuntimeError):
                    backend.fill_reply(1, Mock(), ('id',), 'old', 'reply')
                field.GetCurrentPattern.assert_not_called()


if __name__ == '__main__':
    unittest.main()
