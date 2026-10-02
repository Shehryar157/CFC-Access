"""Reader for MT Framework GMD message files (the game's menu text).

Layout (version 0x00010302):
  header, 0x28 bytes: b"GMD\\0", u32 version, u32 language, u64 unknown,
      u32 key count, u32 string count, u32 key block size,
      u32 string block size, u32 name length
  name: ASCII + zero byte
  entries: key count x 32 bytes (u32 index, u32 hash, u32 hash, u32 pad,
      u64 key offset, u64 bucket link)
  buckets: 256 x u64 (the game's hash-table slots; we don't need them)
  keys: key block, zero-terminated ASCII names
  strings: string block, zero-terminated UTF-8 text, in index order

Usage:
  python -m cfcaccess.gmd <file> [search text]
"""
import struct
import sys


def read_gmd(path):
    """Return a list of (key, text) pairs in the file's order."""
    with open(path, "rb") as f:
        return parse_gmd(f.read())


def parse_gmd(data):
    """Same as read_gmd, from the file's bytes."""
    magic, version, lang, _unk, n_keys, n_strings, key_size, str_size, name_len = \
        struct.unpack_from("<4sIIQIIIII", data, 0)
    if magic != b"GMD\0":
        raise ValueError("not a GMD file")
    pos = 0x28 + name_len + 1
    entries = []
    for i in range(n_keys):
        index, = struct.unpack_from("<I", data, pos)
        key_offset, = struct.unpack_from("<Q", data, pos + 16)
        entries.append((index, key_offset))
        pos += 32
    if n_keys:
        pos += 256 * 8
    key_block = data[pos:pos + key_size]
    pos += key_size
    strings = data[pos:pos + str_size].split(b"\0")[:n_strings]
    strings = [s.decode("utf-8", "replace") for s in strings]

    keys = [""] * n_strings
    for index, key_offset in entries:
        end = key_block.index(b"\0", key_offset)
        keys[index] = key_block[key_offset:end].decode("ascii", "replace")
    return list(zip(keys, strings))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    pairs = read_gmd(sys.argv[1])
    needle = sys.argv[2].lower() if len(sys.argv) > 2 else None
    for i, (key, text) in enumerate(pairs):
        if needle is None or needle in key.lower() or needle in text.lower():
            print(f"{i:5} {key}: {text!r}")
