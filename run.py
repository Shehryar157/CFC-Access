"""CFC Access: screen reader support for Capcom Fighting Collection.

  python run.py              wait for the game, follow it until you press Ctrl+C
  pythonw run.py --with-game started by launch.bat: follow one game session,
                             then exit when the game closes
"""
import ctypes
import os
import sys
import time

from cfcaccess import game as game_mod
from cfcaccess import arcade_games, hotkeys, menus, ocr, speech, text

POLL_SECONDS = 0.05  # check the game 20 times a second
STARTUP_WAIT = 120   # --with-game: give up if the game hasn't appeared by then
HERE = os.path.dirname(os.path.abspath(__file__))


def setup_log():
    """pythonw has no console, so print() would go nowhere: use a log file."""
    if sys.stdout is None:
        os.makedirs(os.path.join(HERE, "logs"), exist_ok=True)
        log = open(os.path.join(HERE, "logs", "cfcaccess.log"), "w", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = log


def already_running():
    """True if another copy of the mod is running.

    A named mutex is a system-wide name only one process can own. We keep
    the handle for the program's lifetime; Windows frees it when we exit.
    """
    global _mutex
    _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "CFCAccess.SingleInstance")
    return ctypes.windll.kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS


def play_session(messages, game):
    speech.say("Connected to Capcom Fighting Collection.")
    print(f"pid={game.pid} base={game.base:#x}")
    reader = menus.MenuReader(game, messages)
    arcade_reader = arcade_games.ArcadeReader(game, messages)
    window = {}

    def game_window():
        if not window.get("hwnd"):
            window["hwnd"] = game_mod.find_window(game.pid)
        return window["hwnd"]

    keys = hotkeys.Hotkeys(game_window)
    arcade_reader.bind_keys(keys)
    screen = ocr.ScreenReader(game_window)

    def story_allowed():
        # Only inside a game with no collection menu open (in menus Enter is
        # the game's own confirm key), and not mid-fight (no text there).
        g = arcade_reader.game_reader
        if g is None or reader.top_view()[1] is not None:
            return False
        return not (hasattr(g, "round_started") and g.in_match())

    def enter_pressed():
        if story_allowed():
            screen.read_screen()        # Enter: read the screen now
    keys.bind(0x0D, enter_pressed)

    def t_pressed():
        # Alt+T: automatic story reading on/off. Plain T: round time.
        if ctypes.windll.user32.GetAsyncKeyState(0x12) & 0x8000:
            screen.toggle_auto()
        else:
            arcade_reader.speak_stat("time_left")
    keys.bind("T", t_pressed)
    while game.is_running():
        reader.poll()
        # While a collection menu is open (including the pause menu) the
        # arcade game isn't being played; after a game closes its memory is
        # left behind, so don't read fights from it.
        if reader.last_view is None:
            arcade_reader.poll()
        keys.poll()
        if screen.auto:
            screen.poll(story_allowed())
        time.sleep(POLL_SECONDS)
    print("game closed")


def wait_for_game(timeout=None):
    start = time.time()
    while timeout is None or time.time() - start < timeout:
        game = game_mod.try_attach()
        if game is not None:
            return game
        time.sleep(1)
    return None


def main():
    if already_running():
        return  # quietly: the running copy owns the log and the speech
    setup_log()
    with_game = "--with-game" in sys.argv
    messages = text.Messages()
    if with_game:
        # Launched with the game: no "waiting" announcement, just follow it.
        game = wait_for_game(STARTUP_WAIT)
        if game is None:
            print("game did not start; exiting")
            return
        play_session(messages, game)
        return
    reader = speech.screen_reader() or "no screen reader, using SAPI"
    speech.say(f"CFC Access started ({reader}). Waiting for Capcom Fighting Collection.")
    while True:
        play_session(messages, wait_for_game())
        speech.say("Capcom Fighting Collection closed.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception:
        import traceback
        traceback.print_exc()
        raise
