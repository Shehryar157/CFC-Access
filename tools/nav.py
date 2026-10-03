"""Verified navigation helpers for research scripts.

Every helper checks the screen through the mod's own MenuReader before and
after pressing keys, and stops (raises) when the game doesn't do what we
expect, instead of pressing on blindly.

    from tools.nav import Nav
    nav = Nav()
    nav.to_main_menu()
    nav.open_row("Options")       # move to the row with this label, press Enter
    nav.expect("Options")
"""
import sys
import time

sys.path.insert(0, __file__.rsplit("tools", 1)[0])
from cfcaccess import menus, text  # noqa: E402
from tools import win  # noqa: E402


class NavError(RuntimeError):
    pass


class Nav:
    def __init__(self):
        self.game, self.hwnd = win.game_window()
        self.reader = menus.MenuReader(self.game, text.Messages())
        win.focus(self.hwnd)

    def view(self):
        return self.reader.top_view()[1]

    def title(self):
        v = self.view()
        return v.title if v else None

    def describe(self):
        v = self.view()
        return self.reader.describe(v, True) if v else "(no menu)"

    def press(self, key, hold=0.1):
        win.press(key, hold=hold)

    def expect(self, title, timeout=4):
        """Wait until the screen with this title is on top."""
        if not win.wait_for(lambda: self.title() == title, timeout):
            raise NavError(f"expected {title!r}, on {self.title()!r}")

    def goto(self, row):
        """Move the cursor to row number `row` (0 = first)."""
        for _ in range(30):
            v = self.view()
            if v is None:
                raise NavError("no menu on screen")
            if v.cursor == row:
                return
            self.press("down" if v.cursor < row else "up")
            win.wait_for(lambda: self.view() and self.view().cursor != v.cursor, 0.8)
        raise NavError(f"could not reach row {row}")

    def goto_label(self, label):
        v = self.view()
        labels = [r.label for r in v.rows]
        if label not in labels:
            raise NavError(f"{label!r} not in {labels}")
        self.goto(labels.index(label))

    def open_row(self, label, expect=None, timeout=4):
        """Go to the row with this label and press Enter."""
        self.goto_label(label)
        before = self.title()
        self.press("enter")
        if expect:
            self.expect(expect, timeout)
        else:
            win.wait_for(lambda: self.title() != before, timeout)

    def back(self, expect=None, timeout=3):
        before = self.title()
        self.press("backspace")
        if expect:
            self.expect(expect, timeout)
        else:
            win.wait_for(lambda: self.title() != before, timeout)

    def to_main_menu(self, tries=8):
        """From the title screen or any menu, get to the main menu."""
        for _ in range(tries):
            t = self.title()
            if t == "Main Menu":
                return
            # On the title screen Enter starts; in menus Backspace goes back.
            self.press("enter" if t is None else "backspace", hold=0.15)
            win.wait_for(lambda: self.title() == "Main Menu", 3)
            time.sleep(0.3)
        raise NavError(f"could not reach the main menu (on {self.title()!r})")
