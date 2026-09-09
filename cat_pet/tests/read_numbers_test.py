import unittest
from coolcat.platform.qt_history import ReadNumbers


class NumberTests(unittest.TestCase):
    def test_cumulative_numbering_and_unaccepted_previews(self):
        def page(items):
            return {'record_keys': [(key,) for key, _ in items],
                    'records': [('message', text) for _, text in items]}
        numbers = ReadNumbers()
        self.assertEqual(numbers.page(page([(1, 'a'), (2, 'b')]), True), [2, 1])
        older = page([(3, 'c'), (1, 'a')])
        self.assertEqual(numbers.page(older), [None, 2])
        self.assertEqual(numbers.count, 2)
        self.assertEqual(numbers.page(older, True), [3, 2])
        self.assertEqual(numbers.page(older, True), [3, 2])
        self.assertEqual(numbers.page(page([(3, 'reused pointer')]), True), [4])


if __name__ == '__main__':
    unittest.main()
