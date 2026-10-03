"""Press keys in the game and print what the mod would say, without speaking.

  python tools/dryrun.py down right right up ...

speech.say is monkey-patched to collect lines instead of talking, and the
menu reader is polled after every key press.
"""
import sys
import time

sys.path.insert(0, __file__.rsplit("tools", 1)[0])
from cfcaccess import menus, speech, text  # noqa: E402
from tools import win  # noqa: E402

said = []
speech.say = lambda line, interrupt=True: said.append(line)  # the monkey-patch


def main(keys):
    game, hwnd = win.game_window()
    reader = menus.MenuReader(game, text.Messages())
    reader.poll()
    print(f"{'(start)':10} {' | '.join(said)}")
    win.focus(hwnd)
    for key in keys:
        said.clear()
        if key.startswith("goto:"):
            # Move until the mod itself reads this row, so a later Enter is safe.
            target = int(key[5:])
            for _ in range(20):
                view = reader.top_view()[1]
                if view is None or view.cursor == target:
                    break
                win.press("down" if view.cursor < target else "up")
                win.wait_for(lambda: (reader.top_view()[1] or view).cursor != view.cursor, 0.8)
            view = reader.top_view()[1]
            if view is None or view.cursor != target:
                sys.exit(f"could not reach row {target}; stopping")
            reader.poll()
            print(f"{key:10} {' | '.join(said) or '(silent)'}")
            continue
        win.press(key, hold=0.15)
        deadline = time.time() + 1.2
        while time.time() < deadline:  # poll like the real mod, 20x a second
            reader.poll()
            time.sleep(0.05)
        print(f"{key:10} {' | '.join(said) or '(silent)'}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main(sys.argv[1:])
