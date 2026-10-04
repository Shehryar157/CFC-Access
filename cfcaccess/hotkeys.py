"""Mod hotkeys, read without hooking the game.

Windows' GetAsyncKeyState says whether a key is down right now. We check our
keys on every poll and fire once per press (on the change from up to down),
and only while the game window is in front, so typing elsewhere is ignored.
The keys still reach the game too; we only use keys the game doesn't bind.
"""
import ctypes

user32 = ctypes.windll.user32


class Hotkeys:
    def __init__(self, hwnd_getter):
        self.hwnd_getter = hwnd_getter   # returns the game window (or None)
        self.handlers = {}               # virtual-key code -> function
        self.down = set()

    def bind(self, key, handler):
        """key: a letter like "G" or a virtual-key code."""
        vk = ord(key.upper()) if isinstance(key, str) else key
        self.handlers[vk] = handler

    def poll(self):
        hwnd = self.hwnd_getter()
        if not hwnd or user32.GetForegroundWindow() != hwnd:
            self.down.clear()
            return
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
