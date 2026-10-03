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
    0x14052F6A0,  # pause menu logic object (briefly listed while closing)
    0x1405A5660,  # online helper layer above the leaderboard
    0x14020B8B0,  # in-game helper layer above the pause menu
    # Appear together with the pause menu; probably its parts (to verify).
    0x1405314F0, 0x14052AE58, 0x14052F8E8,
    # Training mode displays (damage/combo counters, hitboxes, input log).
    0x14052C718, 0x14052C4E8, 0x140527968,
}
MAX_LAYERS = 24
EXE_START, EXE_END = 0x140100000, 0x147800000  # vtables live well past the exe header


@dataclass
class Row:
    label: str
    value: Optional[str] = None
    help: Optional[str] = None


HIDDEN = object()  # a resolver's answer for "this layer isn't on screen"


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
#   +0x320  game number (as on Select Game: 5 = Cyberbots)
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
KEY_NAMES = {7: "Right Alt", 13: "Left Arrow", 14: "Up Arrow", 15: "Right Arrow", 16: "Down Arrow"}
KEY_NAMES.update({29 + i: chr(ord("A") + i) for i in range(26)})
KEY_NAMES.update({55 + i: f"F{i + 1}" for i in range(12)})


def key_name(number):
    name = KEY_NAMES.get(number)
    if name is None:
        log_once(f"UNKNOWN KEY NUMBER {number}")
        return f"key {number}"
    return name


def keyboard_settings(reader, obj):
    msg = reader.msg
    count = _int(reader, obj + 0x36C)
    layout = _int(reader, obj + 0x370)
    game = _int(reader, obj + 0x320)  # the pop-up keeps the game number itself
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
TASKS = 0x668EF90  # the game's list of running tasks ("units")
PAUSE_ITEMS = {
    0: ("CONTINUE", "HELP_CONTINUE"),
    1: ("CONTINUE", "HELP_CONTINUE_TR"),       # Resume, in training mode
    3: ("COMMAND_LIST", "HELP_COMMAND_LIST"),
    4: ("PAD_SETTING", None),
    5: ("DISPLAY_SOUND_SETTINGS", None),
    6: ("TRAINING_MENU", "HELP_TRAINING_MENU"),
    7: ("VERSUS_MENU", "HELP_VERSUS_MENU"),
    9: ("CHARA_CHANGE", "HELP_CHARA_CHANGE"),
    10: ("LOAD", "HELP_LOAD"),                 # Load Quick Save (arcade mode)
    11: ("SAVE", "HELP_SAVE"),                 # Quick Save: not seen yet, follows LOAD in the text
    12: ("QUIT", "HELP_QUIT"),
}
_logged = set()  # unknown ids already logged, so the log isn't flooded


def log_once(message):
    if message not in _logged:
        _logged.add(message)
        print(message)


def find_task(reader, cls):
    """A running task object of this class, from the game's task list."""
    pm = reader.game.pm
    tasks = pm.read_ulonglong(reader.game.base + TASKS)
    for off in range(0x100, 0x800, 8):
        try:
            p = pm.read_ulonglong(tasks + off)
            if p and pm.read_ulonglong(p) == cls:
                return p
        except Exception:
            continue
    return None


def pause_menu(reader, obj):
    msg = reader.msg
    pm = reader.game.pm
    # The logic object (cursor, items) lives in the task list. The layer's
    # +0x790 sometimes points to it too, but not always.
    logic = find_task(reader, PAUSE_LOGIC_CLASS)
    if logic is None:
        logic = pm.read_ulonglong(obj + 0x790)
        if pm.read_ulonglong(logic) != PAUSE_LOGIC_CLASS:
            return None
    # The pause menu isn't destroyed when it closes, only put to sleep: its
    # logic object's status (+0x8) is 2 while open and 256 while hidden.
    if _int(reader, logic + 0x8) & 0x100:
        return HIDDEN
    count = _int(reader, logic + 0x32C)
    items = [_int(reader, logic + 0x334 + 4 * i) for i in range(count)]
    training = 1 in items  # the training-mode Resume
    rows = []
    for item in items:
        if item in PAUSE_ITEMS:
            label, help_key = PAUSE_ITEMS[item]
            if item == 12 and training:
                help_key = "HELP_QUIT_TR"
            rows.append(Row(msg.get(label), None, msg.get(help_key) if help_key else None))
        else:
            log_once(f"UNKNOWN PAUSE ITEM {item}")
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


# ---- Display & Sound Settings (from the pause menu) ----
#   +0x320 cursor, +0x324 count; per row: +0x348 label message,
#   +0x368 description message, +0x388 value
WALLPAPER, SCREEN_FILTER, SCREEN_SIZE, SCREEN_ROTATE = 576, 581, 584, 590
MUSIC_VOLUME, SE_VOLUME = 593, 594


def _display_value(msg, label, value):
    if label in (WALLPAPER, SCREEN_SIZE, SCREEN_ROTATE):
        return msg.by_index(label + 1 + value)
    if label == SCREEN_FILTER:
        # The game shows "None", or "Type" plus a letter: 1 = Type A.
        return msg.by_index(582) if value == 0 else f"{msg.by_index(583)} {chr(64 + value)}"
    if label in (MUSIC_VOLUME, SE_VOLUME):
        return f"{value} of 10"
    return None


