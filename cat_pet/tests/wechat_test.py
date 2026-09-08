"""Text-only adapter regression tests; no desktop, OCR or network access."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from coolcat.platform.wechat import _read_input, _read_window, read_wechat_window


class WeChatTests(unittest.TestCase):
    def setUp(self):
        self.uia = SimpleNamespace(IUIAutomationTextPattern=object(),
                                   IUIAutomationValuePattern=object())
        self.field = Mock()
        self.field.GetCurrentPattern.return_value.QueryInterface.return_value.DocumentRange.GetText.return_value = '草稿'
        self.messages = Mock()
        items = self.messages.FindAll.return_value
        items.Length = 3
        items.GetElement.side_effect = [SimpleNamespace(CurrentName=t)
                                       for t in ('你好', '你好', '下一条')]
        self.automation = Mock()
        self.automation.CreatePropertyCondition.side_effect = lambda key, value: (key, value)
        self.automation.ElementFromHandle.return_value.FindFirst.side_effect = (
            lambda scope, condition: {'chat_input_field': self.field,
                                     'chat_message_list': self.messages}[condition[1]])

    def test_read_messages_and_draft_preserves_repeated_messages(self):
        result = _read_window(self.automation, self.uia, 1, 'read')
        self.assertEqual(result.conversation, '你好\n你好\n下一条')
        self.assertEqual(result.input_text, '草稿')

    def test_draft_does_not_read_message_history(self):
        result = _read_window(self.automation, self.uia, 1, 'draft')
        self.assertEqual(result.input_text, '草稿')
        self.messages.FindAll.assert_not_called()

    def test_conversation_does_not_read_draft(self):
        result = _read_window(self.automation, self.uia, 1, 'conversation')
        self.assertTrue(result.readable)
        self.field.GetCurrentPattern.assert_not_called()

    def test_empty_draft_is_not_replaced_by_accessible_name(self):
        self.field.CurrentName = '会话标题'
        self.field.GetCurrentPattern.return_value.QueryInterface.return_value.DocumentRange.GetText.return_value = ''
        self.assertEqual(_read_input(self.field, self.uia), '')

    def test_value_pattern_fallback(self):
        value = Mock()
        value.QueryInterface.return_value.CurrentValue = '备用文本'
        self.field.GetCurrentPattern.side_effect = [RuntimeError(), value]
        self.assertEqual(_read_input(self.field, self.uia), '备用文本')

    def test_missing_patterns_fail_without_ocr(self):
        self.field.GetCurrentPattern.side_effect = RuntimeError('unsupported')
        with self.assertRaisesRegex(RuntimeError, '文本接口'):
            _read_input(self.field, self.uia)

    def test_missing_message_list(self):
        self.automation.ElementFromHandle.return_value.FindFirst.side_effect = None
        self.automation.ElementFromHandle.return_value.FindFirst.return_value = None
        with self.assertRaisesRegex(RuntimeError, '消息列表'):
            _read_window(self.automation, self.uia, 1, 'conversation')

    def test_old_screenshot_mode_is_rejected(self):
        self.assertTrue(read_wechat_window(1, 'history').error)


if __name__ == '__main__':
    unittest.main()
