import json
import tempfile
import unittest
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import duration_planner as dp

class Stage5PlannerTests(unittest.TestCase):
    def test_moderate_length_within_expected_band(self):
        a=dp.predict(['word '*245], 'en-US',100)
        self.assertEqual(a['estimated_seconds'],100.)
        self.assertTrue(a['within_15_percent'])
    def test_short_script_emits_advice_without_editing(self):
        narration='Hello world. '*10
        a=dp.predict([narration],'en-US',60)
        self.assertFalse(a['within_15_percent'])
        self.assertGreater(a['recommended_token_difference'],0)
        self.assertEqual(narration,'Hello world. '*10)
    def test_vernacular_vietnamese_whitespace_syllables(self):
        a=dp.predict(['từ '*212],'vi-VN',50)
        self.assertAlmostEqual(a['estimated_seconds'],50.,delta=1)
    def test_rate_changes_duration(self):
        tokens=['foo '*120]
        slow=dp.predict(tokens,'en-US',60,.8)
        fast=dp.predict(tokens,'en-US',60,1.2)
        self.assertGreater(slow['estimated_seconds'],fast['estimated_seconds'])
    def test_reject_invalid_config(self):
        for fun in (
            lambda:dp.predict([''],'vi-VN',30),
            lambda:dp.predict(['x'],'fr-FR',30),
            lambda:dp.predict(['x'],'en-US',30,1.5),
            lambda:dp.predict(['x'],'en-US',200),
        ):
            with self.assertRaises(ValueError):fun()
