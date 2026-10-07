import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cycle import FishingCycle, JumpTimer
from vision_text import has_collect, has_disconnect


class CycleTests(unittest.TestCase):
    def collecting(self):
        cycle = FishingCycle()
        self.assertEqual(cycle.step(10, True).phase, 'fishing')
        self.assertEqual(cycle.step(11, False, 10.8, 1, True).phase, 'collecting')
        return cycle

    def test_first_cast_does_not_wait_for_ocr(self):
        cycle = FishingCycle()
        self.assertEqual(cycle.step(10, False).action, 'cast')
        self.assertNotEqual(cycle.step(10.1, False).action, 'cast')

    def test_existing_collect_prompt_blocks_cast(self):
        result = FishingCycle().step(10, False, 9.9, 1, True)
        self.assertEqual(result.phase, 'collecting')
        self.assertTrue(result.hold_t)

    def test_wait_for_delayed_collect_after_bar(self):
        cycle = FishingCycle()
        cycle.step(10, True)
        self.assertEqual(cycle.step(11, False, 10.8, 1).phase, 'waiting_collect')
        self.assertEqual(cycle.step(18, False, 17.9, 2).action, '')
        self.assertEqual(cycle.step(20, False, 19.9, 3, True).phase, 'collecting')

    def test_ocr_miss_does_not_release_t_or_count_collection(self):
        cycle = self.collecting()
        result = cycle.step(12, False, 11.9, 2, False)
        self.assertTrue(result.hold_t)
        self.assertNotEqual(result.action, 'collection_done')
        result = cycle.step(12.1, False, 12, 3, True)
        self.assertTrue(result.hold_t)
        self.assertEqual(cycle.negative_count, 0)

    def test_repeated_same_observation_is_not_three_reads(self):
        cycle = self.collecting()
        for now in (12, 12.5, 13, 14):
            result = cycle.step(now, False, 11.9, 2, False)
            self.assertNotEqual(result.action, 'collection_done')
        self.assertEqual(cycle.negative_count, 1)

    def test_collection_requires_distinct_reads_and_absence_duration(self):
        cycle = self.collecting()
        self.assertTrue(cycle.step(12, False, 11.9, 2).hold_t)
        self.assertTrue(cycle.step(12.8, False, 12.7, 3).hold_t)
        result = cycle.step(13.7, False, 13.6, 4)
        self.assertEqual(result.action, 'collection_done')
        self.assertFalse(result.hold_t)
        self.assertNotEqual(cycle.step(14, False, 13.9, 5).action, 'cast')
        self.assertEqual(cycle.step(15.3, False, 15.2, 6).action, 'cast')

    def test_old_prompt_from_before_bar_is_ignored(self):
        cycle = FishingCycle()
        cycle.step(10, True)
        result = cycle.step(11, False, 9.9, 1, True)
        self.assertEqual(result.phase, 'waiting_collect')
        self.assertFalse(result.hold_t)

    def test_stale_ocr_releases_t_without_confirming_collection(self):
        cycle = self.collecting()
        result = cycle.step(20, False, 10.8, 1, True)
        self.assertFalse(result.hold_t)
        self.assertNotEqual(result.action, 'collection_done')
        result = cycle.step(30.1, False, 10.8, 1, True)
        self.assertEqual(result.action, 'pause')

    def test_collection_timeout_pauses(self):
        cycle = self.collecting()
        self.assertEqual(cycle.step(56, False, 55.9, 2, True).action, 'pause')

    def test_failed_fishing_is_separate_from_confirmed_collection(self):
        cycle = FishingCycle()
        cycle.step(10, True)
        cycle.step(11, False, 10.9, 1)
        self.assertEqual(cycle.step(23, False, 22.9, 2).action, 'no_collection')

    def test_waiting_timeout_retries_once_after_cooldown(self):
        cycle = FishingCycle()
        cycle.step(10, False)
        self.assertEqual(cycle.step(55, False, 54.9, 1).action, 'retry')
        self.assertNotEqual(cycle.step(55.1, False, 55, 2).action, 'cast')
        self.assertEqual(cycle.step(56.6, False, 56.5, 3).action, 'cast')

    def test_reappearing_bar_resumes_control(self):
        cycle = self.collecting()
        result = cycle.step(12, True, 11.9, 2, True)
        self.assertEqual(result.phase, 'fishing')
        self.assertFalse(result.hold_t)


class JumpTests(unittest.TestCase):
    def test_jump_is_deferred_during_fishing_and_collection(self):
        timer = JumpTimer(10)
        self.assertFalse(timer.due(131, 120, True, True, False))
        self.assertTrue(timer.due(132, 120, True, True, True))
        timer.performed(132)
        self.assertFalse(timer.due(133, 120, True, True, True))

    def test_pause_focus_loss_and_disabled_prevent_jump(self):
        timer = JumpTimer(10)
        self.assertFalse(timer.due(200, 120, False, True, True))
        self.assertFalse(timer.due(200, 120, True, False, True))
        self.assertFalse(timer.due(200, 0, True, True, True))


class TextTests(unittest.TestCase):
    def result(self, text, confidence=0.99):
        return [[None, text, confidence]]

    def test_collect_text_and_minor_ocr_errors(self):
        for text in ('Collect', 'Col lect', 'Colect', 'Collecl', 'Coletar'):
            self.assertTrue(has_collect(self.result(text)), text)

    def test_unrelated_or_low_confidence_text_is_not_collect(self):
        self.assertFalse(has_collect(self.result('Golden Fish')))
        self.assertFalse(has_collect(self.result('Collect', 0.2)))

    def test_disconnect_notification(self):
        self.assertTrue(has_disconnect(self.result('Disconnected')))
        self.assertTrue(has_disconnect(self.result('You were kicked')))
        self.assertFalse(has_disconnect(self.result('Collect')))


if __name__ == '__main__':
    unittest.main()