def display_sound(reader, obj):
    msg = reader.msg
    count = _int(reader, obj + 0x324)
    rows = []
    for i in range(count):
        label = _int(reader, obj + 0x348 + 4 * i)
        rows.append(Row(msg.by_index(label, "?"),
                        _display_value(msg, label, _int(reader, obj + 0x388 + 4 * i)),
                        msg.by_index(_int(reader, obj + 0x368 + 4 * i))))
    return View(msg.get("DISPLAY_SOUND_SETTINGS"), _int(reader, obj + 0x320), rows)


# ---- Select Mode pop-up (Enter on Select Game) ----
#   +0x320 game number, +0x328 position in the mode list, +0x32C number of
#   modes, +0x330 + 4*i mode ids (0 Arcade, 1 Versus, 2 Training, 3 Training
#   (Boss)); text = message MODE_ARCADE + id
MODE_ARCADE = 3059


def select_mode(reader, obj):
    msg = reader.msg
    count = _int(reader, obj + 0x32C)
    pos = _int(reader, obj + 0x328)
    if not 0 < count <= 8 or not 0 <= pos < count:
        return None
    mode = _int(reader, obj + 0x330 + 4 * pos)
    return View(msg.get("MODE_SELECT"), 0,
                [Row("", msg.by_index(MODE_ARCADE + mode, f"Mode {mode}"), msg.get("HELP_MODE_SELECT"))])


# ---- Training Menu (pause menu in a training match) ----
# Four pages (Ctrl switches), each a block of 8 slots (0x20 bytes) per table:
#   +0x328 page, +0x340 + 4*page cursor on each page, +0x350 + 4*page rows
#   +0x5E0 labels, +0x660 first value message, +0x6E0 descriptions
#   +0x3E0 current values (+0x4E0 is a copy from when the menu opened)
NET_SIMULATION = 813  # "Network Delay"
TRAINING_PAGES = ["DUMMY_OPTION", "DUMMY_SETTING", "PLAYER_SETTING", "TRAINING_OPTION"]


def training_menu(reader, obj):
    msg = reader.msg
    page = _int(reader, obj + 0x328)
    if not 0 <= page < len(TRAINING_PAGES):
        return None
    count = _int(reader, obj + 0x350 + 4 * page)
    rows = []
    for i in range(count):
        slot = 0x20 * page + 4 * i
        label = _int(reader, obj + 0x5E0 + slot)
        first = _int(reader, obj + 0x660 + slot)
        value = _int(reader, obj + 0x3E0 + slot)
        if label == NET_SIMULATION:
            text = f"{value} of 10"  # drawn as a 10-segment bar
        elif first > 0 and label != MENU_OP_DEFAULT:
            text = msg.by_index(first + value)
        else:
            text = None
        rows.append(Row(msg.by_index(label, "?"), text, msg.by_index(_int(reader, obj + 0x6E0 + slot))))
    return View(msg.get(TRAINING_PAGES[page]), _int(reader, obj + 0x340 + 4 * page), rows)


# ---- Options > Music ----
# A fixed list (the labels aren't stored in the object):
#   +0x320 cursor, +0x324 count, +0x348 + 4*row value (volumes 1..10,
#   jingle 0 = Original, 1 = Remix); +0x328 holds the values from opening.
OPTIONS_MUSIC_ROWS = [
    ("MENU_OP_BGM_VOLUME", "HELP_OP_BGM_VOL", "volume"),
    ("MENU_OP_SE_VOLUME", "HELP_OP_SE_VOL", "volume"),
    ("MENU_OP_VOICE_VOLUME", "HELP_OP_VOICE_VOL", "volume"),
    ("MENU_OP_GAME_VOLUME", "HELP_OP_GAME_VOL", "volume"),
    ("MENU_OP_HERE_SE", "HELP_OP_HERE_SE", "MENU_OP_HERE_SE_{:02d}"),
    ("MENU_OP_DEFAULT", "HELP_OP_DEFAULT", None),
]


def options_music(reader, obj):
    msg = reader.msg
    count = _int(reader, obj + 0x324)
    if count != len(OPTIONS_MUSIC_ROWS):
        return None
    rows = []
    for i, (label, help_key, kind) in enumerate(OPTIONS_MUSIC_ROWS):
        value = _int(reader, obj + 0x348 + 4 * i)
        if kind == "volume":
            text = f"{value} of 10"
        elif kind:
            text = msg.get(kind.format(value), f"value {value}")
        else:
            text = None
        rows.append(Row(msg.get(label), text, msg.get(help_key)))
    return View(msg.get("MENU_OP_SOUND"), _int(reader, obj + 0x320), rows)


