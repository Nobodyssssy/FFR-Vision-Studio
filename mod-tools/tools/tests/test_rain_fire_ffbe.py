"""Offline regression tests for the original Rain Fire integration staging."""
import hashlib
import json
import tempfile
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import rain_fire_ffbe as rain


class RainFireTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = rain.read(rain.ROOT / 'units/ffbe/ultimatepowerrain/unit.json')
        cls.roster = rain.read(rain.ROOT / 'build/diagnostics/rain-units.json')

    def test_authentic_ffbe_fire_mechanics(self):
        skill = rain.source_identity(self.source)
        self.assertEqual(skill['id'], 1503020)
        self.assertEqual(skill['cost']['MP'], 150)
        self.assertEqual(skill['attack_frames'][0], [42,62,82,102,122,142,162,182])
        self.assertEqual(skill['attack_count'], [8])
        self.assertIn('450x', skill['effects'][0])

    def test_original_roster_is_not_modified(self):
        source = json.dumps(self.roster, sort_keys=True, ensure_ascii=False)
        snapshot = {'root': 'JP_2024/ability/1503020', 'records': [{'source':'JP_2024','kind':'ability','id':1503020,'data':{}}]}
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(rain,'STAGE',Path(folder)):
                output = rain.stage_roster(self.roster, snapshot, snapshot['root'], rain.source_identity(self.source))
                staged = rain.read(output)
        self.assertEqual(source, json.dumps(self.roster, sort_keys=True, ensure_ascii=False))
        self.assertEqual(len(staged), 7)
        unit = next(u for u in staged if u['id'] == rain.UNIT_ID)
        fire = unit['skills'][str(rain.SKILL_ID)]
        self.assertEqual(fire['mechanics'], 'converted')
        self.assertEqual(fire['set']['Cost'], 150)
        self.assertEqual(fire['conversionSource']['root'], 'JP_2024/ability/1503020')
        self.assertNotIn('visuals', fire)
        self.assertNotIn('magnification', fire['set'])
        self.assertNotIn('from', fire)
        original = next(u for u in self.roster if u['id'] == rain.UNIT_ID)
        for skill_id, unchanged in original['skills'].items():
            if skill_id != str(rain.SKILL_ID):
                self.assertEqual(unit['skills'][skill_id], unchanged)

    def test_stage_rejects_unrelated_skill(self):
        snapshot = {'root': 'JP_2024/ability/999999'}
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(rain, 'STAGE', Path(folder)):
                with self.assertRaises(rain.Blocked):
                    rain.stage_roster(self.roster, snapshot, 'JP_2024/ability/1503020', rain.source_identity(self.source))


if __name__ == '__main__':
    unittest.main()
