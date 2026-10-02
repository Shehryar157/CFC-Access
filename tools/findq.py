"""Find every 8-byte-aligned place in memory holding a given 64-bit value.

  python tools/findq.py 0x1405215e0 [dump_bytes]

Useful for finding all objects of one class (search for its vtable pointer)
or everything that points at an object (search for the object's address).
"""
import struct
import sys

import numpy as np

sys.path.insert(0, __file__.rsplit("tools", 1)[0])
from cfcaccess import memory  # noqa: E402
from tools import win  # noqa: E402


def find(game, value):
    hits = []
    for start, size, _ in memory.regions(game.pm.process_handle):
        try:
            data = game.pm.read_bytes(start, size)
        except Exception:
            continue
        arr = np.frombuffer(data[:len(data) // 8 * 8], dtype=np.uint64)
        hits.extend(start + int(i) * 8 for i in np.nonzero(arr == value)[0])
    return hits


if __name__ == "__main__":
    game, _ = win.game_window()
    value = int(sys.argv[1], 0)
    dump = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0
    hits = find(game, value)
    print(f"{len(hits)} hits")
    for h in hits:
        line = f"{h:#x}"
        if dump:
            ints = struct.unpack(f"<{dump // 4}i", game.pm.read_bytes(h, dump))
            line += "  " + " ".join(str(i) for i in ints)
        print(line)
