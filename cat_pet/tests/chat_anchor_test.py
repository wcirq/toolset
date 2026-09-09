import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from PyQt5.QtCore import QObject, QRect, QPoint
from coolcat.ui.chat_anchor import ChatAnchor
from coolcat.platform.chat_backend import Session


class AnchorTests(unittest.TestCase):
    def setUp(self):
        self.host = QObject()
        self.host.pet = Mock()
        self.host.pet.width.return_value = 80
        self.host.pet.height.return_value = 60
        self.anchor = ChatAnchor(self.host)
        self.session = Session('session_item_A', (1,), 'A')
        self.anchor.session = self.session
        self.anchor.visible_rows = Mock(return_value=[(self.session, QRect(100, 200, 200, 50))])

    def test_position_tracks_row(self):
        self.assertEqual(self.anchor.position(None), QPoint(260, 194))
        self.anchor.visible_rows.return_value = [(self.session, QRect(100, 300, 200, 50))]
        self.assertEqual(self.anchor.position(None), QPoint(260, 294))

    def test_missing_or_recreated_row_has_no_position(self):
        self.anchor.visible_rows.return_value = []
        self.assertIsNone(self.anchor.position(None))
        self.anchor.visible_rows.return_value = [(Session('session_item_A', (2,), 'A'), QRect(0, 0, 20, 20))]
        self.assertIsNone(self.anchor.position(None))

    def test_hit_only_inside_row(self):
        self.assertEqual(self.anchor.hit(None, QPoint(120, 220))[0], self.session)
        self.assertIsNone(self.anchor.hit(None, QPoint(120, 260)))


if __name__ == '__main__':
    unittest.main()
