import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from collect_input import CollectionHold


class CollectionHoldTests(unittest.TestCase):
    def test_uninterrupted_hold_then_release_and_repress(self):
        hold = CollectionHold()
        self.assertEqual(hold.step(0, True, True), (True, False))
        self.assertEqual(hold.step(7.99, True, True), (True, False))
        self.assertEqual(hold.step(8, True, True), (False, True))
        self.assertEqual(hold.step(8.1, True, True), (False, False))
        self.assertEqual(hold.step(8.21, True, True), (True, False))

    def test_missed_prompt_does_not_interrupt_hold(self):
        hold = CollectionHold()
        hold.step(0, True, True)
        self.assertEqual(hold.step(9, True, False), (True, False))

    def test_pause_resets_retry_timer(self):
        hold = CollectionHold()
        hold.step(0, True, True)
        self.assertEqual(hold.step(9, False, True), (False, False))
        self.assertEqual(hold.step(10, True, True), (True, False))
        self.assertEqual(hold.retries, 0)

    def test_retries_are_bounded(self):
        hold = CollectionHold(interval=1, release_time=.2, max_retries=1)
        hold.step(0, True, True)
        self.assertEqual(hold.step(1, True, True), (False, True))
        hold.step(1.3, True, True)
        self.assertEqual(hold.step(3, True, True), (True, False))