# ---- Options > System ----
# A fixed list: +0x320 cursor, +0x324 count, +0x328 + 4*row value.
#   Language: index of the language-name message (1 = "English [en]")
#   Data Collection: 0 Decline, 1 Agree
#   Menu/Start/Coin Button: one of SYSTEM_KEYS (the key pictures on screen
#   mark left/right with a dot; we say it in words)
SYSTEM_KEYS = ["F1", "F2", "Left Ctrl", "Right Ctrl", "Left Shift", "Right Shift",
               "Left Alt", "Right Alt"]


def options_system(reader, obj):
    msg = reader.msg
    if _int(reader, obj + 0x324) != 6:
        return None
    v = [_int(reader, obj + 0x328 + 4 * i) for i in range(5)]
    key = lambda n: SYSTEM_KEYS[n] if 0 <= n < len(SYSTEM_KEYS) else f"key {n}"
    rows = [
        Row(msg.get("MENU_OP_LANGUAGE"), msg.by_index(v[0], f"language {v[0]}") if v[0] <= 12 else f"language {v[0]}",
            msg.get("HELP_OP_LANG")),
        Row(msg.get("DATA_UPLOAD"), msg.get(f"DATA_UPLOAD_{v[1]:02d}"), msg.get("HELP_DATA_UPLOAD")),
        Row(msg.get("MENU_OP_MENU_BTN"), key(v[2]), msg.get("HELP_OP_MENU_BTN")),
        Row(msg.get("MENU_OP_START_BTN"), key(v[3]), msg.get("HELP_OP_START_BTN")),
        Row(msg.get("MENU_OP_COIN_BTN"), key(v[4]), msg.get("HELP_OP_COIN_BTN")),
        Row(msg.get("MENU_OP_DEFAULT"), None, msg.get("HELP_OP_DEFAULT")),
    ]
    return View(msg.get("MENU_OP_SYSTEM"), _int(reader, obj + 0x320), rows)


# ---- Options > Network ----
#   +0x324 cursor, +0x328 count, +0x34C + 4*row value, +0x3AC + 4*row label message
# label message -> (description message, how to show the value)
NETWORK_ROWS = {
    207: (210, ("message", 208)),   # Microphone: Off / On
    211: (212, ("bar", None)),      # Voice Chat Volume
    213: (214, ("bar", None)),      # Input Delay
    216: (222, ("message", 217)),   # Connection Strength: Any, 2+, 3+, 4+, 5
    175: (176, None),               # Default
}


def options_network(reader, obj):
    msg = reader.msg
    count = _int(reader, obj + 0x328)
    if not 0 < count <= 10:
        return None
    rows = []
    for i in range(count):
        label = _int(reader, obj + 0x3AC + 4 * i)
        value = _int(reader, obj + 0x34C + 4 * i)
        help_id, kind = NETWORK_ROWS.get(label, (None, None))
        if kind and kind[0] == "message":
            text = msg.by_index(kind[1] + value)
        elif kind and kind[0] == "bar":
            text = f"{value} of 10"
        else:
            text = None
        rows.append(Row(msg.by_index(label, "?"), text, msg.by_index(help_id) if help_id else None))
    return View(msg.get("MENU_OP_NET"), _int(reader, obj + 0x324), rows)


# ---- Fighter Awards (main menu) ----
#   +0x324 page: 0 = Challenges, 1 = Play Stats (Y switches)
#   +0x328 game shown on Play Stats (Ctrl / right Ctrl; same order as Select Game)
#   +0x344 medal cursor, +0x348 number of medals on the page
# Challenge n (from 0) is ACHIEVEMENT_<n+1>_NAME/_DESC; Play Stats medal n
# is STATS_<game>_<n>_NAME/_DESC. Earned/complete status and play counts
# are drawn as pictures and aren't read yet.
STATS_PREFIX = ["VAMP", "VHUNT", "VSAV", "VHUNT2", "VSAV2",
                "CYBOTS", "SPF2X", "PFIGHT", "HSF2", "WARZARD"]


def fighter_awards(reader, obj):
    msg = reader.msg
    count = _int(reader, obj + 0x348)
    if not 0 < count <= 100:
        return None
    cursor = _int(reader, obj + 0x344)
    if _int(reader, obj + 0x324) == 0:
        rows = [Row(msg.get(f"ACHIEVEMENT_{n + 1:02d}_NAME", f"Challenge {n + 1}"), None,
                    msg.get(f"ACHIEVEMENT_{n + 1:02d}_DESC")) for n in range(count)]
        return View(msg.get("AWARD_ACHIEVE"), cursor, rows)
    game = _int(reader, obj + 0x328) % len(GAMES)
    prefix = STATS_PREFIX[game]
    rows = [Row(msg.get(f"STATS_{prefix}_{n:02d}_NAME", f"Medal {n + 1}"), None,
                msg.get(f"STATS_{prefix}_{n:02d}_DESC")) for n in range(count)]
    # The game name is part of the title, so changing game announces it.
    return View(f"{msg.get('AWARD_PLAY')}: {GAMES[game][-1][0]}", cursor, rows)


