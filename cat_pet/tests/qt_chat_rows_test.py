"""Geometry guards for the read-only Qt attachment fallback."""
import unittest
import struct
from unittest.mock import Mock

from coolcat.platform.qt_chat_rows import clip_rect, QtChatRows


class ClipTests(unittest.TestCase):
    def test_tracking_mode_is_cleared_after_failure(self):
        reader = QtChatRows(messages=True)
        reader.read = Mock(side_effect=RuntimeError('window changed'))
        with self.assertRaises(RuntimeError):
            reader.track(1, 2, {'identity': (1,)})
        self.assertIsNone(reader.tracking_page)

    def test_offscreen_bubble_children_are_not_traversed(self):
        pointers = {108: 1000, 1008: 100, 1024: 2000, 2016: 300,
                    308: 3000, 3016: 100, 3008: 300}
        ptr = Mock(side_effect=lambda address: pointers.get(address, 0))
        read = lambda address, size: struct.pack('<4i', 1, 1, 0, 1) if address == 2000 else b''
        clip = (0, 0, 100, 100)
        page = QtChatRows._messages(read, ptr,
            lambda obj: 'chat_bubble_item_view' if obj == 300 else 'chat_message_list',
            lambda obj: clip if obj == 100 else (0, -100, 100, -1),
            lambda obj: True, 0, (1,), 100, clip)
        self.assertEqual(page['records'], [])
        self.assertNotIn(unittest.mock.call(3024), ptr.call_args_list)

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
