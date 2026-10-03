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
# Open layers that never hold a menu (backdrops and invisible helpers).
IGNORED_CLASSES = {
    0x1405215E0,  # closed pop-up
    0x14052D048,  # menu backdrop
    0x1405A3830,  # in-game backdrop
    0x14052FD58,  # invisible helper above Select Game
    0x14056E240,  # in-game overlay that always stays on top
    # Appear together with the pause menu; probably its parts (to verify).
    0x1405314F0, 0x14052AE58, 0x14052F8E8,
}
MAX_LAYERS = 24
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


# ---- Keyboard Settings pop-up (Y on Select Game) ----
#   +0x324  cursor: 0 = Key Bindings (layout type), 1..n = bindings, n+1 = Default
#   +0x36C  number of bindings (n); +0x370 layout type (Type A, B, Custom A, B)
#   +0x374 + 0x40*type + 4*i   key number bound to binding i
# Bindings are Menu, Start, Coin, Left, Up, Right, Down, then the selected
# game's buttons, named by that game's CMD_NAME_<prefix>_FF_01.. messages.
SELECT_GAME_CLASS = 0x140530800
FIXED_BINDINGS = ["MENU_OP_PAD_MENU", "MENU_OP_PAD_START", "MENU_OP_PAD_COIN",
                  "MENU_KBD_LEFT", "MENU_KBD_UP", "MENU_KBD_RIGHT", "MENU_KBD_DOWN"]
# Select Game's game number -> prefix of its button-name messages.
BUTTON_PREFIX = ["VAMP", "VAMP", "VAMP", "VAMP", "VAMP",
                 "CYBOTS", "SPF2X", "SGEMF", "HSF2", "WZARD"]

# The game's own key numbers. Worked out from the key icons shown on screen
# for known numbers; unknown ones are spoken as "key N" (and logged).
KEY_NAMES = {7: "Alt", 13: "Left Arrow", 14: "Up Arrow", 15: "Right Arrow", 16: "Down Arrow"}
KEY_NAMES.update({29 + i: chr(ord("A") + i) for i in range(26)})
KEY_NAMES.update({55 + i: f"F{i + 1}" for i in range(12)})


def key_name(number):
    name = KEY_NAMES.get(number)
    if name is None:
        print(f"UNKNOWN KEY NUMBER {number}")
        return f"key {number}"
    return name


def keyboard_settings(reader, obj):
    msg = reader.msg
    count = _int(reader, obj + 0x36C)
    layout = _int(reader, obj + 0x370)
    select = reader.find_layer(SELECT_GAME_CLASS)
    game = _int(reader, select + 0x328) if select else 0
    prefix = BUTTON_PREFIX[game % len(BUTTON_PREFIX)]
    labels = [msg.get(k) for k in FIXED_BINDINGS]
    labels += [msg.get(f"CMD_NAME_{prefix}_FF_{i:02d}", f"Button {i}")
               for i in range(1, count - len(FIXED_BINDINGS) + 1)]
    rows = [Row(msg.get("MENU_KBD_TYPE"), msg.get(f"MENU_OP_PAD_TYPE_{layout:02d}"),
                msg.get("HELP_KBD_TYPE"))]
    for i in range(count):
        key = _int(reader, obj + 0x374 + 0x40 * layout + 4 * i)
        rows.append(Row(labels[i] if i < len(labels) else f"Binding {i + 1}",
                        key_name(key), msg.get("HELP_KBD_KEY")))
    rows.append(Row(msg.get("MENU_OP_DEFAULT"), None, msg.get("HELP_OP_DEFAULT")))
    # The game numbers Default as 15 whatever the number of bindings.
    cursor = _int(reader, obj + 0x324)
    if cursor > count:
        cursor = len(rows) - 1
    return View(msg.get("MENU_KBD_SETTINGS"), cursor, rows)


# ---- In-game pause menu (Menu key, F2 by default) ----
# The layer object points at +0x790 to the menu's logic object, which has
# the cursor (+0x328), item count (+0x32C) and item ids (+0x334 + 4*i).
# The ids index a fixed list of possible items; each mode shows a subset.
# Only ids seen on screen so far are named; others are spoken as "Option N".
PAUSE_LOGIC_CLASS = 0x14052F6A0
PAUSE_ITEMS = {
    0: ("CONTINUE", "HELP_CONTINUE"),
    3: ("COMMAND_LIST", "HELP_COMMAND_LIST"),
    4: ("PAD_SETTING", None),
    5: ("DISPLAY_SOUND_SETTINGS", None),
    7: ("VERSUS_MENU", "HELP_VERSUS_MENU"),
    9: ("CHARA_CHANGE", "HELP_CHARA_CHANGE"),
    12: ("QUIT", "HELP_QUIT"),
}