# ---- Fighter Awards > Stats (X on Play Stats) ----
# A fixed table, no cursor: five kinds of play (AWARD_OFFLINE_PLAY ..
# AWARD_CUSTOM_PLAY), each counted for the Japanese and English versions.
# The counts haven't been located yet (they were all 0 when researched),
# so for now the mod reads the row names and says the counts aren't read.
def award_stats(reader, obj):
    msg = reader.msg
    names = ", ".join(msg.by_index(i) for i in range(2090, 2095))
    summary = f"{names}. Counts for the Japanese and English versions are not read yet."
    return View(msg.get("AWARD_STATS"), 0, [Row(summary)])


# ---- Options > PC Settings ----
#   +0x320 cursor, +0x324 count, +0x328 resolution index, +0x32C display
#   mode (225 + n: Windowed, Borderless Windowed, Fullscreen), +0x330 VSync
#   (0 Off, 1 On), +0x348 number of resolutions, +0x3C8 + 8*n pointer to
#   resolution n, whose record starts with its name ("1280x720").
def _c_string(reader, addr, limit=32):
    raw = reader.game.pm.read_bytes(addr, limit)
    return raw.split(b"\0", 1)[0].decode("ascii", "replace")


def pc_settings(reader, obj):
    msg = reader.msg
    pm = reader.game.pm
    res, disp, vsync = (_int(reader, obj + o) for o in (0x328, 0x32C, 0x330))
    n_res = _int(reader, obj + 0x348)
    res_text = f"resolution {res + 1}"
    if 0 <= res < n_res <= 64:
        res_text = _c_string(reader, pm.read_ulonglong(obj + 0x3C8 + 8 * res)) or res_text
    rows = [
        Row(msg.get("MENU_OP_PC_RESO"), res_text, msg.get("HELP_OP_PC_RESO")),
        Row(msg.get("MENU_OP_PC_DISP"), msg.by_index(225 + disp, f"mode {disp}"), msg.get("HELP_OP_PC_DISP")),
        Row(msg.get("MENU_OP_PC_VSYNC"), msg.get("MENU_OP_ENABLE" if vsync else "MENU_OP_DISABLE"),
            msg.get("HELP_OP_PC_VSYNC")),
        Row(msg.get("MENU_OP_DEFAULT"), None, msg.get("HELP_OP_DEFAULT")),
    ]
    return View(msg.get("MENU_OP_PC"), _int(reader, obj + 0x320), rows)


# ---- Options > Credits ----
# The credits scroll by as pictures (credit.arc textures); there is no text
# to read, so we just say what the screen is. Reading them would need OCR.
def credits(reader, obj):
    msg = reader.msg
    return View(msg.get("MENU_OP_CREDITS"), 0,
                [Row("The credits are scrolling. They are pictures, so CFC Access can't read them yet. "
                     "Press Backspace to go back.")])


# ---- Museum > Gallery (choose a collection of artwork) ----
#   +0x32C selected entry, +0x330 count (11): 0 = the collection itself,
#   then the ten games in Select Game order. Left/Right change it.
def gallery_select(reader, obj):
    msg = reader.msg
    sel, count = _int(reader, obj + 0x32C), _int(reader, obj + 0x330)
    if not 0 <= sel < count <= 16:
        return None
    name = msg.get("GAME_NAME_E") if sel == 0 else GAMES[(sel - 1) % len(GAMES)][-1][0]
    return View(msg.get("GALLERY"), 0, [Row("", f"{name}, {sel + 1} of {count}", msg.get("HELP_GALLERY"))])


# ---- Museum > Music (choose a soundtrack) ----
# Same layout as the gallery picker (+0x32C selected, +0x330 count = 9), but
# Vampire Hunter 2 and Vampire Savior 2 have no soundtrack entry.
MUSIC_ALBUMS = [None, 0, 1, 2, 5, 6, 7, 8, 9]  # None = the collection; else GAMES index


def music_select(reader, obj):
    msg = reader.msg
    sel, count = _int(reader, obj + 0x32C), _int(reader, obj + 0x330)
    if not 0 <= sel < count <= 16:
        return None
    album = MUSIC_ALBUMS[sel] if sel < len(MUSIC_ALBUMS) else None
    name = msg.get("GAME_NAME_E") if album is None else GAMES[album][-1][0]
    return View(msg.get("SOUND"), 0, [Row("", f"{name}, {sel + 1} of {count}", msg.get("HELP_SOUND"))])


# ---- Museum > Music > track list ----
#   +0x32C first track shown in the scrolling window, +0x330 row within the
#   window (selected track = both added), +0x334 number of tracks.
# Track n is SOUND_<prefix>_<nn>, already numbered ("01. Opening Title").
# Track lengths and the play/pause state are drawn but not read yet.
MUSIC_SELECT_CLASS = 0x14052DD48
MUSIC_TRACKS = [23, 44, 65, 74, 51, 23, 33, 58, 66]  # tracks per album, same order
MUSIC_PREFIX = ["JACK", "VAMP", "VHUNT", "VSAV", "CYBOTS", "SPF2X", "PFIGHT", "HSF2", "WARZARD"]


