"""Press keys and see which arcade work-RAM bytes follow them.

  python tools/ramdiff.py right right left

Takes a 64 KB snapshot of arcade RAM (0xFF0000-0xFFFFFF) after each key
and prints the bytes that changed in step with the presses (changed when a
key was pressed, steady while waiting). Cheap: 64 KB per snapshot.
"""
import sys
import time

sys.path.insert(0, __file__.rsplit("tools", 1)[0])
from cfcaccess import arcade  # noqa: E402
from tools import win  # noqa: E402

RAM = 0xFF0000


def ram(a):
    raw = a.game.pm.read_bytes(a.base + RAM, 0x10000)
    # undo the word swap so index i is arcade byte RAM + i
    return bytes(raw[i ^ 1] for i in range(len(raw)))


def main(keys):
    game, hwnd = win.game_window()
    a = arcade.Arcade(game)
    a.locate()
    win.focus(hwnd)
    snaps = [ram(a)]
    for key in keys:
        win.press(key, hold=0.15)
        time.sleep(0.5)
        snaps.append(ram(a))
        time.sleep(0.5)
        snaps.append(ram(a))  # same key, after a pause: should be steady
    win.release_keyboard()
    for i in range(0x10000):
        vals = [s[i] for s in snaps]
        steady = all(vals[k] == vals[k + 1] for k in range(1, len(vals) - 1, 2))
        moved = all(vals[k] != vals[k - 1] for k in range(1, len(vals), 2))
        if steady and moved:
            print(f"{RAM + i:#08x}: {vals[0::2]}")


if __name__ == "__main__":
    main(sys.argv[1:])
