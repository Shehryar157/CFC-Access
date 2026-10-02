"""Reader for MT Framework .arc archives (version 7, as used by this game).

Layout:
  header: b"ARC\\0", u16 version, u16 file count
  entries: one 80-byte row per file:
      name (64 bytes, ASCII, zero padded, no extension)
      u32 type hash (says what kind of file it is; stands in for the extension)
      u32 compressed size
      u32 decompressed size, with flags in the top bits
      u32 offset of the data from the start of the archive
  data: each file compressed with zlib

Usage:
  python -m cfcaccess.arc list <file.arc>
  python -m cfcaccess.arc extract <file.arc> <out_dir>
"""
import os
import struct
import sys
import zlib

ENTRY_SIZE = 80


def read_entries(path):
    with open(path, "rb") as f:
        magic, version, count = struct.unpack("<4sHH", f.read(8))
        if magic != b"ARC\0":
            raise ValueError(f"{path}: not an ARC file (magic {magic!r})")
        table = f.read(ENTRY_SIZE * count)
    entries = []
    for i in range(count):
        row = table[i * ENTRY_SIZE:(i + 1) * ENTRY_SIZE]
        name = row[:64].split(b"\0", 1)[0].decode("ascii", "replace")
        type_hash, csize, dsize_flags, offset = struct.unpack("<IIII", row[64:80])
        entries.append({
            "name": name,
            "type": type_hash,
            "csize": csize,
            "dsize": dsize_flags & 0x1FFFFFFF,
            "offset": offset,
        })
    return entries


def read_file(path, entry):
    with open(path, "rb") as f:
        f.seek(entry["offset"])
        data = f.read(entry["csize"])
    if entry["csize"] == entry["dsize"]:
        return data  # stored uncompressed
    return zlib.decompress(data)


def main(argv):
    cmd, path = argv[1], argv[2]
    entries = read_entries(path)
    if cmd == "list":
        for e in entries:
            print(f"{e['type']:08X} {e['dsize']:>10} {e['name']}")
    elif cmd == "extract":
        out_dir = argv[3]
        for e in entries:
            out = os.path.join(out_dir, e["name"].replace("\\", os.sep) + f".{e['type']:08X}")
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with open(out, "wb") as f:
                f.write(read_file(path, e))
        print(f"extracted {len(entries)} files to {out_dir}")


if __name__ == "__main__":
    main(sys.argv)
