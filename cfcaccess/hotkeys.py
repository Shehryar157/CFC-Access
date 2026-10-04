"""Mod hotkeys, read without hooking the game.

Windows' GetAsyncKeyState says whether a key is down right now. We check our
keys on every poll and fire once per press (on the change from up to down),
and only while the game window is in front, so typing elsewhere is ignored.
The keys still reach the game too; we only use keys the game doesn't bind.
"""
import ctypes
import time

user32 = ctypes.windll.user32

# Keys the player uses to play (arrows, WASD, the Type A attack keys,
# Enter, F1 Start). Pressing any of them counts as "the player is here".
GAME_KEYS = [0x25, 0x26, 0x27, 0x28, ord("W"), ord("A"), ord("S"), ord("D"),
             ord("U"), ord("I"), ord("O"), ord("J"), ord("K"), ord("L"), 0x0D, 0x70]


class _XINPUT_STATE(ctypes.Structure):
    _fields_ = [("packet", ctypes.c_uint32), ("buttons", ctypes.c_uint16),
                ("lt", ctypes.c_uint8), ("rt", ctypes.c_uint8),
                ("lx", ctypes.c_int16), ("ly", ctypes.c_int16),
                ("rx", ctypes.c_int16), ("ry", ctypes.c_int16)]


try:
    _xinput = ctypes.windll.xinput1_4
except OSError:
    _xinput = None


class Hotkeys:
    def __init__(self, hwnd_getter):
        self.hwnd_getter = hwnd_getter   # returns the game window (or None)
        self.handlers = {}               # virtual-key code -> function
        self.down = set()
        self.last_input = 0.0            # when the player last pressed a game key
        self._pad_packets = {}

    def idle_for(self):
        """Seconds since the player last touched the game's controls."""
        return time.monotonic() - self.last_input

    def _check_activity(self):
        if any(user32.GetAsyncKeyState(vk) & 0x8000 for vk in GAME_KEYS):
            self.last_input = time.monotonic()
        if _xinput is not None:
            # A controller's packet number changes whenever its state does.
            state = _XINPUT_STATE()
            for pad in range(4):
                if _xinput.XInputGetState(pad, ctypes.byref(state)) == 0:
                    if self._pad_packets.get(pad, state.packet) != state.packet:
                        self.last_input = time.monotonic()
                    self._pad_packets[pad] = state.packet

    def bind(self, key, handler):
        """key: a letter like "G" or a virtual-key code."""
        vk = ord(key.upper()) if isinstance(key, str) else key
        self.handlers[vk] = handler

    def poll(self):
        hwnd = self.hwnd_getter()
        if not hwnd or user32.GetForegroundWindow() != hwnd:
            self.down.clear()
            return
        self._check_activity()
        for vk, handler in self.handlers.items():
            pressed = bool(user32.GetAsyncKeyState(vk) & 0x8000)
            if pressed and vk not in self.down:
                self.down.add(vk)
                try:
                    handler()
                except Exception as e:  # a broken handler must not stop the mod
                    print(f"hotkey {vk:#x} failed: {e!r}")
            elif not pressed:
                self.down.discard(vk)
