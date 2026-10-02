"""CFC Access: screen reader support for Capcom Fighting Collection.

Run this before or after starting the game. Ctrl+C in the console quits.
"""
import time

from cfcaccess import game as game_mod
from cfcaccess import speech


def main():
    reader = speech.screen_reader() or "no screen reader, using SAPI"
    speech.say(f"CFC Access started ({reader}). Waiting for Capcom Fighting Collection.")

    game = game_mod.wait_for_game()
    header = game.read(game.base, 2)
    if header == b"MZ":
        speech.say("Connected to Capcom Fighting Collection.")
    else:
        speech.say("Found the game but could not read its memory.")
    print(f"pid={game.pid} base={game.base:#x} size={game.size:#x} header={header!r}")

    while game.is_running():
        time.sleep(0.5)
    speech.say("Capcom Fighting Collection closed.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
