import ctypes
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from windows_input import CollectKey, Input, WindowsInput


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

    def test_space_and_left_alt_scan_codes(self):
        events = []

        def sender(count, pointer, size):
            event = pointer.contents
            events.append((event.type, event.value.keyboard.scan, event.value.keyboard.flags))
            return 1

        inputs = WindowsInput(sender)
        for name in ('space', 'alt_l'):
            inputs.key(name, True)
            inputs.key(name, False)
        self.assertEqual(events, [(1, 0x39, 8), (1, 0x39, 10),
                                  (1, 0x38, 8), (1, 0x38, 10)])

    def test_mouse_is_button_input_and_never_a_keyboard_scan_code(self):
        events = []

        def sender(count, pointer, size):
            events.append((pointer.contents.type, pointer.contents.value.mouse.flags))
            return 1

        inputs = WindowsInput(sender)
        inputs.left_mouse(True)
        inputs.left_mouse(False)
        self.assertEqual(events, [(0, 2), (0, 4)])

    def test_failed_mouse_input_is_reported(self):
        with self.assertRaisesRegex(RuntimeError, 'mouse esquerdo'):
            WindowsInput(lambda *args: 0).left_mouse(True)
