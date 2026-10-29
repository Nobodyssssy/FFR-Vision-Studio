"""Offline FFBE source bridge tests; no installed game or Windows binaries required."""
import importlib.util
import os
import json
import sys
import tempfile
from pathlib import Path
import unittest

BRIDGE=Path(__file__).resolve().parents[1]/'rain_memorial_bridge.py'
SOURCES=Path(__file__).resolve().parents[2]
FIXTURES=Path(os.environ.get('FFR_RAIN_TEST_FIXTURES', str(SOURCES)))
spec=importlib.util.spec_from_file_location('rain_memorial_bridge',BRIDGE)
bridge=importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)

class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.db=FIXTURES/'memorial-index.sqlite' if (FIXTURES/'memorial-index.sqlite').is_file() else SOURCES/'build/diagnostics/ffbe-memorial/memorial-index.sqlite'
        self.unit=FIXTURES/'unit.json' if (FIXTURES/'unit.json').is_file() else SOURCES/'units/ffbe/ultimatepowerrain/unit.json'
        self.assertTrue(self.db.is_file(), f'Missing original Memorial DB: {self.db}')
        self.assertTrue(self.unit.is_file(), f'Missing original FFBE unit: {self.unit}')
        self.source=bridge.load_source(self.db,self.unit)

    def test_original_explosions_and_sounds(self):
        self.assertEqual(self.source['particleCount'],8)
        self.assertEqual(self.source['cueCount'],8)
        self.assertEqual([r['qIy86WvJ'] for r in self.source['groups'][:5]],list(bridge.GROUPS))

    def test_single_source_snapshot_and_explicit_scope(self):
        s=bridge.make_snapshot(self.source, database_path=str(self.db))
        self.assertEqual(s['root'],'JP_CLIENT/ability/1503020')
        self.assertEqual(s['records'][0]['data']['attack_frames'],[[42,62,82,102,122,142,162,182]])
        self.assertEqual(s['records'][0]['data']['attack_damage'],[[10,10,10,10,10,10,10,30]])
        self.assertEqual(len(s['records'][0]['data']['effects_raw']),1)
        full=bridge.make_snapshot(self.source,damage_only=False)
        self.assertEqual(len(full['records'][0]['data']['effects_raw']),4)
        kit=bridge.make_kit(s,self.source)
        self.assertEqual(kit['profiles'][s['root']]['snapshot'],s)
        self.assertEqual(len(kit['provenance']['notImplemented']),3)

    def test_cache_source_references(self):
        caches=bridge.make_cache(self.source)
        self.assertEqual(len(caches['F_ABILITY_MST']),1)
        self.assertEqual(len(caches['F_EFFECT_GROUP_MST']),7)
        self.assertTrue(any(x.get('2HjxCGo6')=='eff_explosion_red.bmb'
                            for x in caches['F_EFFECT_MST']))
        self.assertEqual(caches['F_ABILITY_MST'][0]['effect_frames'].count('604950200'),1)

    def test_never_overwrite_existing_kit(self):
        s=bridge.make_snapshot(self.source)
        with tempfile.TemporaryDirectory() as tmp:
            kit=Path(tmp)/'kit.json';out=Path(tmp)/'cache'
            bridge.write_prepared_source(self.source,s,out,kit)
            self.assertTrue(kit.exists())
            self.assertTrue((out/'F_EFFECT_GROUP_MST.json').is_file())
            with self.assertRaises(bridge.SourceError):
                bridge.write_prepared_source(self.source,s,out,kit)

if __name__=='__main__': unittest.main()
