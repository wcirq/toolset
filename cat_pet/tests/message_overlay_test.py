import unittest
from types import SimpleNamespace
from PyQt5.QtCore import QRect, Qt
from PyQt5.QtWidgets import QApplication
from coolcat.ui.message_overlay import MessageReadOverlay


class OverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_clips_numbers_and_hides_without_focus(self):
        api = SimpleNamespace(GetForegroundWindow=lambda: 1)
        backend = SimpleNamespace(api=api, logical_rect=lambda hwnd, r:
            QRect(r.left, r.top, r.right-r.left, r.bottom-r.top))
        overlay = MessageReadOverlay(backend, 1)
        try:
            overlay.display({'clip': (100, 100, 500, 400),
                             'boxes': [(100, 80, 500, 160), (100, 200, 500, 280)],
                             'numbers': [12, 3],
                             'parts': [{'kind': 'avatar', 'rect': (110, 110, 140, 140)},
                                       {'kind': 'time', 'rect': (200, 170, 280, 190)}]})
            self.assertEqual(len(overlay.boxes), 2)
            self.assertEqual(overlay.numbers, [12, 3])
            self.assertEqual(len(overlay.parts), 2)
            self.assertEqual(overlay.boxes[0].top(), 0)
            self.assertTrue(overlay.testAttribute(Qt.WA_TransparentForMouseEvents))
            self.assertTrue(overlay.windowFlags() & Qt.WindowDoesNotAcceptFocus)
            self.assertFalse(overlay.grab().isNull())
            api.GetForegroundWindow = lambda: 2
            overlay.expire()
            self.assertFalse(overlay.isVisible())
        finally:
            overlay.close()
            overlay.deleteLater()


if __name__ == '__main__':
    unittest.main()
