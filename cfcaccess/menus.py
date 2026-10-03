"""Speaking the collection's own menus (main menu, options, select game...).

How we find the menu in memory (worked out with tools/scan.py and
tools/ptrscan.py):
  - A fixed spot in the exe leads, through one or two pointers, to the
    object for whichever menu screen is open ("the current screen").
  - The object's first 8 bytes are its C++ class's vtable address; every
    screen type has its own class, so this identifies the screen.
  - +0x320 holds the cursor (0 = first item) and +0x324 the item count.
  - Screens with values (e.g. Select Game) keep them at further offsets.
"""
from dataclasses import dataclass, field
from typing import Callable, Optional

from . import speech

CURSOR_OFFSET = 0x320
COUNT_OFFSET = 0x324

# Routes to the current screen object: (offset into the exe, pointer offsets).
# Several are kept in case one breaks; the first that makes sense is used.
ROUTES = [
    (0x668E670, [0xF8]),
    (0x668DBB0, [0x4D8]),
    (0x668EF90, [0x5E8]),
    (0x65E5200, [0x88, 0x88]),
]


@dataclass
class Item:
    name: str                    # message key for the item's label
    help: Optional[str] = None   # message key for the description bar
    # Reads the item's current value: value(reader, screen_object) -> text.
    value: Optional[Callable] = None


@dataclass
class Screen:
    title: str                   # message key for the screen's title
    items: list = field(default_factory=list)


def _int(reader, obj, offset):
    return reader.game.pm.read_int(obj + offset)


# ---- Select Game (Offline Play) ----
# Per game: one (title, ROM) pair per version. The game shows the version
# label as "Japanese Version (Japan 940705)": the first word comes from the
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
SEL_GAME, SEL_VERSION, SEL_PLAYER = 0x328, 0x32C, 0x330


def _selected_version(reader, obj):
    versions = GAMES[_int(reader, obj, SEL_GAME) % len(GAMES)]
    if len(versions) == 1:
        return versions[0]  # its version number stays at 1 but shows Japanese
    return versions[_int(reader, obj, SEL_VERSION) % len(versions)]


def select_game_title(reader, obj):
    return _selected_version(reader, obj)[0]


def select_game_version(reader, obj):
    _, region, rom = _selected_version(reader, obj)
    word = reader.msg.get("GAME_VERSION_J" if region == "J" else "GAME_VERSION_E")
    return f"{word} {rom}"


def select_game_player(reader, obj):
    return reader.msg.get("PLAYER_1P" if _int(reader, obj, SEL_PLAYER) == 0 else "PLAYER_2P")


# Screen class (vtable address) -> what's on it. Message keys come from
# msg.arc's menu_eng (python -m cfcaccess.gmd <file> to browse them).
SCREENS = {
    0x14052D278: Screen("MAIN_MENU", [
        Item("OFFLINE_PLAY", "HELP_OFFLINE_PLAY"),
        Item("ONLINE_PLAY", "HELP_ONLINE_PLAY"),
        Item("MUSEUM", "HELP_MUSEUM"),
        Item("FIGHTER_AWARD", "HELP_FIGHTER_AWARD"),
        Item("OPTIONS", "HELP_OPTION"),
        Item("EXIT", "HELP_EXIT"),
    ]),
    0x14052EE60: Screen("OPTIONS", [
        Item("MENU_OP_SYSTEM", "HELP_OP_SYSTEM"),
        Item("MENU_OP_SOUND", "HELP_OP_SOUND"),
        Item("MENU_OP_NET", "HELP_OP_NETWORK"),
        Item("MENU_OP_PC", "HELP_OP_PC"),
        Item("MENU_OP_CREDITS", "HELP_OP_CREDIT"),
    ]),
    0x14052D8F8: Screen("MUSEUM", [
        Item("GALLERY", "HELP_GALLERY"),
        Item("SOUND", "HELP_SOUND"),
    ]),
    0x140530800: Screen("GAME_SELECT", [
        Item("GAME_TITLE", "HELP_GAME_TITLE", select_game_title),
        Item("GAME_VERSION", "HELP_GAME_VERSION", select_game_version),
        Item("PLAYER", "HELP_PLAYER", select_game_player),
    ]),
}


class MenuReader:
    def __init__(self, game, messages):
        self.game = game
        self.msg = messages
        self.last = None    # (screen object, class, cursor, count) last spoken
        self.values = None  # every item's value text, last time we looked

    def _screen_object(self):
        """Address of the current screen object, or None."""
        pm = self.game.pm
        for exe_offset, offsets in ROUTES:
            try:
                p = pm.read_ulonglong(self.game.base + exe_offset)
                for off in offsets:
                    p = pm.read_ulonglong(p + off)
                count = pm.read_int(p + COUNT_OFFSET)
                cursor = pm.read_int(p + CURSOR_OFFSET)
            except Exception:
                continue
            if 0 < count <= 100 and 0 <= cursor < count:
                return p
        return None

    def _values(self, screen, obj):
        out = []
        for item in screen.items:
            try:
                out.append(item.value(self, obj) if item.value else None)
            except Exception:
                out.append(None)
        return out

    def poll(self):
        """Check the menu once; speak if the screen, cursor or a value changed."""
        obj = self._screen_object()
        if obj is None:
            self.last = self.values = None
            return
        pm = self.game.pm
        try:
            cls = pm.read_ulonglong(obj)
            cursor = pm.read_int(obj + CURSOR_OFFSET)
            count = pm.read_int(obj + COUNT_OFFSET)
        except Exception:
            return
        screen = SCREENS.get(cls)
        values = self._values(screen, obj) if screen else None
        state = (obj, cls, cursor, count)
        if state == self.last:
            if values != self.values and values is not None and self.values is not None:
                self._speak_changed_values(screen, cursor, values)
            self.values = values
            return
        new_screen = self.last is None or self.last[:2] != (obj, cls)
        self.last, self.values = state, values
        speech.say(self.describe(cls, cursor, count, new_screen, values))

    def _speak_changed_values(self, screen, cursor, values):
        """A value changed without the cursor moving (Left/Right): say the
        current row's new value first, then any other rows it changed."""
        order = [cursor] + [i for i in range(len(values)) if i != cursor]
        changed = [values[i] for i in order
                   if i < len(self.values) and values[i] != self.values[i] and values[i]]
        if changed:
            speech.say(". ".join(changed))

    def describe(self, cls, cursor, count, with_title, values=None):
        screen = SCREENS.get(cls)
        parts = []
        if screen is None:
            # Not mapped yet: still give position, and log the class so it
            # can be added to SCREENS.
            print(f"UNKNOWN SCREEN class={cls:#x} count={count}")
            if with_title:
                parts.append("Unknown screen.")
            parts.append(f"Item {cursor + 1} of {count}.")
            return " ".join(parts)
        if with_title:
            parts.append(self.msg.get(screen.title, "") + ".")
        if cursor < len(screen.items):
            item = screen.items[cursor]
            label = self.msg.get(item.name, item.name)
            value = values[cursor] if values else None
            if value:
                label = f"{label}: {value}"
            parts.append(f"{label}, {cursor + 1} of {count}.")
            if item.help:
                parts.append(self.msg.get(item.help, ""))
        else:
            parts.append(f"Item {cursor + 1} of {count}.")
        return " ".join(p for p in parts if p)
