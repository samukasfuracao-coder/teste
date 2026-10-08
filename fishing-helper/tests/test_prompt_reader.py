import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prompt_reader import prompt_crop, read_central_prompt


class PromptReaderTests(unittest.TestCase):
    def test_small_window_gets_fourfold_text_enlargement(self):
        image = np.zeros((598, 800, 3), dtype=np.uint8)
        image[280:285, 414:450] = 255  # Collect location in the supplied window
        crop = prompt_crop(image)
        self.assertEqual(crop.shape[1], 960)
        self.assertGreater(crop.max(), 0)

    def test_contrast_retry_recovers_small_collect_label(self):
        ocr = Mock(side_effect=[([], None), ([[[], 'Collect', .99]], None)])
        self.assertEqual(read_central_prompt(ocr, np.zeros((598, 800, 3), np.uint8), 'waiting_collect'), (True, False))
        self.assertEqual(ocr.call_count, 2)

    def test_collecting_negative_uses_retry_even_on_large_window(self):
        ocr = Mock(return_value=([], None))
        self.assertEqual(read_central_prompt(ocr, np.zeros((1080, 1920, 3), np.uint8), 'collecting'), (False, False))
        self.assertEqual(ocr.call_count, 2)

    def test_positive_first_read_avoids_extra_ocr(self):
        ocr = Mock(return_value=([[[], 'Collect', .99]], None))
        self.assertTrue(read_central_prompt(ocr, np.zeros((598, 800, 3), np.uint8), 'collecting')[0])
        self.assertEqual(ocr.call_count, 1)
