"""Offscreen attachment state/geometry tests; never move external windows."""
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PyQt5.QtCore import QPoint, QPointF, QRect, QSize, QTimer, Qt, QEvent
from PyQt5.QtGui import QMouseEvent
from PyQt5.QtWidgets import QApplication, QMenu, QWidget
from coolcat.platform.attachment import (ANCHOR_NAMES, Target, anchor_placements,
                                         attachment_position, corner_position)
from coolcat.ui.attachment import WindowAttachment, secondary_selection_zone
from coolcat.platform.explorer import select_folder

APP = QApplication.instance() or QApplication([])


class Pet(QWidget):
    DRAG, IDLE = 'drag', 'idle'

    def __init__(self):
        super().__init__()
        self.resize(240, 290)
        self.follow = True
        self.snap_edge = 'right'
        self.state = self.DRAG
        self.press_timer = QTimer(self)
        self.messages = []

    def _set_state(self, state, _):
        self.state = state

    def _say(self, text, duration):
        self.messages.append(text)


class Backend:
    def __init__(self):
        self.target = Target(101, 222, 'Test window', 'App', QRect(100, 100, 900, 700))
        self.foreground = True
        self.escape = False
        self.api = SimpleNamespace(IsWindowVisible=lambda hwnd: True)

    def get(self, hwnd):
        return self.target if self.target and self.target.hwnd == hwnd else None

    def all(self):
        return [self.target] if self.target and self.target.visible else []

    def active(self, target):
        return self.foreground

    def escape_pressed(self):
        return self.escape