def music_tracks(reader, obj):
    msg = reader.msg
    count = _int(reader, obj + 0x334)
    if not 0 < count <= 200:
        return None
    select = reader.find_layer(MUSIC_SELECT_CLASS)
    album = _int(reader, select + 0x32C) % len(MUSIC_PREFIX) if select else 0
    # The picker underneath can read wrong for a moment during transitions;
    # each soundtrack has its own track count, so check against that.
    if MUSIC_TRACKS[album] != count:
        matches = [i for i, n in enumerate(MUSIC_TRACKS) if n == count]
        if matches:
            album = matches[0]
    prefix = MUSIC_PREFIX[album]
    entry = MUSIC_ALBUMS[album % len(MUSIC_ALBUMS)]
    title = msg.get("GAME_NAME_E") if entry is None else GAMES[entry][-1][0]
    rows = [Row(msg.get(f"SOUND_{prefix}_{n:02d}", f"Track {n + 1}")) for n in range(count)]
    return View(title, _int(reader, obj + 0x32C) + _int(reader, obj + 0x330), rows)


# ---- Museum > Gallery > picture viewer ----
#   +0x320 picture number (from 0), +0x324 number of pictures.
# Ctrl / right Ctrl: previous / next.
# Captions: exe+GALLERY_STARTS holds one pointer per gallery (picker order)
# into a list of u32 caption message numbers, one per picture.
GALLERY_SELECT_CLASS = 0x14052DB10
GALLERY_STARTS = 0x673F30


def gallery_viewer(reader, obj):
    msg = reader.msg
    pic, count = _int(reader, obj + 0x320), _int(reader, obj + 0x324)
    if not 0 <= pic < count <= 2000:
        return None
    title = msg.get("GALLERY")
    caption = ""
    select = reader.find_layer(GALLERY_SELECT_CLASS)
    if select:
        sel = _int(reader, select + 0x32C)
        title += ": " + (msg.get("GAME_NAME_E") if sel == 0 else GAMES[(sel - 1) % len(GAMES)][-1][0])
        pm = reader.game.pm
        if 0 <= sel < 11:
            captions = pm.read_ulonglong(reader.game.base + GALLERY_STARTS + 8 * sel)
            caption = msg.by_index(pm.read_uint(captions + 4 * pic), "")
    value = f"Picture {pic + 1} of {count}" + (f": {caption}" if caption else "")
    return View(title, 0, [Row("", value)])


# ---- Online Play menu ----
ONLINE_MENU_CLASS = 0x14052DF70
#   +0x320 cursor, +0x324 count, +0x328 + 4*row item id
ONLINE_ITEMS = {
    0: ("CASUAL_MATCH", "HELP_CASUAL_MATCH"),
    1: ("RANK_MATCH", "HELP_RANK_MATCH"),
    2: ("CUSTOM_MATCH", "HELP_CUSTOM_MATCH"),
    3: ("RANK_LEADERBOARD", "HELP_RANK_LEADERBOARD"),
    4: ("ONLINE_OPTION", "HELP_ONLINE_OPTION"),
}


def online_menu(reader, obj):
    msg = reader.msg
    count = _int(reader, obj + 0x324)
    if not 0 < count <= 8:
        return None
    rows = []
    for i in range(count):
        item = _int(reader, obj + 0x328 + 4 * i)
        label, help_key = ONLINE_ITEMS.get(item, (None, None))
        rows.append(Row(msg.get(label, f"Option {item}") if label else f"Option {item}", None,
                        msg.get(help_key) if help_key else None))
    return View(msg.get("ONLINE_PLAY"), _int(reader, obj + 0x320), rows)


# ---- Online > Casual / Ranked match setup ----
#   +0x324 row (0 = game grid, 1 Game Version, 2 Cross-region Matchmaking,
#   3 One-button Special Moves), +0x328 row count, +0x330 game in the grid
#   (0-9, 5 per row), +0x334 version (0 Japanese, 1 English, 2 Either),
#   +0x338 cross-region (0 Off, 1 On), +0x33C one-button (0 On, 1 Off).
# Which games are ticked for matchmaking isn't read yet.
def match_setup(reader, obj):
    msg = reader.msg
    if _int(reader, obj + 0x328) != 4:
        return None
    game = _int(reader, obj + 0x330)
    version = _int(reader, obj + 0x334)
    rows = [
        Row(msg.get("GAME_TITLE"), msg.get(f"GAME_NAME_S{game:02d}", f"game {game + 1}"),
            msg.get("HELP_GAME_TITLE_ON")),
        Row(msg.get("GAME_VERSION"), msg.get(["GAME_VERSION_J", "GAME_VERSION_E", "GAME_VERSION_ANY"][version % 3]),
            msg.get("HELP_GAME_VERSION_ON")),
        Row(msg.get("LOBBY_AREA"), msg.get(f"LOBBY_AREA_{_int(reader, obj + 0x338):02d}"), msg.get("HELP_LOBBY_AREA")),
        Row(msg.get("LOBBY_SPMOVE"), msg.get(f"LOBBY_SPMOVE_{_int(reader, obj + 0x33C):02d}"), msg.get("HELP_LOBBY_SPMOVE")),
    ]
    # Casual and Ranked share this screen: name it after the online menu's choice.
    title = msg.get("CASUAL_MATCH")
    online = reader.find_layer(ONLINE_MENU_CLASS)
    if online:
        item = _int(reader, online + 0x328 + 4 * _int(reader, online + 0x320))
        title = msg.get(ONLINE_ITEMS.get(item, ("CASUAL_MATCH",))[0], title)
    return View(title, _int(reader, obj + 0x324), rows)


