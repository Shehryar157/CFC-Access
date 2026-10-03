"""Find a text string in game memory (UTF-8 and UTF-16).

  python tools/findstr.py "USA 940818" [context_bytes]
"""
import sys

sys.path.insert(0, __file__.rsplit("tools", 1)[0])
from cfcaccess import memory  # noqa: E402
from tools import win  # noqa: E402


def find(game, text, writable_only=False):
    hits = []
    for enc in ("utf-8", "utf-16-le"):
        needle = text.encode(enc)
        for start, size, _ in memory.regions(game.pm.process_handle, writable_only):
            try:
                data = game.pm.read_bytes(start, size)
            except Exception:
                continue
            i = data.find(needle)
            while i != -1:
                hits.append((enc, start + i))
                i = data.find(needle, i + 1)
    return hits


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    game, _ = win.game_window()
    ctx = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    for enc, addr in find(game, sys.argv[1]):
        where = "exe" if game.base <= addr < game.base + game.size else "heap"
        line = f"{enc:9} {addr:#x} {where}"
        if ctx:
            line += "  " + repr(game.pm.read_bytes(addr - ctx, len(sys.argv[1]) + 2 * ctx))
        print(line)
