import ctypes
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from windows_input import CollectKey, Input


class WindowsInputTests(unittest.TestCase):
    def test_t_down_and_up_use_scan_code_and_correct_structure_size(self):
        events = []

        def sender(count, pointer, size):
            event = pointer.contents
            events.append((count, size, event.type, event.value.keyboard.vk,
                           event.value.keyboard.scan, event.value.keyboard.flags))
            return 1

        key = CollectKey(sender)
        key.send(True)
        key.send(False)
        expected_size = 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28
        self.assertEqual(ctypes.sizeof(Input), expected_size)
        self.assertEqual(events, [(1, expected_size, 1, 0, 0x14, 8),
                                  (1, expected_size, 1, 0, 0x14, 10)])

    def test_rejected_input_is_reported_instead_of_claiming_key_is_held(self):
        with self.assertRaisesRegex(RuntimeError, 'Windows não aceitou'):
            CollectKey(lambda *args: 0).send(True)
