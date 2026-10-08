"""Windows scan-code keyboard input with checked delivery to the input queue."""
import ctypes

DWORD = ctypes.c_uint32
WORD = ctypes.c_uint16
ULONG_PTR = ctypes.c_size_t


class KeyboardInput(ctypes.Structure):
    _fields_ = [('vk', WORD), ('scan', WORD), ('flags', DWORD),
                ('time', DWORD), ('extra', ULONG_PTR)]


class MouseInput(ctypes.Structure):
    _fields_ = [('dx', ctypes.c_int32), ('dy', ctypes.c_int32),
                ('data', DWORD), ('flags', DWORD), ('time', DWORD),
                ('extra', ULONG_PTR)]


class HardwareInput(ctypes.Structure):
    _fields_ = [('message', DWORD), ('low', WORD), ('high', WORD)]


class InputUnion(ctypes.Union):
    _fields_ = [('keyboard', KeyboardInput), ('mouse', MouseInput),
                ('hardware', HardwareInput)]


class Input(ctypes.Structure):
    _fields_ = [('type', DWORD), ('value', InputUnion)]


class WindowsInput:
    SCANS = {'t': 0x14, 'space': 0x39, 'alt_l': 0x38}

    def __init__(self, sender=None):
        if sender is None:
            user32 = ctypes.WinDLL('user32', use_last_error=True)
            sender = user32.SendInput
            sender.argtypes = [ctypes.c_uint32, ctypes.POINTER(Input), ctypes.c_int]
            sender.restype = ctypes.c_uint32
        self.sender = sender

    def _send(self, event, label):
        if self.sender(1, ctypes.pointer(event), ctypes.sizeof(Input)) != 1:
            raise RuntimeError(
                f'Windows não aceitou o comando {label}. Verifique se Roblox e Mukz '
                'estão no mesmo nível de permissão (ambos sem administrador).')

    def key(self, name, down):
        event = Input(type=1)
        event.value.keyboard = KeyboardInput(scan=self.SCANS[name],
                                             flags=0x0008 | (0 if down else 0x0002))
        self._send(event, name)

    def left_mouse(self, down):
        event = Input(type=0)
        event.value.mouse = MouseInput(flags=0x0002 if down else 0x0004)
        self._send(event, 'mouse esquerdo')

    def move(self, x, y):
        user32 = ctypes.WinDLL('user32', use_last_error=True)
        user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
        user32.SetCursorPos.restype = ctypes.c_int
        if not user32.SetCursorPos(int(x), int(y)):
            raise RuntimeError('Windows não aceitou o posicionamento do mouse.')


class CollectKey(WindowsInput):
    def send(self, down):
        self.key('t', down)
