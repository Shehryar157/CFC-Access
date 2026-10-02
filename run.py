"""CFC Access: screen reader support for Capcom Fighting Collection.

Run this before or after starting the game. Ctrl+C in the console quits.
"""
import time

from cfcaccess import game as game_mod
from cfcaccess import menus, speech, text

POLL_SECONDS = 0.05  # check the game 20 times a second


def play_session(messages):
    """Wait for the game, read it until it closes."""
    game = game_mod.wait_for_game()
    speech.say("Connected to Capcom Fighting Collection.")
    print(f"pid={game.pid} base={game.base:#x}")
    reader = menus.MenuReader(game, messages)
    while game.is_running():
        reader.poll()
        time.sleep(POLL_SECONDS)
    speech.say("Capcom Fighting Collection closed.")


def main():
    reader = speech.screen_reader() or "no screen reader, using SAPI"
    messages = text.Messages()
    speech.say(f"CFC Access started ({reader}). Waiting for Capcom Fighting Collection.")
    while True:
        play_session(messages)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
