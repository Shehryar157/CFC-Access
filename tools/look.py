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
    """(object, class, cursor, count) of the top open layer, as the mod sees it."""
    reader = menus.MenuReader(game, None)
    layer = reader.top_layer()
    if layer is None:
        return None
    obj, cls = layer
    off = 0x34C if cls == 0x14052E3B8 else 0x320
    return obj, cls, game.pm.read_int(obj + off), game.pm.read_int(obj + off + 4)


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
