import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from screen_mask import mask_overlay


class ScreenMaskTests(unittest.TestCase):
    def test_overlay_is_masked_in_client_coordinates(self):
        frame = np.full((100, 100, 3), 255, dtype=np.uint8)
        mask_overlay(frame, 100, 200, (110, 220, 30, 40))
        self.assertTrue(np.all(frame[20:60, 10:40] == 0))
        self.assertTrue(np.all(frame[:20] == 255))
        self.assertTrue(np.all(frame[:, 40:] == 255))

    def test_overlay_outside_window_does_not_hide_pixels(self):
        frame = np.full((100, 100, 3), 255, dtype=np.uint8)
        mask_overlay(frame, 0, 0, (200, 200, 20, 20))
        self.assertTrue(np.all(frame == 255))

    def test_negative_coordinates_are_clipped(self):
        frame = np.full((100, 100, 3), 255, dtype=np.uint8)
        mask_overlay(frame, 0, 0, (-10, -20, 30, 40))
        self.assertTrue(np.all(frame[:20, :20] == 0))
        self.assertTrue(np.all(frame[20:] == 255))


if __name__ == '__main__':
    unittest.main()
