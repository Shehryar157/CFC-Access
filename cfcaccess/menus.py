"""Speaking the collection's own list menus (main menu, options, museum...).

How we find the menu in memory (worked out with tools/scan.py and
tools/ptrscan.py):
  - A fixed spot in the exe leads, through one or two pointers, to the
    object for whichever list screen is open ("the current screen").
  - The object's first 8 bytes are its C++ class's vtable address; every
    screen type has its own class, so this identifies the screen.
  - +0x320 holds the cursor (0 = first item) and +0x324 the item count.
"""
from dataclasses import dataclass, field

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
class Screen:
    title: str  # message key for the screen's title
    items: list = field(default_factory=list)  # (name key, description key) per item


# Screen class (vtable address) -> what's on it. Message keys come from
# msg.arc's menu_eng (python -m cfcaccess.gmd <file> to browse them).
SCREENS = {
    0x14052D278: Screen("MAIN_MENU", [
        ("OFFLINE_PLAY", "HELP_OFFLINE_PLAY"),
        ("ONLINE_PLAY", "HELP_ONLINE_PLAY"),
        ("MUSEUM", "HELP_MUSEUM"),
        ("FIGHTER_AWARD", "HELP_FIGHTER_AWARD"),
        ("OPTIONS", "HELP_OPTION"),
        ("EXIT", "HELP_EXIT"),
    ]),
    0x14052EE60: Screen("OPTIONS", [
        ("MENU_OP_SYSTEM", "HELP_OP_SYSTEM"),
        ("MENU_OP_SOUND", "HELP_OP_SOUND"),
        ("MENU_OP_NET", "HELP_OP_NETWORK"),
        ("MENU_OP_PC", "HELP_OP_PC"),
        ("MENU_OP_CREDITS", "HELP_OP_CREDIT"),
    ]),
    0x14052D8F8: Screen("MUSEUM", [
        ("GALLERY", "HELP_GALLERY"),
        ("SOUND", "HELP_SOUND"),
    ]),
}


class MenuReader:
    def __init__(self, game, messages):
        self.game = game
        self.msg = messages
        self.last = None  # (screen object, class, cursor, count) last spoken

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

    def poll(self):
        """Check the menu once; speak if the screen or cursor changed."""
        obj = self._screen_object()
        if obj is None:
            self.last = None
            return
        pm = self.game.pm
        try:
            cls = pm.read_ulonglong(obj)
            cursor = pm.read_int(obj + CURSOR_OFFSET)
            count = pm.read_int(obj + COUNT_OFFSET)
        except Exception:
            return
        state = (obj, cls, cursor, count)
        if state == self.last:
            return
        new_screen = self.last is None or self.last[:2] != (obj, cls)
        self.last = state
        speech.say(self.describe(cls, cursor, count, new_screen))

    def describe(self, cls, cursor, count, with_title):
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
            name_key, help_key = screen.items[cursor]
            parts.append(f"{self.msg.get(name_key, name_key)}, {cursor + 1} of {count}.")
            if help_key:
                parts.append(self.msg.get(help_key, ""))
        else:
            parts.append(f"Item {cursor + 1} of {count}.")
        return " ".join(p for p in parts if p)
