"""Geometry guards for the read-only Qt attachment fallback."""
import unittest

from coolcat.platform.qt_chat_rows import clip_rect


class ClipTests(unittest.TestCase):
    def test_scrolled_row_clipped_to_list(self):
        self.assertEqual(clip_rect((60, 40, 300, 105), (60, 80, 300, 636)),
                         (60, 80, 300, 105))

    def test_hidden_row_excluded(self):
        self.assertIsNone(clip_rect((60, 0, 300, 65), (60, 80, 300, 636)))

    def test_negative_monitor_coordinates(self):
        self.assertEqual(clip_rect((-1500, 200, -1200, 281), (-1600, 100, -1000, 900)),
                         (-1500, 200, -1200, 281))

    def test_touching_edge_is_not_a_visible_row(self):
        self.assertIsNone(clip_rect((60, 15, 300, 80), (60, 80, 300, 636)))


if __name__ == '__main__':
    unittest.main()
