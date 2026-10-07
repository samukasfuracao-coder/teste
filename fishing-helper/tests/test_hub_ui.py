import os
import sys
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hub import FishingHub, HubState
from preferences import ProfileStore


@unittest.skipUnless(os.name == 'nt' or os.environ.get('DISPLAY'), 'Requer uma tela Tk.')
class HubUITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = ProfileStore(Path(self.temp.name) / 'perfis.json')
        self.state = HubState(self.store.current())
        self.root = tk.Tk()
        self.app = FishingHub(self.root, self.state, self.store)
        self.root.update()

    def tearDown(self):
        for job in self.root.tk.call('after', 'info'):
            self.root.after_cancel(job)
        self.root.destroy()
        self.temp.cleanup()

    def test_all_tabs_render_and_overlay_bounds_are_reported(self):
        self.assertEqual(len(self.app.notebook.tabs()), 5)
        for page in self.app.pages.values():
            self.app.notebook.select(page)
            self.root.update()
            self.assertTrue(page.winfo_ismapped())
        self.assertIsNotNone(self.state.snapshot()['overlay_rect'])

    def test_branding_is_only_in_title_and_author_below_start(self):
        self.assertEqual(self.root.title(), 'Mukz auto fish')
        self.assertEqual(self.app.author_label.cget('text'), 'by mukz')
        self.assertEqual(str(self.app.author_label.cget('anchor')), 'w')
        self.assertGreaterEqual(self.app.author_label.winfo_rooty(),
                                self.app.start_button.winfo_rooty() + self.app.start_button.winfo_height())

        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)

        texts = [widget.cget('text') for widget in descendants(self.root)
                 if widget.winfo_class() == 'TLabel']
        self.assertNotIn('PESCA AUTO', texts)
        self.assertNotIn('Pesca, coleta e controle em um só lugar.', texts)

    def test_tab_strip_and_borders_match_theme_without_bright_bevels(self):
        for theme in ('dark', 'light'):
            self.state.apply_settings(self.state.settings_snapshot() | {'theme': theme})
            self.app.apply_appearance()
            palette = self.app.PALETTES[theme]
            self.assertEqual(self.app.style.lookup('TNotebook', 'background'), palette['bg'])
            self.assertEqual(self.app.style.lookup('TButton', 'lightcolor'), palette['border'])
            self.assertEqual(self.app.style.lookup('Primary.TButton', 'borderwidth'), 0)

    def test_start_and_pause_buttons_use_engine_events(self):
        self.app.toggle()
        self.assertTrue(self.state.start_requested.is_set())
        self.app.toggle()
        self.assertFalse(self.state.start_requested.is_set())
        self.state.active.set()
        self.app.pause()
        self.assertFalse(self.state.active.is_set())

    def test_live_state_and_real_measurement_preview(self):
        self.state.update(status='Pescando', detail='Teste', bar=True, ocr='Pronto',
                          fps=84, casts=21, inside=True, track=(180, 24, 160, 210, 407))
        self.app.refresh()
        self.root.update()
        self.assertEqual(self.app.status_text.get(), 'Pescando')
        self.assertEqual(self.app.metric_vars['casts'].get(), '21')
        self.assertEqual(self.app.indicators['bar'].get(), 'Detectada')
        self.assertEqual(self.app.indicators['fps'].get(), '84 / 90 FPS')
        self.assertGreater(len(self.app.preview.find_all()), 2)

    def test_apply_pauses_and_persists_functional_and_visual_settings(self):
        self.state.active.set()
        for key, value in dict(theme='light', accent='#a855f7', start_hotkey='f6',
                               jump_interval='180', target_fps='60').items():
            self.app.vars[key].set(value)
        self.app.apply_and_save()
        self.root.update()
        self.assertFalse(self.state.active.is_set())
        loaded = ProfileStore(self.store.path).current()
        self.assertEqual(loaded['start_hotkey'], 'f6')
        self.assertEqual(loaded['theme'], 'light')
        self.assertEqual(self.state.settings_snapshot()['target_fps'], 60)
        self.assertEqual(self.root.cget('background'), self.app.PALETTES['light']['bg'])

    def test_invalid_adjustment_does_not_modify_engine_settings(self):
        before = self.state.settings_snapshot()
        self.app.vars['target_fps'].set('900')
        with patch('hub.messagebox.showerror') as error:
            self.app.apply_and_save()
        error.assert_called_once()
        self.assertEqual(self.state.settings_snapshot(), before)

    def test_load_defaults_changes_draft_only_until_saved(self):
        custom = self.state.settings_snapshot() | {'target_fps': 60}
        self.state.apply_settings(custom)
        self.app.load_fields(custom)
        self.app.load_defaults()
        self.assertEqual(self.app.vars['target_fps'].get(), '90')
        self.assertEqual(self.state.settings_snapshot()['target_fps'], 60)

    def test_profile_selection_updates_fields_and_pauses(self):
        self.store.put('Amigo', self.store.current() | {'start_hotkey': 'f5', 'lookahead': 0.06})
        self.state.active.set()
        self.app.select_profile('Amigo')
        self.root.update()
        self.assertFalse(self.state.active.is_set())
        self.assertEqual(self.app.vars['start_hotkey'].get(), 'f5')
        self.assertEqual(self.state.settings_snapshot()['lookahead'], 0.06)

    def test_hotkey_capture_is_guarded_from_global_shortcuts(self):
        self.app.capture_hotkey('start_hotkey')
        self.root.update()
        self.assertTrue(self.state.snapshot()['suspend_hotkeys'])
        dialog = next(widget for widget in self.root.winfo_children() if isinstance(widget, tk.Toplevel))
        dialog.event_generate('<KeyPress>', keysym='F6')
        self.root.update()
        self.assertEqual(self.app.vars['start_hotkey'].get(), 'f6')
        self.assertTrue(self.state.snapshot()['suspend_hotkeys'])


if __name__ == '__main__':
    unittest.main()
