import threading
import unittest
from coolcat.platform.history_tracking import HistoryTracking


class TrackingTests(unittest.TestCase):
    def test_tracks_without_collector_and_stops_without_late_frames(self):
        frames = []
        ready = threading.Event()
        page = {'records': [('message', 'a')], 'record_keys': [(1,)]}

        class Reader:
            def track(self, hwnd, pid, source):
                return source

        class Window:
            pid = 2
            def __init__(self, hwnd):
                pass
            def annotation(self, source, numbers):
                return numbers

        def receive(frame):
            frames.append(frame)
            if len(frames) >= 3:
                ready.set()

        tracker = HistoryTracking(1, receive, Reader, Window)
        tracker.publish(page, [12])
        tracker.thread.start()
        try:
            self.assertTrue(ready.wait(2), 'Frames must advance without further text reads')
        finally:
            tracker.close()
        self.assertFalse(tracker.thread.is_alive())
        self.assertTrue(all(frame == [12] for frame in frames))
