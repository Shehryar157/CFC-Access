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
from cfcaccess import arcade_games, hotkeys, menus, speech, text

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
    while game.is_running():
        reader.poll()
        arcade_reader.poll()
        keys.poll()
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