# ---- Online > Custom Match > Create Lobby ----
#   +0x324 row cursor, +0x32C + 4*row value. Game: 0 = Any, then the ten
#   games in Select Game order. Comment skips "Any" (value 0 = message 01).
LOBBY_ROWS = [  # label, help, message pattern for the value (None = special)
    ("GAME_TITLE", "HELP_GAME_TITLE", None),
    ("GAME_VERSION", "HELP_GAME_VERSION", None),
    ("LOBBY_AREA", "HELP_LOBBY_AREA", "LOBBY_AREA_{:02d}"),
    ("LOBBY_TITLE", "HELP_LOBBY_TITLE", "LOBBY_TITLE_{:02d}+1"),
    ("LOBBY_EVENT", "HELP_LOBBY_EVENT", "LOBBY_EVENT_{:02d}"),
    ("LOBBY_SPMOVE", "HELP_LOBBY_SPMOVE", "LOBBY_SPMOVE_{:02d}"),
    ("LOBBY_ROUND", "HELP_LOBBY_ROUND", "LOBBY_ROUND_{:02d}"),
    ("LOBBY_NUM", "HELP_LOBBY_NUM", "LOBBY_NUM_{:02d}"),
    ("LOBBY_PERM", "HELP_LOBBY_PERM", "LOBBY_PERM_{:02d}"),
    ("LOBBY_PASS", "HELP_LOBBY_PASS", "LOBBY_PASS_{:02d}"),
]


def lobby_settings(title_key, n_rows, searching):
    """Resolver for Create Lobby (searching=False) or Join Lobby (True).

    Join Lobby is a search filter: "Any" comment and "Either" version are
    real choices there, while Create Lobby's comment list skips "Any".
    """
    def resolve(reader, obj):
        msg = reader.msg
        values = [_int(reader, obj + 0x32C + 4 * i) for i in range(n_rows)]
        game = values[0]
        rows = []
        for i, (label, help_key, pattern) in enumerate(LOBBY_ROWS[:n_rows]):
            v = values[i]
            if i == 0:
                text = msg.get("GAME_NAME_ANY") if game == 0 else msg.get(f"GAME_NAME_S{game - 1:02d}")
            elif i == 1:
                if game == 0 or (searching and v == 2):
                    text = msg.get("GAME_VERSION_ANY")
                else:
                    versions = GAMES[(game - 1) % len(GAMES)]
                    _, region, rom = versions[0] if len(versions) == 1 else versions[v % len(versions)]
                    text = f"{msg.get('GAME_VERSION_J' if region == 'J' else 'GAME_VERSION_E')} {rom}"
            elif pattern.endswith("+1"):
                text = msg.get(pattern[:-2].format(v if searching else v + 1), f"value {v}")
            else:
                text = msg.get(pattern.format(v), f"value {v}")
            rows.append(Row(msg.get(label), text, msg.get(help_key)))
        return View(msg.get(title_key), _int(reader, obj + 0x324), rows)
    return resolve


# ---- Online > Custom Match > Search Lobby ID ----
# Six characters, each 0-9 then A-Z (36 values): +0x324 + 4*i, and +0x340
# the selected position. Left/Right move, Up/Down change the character.
ID_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def lobby_id(reader, obj):
    msg = reader.msg
    chars = [ID_CHARS[_int(reader, obj + 0x324 + 4 * i) % 36] for i in range(6)]
    pos = _int(reader, obj + 0x340)
    if not 0 <= pos < 6:
        return None
    lobby = " ".join(chars)  # spaced so screen readers spell it out
    rows = [Row(f"Character {i + 1}", c, f"ID: {lobby}. {msg.get('HELP_INPUT_LOBBY_ID')}")
            for i, c in enumerate(chars)]
    return View(msg.get("INPUT_LOBBY_ID"), pos, rows)


# ---- Online > Ranked Leaderboard > Select Game ----
#   +0x320 game (Select Game order), +0x324 count
def leaderboard_game(reader, obj):
    msg = reader.msg
    game, count = _int(reader, obj + 0x320), _int(reader, obj + 0x324)
    if not 0 <= game < count <= 16:
        return None
    return View(msg.get("GAME_SELECT"), 0,
                [Row("", f"{GAMES[game % len(GAMES)][-1][0]}, {game + 1} of {count}", msg.get("HELP_RANKING_SELECT"))])


