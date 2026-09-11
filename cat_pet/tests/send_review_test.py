"""One-shot send validation and review lifecycle, no network or real messages."""
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PyQt5.QtWidgets import QApplication, QWidget
from coolcat.platform import wechat
from coolcat.platform.send_guard import SendGuard
from coolcat.ui.send_review import SendReview

APP = QApplication.instance() or QApplication([])


class SendValidationTests(unittest.TestCase):
    def setUp(self):
        self.root, self.field, self.automation, self.uia = Mock(), Mock(), Mock(), Mock()
        self.buttons = self.root.FindAll.return_value
        self.buttons.Length = 1
        self.button = self.buttons.GetElement.return_value
        self.button.CurrentIsEnabled = True
        self.invoke = self.button.GetCurrentPattern.return_value.QueryInterface.return_value.Invoke
        self.identity = ('root', 'editor', 'conversation')
        self.state = (self.root, self.field, self.identity, 'original')
        self.context = patch.object(wechat, '_with_uia',
                                    side_effect=lambda fn: fn(self.automation, self.uia))
        self.context.start()
        self.addCleanup(self.context.stop)

    def send(self, states):
        with patch.object(wechat, '_draft_identity', side_effect=states):
            wechat.send_original_draft(123, self.identity, 'original')

    def test_one_explicit_send_invokes_once(self):
        self.send([self.state, self.state])
        self.invoke.assert_called_once_with()

    def test_changed_draft_or_session_never_invokes(self):
        for identity, draft in ((self.identity, 'edited'), (('other',), 'original')):
            with self.subTest(identity=identity, draft=draft):
                with self.assertRaisesRegex(RuntimeError, '变化'):
                    self.send([(self.root, self.field, identity, draft)])
        self.invoke.assert_not_called()

    def test_change_between_validation_and_action_never_invokes(self):
        with self.assertRaisesRegex(RuntimeError, '变化'):
            self.send([self.state, (self.root, self.field, self.identity, 'edited')])
        self.invoke.assert_not_called()

    def test_ambiguous_button_never_invokes(self):
        self.buttons.Length = 2
        with self.assertRaisesRegex(RuntimeError, '唯一'):
            self.send([self.state])
        self.invoke.assert_not_called()

    def test_invoke_error_is_not_retried(self):
        self.invoke.side_effect = RuntimeError('outcome unknown')
        with self.assertRaisesRegex(RuntimeError, 'unknown'):
            self.send([self.state, self.state])
        self.invoke.assert_called_once_with()


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.pet = QWidget()
        self.pet._say = Mock()
        self.pet.config = {}
        self.owner = QWidget()
        self.owner.pet = self.pet
        self.owner.target = SimpleNamespace(hwnd=123, pid=456)
        self.owner._is_wechat_target = lambda: True
        with patch('coolcat.ui.send_review.SendGuard'):
            self.review = SendReview(self.owner)
        self.review.timer.stop()
        self.review.hwnd, self.review.pid = 123, 456
        self.threads = patch('coolcat.ui.send_review.threading.Thread')
        self.thread = self.threads.start()
        self.review.intercepted(123, 456)
        self.generation = self.review.generation

    def tearDown(self):
        self.review.close()
        self.threads.stop()
        self.pet.close()
        self.owner.close()

    def test_duplicate_hook_request_does_not_start_second_worker(self):
        self.review.intercepted(123, 456)
        self.thread.assert_called_once()

    def test_mouse_request_reads_draft_without_requiring_editor_focus(self):
        self.review._dismiss(self.generation)
        self.review.intercepted(123, 456, 'mouse')
        run = self.thread.call_args.kwargs['target']
        with patch('coolcat.ui.send_review.focused_chat_input') as focus:
            with patch('coolcat.ui.send_review.capture_send_draft', return_value=(('id',), 'draft')):
                with patch('coolcat.ui.send_review.analyze_wechat_text', return_value='advice'):
                    run()
        focus.assert_not_called()
        self.assertEqual(self.review.dialog.draft.toPlainText(), 'draft')
        self.assertEqual(self.review.dialog.advice.toPlainText(), 'advice')

    def test_mouse_region_is_armed_without_keyboard_focus(self):
        self.review.pending = False
        import time
        region, frame = (30, 30, 60, 60), (0, 0, 100, 100)
        self.review._focused(self.generation, (False, region, frame), time.monotonic())
        self.review.guard.pulse.assert_called_with(False, False)
        self.review.guard.mouse_region.assert_called_with(region, frame)

    def test_slow_probe_disarms_both_input_paths(self):
        self.review.pending = False
        import time
        self.review._focused(self.generation, (True, (1, 1, 2, 2), (0, 0, 3, 3)), time.monotonic() - 2)
        self.review.guard.pulse.assert_called_with(False, False)
        self.review.guard.mouse_region.assert_called_with(None, None)

    def test_double_click_and_late_ai_result_cannot_resend(self):
        self.review._result(self.generation, ('identity',), 'original', '', 'loading')
        self.review._send()
        self.review._result(self.generation, ('identity',), 'original', 'advice', '')
        self.review._send()
        self.assertEqual(self.thread.call_count, 2)  # capture + one send
        self.assertFalse(self.review.dialog.send.isEnabled())
        self.review.guard.pulse.assert_called_with(False, False)
        self.review.guard.mouse_region.assert_called_with()
        self.review.guard.cancel_close.assert_called_once()

    def test_other_bound_chat_disarms_both_paths(self):
        self.review.pending = False
        self.review.sync = Mock()
        self.review.bound_session = object()
        with patch('coolcat.platform.chat_backend.require_selected_session', side_effect=RuntimeError('other chat')):
            with patch('coolcat.ui.send_review.send_guard_state') as probe:
                self.review._poll()
                self.thread.call_args.kwargs['target']()
        probe.assert_not_called()
        self.review.guard.pulse.assert_called_with(False, False)
        self.review.guard.mouse_region.assert_called_with(None, None)

    def test_pending_dialog_does_not_rearm(self):
        import time
        self.review.guard.mouse_region.reset_mock()
        self.review._focused(self.generation, (True, (1, 1, 2, 2), (0, 0, 3, 3)), time.monotonic())
        self.review.guard.mouse_region.assert_not_called()

    def test_stale_model_reply_after_cancel_is_ignored(self):
        self.review._dismiss(self.generation)
        self.review._result(self.generation, ('identity',), 'original', 'advice', '')
        self.assertIsNone(self.review.dialog)
        self.review.guard.cancel_close.assert_called_once()

    def test_previous_request_reply_cannot_overwrite_new_dialog(self):
        self.review._dismiss(self.generation)
        self.review.intercepted(123, 456)
        self.review._result(self.generation, ('identity',), 'stale', 'advice', '')
        self.assertEqual(self.review.dialog.draft.toPlainText(), '')

    def test_unreadable_draft_disables_send(self):
        self.review._result(self.generation, None, '', '', 'read failed')
        self.assertFalse(self.review.dialog.send.isEnabled())


