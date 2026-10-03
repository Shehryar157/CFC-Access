"""Memory diff scanner: find addresses whose value follows a sequence.

  python tools/scan.py "0 down 1 down 2 up 1 up 0"

Numbers are the values we expect at the moment of each snapshot; words are
keys pressed in between (see tools/win.py for key names). Every address is
tried as u8, u16 and i32. Survivors are printed and saved to
scratch/scan_result.txt.

How it works: the first snapshot is kept whole. After the second one we
compare the two with numpy and keep only the positions (indices) where the
values matched; from then on we only re-check those indices, so memory use
stays small.
"""
import sys
import time

import numpy as np

sys.path.insert(0, __file__.rsplit("tools", 1)[0])
from cfcaccess import memory  # noqa: E402
from tools import win  # noqa: E402

TYPES = {"u8": np.uint8, "u16": np.uint16, "i32": np.int32}


def snapshot(game, only=None):
    """Read every writable region (or just the regions in `only`)."""
    snap = {}
    for start, size, _ in memory.regions(game.pm.process_handle):
        if only is not None and start not in only:
            continue
        try:
            snap[start] = game.pm.read_bytes(start, size)
        except Exception:
            pass  # region freed or protected between query and read
    return snap


def view(data, dtype):
    n = len(data) - len(data) % np.dtype(dtype).itemsize
    return np.frombuffer(data[:n], dtype=dtype)


def describe(game, address):
    if game.base <= address < game.base + game.size:
        return f"{address:#x} (exe+{address - game.base:#x})"
    return f"{address:#x}"


# Where each kind of list draws its rows: (x, first row y, row spacing, rows).
LAYOUTS = {
    "main": (215, 156, 53.3, 6),          # main menu, options, museum
    "gamesettings": (195, 245, 53.3, 6),  # Game Settings pop-up
    "pause": (232, 178, 53.3, 7),         # in-game pause menu
    "leaderboard": (120, 214, 48.7, 7),   # ranked leaderboard rows
}
layout = "main"


def detect_main_menu(hwnd):
    """Read the list cursor from a screenshot: the highlighted row is teal."""
    from PIL import Image
    x, y0, step, rows = LAYOUTS[layout]
    im = Image.open(win.screenshot(hwnd, "scratch/detect.png"))
    lit = [i for i in range(rows) if (lambda c: c[2] > 90 and c[2] - c[0] > 60)(im.getpixel((x, int(y0 + step * i))))]
    if len(lit) != 1:
        sys.exit(f"could not see the cursor (lit rows {lit}); see scratch/detect.png")
    return lit[0]


def is_value(step):
    return step == "?" or step.lstrip("-").isdigit()


def main(spec):
    game, hwnd = win.game_window()
    steps = spec.split()
    values = []
    win.focus(hwnd)

    first = None
    cands = {}  # (type, region start) -> numpy array of element indices
    for step in steps:
        if not is_value(step):
            win.press(step)
            time.sleep(0.5)  # let menu animations finish
            continue
        # "?" means: don't trust the key presses, look at the screen.
        value = detect_main_menu(hwnd) if step == "?" else int(step)
        values.append(value)
        print(f"value {value}")
        t0 = time.time()
        if first is None:
            first = (value, snapshot(game))
            total = sum(len(b) for b in first[1].values())
            print(f"snapshot 1: {len(first[1])} regions, {total / 2**20:.0f} MB, {time.time() - t0:.1f}s")
            continue
        if first[1] is not None and value == first[0]:
            # Same value as the first snapshot: comparing would keep millions
            # of unchanged spots. Wait for a change before the first filter.
            print("value unchanged; waiting for a change before filtering")
            continue
        if first[1] is not None:
            v0, snap0 = first
            snap1 = snapshot(game)
            for tname, dt in TYPES.items():
                for start, b0 in snap0.items():
                    b1 = snap1.get(start)
                    if b1 is None:
                        continue
                    n = min(len(b0), len(b1))
                    a0, a1 = view(b0[:n], dt), view(b1[:n], dt)
                    idx = np.nonzero((a0 == v0) & (a1 == value))[0]
                    if len(idx):
                        cands[(tname, start)] = idx
            first = (v0, None)  # free the big first snapshot
        else:
            snap = snapshot(game, only={start for _, start in cands})
            for key in list(cands):
                tname, start = key
                data = snap.get(start)
                if data is None:
                    del cands[key]
                    continue
                arr = view(data, TYPES[tname])
                idx = cands[key]
                idx = idx[idx < len(arr)]
                idx = idx[arr[idx] == value]
                if len(idx):
                    cands[key] = idx
                else:
                    del cands[key]
        count = sum(len(i) for i in cands.values())
        print(f"after value {value}: {count} candidates ({time.time() - t0:.1f}s)")

    lines = []
    for (tname, start), idx in sorted(cands.items()):
        size = np.dtype(TYPES[tname]).itemsize
        for i in idx:
            lines.append(f"{tname} {describe(game, start + int(i) * size)}")
    with open("scratch/scan_result.txt", "w") as f:
        f.write("\n".join(lines))
    print(f"{len(lines)} results (sequence {values}); first 60:")
    print("\n".join(lines[:60]))


if __name__ == "__main__":
    if len(sys.argv) > 2:
        layout = sys.argv[2]
    main(sys.argv[1])
