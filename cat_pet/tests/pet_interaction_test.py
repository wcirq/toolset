"""Mouse gesture and screenshot lifetime regressions; no camera or native input."""
import os
import sys
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PyQt5.QtCore import QPoint, QPointF, QRect, QEvent, Qt
from PyQt5.QtGui import QMouseEvent
from PyQt5.QtWidgets import QApplication
from coolcat.cat_window import CatWindow
from coolcat.config import DEFAULT_CONFIG
from coolcat.platform.attachment import Target

APP = QApplication.instance() or QApplication([])


class InteractionTests(unittest.TestCase):
    def setUp(self):
        self.target = Target(123, 456, 'test', 'App', QRect(50, 50, 800, 600))
        self.backend = SimpleNamespace(
            get=lambda _: self.target, all=lambda: [self.target],
            active=lambda _: True, escape_pressed=lambda: False,
            api=SimpleNamespace(IsWindowVisible=lambda _: True))
        with ExitStack() as stack:
            stack.enter_context(patch('coolcat.cat_window.load_config', return_value=dict(DEFAULT_CONFIG)))
            stack.enter_context(patch('coolcat.cat_window.is_autostart_enabled', return_value=False))
            stack.enter_context(patch('coolcat.ui.attachment.NativeWindows', return_value=self.backend))
            for method in ('_start_camera_thread', '_apply_hotkey', '_apply_monitor_hotkey',
                           '_apply_screenshot_hotkey'):
                stack.enter_context(patch.object(CatWindow, method))
            self.pet = CatWindow()
        for timer in (self.pet.timer, self.pet.fullscreen_timer, self.pet.attachment.timer,
                      self.pet.attachment.send_review.timer):
            timer.stop()
        self.pet.move(300, 300)
        self.pet.show()

    def tearDown(self):
        self.pet.attachment.close()
        self.pet.press_timer.stop()
        for overlay in tuple(self.pet._screenshot_overlays):
            overlay.close()
        APP.sendPostedEvents(None, QEvent.DeferredDelete)
        self.pet.tray.hide()
        for manager in (self.pet.hotkey_mgr, self.pet.monitor_hotkey_mgr, self.pet.screenshot_hotkey_mgr):
            APP.removeNativeEventFilter(manager)
        self.pet.preview.hide()
        self.pet.hide()
        self.pet.deleteLater()

    def mouse(self, kind, delta=QPoint()):
        local = QPoint(50, 50)
        event = QMouseEvent(kind, QPointF(local), QPointF(QPoint(350, 350) + delta),
                            Qt.NoButton if kind == QEvent.MouseMove else Qt.LeftButton,
                            Qt.NoButton if kind == QEvent.MouseButtonRelease else Qt.LeftButton,
                            Qt.NoModifier)
        {QEvent.MouseButtonPress: self.pet.mousePressEvent,
         QEvent.MouseMove: self.pet.mouseMoveEvent,
         QEvent.MouseButtonRelease: self.pet.mouseReleaseEvent}[kind](event)

    def test_stationary_hold_never_starts_attachment(self):
        self.pet.snap_edge = 'left'
        original = self.pet.pos()
        self.mouse(QEvent.MouseButtonPress)
        with patch.object(self.pet.attachment, 'update_drag') as scan:
            self.pet.attachment.tick()
            self.mouse(QEvent.MouseMove, QPoint(2, 1))
            self.pet._on_long_press()
            self.pet.attachment.tick()
            scan.assert_not_called()
        self.assertTrue(self.pet.preview.isVisible())
        self.assertFalse(self.pet.attachment.dragging)
        self.assertEqual(self.pet.pos(), original)
        self.assertEqual(self.pet.snap_edge, 'left')
        self.mouse(QEvent.MouseButtonRelease)
        self.assertFalse(self.pet.preview.isVisible())
        self.assertIsNone(self.pet.attachment.target)

    def test_attached_hold_preserves_binding(self):
        self.pet.attachment.attach(self.target, 'top-left')
        original = self.pet.pos()
        self.mouse(QEvent.MouseButtonPress)
        self.pet._on_long_press()
        self.mouse(QEvent.MouseMove, QPoint(40, 40))
        self.mouse(QEvent.MouseButtonRelease)
        self.assertEqual(self.pet.pos(), original)
        self.assertIs(self.pet.attachment.target, self.target)
        self.assertEqual(self.pet.attachment.corner, 'top-left')

    def test_threshold_starts_drag_once_and_cancels_hold(self):
        self.mouse(QEvent.MouseButtonPress)
        with patch.object(self.pet.attachment, 'begin_drag', wraps=self.pet.attachment.begin_drag) as begin:
            with patch.object(self.pet.attachment, 'update_drag'):
                self.mouse(QEvent.MouseMove, QPoint(7, 0))
                begin.assert_not_called()
                self.mouse(QEvent.MouseMove, QPoint(8, 0))
                self.mouse(QEvent.MouseMove, QPoint(1, 0))
                begin.assert_called_once()
        self.pet._on_long_press()
        self.assertFalse(self.pet.longpress_active)
        self.assertFalse(self.pet.press_timer.isActive())

    def test_duplicate_screenshot_hotkey_preserves_selection(self):
        self.pet._on_screenshot_hotkey()
        overlay = self.pet._screenshot_overlay
        overlay.selection = QRect(20, 20, 80, 60)
        self.pet._on_screenshot_hotkey()
        APP.sendPostedEvents(None, QEvent.DeferredDelete)
        self.assertIs(self.pet._screenshot_overlay, overlay)
        self.assertEqual(overlay.selection, QRect(20, 20, 80, 60))
        self.assertTrue(overlay.isVisible())

    def test_old_screenshot_destruction_does_not_clear_new_window(self):
        self.pet._on_screenshot_hotkey()
        old = self.pet._screenshot_overlay
        old.close()  # WA_DeleteOnClose is deferred.
        self.pet._on_screenshot_hotkey()
        new = self.pet._screenshot_overlay
        self.assertIsNot(old, new)
        APP.sendPostedEvents(None, QEvent.DeferredDelete)
        self.assertIs(self.pet._screenshot_overlay, new)
        self.assertTrue(new.isVisible())

    def test_hidden_screenshot_remains_owned_until_closed(self):
        self.pet._on_screenshot_hotkey()
        old = self.pet._screenshot_overlay
        old.hide()  # OCR results can hide a capture while work still runs.
        self.pet._on_screenshot_hotkey()
        self.assertIn(old, self.pet._screenshot_overlays)
        self.assertEqual(len(self.pet._screenshot_overlays), 2)
        old.close()
        APP.sendPostedEvents(None, QEvent.DeferredDelete)
        self.assertEqual(len(self.pet._screenshot_overlays), 1)

    def test_attachment_pauses_during_screenshot_then_resumes(self):
        self.pet.attachment.attach(self.target, 'top-left')
        self.pet._on_screenshot_hotkey()
        with patch.object(self.pet.attachment, '_activity_position', return_value=QPoint(200, 200)) as move:
            self.pet.attachment.tick()
            move.assert_not_called()
            self.pet._screenshot_overlay.close()
            APP.sendPostedEvents(None, QEvent.DeferredDelete)
            self.pet.attachment.tick()
            move.assert_called_once()


if __name__ == '__main__':
    unittest.main()