def pause_menu(reader, obj):
    msg = reader.msg
    pm = reader.game.pm
    logic = pm.read_ulonglong(obj + 0x790)
    if pm.read_ulonglong(logic) != PAUSE_LOGIC_CLASS:
        return None
    count = _int(reader, logic + 0x32C)
    rows = []
    for i in range(count):
        item = _int(reader, logic + 0x334 + 4 * i)
        if item in PAUSE_ITEMS:
            label, help_key = PAUSE_ITEMS[item]
            rows.append(Row(msg.get(label), None, msg.get(help_key) if help_key else None))
        else:
            print(f"UNKNOWN PAUSE ITEM {item}")
            rows.append(Row(f"Option {item}"))
    return View(msg.get("PAUSE_MENU"), _int(reader, logic + 0x328), rows)


# ---- Versus Menu (from the pause menu) ----
#   +0x328 cursor, +0x32C count, +0x330 + 4*row option id,
#   +0x370 + 4*id current value (+0x350 holds the values from before the
#   menu was opened)
VERSUS_OPTIONS = {
    0: ("VS_PLAYER", "HELP_VS_PLAYER", None),
    1: ("LOBBY_ROUND", "HELP_LOBBY_ROUND", "LOBBY_ROUND_{:02d}"),
    2: ("LOBBY_SPMOVE", "HELP_LOBBY_SPMOVE", "LOBBY_SPMOVE_{:02d}"),
    3: ("MENU_OP_DEFAULT", "HELP_OP_DEFAULT", None),
}
OPPONENT_VALUES = {0: "DUMMY_ACTION_05", 1: "DUMMY_ACTION_06"}  # "Human", "CPU"


def versus_menu(reader, obj):
    msg = reader.msg
    count = _int(reader, obj + 0x32C)
    rows = []
    for i in range(count):
        oid = _int(reader, obj + 0x330 + 4 * i)
        label, help_key, values = VERSUS_OPTIONS.get(oid, (None, None, None))
        value = _int(reader, obj + 0x370 + 4 * oid)
        if oid == 0:
            text = msg.get(OPPONENT_VALUES[value]) if value in OPPONENT_VALUES else f"value {value}"
        elif values:
            text = msg.get(values.format(value), f"value {value}")
        else:
            text = None
        rows.append(Row(msg.get(label, f"Option {oid}") if label else f"Option {oid}", text,
                        msg.get(help_key) if help_key else None))
    return View(msg.get("VERSUS_MENU"), _int(reader, obj + 0x328), rows)


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
    0x14052E5C8: keyboard_settings,
    0x14052A9B0: pause_menu,
    0x140531700: versus_menu,
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

    def open_layers(self):
        """(object, class) of each open layer, topmost first.

        The list of slots ends at the first empty one. (The number at +0xE0
        matched the menus but not in-game, so we don't rely on it.)
        """
        pm = self.game.pm
        try:
            mgr = pm.read_ulonglong(self.game.base + MANAGER)
        except Exception:
            return []
        layers = []
        for i in range(MAX_LAYERS):
            try:
                obj = pm.read_ulonglong(mgr + LAYER_BASE + LAYER_STRIDE * i)
            except Exception:
                break
            if obj == 0:
                break
            try:
                cls = pm.read_ulonglong(obj)
            except Exception:
                continue
            if EXE_START <= cls < EXE_END and cls not in IGNORED_CLASSES:
                layers.append((obj, cls))
        layers.reverse()
        return layers

    def top_view(self):
        """The topmost layer we can read as a menu, as ((object, class), View).

        Some open layers are invisible helpers with no menu in them; reading
        them fails, so we skip down to the next layer.
        """
        layers = self.open_layers()
        if not layers:
            return None, None
        layer = layers[0]
        try:
            view = self.view(*layer)
        except Exception:
            view = None
        if view is None:
            # Something we can't read yet. Say so rather than reading the
            # screen underneath it, which would be misleading.
            view = View(f"Unknown screen {layer[1]:#x}", 0, [Row("not readable yet")])
        if not 0 <= view.cursor < len(view.rows):
            return None, None
        return layer, view

    def top_layer(self):
        """(object, class) of the topmost readable layer, or None."""
        return self.top_view()[0]

    def find_layer(self, cls):
        """Object of the open layer with this class anywhere in the stack, or None."""
        pm = self.game.pm
        try:
            mgr = pm.read_ulonglong(self.game.base + MANAGER)
            top = pm.read_int(mgr + LAYER_TOP)
            for i in range(min(top, 31), -1, -1):
                obj = pm.read_ulonglong(mgr + LAYER_BASE + LAYER_STRIDE * i)
                if pm.read_ulonglong(obj) == cls:
                    return obj
        except Exception:
            pass
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
        layer, view = self.top_view()
        if view is None:
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
