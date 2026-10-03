"""Speaking the collection's own menus (main menu, options, select game...).

How we find the menu in memory (worked out with tools/scan.py and
tools/ptrscan.py):
  - A fixed spot in the exe (MANAGER) points to the GUI manager. It keeps a
    stack of screen layers: +0xE0 is the highest slot in use, and slot i's
    object pointer is at +0xE8 + 16*i. Slot 0 is the backdrop, then full
    screens (main menu, select game...), then pop-ups (game settings).
  - A closed pop-up keeps its slot, but its object's class turns into the
    generic CLOSED_CLASS or into leftover junk; we skip those and read the
    topmost layer that is really open.
  - An object's first 8 bytes are its C++ class's vtable address, which
    identifies the screen. Full screens keep the cursor at +0x320 and the
    item count right after it; pop-ups at +0x34C.

Each screen is described by a "resolver": a function that reads the screen
object and returns a View (title + rows of finished text). The speaking code
only compares and speaks Views, whatever screen they came from.
"""
from dataclasses import dataclass, field
from typing import Optional

from . import speech

MANAGER = 0x668E670
LAYER_TOP, LAYER_BASE, LAYER_STRIDE = 0xE0, 0xE8, 16
CLOSED_CLASS = 0x1405215E0
BACKDROP_CLASS = 0x14052D048
EXE_START, EXE_END = 0x140000000, 0x147800000


@dataclass
class Row:
    label: str
    value: Optional[str] = None
    help: Optional[str] = None


@dataclass
class View:
    title: str
    cursor: int
    rows: list = field(default_factory=list)


def _int(reader, addr):
    return reader.game.pm.read_int(addr)


# ---- Fixed list screens (main menu, options, museum) ----

def fixed_list(title_key, items, cursor_offset=0x320):
    """Resolver for a screen with a fixed list of (label key, help key)."""
    def resolve(reader, obj):
        msg = reader.msg
        return View(
            title=msg.get(title_key, ""),
            cursor=_int(reader, obj + cursor_offset),
            rows=[Row(msg.get(label, label), None, msg.get(help) if help else None)
                  for label, help in items],
        )
    return resolve


# ---- Select Game (Offline Play) ----
# Per game: one (title, region, ROM) entry per version. The game shows the
# version as "Japanese Version (Japan 940705)": the first words come from the
# menu text, the ROM region and date from this table. Vampire Hunter 2 and
# Vampire Savior 2 were only released in Japan, so they have one version.
GAMES = [
    [("Vampire: The Night Warriors", "J", "(Japan 940705)"),
     ("Darkstalkers: The Night Warriors", "E", "(USA 940818)")],
    [("Vampire Hunter: Darkstalkers' Revenge", "J", "(Japan 950302)"),
     ("Night Warriors: Darkstalkers' Revenge", "E", "(USA 950406)")],
    [("Vampire Savior: The Lord of Vampire", "J", "(Japan 970519)"),
     ("Vampire Savior: The Lord of Vampire", "E", "(USA 970519)")],
    [("Vampire Hunter 2: Darkstalkers' Revenge", "J", "(Japan 970929)")],
    [("Vampire Savior 2: The Lord of Vampire", "J", "(Japan 970913)")],
    [("Cyberbots: Fullmetal Madness", "J", "(Japan 950420)"),
     ("Cyberbots: Fullmetal Madness", "E", "(USA 950424)")],
    [("Super Puzzle Fighter II X", "J", "(Japan 960531)"),
     ("Super Puzzle Fighter II Turbo", "E", "(USA 960620)")],
    [("Pocket Fighter", "J", "(Japan 970904)"),
     ("Super Gem Fighter Minimix", "E", "(USA 970904)")],
    [("Hyper Street Fighter II: The Anniversary Edition", "J", "(Japan 040202)"),
     ("Hyper Street Fighter II: The Anniversary Edition", "E", "(USA 040202)")],
    [("Warzard", "J", "(Japan 961121)"),
     ("Red Earth", "E", "(USA 961121)")],
]


