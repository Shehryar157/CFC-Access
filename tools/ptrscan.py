"""Pointer path scanner: find stable routes from the exe to an address.

  python tools/ptrscan.py scan 0x2ba71c00 [max_offset] [depth]
      writes scratch/paths.txt
  python tools/ptrscan.py check scratch/paths.txt
      after a restart, prints each path's current value so we can keep the
      ones that still lead to the right thing

A path "exe+0x5a1230 0x80 0x10 0x20" means:
  p = read_u64(exe_base + 0x5a1230); p = read_u64(p + 0x80);
  p = read_u64(p + 0x10); value is at p + 0x20.
"""
import sys

import numpy as np

sys.path.insert(0, __file__.rsplit("tools", 1)[0])
from cfcaccess import memory  # noqa: E402
from tools import win  # noqa: E402


def pointer_map(game):
    """All aligned 8-byte values that look like user-space addresses.

    Returns (values, holders) sorted by value, so we can binary-search
    "who points into [lo, hi]".
    """
    values, holders = [], []
    for start, size, _ in memory.regions(game.pm.process_handle):
        try:
            data = game.pm.read_bytes(start, size)
        except Exception:
            continue
        arr = np.frombuffer(data[:len(data) // 8 * 8], dtype=np.uint64)
        mask = (arr >= 0x10000) & (arr < 0x7FFFFFFFFFFF) & ((arr & 7) == 0)
        idx = np.nonzero(mask)[0]
        values.append(arr[idx])
        holders.append(np.uint64(start) + idx.astype(np.uint64) * np.uint64(8))
    values = np.concatenate(values)
    holders = np.concatenate(holders)
    order = np.argsort(values, kind="stable")
    return values[order], holders[order]


def scan(game, target, max_offset=0x1000, depth=5, per_level=3000):
    values, holders = pointer_map(game)
    print(f"pointer map: {len(values):,} pointers")
    exe_lo, exe_hi = game.base, game.base + game.size
    results = []
    frontier = {target: []}  # address -> offsets from it to the target
    seen = set(frontier)
    for level in range(depth):
        nxt = {}
        for addr, offs in frontier.items():
            lo = np.searchsorted(values, np.uint64(max(addr - max_offset, 0)), "left")
            hi = np.searchsorted(values, np.uint64(addr), "right")
            for v, h in zip(values[lo:hi], holders[lo:hi]):
                v, h = int(v), int(h)
                path = [addr - v] + offs
                if exe_lo <= h < exe_hi:
                    results.append((h - exe_lo, path))
                elif h not in seen and len(nxt) < per_level:
                    seen.add(h)
                    nxt[h] = path
        print(f"level {level + 1}: {len(nxt)} new holders, {len(results)} paths so far")
        frontier = nxt
        if not frontier:
            break
    return results


def follow(game, exe_offset, offsets):
    p = game.base + exe_offset
    for off in offsets:
        p = game.pm.read_ulonglong(p) + off
    return p


def main(argv):
    game, _ = win.game_window()
    if argv[1] == "scan":
        target = int(argv[2], 0)
        max_offset = int(argv[3], 0) if len(argv) > 3 else 0x1000
        depth = int(argv[4]) if len(argv) > 4 else 5
        results = scan(game, target, max_offset, depth)
        results.sort(key=lambda r: (len(r[1]), r[1]))
        with open("scratch/paths.txt", "w") as f:
            for exe_off, offs in results:
                f.write(f"exe+{exe_off:#x} " + " ".join(f"{o:#x}" for o in offs) + "\n")
        print(f"{len(results)} paths written to scratch/paths.txt; shortest:")
        for exe_off, offs in results[:20]:
            print(f"  exe+{exe_off:#x} " + " ".join(f"{o:#x}" for o in offs))
    elif argv[1] == "check":
        for line in open(argv[2]):
            parts = line.split()
            exe_off = int(parts[0][4:], 0)
            offs = [int(p, 0) for p in parts[1:]]
            try:
                addr = follow(game, exe_off, offs)
                print(f"{game.pm.read_int(addr):6}  {line.strip()}")
            except Exception:
                print(f"{'broken':>6}  {line.strip()}")


if __name__ == "__main__":
    main(sys.argv)
