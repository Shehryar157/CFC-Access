"""Research helper for the arcade games.

  python tools/arcadetool.py go "Cyberbots"   go to that game's arcade mode, coin, start
  python tools/arcadetool.py fp               print the running game's fingerprint
  python tools/arcadetool.py save | load      quick save / quick load (pause menu)
  python tools/arcadetool.py keys d d a s     tap keys; list RAM bytes that changed
                                              at every tap; screenshots in
                                              scratch/arcsteps.png
  python tools/arcadetool.py peek ff8300 64   hex dump of arcade memory
Keys are the game's Type A bindings: w a s d move, u i o j k l attack,
f1 start, ralt coin.
"""
import pickle
import sys
import time

sys.path.insert(0, __file__.rsplit("tools", 1)[0])
from PIL import Image  # noqa: E402

from cfcaccess import arcade  # noqa: E402
from tools import ramdiff, win  # noqa: E402
from tools.nav import Nav  # noqa: E402

win.SCAN.update({
    "ralt": (0x38, True), "u": (0x16, False), "i": (0x17, False), "o": (0x18, False),
    "j": (0x24, False), "k": (0x25, False), "l": (0x26, False),
    "w": (0x11, False), "a": (0x1E, False), "s": (0x1F, False), "d": (0x20, False),
})


def nav():
    return Nav()


def pause(n):
    if (n.title() or "").startswith("Quick save"):
        n.press("enter", hold=0.1)
        win.wait_for(lambda: n.title() == "Pause Menu", 3)
    if n.title() == "Pause Menu":
        return
    for hold in (0.25, 0.4, 0.6):
        n.press("f2", hold=hold)
        if win.wait_for(lambda: n.title() == "Pause Menu", 3):
            return
    raise SystemExit("no pause menu: " + n.describe())


def resume(n):
    if n.title() == "Pause Menu":
        n.goto_label("Resume")
        n.press("enter", hold=0.1)
        win.wait_for(lambda: n.title() is None, 3)
    time.sleep(0.3)


def to_select_game(n):
    for _ in range(8):
        win.wait_for(lambda: n.title() != "", 10)  # "" = the "Saving..." notice
        t = n.title()
        if t == "Select Game":
            return
        if t == "Select Mode":
            n.press("backspace", hold=0.15)
            win.wait_for(lambda: n.title() == "Select Game", 3)
            continue
        if t == "Main Menu":
            n.open_row("Offline Play", "Select Game")
            return
        if t is None:
            # Either inside a game or between screens: give a menu a moment
            # to appear before assuming we're in a game.
            if win.wait_for(lambda: n.title() is not None, 4):
                continue
            try:
                pause(n)
            except SystemExit:
                pass
            continue
        if t == "Pause Menu":
            n.goto_label("Quit")
            n.press("enter", hold=0.15)
            win.wait_for(lambda: (n.title() or "").startswith("Exit"), 3)
            continue
        if t.startswith("Exit") or t.startswith("Quick save"):
            n.goto_label("Yes" if t.startswith("Exit") else "OK")
            n.press("enter", hold=0.15)
            win.wait_for(lambda: n.title() != t, 12)
            continue
        n.press("backspace", hold=0.15)
        win.wait_for(lambda: n.title() != t, 3)
    n.expect("Select Game", 2)


