"""Pattern scan for values whose exact numbers we don't know.

Each step presses a key (or nothing) and then states how the value must
relate to earlier snapshots, e.g. for a cursor:

    start      v0
    right      v1 != v0
    left       v2 == v0
    right      v3 == v1
    (wait)     v4 == v3

Usage (from code): survivors = run(game, steps) where steps is a list of
(key or None, rule) and rule(values_so_far, new) -> bool numpy mask.
Only bytes (u8) are tracked, which works whatever the byte order.
"""
import sys
import time

import numpy as np

sys.path.insert(0, __file__.rsplit("tools", 1)[0])
from tools import scan, win  # noqa: E402


def run(game, steps, settle=0.6, regions=None):
    cands = None  # region start -> (indices, list of value arrays)
    for key, rule in steps:
        if key:
            win.press(key, hold=0.15)
        time.sleep(settle)
        only = regions if cands is None else set(cands)
        snap = scan.snapshot(game, only=only)
        new = {}
        for start, data in snap.items():
            arr = np.frombuffer(data, dtype=np.uint8)
            if cands is None:
                new[start] = data  # keep raw bytes; narrowed on the next step
                continue
            if isinstance(cands.get(start), (bytes, bytearray)):
                first = np.frombuffer(cands[start], dtype=np.uint8)
                k = min(len(first), len(arr))
                keep = rule([first[:k]], arr[:k])
                idx = np.nonzero(keep)[0]
                if len(idx):
                    new[start] = (idx, [first[idx].copy(), arr[idx].copy()])
                continue
            if start not in cands:
                continue
            idx, hist = cands[start]
            idx_ok = idx < len(arr)
            idx, hist = idx[idx_ok], [h[idx_ok] for h in hist]
            cur = arr[idx]
            keep = rule(hist, cur)
            if keep.any():
                new[start] = (idx[keep], [h[keep] for h in hist] + [cur[keep]])
        if cands is not None or True:
            cands = new
        total = sum(len(c) if isinstance(c, (bytes, bytearray)) else len(c[0]) for c in cands.values())
        print(f"{key or 'wait':6} {total} candidates", flush=True)
    win.release_keyboard()
    out = []
    for start, (idx, hist) in cands.items():
        for j, i in enumerate(idx):
            out.append((start + int(i), [int(h[j]) for h in hist]))
    return out
