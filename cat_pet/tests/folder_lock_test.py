"""Directory lock tests with fake tabs; never navigate real Explorer windows."""
import os
import sys
import threading
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from coolcat.platform.folder_lock import (LockPolicy, Tab, is_same_or_descendant,
                                          same_path, tab_navigator)
from coolcat.platform.explorer import browser_is_active


class FolderLockTests(unittest.TestCase):
    def setUp(self):
        self.cancelled = threading.Event()
        self.navigate = Mock()
        self.original = Tab('original', True, 'D:\\folder', self.navigate)
        self.policy = LockPolicy([self.original])

    def test_same_folder_does_not_navigate(self):
        self.original.path = 'd:\\FOLDER\\'
        self.assertEqual(self.policy.step([self.original], 1, self.cancelled), 'locked')
        self.navigate.assert_not_called()
        self.assertFalse(same_path('', 'D:\\folder'))

    def test_navigation_rolls_back_only_captured_tab(self):
        other = Tab('other', False, 'D:\\elsewhere', Mock())
        self.original.path = 'D:\\new'
        self.assertEqual(self.policy.step([other, self.original], 1, self.cancelled), 'restoring')
        self.navigate.assert_called_once_with('D:\\folder')
        other.navigate.assert_not_called()

    def test_children_allowed_parent_sibling_and_other_drive_rejected(self):
        for path in ('D:\\folder\\child', 'd:\\FOLDER\\child\\deep'):
            self.original.path = path
            self.assertEqual(self.policy.step([self.original], 1, self.cancelled), 'locked')
        self.navigate.assert_not_called()
        for path in ('D:\\', 'D:\\other', 'E:\\folder', 'D:\\folder2'):
            self.assertFalse(is_same_or_descendant(path, 'D:\\folder'))
        self.assertTrue(is_same_or_descendant('D:\\folder', 'D:\\folder'))
        self.original.path = 'D:\\'
        self.assertEqual(self.policy.step([self.original], 2, self.cancelled), 'restoring')
        self.navigate.assert_called_once_with('D:\\folder')

    def test_other_tab_is_not_modified_and_return_resumes(self):
        self.original.visible = False
        self.original.path = 'D:\\new'
        other = Tab('other', True, 'D:\\elsewhere', Mock())
        self.assertEqual(self.policy.step([other, self.original], 1, self.cancelled), 'paused')
        self.navigate.assert_not_called()
        other.navigate.assert_not_called()
        other.visible, self.original.visible = False, True
        self.assertEqual(self.policy.step([other, self.original], 2, self.cancelled), 'restoring')
        self.navigate.assert_called_once_with('D:\\folder')

    def test_replacement_tab_same_path_does_not_inherit_lock(self):
        other = Tab('replacement', True, 'D:\\folder', Mock())
        with self.assertRaises(ValueError):
            self.policy.step([other], 1, self.cancelled)
        other.navigate.assert_not_called()

    def test_virtual_navigation_returns_to_real_folder(self):
        self.original.path = ''
        self.policy.step([self.original], 1, self.cancelled)
        self.navigate.assert_called_once_with('D:\\folder')

    def test_ambiguous_or_virtual_capture_rejected(self):
        for tabs in ([], [Tab('virtual', True, '', Mock())],
                     [Tab('unknown', None, 'D:\\folder', Mock())],
                     [self.original, Tab('other', True, 'D:\\other', Mock())]):
            with self.subTest(tabs=tabs), self.assertRaises(ValueError):
                LockPolicy(tabs)

    def test_cancellation_prevents_navigation(self):
        self.original.path = 'D:\\new'
        self.cancelled.set()
        self.assertEqual(self.policy.step([self.original], 1, self.cancelled), 'cancelled')
        self.navigate.assert_not_called()

    def test_restore_cooldown_and_failure_limit(self):
        self.original.path = 'D:\\new'
        for now in (1, 1.5, 3, 5):
            self.policy.step([self.original], now, self.cancelled)
        self.assertEqual(self.navigate.call_count, 3)
        with self.assertRaises(ValueError):
            self.policy.step([self.original], 7, self.cancelled)

    def test_successful_restore_resets_failure_count(self):
        self.original.path = 'D:\\new'
        self.policy.step([self.original], 1, self.cancelled)
        self.original.path = 'D:\\folder'
        self.policy.step([self.original], 2, self.cancelled)
        self.assertEqual(self.policy.attempts, 0)

    def test_both_views_visible_only_selected_tab_matches(self):
        browser = Mock()
        browser.GetWindow.return_value = 111
        browser.QueryActiveShellView.return_value.GetWindow.return_value = 999
        self.assertTrue(browser_is_active(10, browser, lambda hwnd: True, 111))
        self.assertFalse(browser_is_active(10, browser, lambda hwnd: True, 222))

    def test_switch_immediately_before_navigation_is_not_modified(self):
        window, browser = Mock(), Mock()
        browser.GetWindow.return_value = 111
        navigate = tab_navigator(10, window, browser, lambda hwnd: True)
        with patch('coolcat.platform.folder_lock.active_tab_hwnd', return_value=222):
            self.assertFalse(navigate('D:\\folder'))
        window.Navigate2.assert_not_called()

    def test_navigator_targets_bound_com_tab(self):
        window, browser = Mock(), Mock()
        browser.GetWindow.return_value = 111
        navigate = tab_navigator(10, window, browser, lambda hwnd: True)
        with patch('coolcat.platform.folder_lock.active_tab_hwnd', return_value=111):
            self.assertTrue(navigate('D:\\folder'))
        window.Navigate2.assert_called_once_with('D:\\folder')


if __name__ == '__main__':
    unittest.main()
