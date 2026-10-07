import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from startup_input import StartupLockTap


class StartupLockTapTests(unittest.TestCase):
    def setUp(self):
        self.lock_tap = StartupLockTap()
        self.active = threading.Event()
        self.active.set()
        self.stopped = Mock()
        self.stopped.is_set.return_value = False
        self.actions = []

    def start(self, enabled=True, focused=lambda: True, press=None):
        return self.lock_tap.initialize(
            enabled, self.active, self.stopped, focused,
            lambda: self.actions.append('mouse_up'),
            lambda: self.actions.append('t_up'),
            press or (lambda key: self.actions.append(('down', key))),
            lambda key: self.actions.append(('up', key)), 'alt_l')

    def test_left_alt_is_released_before_fishing_and_only_sent_once(self):
        self.assertTrue(self.start())
        self.assertEqual(self.actions, ['mouse_up', 't_up', ('down', 'alt_l'), ('up', 'alt_l')])
        self.assertFalse(self.lock_tap.held)
        self.active.clear()
        self.assertFalse(self.start())
        self.active.set()
        self.assertFalse(self.start())
        self.assertEqual(self.actions.count(('down', 'alt_l')), 1)

    def test_no_focus_or_paused_does_not_consume_first_start(self):
        self.assertFalse(self.start(focused=lambda: False))
        self.active.clear()
        self.assertFalse(self.start())
        self.assertFalse(self.lock_tap.done)
        self.active.set()
        self.assertTrue(self.start())

    def test_disabled_on_first_start_does_not_toggle_after_resume(self):
        self.assertFalse(self.start(enabled=False))
        self.assertTrue(self.lock_tap.done)
        self.assertFalse(self.start(enabled=True))
        self.assertEqual(self.actions, [])

    def test_release_is_attempted_even_if_press_fails(self):
        def fail(key):
            raise RuntimeError('input failed')
        with self.assertRaises(RuntimeError):
            self.start(press=fail)
        self.assertIn(('up', 'alt_l'), self.actions)
        self.assertFalse(self.lock_tap.held)

    def test_stop_or_focus_loss_before_press_sends_nothing(self):
        self.stopped.is_set.return_value = True
        self.assertFalse(self.start())
        self.stopped.is_set.return_value = False
        focused = Mock(side_effect=[True, False])
        self.assertFalse(self.start(focused=focused))
        self.assertNotIn(('down', 'alt_l'), self.actions)
        self.assertFalse(self.lock_tap.done)


if __name__ == '__main__':
    unittest.main()
