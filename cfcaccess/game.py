"""Finding and attaching to the running game.

pymem wraps the Windows functions OpenProcess and ReadProcessMemory, which
let one program read another program's memory (with the user's own
permissions; no admin rights are needed for a game the user launched).
"""
import time

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


def try_attach():
    """Return a Game if it's running, otherwise None."""
    try:
        return Game(pymem.Pymem(EXE_NAME))
    except (pymem.exception.ProcessNotFound, pymem.exception.CouldNotOpenProcess):
        return None


def wait_for_game(poll_seconds=1.0):
    """Block until the game is running, then return a Game."""
    while True:
        game = try_attach()
        if game is not None:
            return game
        time.sleep(poll_seconds)
