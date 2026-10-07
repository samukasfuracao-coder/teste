import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import window_icon


class IconTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bundle = self.root / '_internal'
        self.bundle.mkdir()

    def test_packaged_icon_is_found_in_bundle(self):
        icon = self.bundle / 'icone.ico'
        icon.write_bytes(b'test resource')
        with patch.object(sys, 'frozen', True, create=True), \
                patch.object(sys, '_MEIPASS', str(self.bundle), create=True), \
                patch.object(sys, 'executable', str(self.root / 'PescaAuto.exe')):
            self.assertEqual(window_icon.icon_path(), icon)

    def test_external_icon_overrides_bundle_for_window(self):
        icon = self.root / 'icone.ico'
        icon.write_bytes(b'test external resource')
        with patch.object(sys, 'frozen', True, create=True), \
                patch.object(sys, '_MEIPASS', str(self.bundle), create=True), \
                patch.object(sys, 'executable', str(self.root / 'PescaAuto.exe')):
            self.assertEqual(window_icon.icon_path(), icon)

    def test_missing_optional_icon_does_not_fail(self):
        with patch.object(sys, '_MEIPASS', str(self.bundle), create=True):
            self.assertIsNone(window_icon.icon_path())

    def test_icon_is_applied_as_default_to_all_tk_windows(self):
        fake_root = Mock()
        path = self.bundle / 'icone.ico'
        with patch.object(sys, 'platform', 'win32'), patch.object(window_icon, 'icon_path', return_value=path):
            self.assertTrue(window_icon.apply_window_icon(fake_root))
        fake_root.iconbitmap.assert_called_once_with(default=str(path))

    def test_taskbar_identity_is_independent_from_python(self):
        function = Mock(return_value=0)
        windll = Mock()
        windll.shell32.SetCurrentProcessExplicitAppUserModelID = function
        with patch.object(sys, 'platform', 'win32'), \
                patch.object(window_icon.ctypes, 'windll', windll, create=True):
            window_icon.prepare_app_identity()
        function.assert_called_once_with('PescaAuto.Desktop.Hub')


if __name__ == '__main__':
    unittest.main()
