"""Finding and attaching to the running game.

pymem wraps the Windows functions OpenProcess and ReadProcessMemory, which
let one program read another program's memory (with the user's own
permissions; no admin rights are needed for a game the user launched).
"""
import ctypes
import time
from ctypes import wintypes

import pymem
import pymem.exception
import pymem.process

EXE_NAME = "CapcomFightingCollection.exe"


class Game:
    def __init__(self, pm):
        self.pm = pm
        module = pymem.process.module_from_name(pm.process_handle, EXE_NAME)
        # Where Windows loaded the exe this time. Changes every launch.
        self.base = module.lpBaseOfDll
        self.size = module.SizeOfImage

    @property
    def pid(self):
        return self.pm.process_id

    def is_running(self):
        """True while the game process is still alive."""
        try:
            self.pm.read_bytes(self.base, 2)
            return True
        except pymem.exception.MemoryReadError:
            return False

    def read(self, address, length):
        return self.pm.read_bytes(address, length)


_user32 = ctypes.WinDLL("user32")


def find_window(pid):
    """The process's visible top-level window, or None."""
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _):
        owner = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and _user32.IsWindowVisible(hwnd):
            found.append(hwnd)
        return True

    _user32.EnumWindows(callback, 0)
    return found[0] if found else None


def try_attach():
    """Return a Game if it's running, otherwise None.

    A crashed or closing copy of the game can linger for a while with no
    window, so we pick the copy that has a window.
    """
    for proc in pymem.process.list_processes():
        if proc.szExeFile.decode(errors="replace").lower() != EXE_NAME.lower():
            continue
        if find_window(proc.th32ProcessID) is None:
            continue
        try:
            pm = pymem.Pymem()
            pm.open_process_from_id(proc.th32ProcessID)
            return Game(pm)
        except (pymem.exception.ProcessNotFound, pymem.exception.CouldNotOpenProcess):
            continue
    return None


def wait_for_game(poll_seconds=1.0):
    """Block until the game is running, then return a Game."""
    while True:
        game = try_attach()
        if game is not None:
            return game
        time.sleep(poll_seconds)
