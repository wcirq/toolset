"""Track geometry independently of expensive, consistent text snapshots."""
import threading
import time


class HistoryTracking:
    def __init__(self, hwnd, progress, reader_factory, window_factory):
        self.hwnd, self.progress = hwnd, progress
        self.reader_factory, self.window_factory = reader_factory, window_factory
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.latest = None
        self.thread = threading.Thread(target=self.run, daemon=True,
                                       name='chat-geometry')

    def publish(self, page, numbers):
        # Pages are replaced, never mutated by the history collector.
        lookup = dict(zip(zip(page.get('record_keys', []), page['records']), numbers))
        with self.lock:
            self.latest = (page, lookup)

    def run(self):
        # QtChatRows.track temporarily modifies reader state: never share it
        # with the text reader or another tracking thread.
        reader, window = self.reader_factory(), self.window_factory(self.hwnd)
        while not self.stop.is_set():
            started = time.monotonic()
            with self.lock:
                source = self.latest
            if source is not None:
                try:
                    page, lookup = source
                    tracked = reader.track(self.hwnd, window.pid, page)
                    numbers = [lookup.get((key, record)) for key, record in
                               zip(tracked.get('record_keys', []), tracked['records'])]
                    data = window.annotation(tracked, numbers, provisional=True)
                except Exception:
                    data = None
                with self.lock:
                    # Discard an obsolete frame if a new page arrived mid-read.
                    if self.latest is source and not self.stop.is_set():
                        self.progress(data)
            self.stop.wait(max(.001, 1 / 60 - (time.monotonic() - started)))

    def close(self):
        self.stop.set()
        self.thread.join()