def select_game(reader, obj):
    msg = reader.msg
    versions = GAMES[_int(reader, obj + 0x328) % len(GAMES)]
    # A Japan-only game's version number stays at 1 but it shows Japanese.
    title, region, rom = versions[0] if len(versions) == 1 else \
        versions[_int(reader, obj + 0x32C) % len(versions)]
    version = f"{msg.get('GAME_VERSION_J' if region == 'J' else 'GAME_VERSION_E')} {rom}"
    player = msg.get("PLAYER_1P" if _int(reader, obj + 0x330) == 0 else "PLAYER_2P")
    return View(
        title=msg.get("GAME_SELECT"),
        cursor=_int(reader, obj + 0x320),
        rows=[
            Row(msg.get("GAME_TITLE"), title, msg.get("HELP_GAME_TITLE")),
            Row(msg.get("GAME_VERSION"), version, msg.get("HELP_GAME_VERSION")),
            Row(msg.get("PLAYER"), player, msg.get("HELP_PLAYER")),
        ],
    )


# ---- Game Settings / EX Settings pop-up (X on Select Game) ----
# Rows differ per game, so we read the game's own tables of message numbers,
# all indexed by an option id:
#   +0x354 + 4*row   option id shown on each row of the current page
#   +0x554 + 4*id    label message      (644 = "Game Difficulty")
#   +0x5A4 + 4*id    first value message (646 = "Low" for Attack Power)
#   +0x5F4 + 4*id    description message
#   +0x374 + 4*id    current value: text = message[first value + value]
#   +0x340           page: 0 = Game Settings, 1 = EX Settings
OPT_DIFFICULTY = 644    # shown as stars, not text
MENU_OP_DEFAULT = 175   # "Default" has no value


def game_settings(reader, obj):
    msg = reader.msg
    count = _int(reader, obj + 0x350)
    rows = []
    for i in range(count):
        oid = _int(reader, obj + 0x354 + 4 * i)
        label_id = _int(reader, obj + 0x554 + 4 * oid)
        first = _int(reader, obj + 0x5A4 + 4 * oid)
        value = _int(reader, obj + 0x374 + 4 * oid)
        if label_id == OPT_DIFFICULTY:
            text = f"{value} of 8 stars"
        elif label_id == MENU_OP_DEFAULT or first <= 0:
            text = None
        else:
            text = msg.by_index(first + value)
        rows.append(Row(msg.by_index(label_id, "?"), text,
                        msg.by_index(_int(reader, obj + 0x5F4 + 4 * oid))))
    page = _int(reader, obj + 0x340)
    return View(
        title=msg.get("MENU_OP_GAME_SETTING" if page == 0 else "EX_SETTINGS"),
        cursor=_int(reader, obj + 0x34C),
        rows=rows,
    )


# Screen class (vtable address) -> resolver. Message keys come from msg.arc's
# menu_eng (python -m cfcaccess.gmd <file> to browse them).
SCREENS = {
    0x14052D278: fixed_list("MAIN_MENU", [
        ("OFFLINE_PLAY", "HELP_OFFLINE_PLAY"),
        ("ONLINE_PLAY", "HELP_ONLINE_PLAY"),
        ("MUSEUM", "HELP_MUSEUM"),
        ("FIGHTER_AWARD", "HELP_FIGHTER_AWARD"),
        ("OPTIONS", "HELP_OPTION"),
        ("EXIT", "HELP_EXIT"),
    ]),
    0x14052EE60: fixed_list("OPTIONS", [
        ("MENU_OP_SYSTEM", "HELP_OP_SYSTEM"),
        ("MENU_OP_SOUND", "HELP_OP_SOUND"),
        ("MENU_OP_NET", "HELP_OP_NETWORK"),
        ("MENU_OP_PC", "HELP_OP_PC"),
        ("MENU_OP_CREDITS", "HELP_OP_CREDIT"),
    ]),
    0x14052D8F8: fixed_list("MUSEUM", [
        ("GALLERY", "HELP_GALLERY"),
        ("SOUND", "HELP_SOUND"),
    ]),
    0x140530800: select_game,
    0x14052E3B8: game_settings,
}

