"""Press keys, then screenshot the game and print the current screen object.

  python tools/look.py [key ...]

Saves scratch/look.png (the 1280x720 game image) and prints the screen
class, cursor and count the mod would see.
"""
import sys
import time

sys.path.insert(0, __file__.rsplit("tools", 1)[0])
from PIL import Image  # noqa: E402

from cfcaccess import menus  # noqa: E402
from tools import win  # noqa: E402


def current(game):
    for exe_offset, offsets in menus.ROUTES:
        try:
            p = game.pm.read_ulonglong(game.base + exe_offset)
            for off in offsets:
                p = game.pm.read_ulonglong(p + off)
            return p, game.pm.read_ulonglong(p), game.pm.read_int(p + 0x320), game.pm.read_int(p + 0x324)
        except Exception:
            continue
    return None


if __name__ == "__main__":
    game, hwnd = win.game_window()
    win.focus(hwnd)
    for key in sys.argv[1:]:
        win.press(key, hold=0.15)
        time.sleep(0.7)
    time.sleep(1)
    Image.open(win.screenshot(hwnd, "scratch/look_full.png")).crop((0, 0, 1280, 720)).save("scratch/look.png")
    cur = current(game)
    if cur:
        obj, cls, cursor, count = cur
        known = "known" if cls in menus.SCREENS else "UNKNOWN"
        print(f"object={obj:#x} class={cls:#x} ({known}) cursor={cursor} count={count}")
    else:
        print("no screen object")