# ---- Online > Ranked Leaderboard ----
#   +0x320 game (Select Game order); Ctrl / right Ctrl change it.
#   +0x344 how far the list is scrolled, +0x348 highlighted row on screen;
#   highlighted entry = both added.
# The downloaded entries: [exe+0x79F718]+0x240 points to a block whose
# entries start at +0x58, every 0x1D8 bytes: name (UTF-8) at +0xE0,
# League Points at +0x148. Your own row at the bottom isn't read yet.
LEADERBOARD_BLOCK = (0x79F718, 0x240)
# The league badge isn't stored: it follows from League Points. The game's
# 20 minimum scores are at exe+LEAGUE_MINIMUMS; the names match the badge
# pictures (checked on screen for Rookie, Super/Ultra Gold, Platinum, Ultra
# Platinum, Diamond, Ultimate Grand Master and Warlord; the rest follow the
# same pattern).
LEAGUE_MINIMUMS = 0x669FB0
LEAGUES = ["Rookie", "Bronze", "Super Bronze", "Ultra Bronze", "Silver", "Super Silver",
           "Ultra Silver", "Gold", "Super Gold", "Ultra Gold", "Platinum", "Super Platinum",
           "Ultra Platinum", "Diamond", "Super Diamond", "Ultra Diamond", "Master",
           "Grand Master", "Ultimate Grand Master", "Warlord"]
# Your own record (the row pinned at the bottom): name at +0xE0. Points are
# assumed at +0x148 like the other entries (unverified: they were 0).
OWN_RECORD = (0x668F140, 0x38, 0x230)


def league(reader, points):
    pm = reader.game.pm
    name = LEAGUES[0]
    for i, minimum in enumerate(LEAGUES):
        if points >= pm.read_uint(reader.game.base + LEAGUE_MINIMUMS + 4 * i):
            name = LEAGUES[i]
    return name


def own_entry(reader):
    pm = reader.game.pm
    try:
        p = pm.read_ulonglong(reader.game.base + OWN_RECORD[0])
        for off in OWN_RECORD[1:-1]:
            p = pm.read_ulonglong(p + off)
        rec = p + OWN_RECORD[-1]  # the record sits inside that object
        name = pm.read_bytes(rec + LB_NAME, 64).split(bytes([0]), 1)[0].decode("utf-8", "replace")
        points = pm.read_int(rec + LB_POINTS)
    except Exception:
        return ""
    return f"You: {name}, {league(reader, points)}, {points} League Points" if name else ""
LB_FIRST, LB_STRIDE, LB_NAME, LB_POINTS = 0x58, 0x1D8, 0xE0, 0x148


def leaderboard(reader, obj):
    msg = reader.msg
    pm = reader.game.pm
    game = _int(reader, obj + 0x320)
    if not 0 <= game < len(GAMES):
        return None
    title = f"{msg.get('RANK_LEADERBOARD')}: {GAMES[game][-1][0]}"
    index = _int(reader, obj + 0x344) + _int(reader, obj + 0x348)
    try:
        block = pm.read_ulonglong(pm.read_ulonglong(reader.game.base + LEADERBOARD_BLOCK[0]) + LEADERBOARD_BLOCK[1])
        entry = block + LB_FIRST + LB_STRIDE * index
        name = pm.read_bytes(entry + LB_NAME, 64).split(b"\0", 1)[0].decode("utf-8", "replace")
        points = pm.read_int(entry + LB_POINTS)
    except Exception:
        name = ""
    if not name:
        return View(title, 0, [Row("No entries.")])
    # A single row whose value changes, so moving speaks the new entry.
    return View(title, 0, [Row("", f"Rank {index + 1}: {name}, {league(reader, points)}, {points} League Points",
                               own_entry(reader))])


# ---- Pause > Move List ----
#   +0x320 game (Select Game order), +0x338 page, +0x344 + 4*row record
#   number in that game's move table, +0x3C8 rows on the page, +0x3C4 scroll.
# There is no row highlight (Up/Down scroll), and a page mostly fits on
# screen, so the whole page is read as one announcement when it opens.
BASIC_MOVES_CHARACTER = 127
# Cyberbots' move tables are per robot, in the order of the robot name list
# in the exe (Blodia, Reptos, Fordy, Guldin, Swordsman ...; checked against
# each robot's first special move). Each maps to its STATS_CYBOTS roster
# entry, so the name comes from the (translatable) text file.
CYBOTS_ROBOT_ROSTER = [6, 9, 12, 15, 7, 11, 10, 16, 17, 8, 13, 20, 18, 19, 21, 14]


def move_list(reader, obj):
    from .movelist import MoveLists
    msg = reader.msg
    if getattr(reader, "moves", None) is None:
        reader.moves = MoveLists(reader.game, msg)
    game = _int(reader, obj + 0x320)
    count = _int(reader, obj + 0x3C8)
    if not 0 <= game < len(GAMES) or not 0 < count <= 64:
        return None
    records = [_int(reader, obj + 0x344 + 4 * i) for i in range(count)]
    character = reader.moves.record_character(game, records[0])
    if character == BASIC_MOVES_CHARACTER:
        title = msg.get("BASIC_MOVES")
    else:
        # The move tables number characters like the Fighter Awards roster
        # (checked: Hyper Street Fighter II, 0 = Ryu); Cyberbots uses robots.
        name = None
        if STATS_PREFIX[game] == "CYBOTS":
            if character < len(CYBOTS_ROBOT_ROSTER):
                name = msg.get(f"STATS_CYBOTS_{CYBOTS_ROBOT_ROSTER[character]:02d}_NAME")
        else:
            name = msg.get(f"STATS_{STATS_PREFIX[game]}_{character:02d}_NAME")
        title = f"{name}: {msg.get('PLAYER_MOVES')}" if name else msg.get("PLAYER_MOVES")
    lines = [reader.moves.record_text(game, r) for r in records]
    page = ". ".join(l.rstrip(".") for l in lines if l) + "."
    return View(f"{title}, page {_int(reader, obj + 0x338) + 1}", 0, [Row(page)])