MISS_LIMIT = 6  # invalid reads in a row (at 20 a second) before a screen counts as gone

# For screens we don't know yet: where to look for a cursor and count.
GUESS_CURSOR_OFFSETS = (0x320, 0x34C)


class MenuReader:
    def __init__(self, game, messages):
        self.game = game
        self.msg = messages
        self.last_layer = None  # (object, class) of the layer last spoken
        self.last_view = None   # the View last spoken
        self.misses = 0         # invalid reads in a row

    def top_layer(self):
        """(object, class) of the topmost open screen layer, or None."""
        pm = self.game.pm
        try:
            mgr = pm.read_ulonglong(self.game.base + MANAGER)
            top = pm.read_int(mgr + LAYER_TOP)
        except Exception:
            return None
        if not 0 <= top < 32:
            return None
        for i in range(top, -1, -1):
            try:
                obj = pm.read_ulonglong(mgr + LAYER_BASE + LAYER_STRIDE * i)
                cls = pm.read_ulonglong(obj)
            except Exception:
                continue
            if EXE_START <= cls < EXE_END and cls not in (CLOSED_CLASS, BACKDROP_CLASS):
                return obj, cls
        return None

    def view(self, obj, cls):
        resolve = SCREENS.get(cls)
        if resolve is not None:
            return resolve(self, obj)
        # Unknown screen: find a plausible cursor and count, and log the class
        # so the screen can be added to SCREENS.
        for off in GUESS_CURSOR_OFFSETS:
            cursor, count = _int(self, obj + off), _int(self, obj + off + 4)
            if 0 < count <= 100 and 0 <= cursor < count:
                return View(f"Unknown screen {cls:#x}", cursor,
                            [Row(f"Item {i + 1}") for i in range(count)])
        return None

    def poll(self):
        """Check the menu once; speak if the screen, cursor or a value changed."""
        layer = self.top_layer()
        view = None
        if layer is not None:
            try:
                view = self.view(*layer)
            except Exception:
                view = None
        if view is None or not 0 <= view.cursor < len(view.rows):
            # During animations a read can be briefly invalid. Only forget the
            # screen (so it's announced afresh) after several misses in a row.
            self.misses += 1
            if self.misses >= MISS_LIMIT:
                self.last_layer = self.last_view = None
            return
        self.misses = 0
        old, old_layer = self.last_view, self.last_layer
        self.last_view, self.last_layer = view, layer
        if old is None or old_layer != layer or old.title != view.title:
            # A different screen (or page): title, then the current row.
            if view.title.startswith("Unknown screen"):
                print(f"UNKNOWN SCREEN {view.title}")
            speech.say(self.describe(view, with_title=True))
        elif old.cursor != view.cursor:
            speech.say(self.describe(view, with_title=False))
        else:
            self._speak_value_changes(old, view)

    def _speak_value_changes(self, old, view):
        """A value changed without the cursor moving (Left/Right): say the
        current row's new value first, then any other rows it changed."""
        order = [view.cursor] + [i for i in range(len(view.rows)) if i != view.cursor]
        changed = [view.rows[i].value for i in order
                   if i < len(old.rows) and view.rows[i].value != old.rows[i].value
                   and view.rows[i].value]
        if changed:
            speech.say(". ".join(changed))

    def describe(self, view, with_title):
        parts = []
        if with_title and view.title:
            parts.append(view.title + ".")
        row = view.rows[view.cursor]
        label = f"{row.label}: {row.value}" if row.value else row.label
        parts.append(f"{label}, {view.cursor + 1} of {len(view.rows)}.")
        if row.help:
            parts.append(row.help)
        return " ".join(parts)
