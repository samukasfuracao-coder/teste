import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from preferences import DEFAULTS, ProfileStore, validate_settings
from hub import HubState


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'perfis.json'

    def test_roundtrip_preserves_per_user_profile_and_active_selection(self):
        store = ProfileStore(self.path)
        store.put('Meu PC', DEFAULTS | {'start_hotkey': 'f6', 'jump_interval': 180,
                                      'theme': 'light', 'accent': '#a855f7'})
        loaded = ProfileStore(self.path)
        self.assertEqual(loaded.active, 'Meu PC')
        self.assertEqual(loaded.current()['start_hotkey'], 'f6')
        self.assertEqual(loaded.current()['jump_interval'], 180)
        self.assertEqual(loaded.current()['theme'], 'light')

    def test_import_keeps_existing_profile_when_names_collide(self):
        store = ProfileStore(self.path)
        export = self.path.parent / 'export.json'
        store.export(export)
        name = store.import_profile(export)
        self.assertEqual(name, 'Padrão (2)')
        self.assertEqual(len(store.profiles), 2)
        self.assertIn('Padrão', store.profiles)

    def test_invalid_file_is_preserved_before_saving_defaults(self):
        self.path.write_text('broken original', encoding='utf-8')
        store = ProfileStore(self.path)
        self.assertTrue(store.warning)
        self.assertEqual(self.path.read_text(), 'broken original')
        store.put('Recuperado', DEFAULTS)
        self.assertEqual(self.path.with_suffix('.json.bak').read_text(), 'broken original')
        self.assertEqual(ProfileStore(self.path).active, 'Recuperado')

    def test_invalid_import_does_not_change_profiles(self):
        store = ProfileStore(self.path)
        import_path = self.path.parent / 'invalid.json'
        import_path.write_text(json.dumps(dict(version=1, name='Erro',
                                              settings={'target_fps': 999})))
        with self.assertRaises(ValueError):
            store.import_profile(import_path)
        self.assertEqual(list(store.profiles), ['Padrão'])

    def test_cannot_delete_last_profile(self):
        with self.assertRaises(ValueError):
            ProfileStore(self.path).delete('Padrão')

    def test_malformed_active_selection_recovers_without_partial_state(self):
        self.path.write_text(json.dumps(dict(version=1, active=[],
                                              profiles={'Meu PC': DEFAULTS})))
        store = ProfileStore(self.path)
        self.assertEqual(store.active, 'Meu PC')
        self.assertEqual(store.current(), DEFAULTS)

    def test_runtime_snapshot_is_independent_and_settings_apply_together(self):
        state = HubState()
        snapshot = state.settings_snapshot()
        snapshot['jump_interval'] = 999
        self.assertEqual(state.settings_snapshot()['jump_interval'], 120)
        state.apply_settings(DEFAULTS | {'jump_interval': 180, 'start_hotkey': 'f5'})
        self.assertEqual(state.snapshot()['jump_interval'], 180)
        self.assertEqual(state.settings_snapshot()['start_hotkey'], 'f5')

    def test_validation_blocks_bad_values_and_colliding_hotkeys(self):
        for invalid in [{'lookahead': float('nan')}, {'lookahead': float('inf')},
                        {'target_fps': 89.5}, {'target_fps': True},
                        {'start_hotkey': 't'}, {'exit_hotkey': 'f8'},
                        {'accent': 'blue'}, {'scale': 400}, {'topmost': 'false'}]:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                validate_settings(invalid)

    def test_export_contains_settings_without_live_counters(self):
        store = ProfileStore(self.path)
        path = self.path.parent / 'share.json'
        store.export(path)
        payload = json.loads(path.read_text())
        self.assertEqual(set(payload), {'version', 'name', 'settings'})
        self.assertNotIn('casts', payload['settings'])


if __name__ == '__main__':
    unittest.main()
