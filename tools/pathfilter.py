"""Narrow a list of pointer paths by checking them against the screen.

  python tools/pathfilter.py <in.txt> <out.txt> "goto3 goto0 backspace ? goto1 goto5"

Steps:
  gotoN      move the list cursor to item N (read from the screen), then keep
             only paths whose value equals the cursor
  ?          keep paths whose value equals the cursor shown on screen
  other      press that key and wait (see tools/win.py for key names)
"""
import sys
import time

sys.path.insert(0, __file__.rsplit("tools", 1)[0])
from tools import ptrscan, scan, win  # noqa: E402


def load(path):
    out = []
    for line in open(path):
        p = line.split()
        if p:
            out.append((int(p[0][4:], 0), [int(x, 0) for x in p[1:]], line.strip()))
    return out


def main(src, dst, spec):
    game, hwnd = win.game_window()
    paths = load(src)
    print(f"{len(paths)} paths")
    win.focus(hwnd)

    def keep(expected):
        nonlocal paths
        survivors = []
        for e, offs, line in paths:
            try:
                if game.pm.read_int(ptrscan.follow(game, e, offs)) == expected:
                    survivors.append((e, offs, line))
            except Exception:
                pass
        paths = survivors
        print(f"cursor {expected}: {len(paths)} paths left")

    for step in spec.split():
        if step.startswith("goto"):
            target = int(step[4:])
            for _ in range(10):
                c = scan.detect_main_menu(hwnd)
                if c == target:
                    break
                win.press("down" if c < target else "up", hold=0.15)
                time.sleep(0.6)
            keep(scan.detect_main_menu(hwnd))
        elif step == "?":
            keep(scan.detect_main_menu(hwnd))
        else:
            win.press(step, hold=0.15)
            time.sleep(2)

    with open(dst, "w") as f:
        f.write("\n".join(line for _, _, line in paths) + "\n")
    for _, _, line in paths[:25]:
        print(" ", line)


if __name__ == "__main__":
    main(*sys.argv[1:4])
