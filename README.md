# CFC Access

Screen reader support for **Capcom Fighting Collection** (Steam, PC). It speaks the collection's menus, the arcade games' character select screens, fights, story text and more, through NVDA, JAWS or another screen reader, or Windows' built-in voice if none is running.

Current version: **1.0.0**

## Contents

- [Installing](#installing)
- [What the mod covers](#what-the-mod-covers)
- [What it does not cover yet](#what-it-does-not-cover-yet)
- [Keys](#keys)
- [Event sounds](#event-sounds)
- [How it works](#how-it-works)
- [Building from source](#building-from-source)
- [Credits](#credits)

## Installing

1. Download `CFCAccess-Setup-1.0.0.exe` from the [Releases](../../releases) page.
2. Run it. Windows asks for permission, because the setup writes into the game's folder. Every step is a standard Windows message box, read in full by screen readers.
3. The setup finds the game through Steam. If it can't, it asks you to choose the game's folder: the one that contains `CapcomFightingCollection.exe`.
4. When it says "CFC Access is installed", start Capcom Fighting Collection from Steam as usual. A few seconds after the game opens you hear **"CFC Access version 1.0.0 loaded"**.

There's nothing else to set up and no need to start the mod yourself: it starts and stops together with the game.

**To uninstall**, run `Uninstall CFC Access.exe` in the game's `CFCAccess` folder.

**Requirements:** Windows 10 or 11 (64-bit) and the Steam version of the game. A screen reader is optional; without one, Windows' own voice is used.

## What the mod covers

**The collection's menus:** everything a sighted player reads, including each item's description line.
- Main menu, Options (System, Music, Network, PC Settings, Credits)
- Keyboard and controller settings, with key names
- Museum: gallery with picture captions, and the music player (tracks, play state, shuffle, repeat)
- Fighter Awards: challenges, play stats
- Offline play: game and version select, game and EX settings, the pause menu, Display & Sound, Versus and Training menus
- The **move list** for every character, with inputs spoken as words ("down, down-forward, forward, punch")
- Pop-ups and yes/no questions

**Online play:**
- The Online menu and Casual/Ranked match setup
- "Looking for an opponent" and the standby choice
- Custom Match: creating, joining and searching lobbies, passcodes
- Your lobby: your name, Ready/Standby status, the lobby ID spelled out, the number of players
- The Ranked Leaderboard: rank, name, League Points, league

**All ten arcade games**, English and Japanese versions:
- Hyper Street Fighter II, Darkstalkers, Night Warriors, Vampire Savior, Vampire Hunter 2, Vampire Savior 2, Cyberbots, Super Gem Fighter Mini Mix, Red Earth (Warzard) and Super Puzzle Fighter II Turbo (X)

In the fighting games:
- The character under the select cursor, plus game-specific choices (speed, fighting style, Cyberbots' pilot and body, Red Earth's password prompt)
- "Ryu versus Ken" when a match starts, "Next round" between rounds
- Health, opponent's health, round time, super meter (as an exact percentage) and rounds won, on keys
- Sounds for low health, a full super meter, the last 10 seconds, and rounds won or lost
- The "Continue?" countdown
- Silence during the attract-mode demos, so demo fights don't trigger sounds

In Super Puzzle Fighter:
- Each falling pair and where it would land ("red over blue crash, on green")
- Moves and turns, clears ("Cleared 6: 4 green, 2 red"), power gems, diamonds
- Attacks sent and counter gems coming
- Danger warnings, "You win" / "You lose", the Continue countdown
- Any column of either board on a key

**Story text, win quotes and endings** are read from the screen with Windows' built-in text recognition: on a key, or automatically.

## What it does not cover yet

- **Online, with other players:** other players' rows in a lobby, the "opponent found" screen and online match results. These only appear with a real opponent and haven't been mapped yet.
- **Fighter Awards:** which challenges you've earned, and completion percentages.
- **Training mode:** the on-screen damage and combo counters.
- **Red Earth:** only the first boss (Hauzer) is named; the others are announced as "the boss". Typing a password in after choosing "Yes" isn't spoken.
- **Japanese story text:** needs Windows' Japanese text recognition. Install it with an administrator PowerShell:
  `Add-WindowsCapability -Online -Name "Language.OCR~~~ja-JP~0.0.1.0"`
- **Positions in a fight:** distance to the opponent, jumps and projectiles aren't described. The games' own sounds carry most of this.

## Keys

The collection's own keys (default keyboard layout):

| Key | Action |
|---|---|
| Arrows | Move in menus / move in games |
| Enter | Confirm |
| Backspace | Back |
| Ctrl / Right Ctrl | Previous / next page |
| F1 | Start |
| F2 | Menu (pause), hold briefly |
| Right Alt | Coin |
| U, I, O, J, K, L | Attack buttons (depends on the game and the Type A/B layout) |

The mod's keys, which work only while the game window is in front:

| Key | Where | Speaks |
|---|---|---|
| H | In a fight | Your health, as a percentage |
| G | In a fight | Your opponent's name and health |
| T | In a fight | Round time left |
| M | In a fight | Super meter: the level and percentage to the next |
| R | In a fight | Rounds won by each side |
| Enter | In a game, with no menu open | Reads the text on screen (story, win quotes, endings) |
| Alt+T | Anywhere | Automatic story reading on or off (remembered) |
| 1 to 6 | Super Puzzle Fighter | Your board's column, bottom first |
| Shift+1 to 6 | Super Puzzle Fighter | The opponent's column |
| H / G | Super Puzzle Fighter | Heights of every column, yours / opponent's |
| M | Super Puzzle Fighter | The next pair |

The fight keys stay silent outside a fight, because none of those values are on screen then. To skip a story, use the game's own Start key (F1).

## Event sounds

The mod plays a short sound for important moments. Until you add your own sounds, it speaks a word instead. To use sounds, put WAV files with these names in the `CFCAccess\sounds` folder:

| File | When |
|---|---|
| `low_health.wav` | Your health drops below a quarter |
| `enemy_low_health.wav` | The opponent's health drops below a quarter |
| `super_ready.wav` | Your super meter becomes full |
| `enemy_super_ready.wav` | The opponent's super meter becomes full |
| `time_low.wav` | 10 seconds left in the round |
| `round_won.wav` | You win a round |
| `round_lost.wav` | You lose a round |
| `danger.wav` | Super Puzzle Fighter: your middle columns are nearly full |

## How it works

*For the technically minded.*

CFC Access is a separate program, written in Python. It **reads** the game's memory 20 times a second and never changes it. Nothing is injected into the game.

- **Starting with the game.** The setup places a small `dinput8.dll` next to the game, written in C and built with Zig. Windows loads it because the game asks for the system's DirectInput library. It passes every call through to the real `dinput8.dll` in System32, and starts the command written in `CFCAccess.txt`, which is the mod.
- **Menus.** Capcom Fighting Collection runs on Capcom's MT Framework engine. Its GUI manager keeps a stack of open screens; each screen object's class (its vtable address) says which screen it is. For each known screen, the mod reads the cursor and the values from the object's fields. Labels and help lines come from the game's own text archive (`msg.arc`, a GMD message file), so all text is the game's own wording.
- **The arcade games.** The collection emulates CPS2 and CPS3 arcade boards. A pointer in the game leads to the emulated board's memory. Each game is recognised by the first bytes of its program ROM. Each game's reader knows where that game keeps health, timers, meters and select cursors. Some addresses come from the community's [fbneo-training-mode](https://github.com/peon2/fbneo-training-mode) scripts; most were found by changing something in the game and watching which values changed. Round results are worked out from the health bars, so the same code works for every game.
- **Story text** is drawn by the arcade boards as graphics. The mod captures the game window and runs Windows' built-in OCR on it (through the `winrt` packages). It first keeps only the bright pixels and thickens the pixel-font letters, which makes the recognition much more accurate.
- **Speech** goes through [Tolk](https://github.com/ndarilek/tolk), which talks to NVDA, JAWS and other screen readers, or falls back to SAPI.

Source layout:

| Path | Contents |
|---|---|
| `run.py` | Main loop |
| `cfcaccess/menus.py` | Every collection screen |
| `cfcaccess/arcade_games.py` | One reader per arcade game |
| `cfcaccess/movelist.py` | Move list decoding |
| `cfcaccess/ocr.py` | Screen text reading |
| `loader/` | The auto-start DLL |
| `installer/` | The setup program |
| `tools/` | Research and build tools |

## Building from source

Requires Python 3.11 (64-bit) on Windows.

```
pip install -r requirements.txt pyinstaller
python tools/build_loader.py build
python tools/build_release.py
```

`build_loader.py` compiles the auto-start DLL with [Zig](https://ziglang.org/) (`zig cc`). Set the path to `zig.exe` at the top of that file first.

This produces `dist/CFCAccess-Setup-<version>.exe`. To run the mod from source instead, start the game and run `python run.py`.

## Credits

- **Shehryar157:** creator, design and testing
- **Claude (Anthropic):** programming and reverse engineering, through Claude Code
- **Capcom:** Capcom Fighting Collection
- **peon2 and contributors:** [fbneo-training-mode](https://github.com/peon2/fbneo-training-mode), memory maps for several of the games
- **Davy Kager and contributors:** [Tolk](https://github.com/ndarilek/tolk) screen reader library (LGPL 3)
- **NV Access:** NVDA Controller Client (LGPL 2.1)
- **Pymem, Pillow, PyWinRT, PyInstaller and Zig:** the libraries and tools the mod is built with

CFC Access is a fan-made accessibility mod, not affiliated with or endorsed by Capcom.
