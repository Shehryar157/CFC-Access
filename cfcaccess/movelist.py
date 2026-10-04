"""Move lists (pause menu > Move List), decoded from the game's own tables.

Everything lives in the exe (found 2026-10-04 while the Move List was open):
  MOVE_TABLES       one pointer per game (Select Game order) to its move table
  move record       12 bytes: u8 character (127 = basic moves for everyone),
                    u8 ?, u8 one-button shortcut, u8 ?, u32 name message
                    (45 = a blank name: a continuation line such as "Or ..."),
                    u16 input number, u8 prefix, u8 suffix
  INPUT_INDEX       pointer per input; input n is entry n - 1. Each input is a
                    zero-terminated byte string:
                      0x01-0x3C  icon (position + 1 in the icon list, from C_P)
                      0x3D-0x45  "MID" messages 878.. ("+", "/", "->",
                                 "(Tap Repeatedly)", "Standing", ...)
                      0x46-0x4A  suffix messages 958.. ("(Chargeable)",
                                 "(Press Simultaneously)", ...)
  PREFIXES          message number per prefix ("Near Opponent", "Or", ...);
                    suffixes use the same list starting at SUFFIX_START.
The icon names (C_P, C_6, C_236 ...) come from msg.arc's font_img_kbd file.
"""
import re
import struct

from . import arc, text

MOVE_TABLES = 0x673460   # offsets from the exe base
INPUT_INDEX = 0x672948
PREFIXES = 0x6732D0
SUFFIX_START = 68        # suffix n is PREFIXES[SUFFIX_START + n]
BLANK_NAME = 45          # message 45 is a single space
ICON_FILE = r"ui\0_system\00_font\font_img_kbd"
ICON_TYPE = 0x07F768AF
FIRST_C_ICON = "C_P"

DIRECTIONS = {"1": "down-back", "2": "down", "3": "down-forward", "4": "back", "5": "neutral",
              "6": "forward", "7": "up-back", "8": "up", "9": "up-forward"}
MOTION_NAMES = {
    "236": "quarter circle forward", "214": "quarter circle back",
    "623": "dragon punch motion", "421": "reverse dragon punch motion",
    "41236": "half circle forward", "63214": "half circle back",
}
BUTTONS = {
    "C_P": "any punch", "C_LP": "light punch", "C_MP": "medium punch", "C_HP": "heavy punch",
    "C_K": "any kick", "C_LK": "light kick", "C_MK": "medium kick", "C_HK": "heavy kick",
    "C_A": "any attack", "C_A1": "attack 1", "C_A2": "attack 2", "C_B": "boost", "C_W": "weapon",
    "C_P2": "punch", "C_K2": "kick", "C_S2": "special", "C_START": "start",
    "C_5": "any direction", "C_S": "special", "C_SP": "special move button",
    "C_EX": "EX button", "C_1BTN": "one-button special",
}
SHORTCUTS = {16: "special move button", 18: "down plus special move button",
             20: "back plus special move button", 22: "forward plus special move button",
             32: "EX button"}


def load_icon_names(game_dir=None):
    """Icon names in order, from the icon font's GII file in msg.arc."""
    from .paths import find_game_dir
    game_dir = game_dir or find_game_dir()
    path = game_dir + "\\" + text.MSG_ARC
    for entry in arc.read_entries(path):
        if entry["type"] == ICON_TYPE and entry["name"] == ICON_FILE:
            data = arc.read_file(path, entry)
            return [m.group().decode() for m in re.finditer(rb"[A-Z][A-Z0-9_]+", data)
                    if m.group() != b"GII"]
    return []


def speak_icon(name):
    """Words for one icon name, e.g. C_236 -> 'quarter circle forward'."""
    if name in BUTTONS:
        return BUTTONS[name]
    m = re.fullmatch(r"C_(\d+)(T?)", name)
    if not m:
        return name.replace("C_", "").lower()
    digits, charge = m.groups()
    if charge:  # charge icons: hold that direction
        return "hold " + DIRECTIONS.get(digits, digits)
    if len(digits) == 1:
        return DIRECTIONS.get(digits, digits)
    path = ", ".join(DIRECTIONS.get(d, d) for d in digits)
    named = MOTION_NAMES.get(digits)
    return f"{named} ({path})" if named else path


class MoveLists:
    def __init__(self, game, messages):
        self.game = game
        self.msg = messages
        self.icons = load_icon_names()
        self.first_c = self.icons.index(FIRST_C_ICON) if FIRST_C_ICON in self.icons else 87

    def _u64(self, offset):
        return self.game.pm.read_ulonglong(self.game.base + offset)

    def input_text(self, number):
        if number <= 0:
            return ""
        pm = self.game.pm
        ptr = pm.read_ulonglong(self.game.base + INPUT_INDEX + 8 * (number - 1))
        raw = pm.read_bytes(ptr, 48).split(b"\0", 1)[0]
        words = []
        for c in raw:
            if c <= 0x3C:
                i = self.first_c + c - 1
                words.append(speak_icon(self.icons[i]) if i < len(self.icons) else f"icon {c}")
            elif c <= 0x45:
                words.append(self.msg.raw_by_index(878 + c - 0x3D))
            else:
                words.append(self.msg.raw_by_index(958 + c - 0x46))
        out = " ".join(w for w in words if w)
        return out.replace(" + ", " plus ").replace(" / ", " or ")

    def _list_message(self, index):
        return self.game.pm.read_uint(self.game.base + PREFIXES + 4 * index)

    def record_text(self, game_index, record):
        pm = self.game.pm
        table = self._u64(MOVE_TABLES + 8 * game_index)
        raw = pm.read_bytes(table + 12 * record, 12)
        _char, _h1, shortcut, _h3, name, inp, pre, suf = struct.unpack("<BBBBIHBB", raw)
        parts = []
        if pre:
            parts.append(self.msg.raw_by_index(self._list_message(pre)))
        parts.append(self.input_text(inp))
        if suf:
            parts.append(self.msg.raw_by_index(self._list_message(SUFFIX_START + suf)))
        how = " ".join(p for p in parts if p).strip()
        label = "" if name == BLANK_NAME else self.msg.by_index(name, "")
        line = f"{label}: {how}" if label else how
        if shortcut in SHORTCUTS:
            line += f". Shortcut: {SHORTCUTS[shortcut]}"
        # Prefixes can contain icons themselves ("Or During Normal <ICON C_A1>
        # Throw"); turn those into words before the remaining tags are dropped.
        line = re.sub(r"<ICON (C_\w+)>", lambda m: " " + speak_icon(m.group(1)) + " ", line)
        return text.clean(line)

    def record_character(self, game_index, record):
        table = self._u64(MOVE_TABLES + 8 * game_index)
        return self.game.pm.read_bytes(table + 12 * record, 1)[0]
