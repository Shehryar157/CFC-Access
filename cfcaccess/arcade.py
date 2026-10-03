"""Reading the emulated arcade machine's memory.

Each game runs on an emulated arcade board (CPS2 for most of them). The
emulator keeps the board's whole 16 MB address space (program ROM, video
and work RAM) in one block of the collection's memory, with a 0xA0-byte
header in front. So arcade address X lives at  block + 0xA0 + X.

The arcade CPU (a 68000) stores numbers high byte first, while the PC
stores them low byte first; the emulator keeps each 2-byte word in PC
order. So a 2-byte value can be read directly, and a single byte at arcade
address X is at X ^ 1 (its neighbour within the word).

Community memory maps (MAME / FBNeo training scripts) give addresses like
0xFF8366 for player 1's health in Hyper Street Fighter II; those can be
used as-is with read_word / read_byte.
"""
import struct

# Routes from the exe to the arcade block (found 2026-10-04 with
# tools/ptrscan.py). The pointer already points past the header, at arcade
# address 0. All six agreed in Hyper Street Fighter II; other games unchecked.
ROUTES = [(0x8A1E68, []), (0xB05888, []), (0x4C516F0, []), (0x4C517A8, []),
          (0x8A1E60, [0x30]), (0xC110C0, [0x30])]


class Arcade:
    def __init__(self, game):
        self.game = game
        self.base = None

    def locate(self):
        """Find the arcade address space; returns True if found."""
        pm = self.game.pm
        for exe_offset, offsets in ROUTES:
            try:
                p = pm.read_ulonglong(self.game.base + exe_offset)
                for off in offsets:
                    p = pm.read_ulonglong(p + off)
                if p:
                    self.base = p
                    return True
            except Exception:
                continue
        self.base = None
        return False

    def read_word(self, address):
        raw = self.game.pm.read_bytes(self.base + address, 2)
        return struct.unpack("<H", raw)[0]

    def read_byte(self, address):
        return self.game.pm.read_bytes(self.base + (address ^ 1), 1)[0]

    def read_words(self, address, count):
        raw = self.game.pm.read_bytes(self.base + address, 2 * count)
        return struct.unpack(f"<{count}H", raw)