def go(n, game):
    to_select_game(n)
    names = tuple(game.split("|"))   # "Darkstalkers|Vampire: The Night"
    n.goto(0)
    for _ in range(12):
        if n.view().rows[0].value.startswith(names):
            break
        b = n.view().rows[0].value
        n.press("right", hold=0.15)
        win.wait_for(lambda: n.view().rows[0].value != b, 1)
    if not n.view().rows[0].value.startswith(names):
        raise SystemExit("game not found: " + n.describe())
    # English version where there is one (the story text is then English).
    n.goto(1)
    for _ in range(3):
        if n.view().rows[1].value.startswith("English"):
            break
        b = n.view().rows[1].value
        n.press("right", hold=0.15)
        win.wait_for(lambda: n.view().rows[1].value != b, 1)
    print(n.describe())
    for _ in range(3):
        n.press("enter", hold=0.15)
        if win.wait_for(lambda: n.title() == "Select Mode", 3):
            break
    for _ in range(4):
        if n.view().rows[0].value == "Arcade Mode":
            break
        b = n.view().rows[0].value
        n.press("right", hold=0.15)
        win.wait_for(lambda: n.view().rows[0].value != b, 1)
    n.press("enter", hold=0.15)
    time.sleep(14)          # let the board boot past its logo
    n.press("ralt", hold=0.25)
    time.sleep(1.0)
    n.press("f1", hold=0.25)
    time.sleep(2.0)
    win.release_keyboard()
    fp(n)


def fp(n):
    a = arcade.Arcade(n.game)
    a.locate()
    print("fingerprint", n.game.pm.read_bytes(a.base, 8).hex())


def save(n):
    pause(n)
    n.goto_label("Quick Save")
    n.press("enter", hold=0.1)
    win.wait_for(lambda: "Overwrite" in (n.title() or "") or (n.title() or "").startswith("Quick save"), 4)
    if "Overwrite" in (n.title() or ""):
        n.goto_label("Yes")
        n.press("enter", hold=0.1)
        win.wait_for(lambda: (n.title() or "").startswith("Quick save"), 4)
    n.press("enter", hold=0.1)
    win.wait_for(lambda: n.title() == "Pause Menu", 3)
    resume(n)
    win.release_keyboard()
    print("saved")


def load(n):
    pause(n)
    time.sleep(0.3)
    n.goto_label("Load Quick Save")
    n.press("enter", hold=0.1)
    win.wait_for(lambda: (n.title() or "").startswith(("Load", "Quick save")), 3)
    if (n.title() or "").startswith("Load"):
        n.goto_label("Yes")
        n.press("enter", hold=0.1)
        win.wait_for(lambda: (n.title() or "").startswith("Quick save"), 4)
    n.press("enter", hold=0.1)
    win.wait_for(lambda: n.title() == "Pause Menu", 3)
    time.sleep(0.3)
    resume(n)
    win.release_keyboard()


def keys(n, key_list):
    a = arcade.Arcade(n.game)
    a.locate()

    def shot():
        return Image.open(win.screenshot(n.hwnd, "scratch/t.png")).crop((0, 0, 1280, 720)).resize((256, 144))

    frames, snaps = [shot()], [ramdiff.ram(a)]
    for key in key_list:
        n.press(key, hold=0.05)
        time.sleep(0.35)
        frames.append(shot())
        snaps.append(ramdiff.ram(a))
    win.release_keyboard()
    pickle.dump(snaps, open("scratch/arcsnaps.pkl", "wb"))
    sheet = Image.new("RGB", (256 * len(frames), 144))
    for i, f in enumerate(frames):
        sheet.paste(f, (256 * i, 0))
    sheet.save("scratch/arcsteps.png")
    for i in range(0x10000):
        v = [x[i] for x in snaps]
        if all(v[j] != v[j - 1] for j in range(1, len(v))) and max(v) < 64:
            print(f"{0xFF0000 + i:#08x}: {v}")


def peek(n, address, length):
    a = arcade.Arcade(n.game)
    a.locate()
    data = bytes(a.read_byte(address + i) for i in range(length))
    for off in range(0, length, 16):
        print(f"{address + off:#08x}: {data[off:off + 16].hex(' ')}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    cmd = sys.argv[1]
    n = nav()
    if cmd == "go":
        go(n, sys.argv[2])
    elif cmd == "fp":
        fp(n)
    elif cmd == "save":
        save(n)
    elif cmd == "load":
        load(n)
    elif cmd == "keys":
        keys(n, sys.argv[2:])
    elif cmd == "peek":
        peek(n, int(sys.argv[2], 16), int(sys.argv[3]) if len(sys.argv) > 3 else 64)
