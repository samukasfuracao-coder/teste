import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tracking_control import track_step


class TrackingTests(unittest.TestCase):
    def test_boundaries_override_prediction(self):
        self.assertFalse(track_step(105, 20, 100, 140, 1, (104, 120, .99), 500, True, .3)[0])
        self.assertTrue(track_step(135, 20, 100, 140, 1, (136, 120, .99), -500, False, .3)[0])

    def test_detection_jump_does_not_create_velocity(self):
        self.assertEqual(track_step(120, 20, 100, 140, 1, (50, 120, .99), 500, False, .08)[2], 0)

    def test_stale_sample_resets_velocity(self):
        self.assertEqual(track_step(120, 20, 100, 140, 1, (119, 120, .5), 500, False, .08)[2], 0)

    def test_resolution_scaling_preserves_decision(self):
        for scale in (1, 1.5, 2):
            self.assertTrue(track_step(130*scale, 20*scale, 100*scale, 140*scale, 1, None, 0, False, .08)[0])
