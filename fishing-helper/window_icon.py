"""Window/taskbar identity and optional ICO resource for Windows."""
import ctypes
import logging
import sys
import tkinter as tk
from pathlib import Path


def prepare_app_identity():
    if sys.platform != 'win32':
        return
    try:
        function = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID
        function.argtypes = [ctypes.c_wchar_p]
        function.restype = ctypes.c_long
        result = function('PescaAuto.Desktop.Hub')
        if result != 0:
            logging.getLogger('pesca-auto').warning('Windows não aceitou a identidade da barra de tarefas: %s', result)
    except (OSError, AttributeError):
        logging.getLogger('pesca-auto').warning('Não foi possível definir a identidade da barra de tarefas.')


def icon_path():
    if getattr(sys, 'frozen', False):
        external = Path(sys.executable).resolve().parent / 'icone.ico'
        if external.is_file():
            return external
    directory = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
    bundled = directory / 'icone.ico'
    return bundled if bundled.is_file() else None


def apply_window_icon(root):
    if sys.platform != 'win32':
        return False
    path = icon_path()
    if path is None:
        return False
    try:
        # Default applies to the main hub and subsequent Tk dialogs.
        root.iconbitmap(default=str(path))
        return True
    except (tk.TclError, OSError):
        logging.getLogger('pesca-auto').warning('Não foi possível carregar o ícone ICO da janela.', exc_info=True)
        return False