class AttachmentTests(unittest.TestCase):
    def setUp(self):
        self.pet, self.backend = Pet(), Backend()
        self.controller = WindowAttachment(self.pet, self.backend)
        self.controller.timer.stop()
        self.pet.show()

    def tearDown(self):
        self.controller.close()
        self.pet.close()

    def attach(self):
        self.assertTrue(self.controller.attach(self.backend.target, 'bottom-right'))

    def test_geometry_negative_monitor_and_oversize(self):
        rect = QRect(-1920, -200, 1000, 800)
        self.assertEqual(corner_position(rect, QSize(240, 290), 'top-left'), QPoint(-1910, -190))
        self.assertEqual(corner_position(rect, QSize(240, 290), 'bottom-right'), QPoint(-1170, 300))
        self.assertEqual(corner_position(rect, QSize(2000, 900), 'bottom-right'), rect.topLeft())
        edge_positions = {key: attachment_position(rect, QSize(240, 290), key)
                          for key in ANCHOR_NAMES}
        self.assertEqual(len(set((p.x(), p.y()) for p in edge_positions.values())), 8)
        corner_grid = {(attachment_position(rect, QSize(240, 290), 'top-left', cell).x(),
                        attachment_position(rect, QSize(240, 290), 'top-left', cell).y())
                       for cell in anchor_placements('top-left')}
        self.assertEqual(len(corner_grid), 4)
        self.assertEqual(len(anchor_placements('top')), 2)

    def test_follow_move_resize_and_modes(self):
        self.attach()
        self.assertFalse(self.pet.follow)
        self.assertIsNone(self.pet.snap_edge)
        self.assertEqual(self.pet.pos(), QPoint(750, 500))
        self.backend.target.rect = QRect(-800, 40, 1200, 850)
        self.controller.tick()
        self.assertEqual(self.pet.pos(), QPoint(150, 590))
        self.pet.resize(120, 145)
        self.controller.tick()
        self.assertEqual(self.pet.pos(), QPoint(270, 735))

    def test_hide_restore_background_minimize_manual(self):
        self.attach()
        self.backend.foreground = False
        self.controller.tick()
        self.assertFalse(self.pet.isVisible())
        self.backend.foreground = True
        self.controller.tick()
        self.assertTrue(self.pet.isVisible())
        self.backend.target.visible = False
        self.controller.tick()
        self.assertFalse(self.pet.isVisible())
        self.backend.target.visible = True
        self.controller.tick()
        self.assertTrue(self.pet.isVisible())
        self.controller.manual_hidden = True
        self.pet.hide()
        self.controller.tick()
        self.assertFalse(self.pet.isVisible())

    def test_closed_and_reused_handle(self):
        self.attach()
        self.backend.foreground = False
        self.controller.tick()
        self.backend.target = None
        self.controller.tick()
        self.assertIsNone(self.controller.target)
        self.assertTrue(self.pet.isVisible())

    def test_pid_reuse_detaches(self):
        self.attach()
        self.backend.target = Target(101, 999, 'New process', 'App', QRect(0, 0, 500, 500))
        self.controller.tick()
        self.assertIsNone(self.controller.target)

    def test_short_drag_snaps_back_and_escape_restores(self):
        self.attach()
        self.controller.begin_drag()
        self.pet.move(self.pet.pos() + QPoint(15, 10))
        with patch.object(self.controller, 'update_drag'):
            self.assertTrue(self.controller.end_drag(20))
        self.assertEqual(self.pet.pos(), QPoint(750, 500))
        self.controller.begin_drag()
        self.pet.move(400, 300)
        self.backend.escape = True
        self.controller.tick()
        self.assertEqual(self.pet.pos(), QPoint(750, 500))
        self.assertIsNotNone(self.controller.target)
        self.assertTrue(self.controller.end_drag(500))

    def test_drag_suspends_tracking_and_long_drag_detaches(self):
        self.attach()
        self.controller.begin_drag()
        self.pet.move(500, 200)
        self.controller.tick()
        self.assertEqual(self.pet.pos(), QPoint(500, 200))
        with patch.object(self.controller, 'update_drag'):
            self.assertFalse(self.controller.end_drag(200))
        self.assertIsNone(self.controller.target)

    def test_corner_preview_release_and_disable(self):
        self.controller.begin_drag()
        self.pet.move(750, 500)
        with patch('coolcat.ui.attachment.QCursor.pos', return_value=QPoint(970, 770)):
            self.controller.update_drag(force=True)
            self.assertEqual(self.controller.candidate_corner, 'bottom-right')
            self.assertTrue(self.controller.end_drag(200))
        self.assertIsNotNone(self.controller.target)
        self.controller._set_enabled(False)
        self.assertIsNone(self.controller.candidate)

    def test_edge_preview_uses_two_exact_pet_rectangles(self):
        self.controller.begin_drag()
        expected = attachment_position(self.backend.target.rect, self.pet.size(), 'top', (0, 1))
        self.pet.move(expected)
        with patch('coolcat.ui.attachment.QCursor.pos', return_value=QPoint(550, 120)):
            self.controller.update_drag(force=True)
        self.assertEqual(self.controller.candidate_corner, 'top')
        self.assertEqual(self.controller.candidate_placement, (0, 1))
        self.assertEqual(len(self.controller.preview.markers), 2)
        local_expected = QRect(expected - self.controller.preview.origin, self.pet.size())
        self.assertEqual(self.controller.preview.markers[(0, 1)], local_expected)

    def test_corner_preview_four_rectangles_match_all_final_positions(self):
        self.controller.begin_drag()
        selected = (0, 1)
        expected = attachment_position(self.backend.target.rect, self.pet.size(), 'top-left', selected)
        self.pet.move(expected)
        with patch('coolcat.ui.attachment.QCursor.pos', return_value=QPoint(105, 105)):
            self.controller.update_drag(force=True)
        self.assertEqual(self.controller.candidate_corner, 'top-left')
        self.assertEqual(self.controller.candidate_placement, selected)
        self.assertEqual(len(self.controller.preview.markers), 4)
        for cell, marker in self.controller.preview.markers.items():
            actual = QRect(attachment_position(self.backend.target.rect, self.pet.size(),
                                               'top-left', cell) - self.controller.preview.origin,
                           self.pet.size())
            self.assertEqual(marker, actual)

    def test_preview_with_anchor_but_no_selected_cell_does_not_crash(self):
        self.controller.preview.display(self.backend.target, self.pet.size(), 'left', None)
        APP.processEvents()
        image = self.controller.preview.grab()
        self.assertFalse(image.isNull())

    def test_secondary_grid_keeps_original_target_over_other_window(self):
        original = self.backend.target
        other = Target(202, 333, 'Other window', 'App', QRect(0, 0, 90, 90))
        self.controller.begin_drag()
        self.pet.move(attachment_position(original.rect, self.pet.size(), 'top-left', (1, 1)))
        with patch.object(self.backend, 'all', return_value=[original]), \
                patch('coolcat.ui.attachment.QCursor.pos', return_value=QPoint(120, 120)):
            self.controller.update_drag(force=True)
        self.assertEqual(self.controller.candidate.hwnd, original.hwnd)
        self.assertEqual(self.controller.candidate_corner, 'top-left')

        across = attachment_position(original.rect, self.pet.size(), 'top-left', (0, 0))
        self.pet.move(across)
        # This point is across the original frame and over another eligible app,
        # but still belongs to the original target's corner selection zone.
        with patch.object(self.backend, 'all', return_value=[other, original]), \
                patch('coolcat.ui.attachment.QCursor.pos', return_value=QPoint(50, 50)):
            self.controller.update_drag(force=True)
        self.assertEqual(self.controller.candidate.hwnd, original.hwnd)
        self.assertEqual(self.controller.candidate_corner, 'top-left')
        self.assertEqual(self.controller.candidate_placement, (0, 0))

    def test_leaving_entire_secondary_grid_allows_new_target(self):
        original = self.backend.target
        other = Target(202, 333, 'Other window', 'App', QRect(900, 900, 300, 250))
        self.controller.candidate = original
        self.controller.candidate_corner = 'top-left'
        zone = secondary_selection_zone(original.rect, self.pet.size(), 'top-left')
        self.assertFalse(zone.contains(QPoint(950, 950)))
        self.pet.move(attachment_position(other.rect, self.pet.size(), 'top-left', (1, 1)))
        with patch.object(self.backend, 'all', return_value=[other, original]), \
                patch('coolcat.ui.attachment.QCursor.pos', return_value=QPoint(950, 950)):
            self.controller.update_drag(force=True)
        self.assertEqual(self.controller.candidate.hwnd, other.hwnd)

    def test_vertical_edge_slides_y_cancels_sideways_and_enters_corner(self):
        target = self.backend.target
        self.controller.begin_drag()
        self.pet.move(target.rect.left() + 10, 300)
        with patch('coolcat.ui.attachment.QCursor.pos', return_value=QPoint(150, 350)):
            self.controller.update_drag(force=True)
        self.assertEqual(self.controller.candidate_corner, 'left')
        first_ratio = self.controller.candidate_edge_ratio
        self.pet.move(target.rect.left() + 10, 450)
        with patch('coolcat.ui.attachment.QCursor.pos', return_value=QPoint(150, 500)):
            self.controller.update_drag(force=True)
        self.assertEqual(self.controller.candidate_corner, 'left')
        self.assertGreater(self.controller.candidate_edge_ratio, first_ratio)
        self.pet.move(400, 300)
        with patch('coolcat.ui.attachment.QCursor.pos', return_value=QPoint(450, 350)):
            self.controller.update_drag(force=True)
        self.assertIsNone(self.controller.candidate_corner)
        self.pet.move(110, 110)
        with patch('coolcat.ui.attachment.QCursor.pos', return_value=QPoint(150, 150)):
            self.controller.update_drag(force=True)
        self.assertEqual(self.controller.candidate_corner, 'top-left')

    def test_horizontal_edge_slides_x_and_preserves_ratio_after_attach(self):
        target = self.backend.target
        self.controller.begin_drag()
        self.pet.move(500, target.rect.top() + 10)
        with patch('coolcat.ui.attachment.QCursor.pos', return_value=QPoint(550, 150)):
            self.controller.update_drag(force=True)
            ratio = self.controller.candidate_edge_ratio
            self.assertEqual(self.controller.candidate_corner, 'top')
            self.assertTrue(self.controller.end_drag(200))
        self.assertEqual(self.controller.corner, 'top')
        self.assertAlmostEqual(self.controller.edge_ratio, ratio)
        expected = attachment_position(target.rect, self.pet.size(), 'top', self.controller.placement,
                                       edge_ratio=ratio)
        self.assertEqual(self.pet.pos(), expected)

    def test_maximized_overlap_uses_configured_screen_edge_distance(self):
        screen = SimpleNamespace(geometry=lambda: QRect(0, 0, 800, 600))
        target = Target(9, 8, 'Maximized', 'App', QRect(0, 0, 800, 600), True, True)
        with patch.object(QApplication, 'screenAt', return_value=screen), \
                patch.object(QApplication, 'keyboardModifiers', return_value=Qt.NoModifier):
            self.assertEqual(self.controller._resolve_intent(target, QPoint(4, 300)), 'screen')
            self.assertEqual(self.controller._resolve_intent(target, QPoint(5, 300)), 'software')
            self.assertEqual(self.controller._resolve_intent(target, QPoint(796, 300)), 'screen')
            self.assertEqual(self.controller._resolve_intent(target, QPoint(795, 300)), 'software')
            self.assertEqual(self.controller._resolve_intent(target, QPoint(400, 4)), 'screen')
            self.assertEqual(self.controller._resolve_intent(target, QPoint(400, 595)), 'software')
            self.assertEqual(self.controller._resolve_intent(target, QPoint(400, 596)), 'screen')

    def test_screen_edge_distance_is_configurable(self):
        screen = SimpleNamespace(geometry=lambda: QRect(0, 0, 800, 600))
        target = Target(9, 8, 'Maximized', 'App', QRect(0, 0, 800, 600), True, True)
        self.pet.config = {'screen_edge_intent_px': 10}
        with patch.object(QApplication, 'screenAt', return_value=screen), \
                patch.object(QApplication, 'keyboardModifiers', return_value=Qt.NoModifier):
            self.assertEqual(self.controller._resolve_intent(target, QPoint(9, 300)), 'screen')
            self.assertEqual(self.controller._resolve_intent(target, QPoint(10, 300)), 'software')

    def test_non_maximized_window_keeps_software_attachment_at_screen_edge(self):
        screen = SimpleNamespace(geometry=lambda: QRect(0, 0, 800, 600))
        target = Target(9, 8, 'Normal', 'App', QRect(0, 0, 800, 600), True, False)
        with patch.object(QApplication, 'screenAt', return_value=screen), \
                patch.object(QApplication, 'keyboardModifiers', return_value=Qt.NoModifier):
            self.assertEqual(self.controller._resolve_intent(target, QPoint(0, 300)), 'auto')

    def test_shift_and_ctrl_force_overlap_intent(self):
        screen = SimpleNamespace(geometry=lambda: QRect(0, 0, 800, 600))
        target = Target(9, 8, 'Maximized', 'App', QRect(0, 0, 800, 600), True, True)
        with patch.object(QApplication, 'screenAt', return_value=screen):
            with patch.object(QApplication, 'keyboardModifiers', return_value=Qt.ShiftModifier):
                self.assertEqual(self.controller._resolve_intent(target, QPoint(0, 300), 1), 'software')
            with patch.object(QApplication, 'keyboardModifiers', return_value=Qt.ControlModifier):
                self.assertEqual(self.controller._resolve_intent(target, QPoint(30, 300), 2), 'screen')

    def test_screen_intent_is_consumed_once_on_release(self):
        self.controller.begin_drag()
        self.controller.intent_mode = 'screen'
        self.controller.intent_edge = 'left'
        with patch.object(self.controller, 'update_drag'):
            self.assertFalse(self.controller.end_drag(100))
        self.assertEqual(self.controller.take_screen_intent(), 'left')
        self.assertIsNone(self.controller.take_screen_intent())

    def test_stale_folder_result_and_menu(self):
        self.attach()
        token = self.controller.generation
        self.controller._folder_ready(101, token, 'folder', 'D:\\folder')
        self.assertEqual(self.controller.folder_path, 'D:\\folder')
        self.controller.detach()
        self.controller._folder_ready(101, token, 'old', 'D:\\old')
        self.assertEqual(self.controller.folder_path, '')
        menu = QMenu()
        self.controller.add_menu(menu)
        self.assertEqual(menu.actions()[0].text(), '软件窗口吸附')

    def test_position_menu_has_eight_anchors_and_grids(self):
        self.attach()
        menu = QMenu()
        self.controller.populate_menu(menu)
        position_action = next(a for a in menu.actions() if a.text() == '吸附位置')
        anchors = position_action.menu().actions()
        self.assertEqual(len(anchors), 8)
        counts = {action.text().replace(' ✓', ''): len(action.menu().actions())
                  for action in anchors}
        for name in ('左上角', '右上角', '左下角', '右下角'):
            self.assertEqual(counts[name], 4)
        for name in ('上边缘', '下边缘', '左边缘', '右边缘'):
            self.assertEqual(counts[name], 2)

    def test_explorer_tabs_and_virtual_folders(self):
        self.assertEqual(select_folder([(False, 'old', 'D:\\old'),
                                        (True, 'new', 'D:\\new')]), ('new', 'D:\\new'))
        self.assertEqual(select_folder([(True, '此电脑', '')]), ('此电脑', ''))
        self.assertEqual(select_folder([(None, 'unknown', 'D:\\wrong')])[1], '')
        self.assertEqual(select_folder([(True, 'a', 'D:\\a'), (True, 'b', 'D:\\b')])[1], '')
        self.assertEqual(select_folder([])[1], '')

    def test_directory_lock_lifecycle_and_menu(self):
        self.backend.target.kind = 'CabinetWClass'
        # Do not query real Explorer from an offscreen fake-window test.
        with patch.object(self.controller.reader, 'request'):
            self.attach()
            with patch.object(self.controller.folder_lock, 'start') as start:
                self.controller.lock_folder()
                start.assert_called_once()
            self.assertEqual(self.controller.lock_state, 'pending')
            token = self.controller.folder_lock.token
            self.controller._lock_changed(token, 'locked', 'D:\\folder')
            menu = QMenu()
            self.controller.populate_menu(menu)
            self.assertIn('解除目录锁定', [a.text() for a in menu.actions()])
            self.controller.attach(self.backend.target, 'top-left')
            self.assertEqual(self.controller.lock_path, 'D:\\folder')
            self.controller.detach()
            self.assertFalse(self.controller.lock_state)
            self.controller._lock_changed(token, 'locked', 'D:\\stale')
            self.assertFalse(self.controller.lock_state)

    def test_directory_lock_error_is_visible_and_cancels(self):
        self.attach()
        token = self.controller.folder_lock.token
        self.controller.lock_state = 'pending'
        self.controller._lock_changed(token, 'error', '测试：标签页已关闭')
        self.assertFalse(self.controller.lock_state)
        self.assertEqual(self.controller.lock_error, '测试：标签页已关闭')
        self.assertIn('测试：标签页已关闭', self.pet.messages)

    def test_pet_mouse_event_integration(self):
        from contextlib import ExitStack
        from coolcat.cat_window import CatWindow
        from coolcat.config import DEFAULT_CONFIG
        with ExitStack() as stack:
            stack.enter_context(patch('coolcat.cat_window.load_config', return_value=dict(DEFAULT_CONFIG)))
            stack.enter_context(patch('coolcat.cat_window.is_autostart_enabled', return_value=False))
            stack.enter_context(patch('coolcat.ui.attachment.NativeWindows', return_value=self.backend))
            for method in ('_start_camera_thread', '_apply_hotkey', '_apply_monitor_hotkey',
                           '_apply_screenshot_hotkey'):
                stack.enter_context(patch.object(CatWindow, method))
            pet = CatWindow()
        try:
            pet.timer.stop()
            pet.fullscreen_timer.stop()
            pet.attachment.timer.stop()
            pet.resize(240, 290)
            pet.move(300, 300)
            def event(kind, local, global_pos, button, buttons):
                return QMouseEvent(kind, QPointF(local), QPointF(global_pos), button, buttons, Qt.NoModifier)
            pet.mousePressEvent(event(QEvent.MouseButtonPress, QPoint(50, 50), QPoint(350, 350),
                                      Qt.LeftButton, Qt.LeftButton))
            with patch('coolcat.ui.attachment.QCursor.pos', return_value=QPoint(800, 550)):
                pet.mouseMoveEvent(event(QEvent.MouseMove, QPoint(50, 50), QPoint(800, 550),
                                         Qt.NoButton, Qt.LeftButton))
                pet.mouseReleaseEvent(event(QEvent.MouseButtonRelease, QPoint(50, 50), QPoint(800, 550),
                                            Qt.LeftButton, Qt.NoButton))
            self.assertEqual(pet.attachment.target.hwnd, 101)
            self.assertEqual(pet.attachment.corner, 'bottom-right')
            self.assertIsNone(pet.snap_edge)
            self.assertFalse(pet.dragging)
            def context_actions():
                captured = []
                def capture(menu, position):
                    captured.extend(a.text() for a in menu.actions())
                with patch.object(QMenu, 'exec_', capture):
                    pet.contextMenuEvent(SimpleNamespace(globalPos=lambda: QPoint(800, 550)))
                return captured
            attached_actions = context_actions()
            self.assertIn('脱离软件窗口', attached_actions)
            self.assertIn('吸附位置', attached_actions)
            self.assertNotIn('软件窗口吸附', attached_actions)  # No extra submenu.
            for text in ('区域截图', '设置', '摄像头预览', '与小猫互动', '退出'):
                self.assertNotIn(text, attached_actions)
            pet.attachment.target.kind = 'CabinetWClass'
            explorer_actions = context_actions()
            self.assertIn('复制当前目录路径', explorer_actions)
            self.assertIn('锁定当前标签页目录（导航后退回）', explorer_actions)
            pet.attachment.lock_state = 'locked'
            pet.attachment.lock_path = 'D:\\folder'
            self.assertIn('解除目录锁定', context_actions())
            pet._toggle_follow()
            self.assertIsNone(pet.attachment.target)
            self.assertTrue(pet.follow)
            normal_actions = context_actions()
            self.assertIn('区域截图', normal_actions)
            self.assertIn('设置', normal_actions)
            self.assertIn('软件窗口吸附', normal_actions)
        finally:
            pet.attachment.close()
            pet.press_timer.stop()
            pet.tray.hide()
            for manager in (pet.hotkey_mgr, pet.monitor_hotkey_mgr, pet.screenshot_hotkey_mgr):
                APP.removeNativeEventFilter(manager)
            pet.hide()
            pet.deleteLater()

    def test_locked_tab_emotion_and_return_timeout(self):
        self.attach()
        self.pet.config = {'locked_tab_behavior': 'emotion'}
        self.controller.lock_state = 'paused'
        self.controller.tick()
        self.assertEqual(self.pet._tab_mood, 'angry')
        self.assertTrue(self.pet.isVisible())
        with patch('coolcat.ui.attachment.time.monotonic', return_value=100):
            self.controller.lock_state = 'locked'
            self.controller.tick()
        self.assertEqual(self.pet._tab_mood, 'happy')
        with patch('coolcat.ui.attachment.time.monotonic', return_value=103):
            self.controller.tick()
        self.assertEqual(self.pet._tab_mood, '')
        self.controller.unlock_folder()
        self.assertEqual(self.pet._tab_mood, '')

    def test_focus_emotion_return_and_expiry(self):
        self.attach()
        self.pet.config = {'attached_focus_behavior': 'emotion'}
        self.backend.foreground = False
        self.controller.tick()
        self.assertTrue(self.pet.isVisible())
        self.assertEqual(self.pet._tab_mood, 'angry')
        with patch('coolcat.ui.attachment.time.monotonic', return_value=100):
            self.backend.foreground = True
            self.controller.tick()
        self.assertEqual(self.pet._tab_mood, 'happy')
        with patch('coolcat.ui.attachment.time.monotonic', return_value=103):
            self.controller.tick()
        self.assertEqual(self.pet._tab_mood, '')
        self.backend.foreground = False
        self.controller.tick()
        self.controller.detach()
        self.assertEqual(self.pet._tab_mood, '')
        self.assertFalse(self.controller._focus_away)

    def test_focus_keep_visible_live_change_and_minimize(self):
        self.attach()
        self.backend.foreground = False
        self.controller.tick()
        self.assertFalse(self.pet.isVisible())  # Legacy/default behavior.
        self.pet.config = {'attached_focus_behavior': 'none'}
        self.controller.tick()
        self.assertTrue(self.pet.isVisible())
        self.assertEqual(self.pet._tab_mood, '')
        self.backend.target.visible = False
        self.controller.tick()
        self.assertFalse(self.pet.isVisible())
        self.backend.target.visible = True
        self.controller.tick()
        self.assertTrue(self.pet.isVisible())
        self.controller.manual_hidden = True
        self.controller.tick()
        self.assertFalse(self.pet.isVisible())

    def test_focus_tab_priority(self):
        self.attach()
        self.pet.config = {'attached_focus_behavior': 'emotion', 'locked_tab_behavior': 'hide'}
        self.backend.foreground = False
        self.controller.lock_state = 'paused'
        self.controller.tick()
        self.assertFalse(self.pet.isVisible())
        self.backend.foreground = True
        self.controller.tick()
        self.assertFalse(self.pet.isVisible())  # Returning focus doesn't unhide an away tab.
        self.pet.config['locked_tab_behavior'] = 'emotion'
        self.controller.tick()
        self.assertTrue(self.pet.isVisible())
        self.assertEqual(self.pet._tab_mood, 'angry')  # Tab angry beats focus happy.
        self.backend.foreground = False
        self.controller.lock_state = 'locked'
        self.controller.tick()
        self.assertEqual(self.pet._tab_mood, 'angry')  # Focus angry beats tab happy.

    def test_locked_tab_hide_restore_and_live_setting(self):
        self.attach()
        self.pet.config = {'locked_tab_behavior': 'hide'}
        self.controller.lock_state = 'paused'
        self.controller.tick()
        self.assertFalse(self.pet.isVisible())
        self.pet.config['locked_tab_behavior'] = 'none'
        self.controller.tick()
        self.assertTrue(self.pet.isVisible())
        self.assertEqual(self.pet._tab_mood, '')
        self.pet.config['locked_tab_behavior'] = 'hide'
        self.controller.tick()
        self.assertFalse(self.pet.isVisible())
        self.controller.lock_state = 'locked'
        self.controller.tick()
        self.assertTrue(self.pet.isVisible())
        self.controller.lock_state = 'paused'
        self.controller.tick()
        self.controller.unlock_folder()
        self.controller.tick()
        self.assertTrue(self.pet.isVisible())
        self.controller.manual_hidden = True
        self.controller.tick()
        self.assertFalse(self.pet.isVisible())


if __name__ == '__main__':
    unittest.main()