# ---- Yes/No dialogs ("Exit the game?") ----
#   +0x360 question message, +0x324 button count, +0x32C + 4*i button
#   messages (36 = "Yes", 37 = "No"), +0x37C cursor (0 = first button)
def dialog(reader, obj):
    msg = reader.msg
    count = _int(reader, obj + 0x324)
    if not 0 < count <= 4:
        return None
    rows = [Row(msg.by_index(_int(reader, obj + 0x32C + 4 * i), "?")) for i in range(count)]
    return View(msg.by_index(_int(reader, obj + 0x360), ""), _int(reader, obj + 0x37C), rows)


# Screen class (vtable address) -> resolver. A resolver returns HIDDEN for a
# layer that exists but isn't on screen, so the layer below is read instead. Message keys come from msg.arc's
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
    0x140528D90: dialog,
    0x14052E1A8: display_sound,
    0x140530A38: select_mode,
    0x14052F490: training_menu,
    0x14052F070: options_music,
    0x14052F280: options_system,
    0x14052E800: options_network,
    0x140527BC0: fighter_awards,
    0x140528070: award_stats,
    0x14052EC50: pc_settings,
    0x1405297F8: credits,
    0x14052DB10: gallery_select,
    0x14052A090: gallery_viewer,
    0x14052DD48: music_select,
    0x140530C48: music_tracks,
    0x14052DF70: online_menu,
    0x14052D4B0: match_setup,
    0x1405293D0: lobby_settings("CREATE_LOBBY", 10, searching=False),
    0x14052BEB8: lobby_settings("JOIN_LOBBY", 6, searching=True),
    0x14052B580: lobby_id,
    0x14052FF70: leaderboard_game,
    0x140530180: leaderboard,
    0x1405290E8: move_list,
    0x14052FB10: lambda reader, obj: View("", 0, [Row(reader.msg.get("POP_GET_RANKING"))]),
    0x140529A28: fixed_list("CUSTOM_MATCH", [
        ("CREATE_LOBBY", "HELP_CREATE_LOBBY"),
        ("JOIN_LOBBY", "HELP_JOIN_LOBBY"),
        ("SEARCH_LOBBY_ID", "HELP_SEARCH_LOBBY_ID"),
    ]),
    0x14052A2D0: None,  # drawing helper of the picture viewer
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
        self.pending = None     # a new screen seen once, waiting to be confirmed

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
            if not EXE_START <= cls < EXE_END or cls in IGNORED_CLASSES:
                continue
            # Status +0x8: the 0x100 bit means asleep (closing or hidden).
            try:
                if pm.read_int(obj + 0x8) & 0x100:
                    continue
            except Exception:
                continue
            layers.append((obj, cls))
        layers.reverse()
        return layers

    def top_view(self):
        """The topmost layer we can read as a menu, as ((object, class), View).

        Some open layers are invisible helpers with no menu in them; reading
        them fails, so we skip down to the next layer.
        """
        layers = self.open_layers()
        view = None
        for layer in layers:
            try:
                view = self.view(*layer)
            except Exception:
                view = None
            if view is not HIDDEN:
                break
        else:
            return None, None
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
        for obj, c in self.open_layers():
            if c == cls:
                return obj
        return None

    def view(self, obj, cls):
        if cls in SCREENS:
            resolve = SCREENS[cls]
            return resolve(self, obj) if resolve else HIDDEN
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
        if old is None or old_layer != layer or old.title != view.title:
            # A different screen (or page). During transitions screens can
            # flash by for a frame or two, so only announce one that is
            # still there on the next check.
            key = (layer, view.title)
            if self.pending != key:
                self.pending = key
                return
            self.pending = None
            self.last_view, self.last_layer = view, layer
            if view.title.startswith("Unknown screen"):
                log_once(f"UNKNOWN SCREEN {view.title}")
            speech.say(self.describe(view, with_title=True))
            return
        self.pending = None
        self.last_view, self.last_layer = view, layer
        if old.cursor != view.cursor:
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
            title = view.title
            parts.append(title if title[-1] in ".?!:" else title + ".")
        row = view.rows[view.cursor]
        if row.label and row.value:
            label = f"{row.label}: {row.value}"
        else:
            label = row.label or row.value or ""
        if len(view.rows) > 1:
            parts.append(f"{label}, {view.cursor + 1} of {len(view.rows)}.")
        else:
            parts.append(label if label[-1:] in ".?!" else f"{label}.")
        if row.help:
            parts.append(row.help)
        return " ".join(parts)