class MouseRegionTests(unittest.TestCase):
    def setUp(self):
        self.root, self.automation = Mock(), Mock()
        self.automation.ElementFromHandle.return_value = self.root
        self.buttons = self.root.FindAll.return_value
        self.buttons.Length = 1
        self.button = self.buttons.GetElement.return_value
        self.button.CurrentIsEnabled = True
        self.button.CurrentIsOffscreen = False
        self.button.CurrentBoundingRectangle = SimpleNamespace(left=-150, top=100, right=-50, bottom=140)

    def probe(self, frames=None):
        with patch.object(wechat, '_with_uia', side_effect=lambda fn: fn(self.automation, Mock())):
            with patch.object(wechat, '_input_focused', return_value=False):
                with patch.object(wechat, 'physical_window_rect', side_effect=frames or [(-800, 0, 0, 600)] * 2):
                    return wechat.send_guard_state(123)

    def test_negative_monitor_coordinates_are_retained(self):
        self.assertEqual(self.probe(), (False, (-150, 100, -50, 140), (-800, 0, 0, 600)))

    def test_disabled_hidden_or_ambiguous_buttons_are_not_armed(self):
        self.button.CurrentIsEnabled = False
        self.assertEqual(self.probe(), (False, None, None))
        self.button.CurrentIsEnabled = True
        self.button.CurrentIsOffscreen = True
        self.assertEqual(self.probe(), (False, None, None))
        self.buttons.Length = 2
        self.assertEqual(self.probe(), (False, None, None))

    def test_window_moves_during_probe(self):
        self.assertEqual(self.probe([(-800, 0, 0, 600), (-700, 0, 100, 600)]), (False, None, None))

    def test_outside_button_rectangle_is_rejected(self):
        self.button.CurrentBoundingRectangle.right = 100
        self.assertEqual(self.probe(), (False, None, None))

    def test_signed_coordinates_pack_without_truncation(self):
        import ctypes
        packed = SendGuard._pack_point(-1920, -200)
        self.assertEqual(ctypes.c_int32(packed & 0xffffffff).value, -1920)
        self.assertEqual(ctypes.c_int32(packed >> 32).value, -200)


if __name__ == '__main__':
    unittest.main()
