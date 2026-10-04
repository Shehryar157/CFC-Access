"""Speaking what happens inside the emulated arcade games.

ArcadeReader polls the emulated board's memory (see arcade.py), works out
which game is running from a fingerprint of its program, and hands the
memory to that game's reader.

FightingGame holds everything the fighting games share: announcing the
character under the select cursor and the match-up when a round starts,
the stat hotkeys (H, G, T, M, R) and the event sounds. Each game is a small
subclass that says WHERE its values are (class attributes) and can add
extra select-screen announcements.

Addresses come from fbneo-training-mode (github.com/peon2) and from our own
tests (see each game's comments).
"""
import ctypes

from . import arcade, sounds, speech


def bcd(v):
    """A byte holding two decimal digits (0x47 means 47)."""
    return (v >> 4) * 10 + (v & 15)


class FightingGame:
    # ---- filled in by each game ----
    STATS = ""            # roster prefix in the text file (STATS_<x>_nn_NAME)
    ROSTER = None         # arcade character number -> roster index (None = same)
    CHAR = (None, None)   # byte address of each player's character
    HEALTH = (None, None) # address of each player's health
    HEALTH_SIZE = 2       # bytes
    FULL = 144
    METER = (None, None)  # address of each player's meter (bar)
    METER_SIZE = 1
    METER_FULL = 1        # bar maximum
    METER_STOCKS = None   # address of each player's stock count, if stocked
    METER_STOCKS_MAX = 0
    TIMER = None          # byte, two decimal digits (or plain, see TIMER_BCD)
    TIMER_BCD = True
    ROUNDS = (None, None) # byte: rounds won this match
    LOW = 0.25            # "low health" below a quarter
    JAPANESE_NAMES = False  # Japan-only games show the Japanese names
    SPEAK_CHAR_AT_SELECT = True  # say CHAR's name when it changes at select

    def __init__(self, reader):
        self.r = reader
        self.a = reader.arcade
        self.last = {}
        self.last_pair = None
        self.round_started = False

    # ---- reading ----
    # rb / rw read one byte / one 2-byte word at an arcade address. CPS2
    # games use arcade.py's layout as-is; Red Earth (CPS3) overrides them.
    def rb(self, address):
        return self.a.read_byte(address)

    def rw(self, address):
        return self.a.read_word(address)

    def read(self, address, size):
        return self.rw(address) if size == 2 else self.rb(address)

    def char(self, p):
        return self.rb(self.CHAR[p]) if self.CHAR[p] is not None else None

    def full(self, p):
        """Health at the start of a round (the same for everyone in most games)."""
        return self.FULL

    def health(self, p):
        v = self.read(self.HEALTH[p], self.HEALTH_SIZE)
        if self.HEALTH_SIZE == 2 and v >= 0x8000:
            return v - 0x10000  # a 2-byte health can dip below 0
        return v

    def name(self, char):
        if char is None:
            return "opponent"
        index = self.ROSTER[char] if self.ROSTER and 0 <= char < len(self.ROSTER) else None
        if self.ROSTER is None:
            index = char
        if index is None:
            return f"character {char}"
        text = self.r.msg.get(f"STATS_{self.STATS}_{index:02d}_NAME", "")
        # Some fighters have different names in Japan and elsewhere; the text
        # file gives both ("Balrog (EN)/M. Bison (JP)"). Use the English one.
        if "(EN)/" in text:
            english, rest = text.split(" (EN)/", 1)
            text = rest.replace(" (JP)", "") if self.JAPANESE_NAMES else english
        return text or f"character {char}"

    def meter_parts(self, p):
        """(full stocks, fraction of the current bar)."""
        bar = self.read(self.METER[p], self.METER_SIZE)
        stocks = self.rb(self.METER_STOCKS[p]) if self.METER_STOCKS else 0
        return stocks, min(1.0, bar / self.METER_FULL)

    def super_ready(self, p):
        stocks, frac = self.meter_parts(p)
        return stocks > 0 if self.METER_STOCKS else frac >= 1.0

    def timer(self):
        if self.TIMER is None:
            return None
        v = self.rb(self.TIMER)
        return bcd(v) if self.TIMER_BCD else v

    def wins(self, p):
        return self.rb(self.ROUNDS[p]) if self.ROUNDS[p] is not None else None

    # ---- helpers ----
    def changed(self, key, value):
        old = self.last.get(key)
        self.last[key] = value
        return old is not None and old != value

    def crossed(self, key, now_true):
        """True once when a condition becomes true (not while it stays true)."""
        before = self.last.get(key)
        self.last[key] = now_true
        return now_true and before is False

    @staticmethod
    def percent(value, full):
        return max(0, min(100, round(100 * value / full)))

    def in_match(self):
        """A round is being fought: both fighters standing, clock running."""
        h1, h2 = self.health(0), self.health(1)
        t = self.timer()
        return (self.round_started and 0 < h1 <= self.full(0) and 0 < h2 <= self.full(1)
                and (t is None or t > 0))

    # ---- polling ----
    def select_extras(self):
        """Games override this to announce extra select-screen choices."""

    def poll(self):
        c1, c2 = self.char(0), self.char(1)
        if not self.round_started:
            self.select_extras()
            if self.changed("p1", c1) and self.SPEAK_CHAR_AT_SELECT:
                speech.say(self.name(c1))
        else:
            self.changed("p1", c1)
        # A round starts when both health values jump to full (they are 0
        # or stale during the versus screen; the opponent is set by then).
        h1, h2 = self.health(0), self.health(1)
        full = h1 == self.full(0) and h2 == self.full(1) and h1 > 0
        if full:
            self.round_started = True
        elif h1 <= 0 or h2 <= 0:
            self.round_started = False  # someone is down: the round is over
        if full and self.last.get("full") is False:
            pair = (c1, c2)
            if pair != self.last_pair:
                speech.say(f"{self.name(c1)} versus {self.name(c2)}")
                self.last_pair = pair
            else:
                speech.say("Next round")
        self.last["full"] = full
        self.fight_events(h1, h2)

    def fight_events(self, h1, h2):
        in_round = self.in_match()
        if self.crossed("p1_low", in_round and h1 < self.LOW * self.full(0)):
            sounds.play("low_health")
        if self.crossed("p2_low", in_round and h2 < self.LOW * self.full(1)):
            sounds.play("enemy_low_health")
        if self.METER[0] is not None:
            if self.crossed("p1_super", in_round and self.super_ready(0)):
                sounds.play("super_ready")
            if self.crossed("p2_super", in_round and self.super_ready(1)):
                sounds.play("enemy_super_ready")
        t = self.timer()
        if self.crossed("time_low", in_round and t is not None and t <= 10):
            sounds.play("time_low")
        if self.ROUNDS[0] is not None:
            w = (self.wins(0), self.wins(1))
            prev = self.last.get("wins")
            self.last["wins"] = w
            if prev is not None:
                if w[0] == prev[0] + 1:
                    sounds.play("round_won")
                elif w[1] == prev[1] + 1:
                    sounds.play("round_lost")

    # ---- hotkey readouts ----
    def your_health(self):
        return f"Health {self.percent(self.health(0), self.full(0))} percent"

    def enemy_health(self):
        return f"{self.name(self.char(1))} {self.percent(self.health(1), self.full(1))} percent"

    def meter(self):
        if self.METER[0] is None:
            return "Meter not available yet"
        stocks, frac = self.meter_parts(0)
        if self.METER_STOCKS:
            level = f"Level {stocks}" if stocks else "Level 0"
            return f"{level}, {self.percent(frac, 1)} percent to the next"
        return "Super ready" if frac >= 1.0 else f"Meter {self.percent(frac, 1)} percent"

    def time_left(self):
        t = self.timer()
        return "Round time not available yet" if t is None else f"Time {t}"

    def rounds(self):
        if self.ROUNDS[0] is None:
            return "Rounds not available yet"
        return f"Rounds won: you {self.wins(0)}, opponent {self.wins(1)}"


class HSF2(FightingGame):
    """Hyper Street Fighter II: The Anniversary Edition (tested 2026-10-04)."""

    STATS = "HSF2"
    # Arcade character order (Ryu, E. Honda, Blanka, Guile, Ken, ...) ->
    # the collection's roster order (STATS_HSF2_nn).
    ROSTER = [0, 2, 4, 6, 1, 3, 5, 7, 15, 14, 12, 13, 9, 8, 10, 11, 16]
    CHAR = (0xFF8667, 0xFF8A67)
    HEALTH = (0xFF8366, 0xFF8766)
    FULL = 144
    METER = (0xFF85F0, 0xFF89F0)
    METER_FULL = 48
    TIMER = 0xFF8BFC
    ROUNDS = (0xFF8685, 0xFF8A85)
    SPEED = 0xFF8B63      # 0, 1, 2 = game speed 1, 2, 3
    PLTYPE = 0xFF83CC     # P1: 0 Super X ... 4 Normal
    PLTYPES = ["Super X", "Super", "Turbo", "Dash", "Normal"]

    def select_extras(self):
        speed = self.a.read_byte(self.SPEED)
        if self.changed("speed", speed) and speed <= 2:
            speech.say(f"Speed {speed + 1}")
        pltype = self.a.read_byte(self.PLTYPE)
        if self.changed("pltype", pltype) and pltype < len(self.PLTYPES):
            speech.say(self.PLTYPES[pltype])


class Cyberbots(FightingGame):
    """Cyberbots: Fullmetal Madness. Health, meter, timer from fbneo-training-
    mode cybots.lua; select screens, robots and rounds from our tests
    (2026-10-04)."""

    STATS = "CYBOTS"
    # CHAR is the robot (VA) each player fights with, in the order of the
    # robot name list in the exe; the match-up names robots, as the screen does.
    ROSTER = [6, 9, 12, 15, 7, 11, 10, 16, 17, 8, 13, 20, 18, 19, 21, 14]
    CHAR = (0xFF8511, 0xFF8911)
    SPEAK_CHAR_AT_SELECT = False
    HEALTH = (0xFF81E5, 0xFF85E5)
    HEALTH_SIZE = 1
    FULL = 152
    METER = (0xFF8534, 0xFF8934)
    METER_FULL = 63
    TIMER = 0xFFEBA0
    ROUNDS = (0xFF84AD, 0xFF88AD)
    PILOT = 0xFF8529      # P1 pilot cursor, arcade order
    PILOTS = [0, 2, 1, 5, 3, 4]  # arcade pilot -> STATS_CYBOTS_nn (Jin, Mary, ...)
    BODY = 0xFFD5E0       # body type cursor: Blodia, Reptos, Fordy, Guldin
    BODIES = [6, 9, 12, 15]

    def select_extras(self):
        msg = self.r.msg
        pilot = self.a.read_byte(self.PILOT)
        if self.changed("pilot", pilot) and pilot < len(self.PILOTS):
            speech.say(msg.get(f"STATS_CYBOTS_{self.PILOTS[pilot]:02d}_NAME", ""))
        body = self.a.read_byte(self.BODY)
        if self.changed("body", body) and body < len(self.BODIES):
            speech.say(msg.get(f"STATS_CYBOTS_{self.BODIES[body]:02d}_NAME", ""))


class Darkstalkers(FightingGame):
    """Darkstalkers: The Night Warriors / Vampire. Health and meter from
    fbneo-training-mode dstlk.lua; select, characters, timer from our tests
    (2026-10-04); rounds provisional."""

    STATS = "VAMP"
    # Arcade character numbers (1 Demitri, 2 Jon Talbain, 3 Victor,
    # 4 Lord Raptor, 5 Morrigan, 6 Anakaris, 7 Felicia, 8 Bishamon, 9 Rikuo,
    # 10 Sasquatch) -> STATS_VAMP_nn. 0 and 11+ are the bosses (not seen yet).
    ROSTER = [None, 0, 1, 3, 2, 4, 5, 6, 7, 8, 9]
    CHAR = (0xFF838A, 0xFF878A)
    SPEAK_CHAR_AT_SELECT = False
    HEALTH = (0xFF83CB, 0xFF87CB)
    HEALTH_SIZE = 1
    FULL = 0x90
    METER = (0xFF855F, 0xFF895F)
    METER_FULL = 0x50
    TIMER = 0xFF9409
    ROUNDS = (0xFF8336, 0xFF8736)   # provisional: seen 0 -> 1 once
    CURSOR = 0xFF8729     # P1 grid cursor, same numbering as CHAR
    SPEED = 0xFFF424      # 0, 1, 2 = speed 1, 2, 3

    def select_extras(self):
        speed = self.a.read_byte(self.SPEED)
        if self.changed("speed", speed) and speed <= 2:
            speech.say(f"Speed {speed + 1}")
        cursor = self.a.read_byte(self.CURSOR)
        if self.changed("cursor", cursor) and 0 < cursor < len(self.ROSTER):
            speech.say(self.name(cursor))


class NightWarriors(FightingGame):
    """Night Warriors: Darkstalkers' Revenge / Vampire Hunter. Health,
    meter from fbneo-training-mode nwarr.lua; select, characters, timer from
    our tests (2026-10-04). Player 2's data is 0x500 after player 1's."""

    STATS = "VHUNT"
    # Arcade numbers 1-14 (Demitri, Jon Talbain, Victor, Lord Raptor,
    # Morrigan, Anakaris, Felicia, Bishamon, Rikuo, Sasquatch, Huitzil,
    # Pyron, Hsien-Ko, Donovan) -> STATS_VHUNT_nn.
    ROSTER = [None, 2, 3, 5, 4, 6, 7, 8, 9, 10, 11, 12, 13, 1, 0]
    CHAR = (0xFF838A, 0xFF888A)
    SPEAK_CHAR_AT_SELECT = False
    HEALTH = (0xFF83CB, 0xFF88CB)
    HEALTH_SIZE = 1
    FULL = 144
    METER = (0xFF855F, 0xFF8A5F)
    METER_FULL = 0x70
    METER_STOCKS = (0xFF8565, 0xFF8A65)
    TIMER = 0xFF8E09
    CURSOR = 0xFF8829     # P1 grid cursor, same numbering as CHAR
    SPEED = 0xFF81DF      # 0 Normal, 1 Turbo

    def select_extras(self):
        speed = self.a.read_byte(self.SPEED)
        if self.changed("speed", speed) and speed <= 1:
            speech.say(["Normal", "Turbo"][speed])
        cursor = self.a.read_byte(self.CURSOR)
        if self.changed("cursor", cursor) and 0 < cursor < len(self.ROSTER):
            speech.say(self.name(cursor))


class VampireSavior(FightingGame):
    """Vampire Savior: The Lord of Vampire. Health, stocked meter from
    fbneo-training-mode vsav.lua; select cursor, characters, timer from our
    tests (2026-10-04). Rounds not found yet (one candidate reset to 0)."""

    STATS = "VSAV"
    # Arcade numbers -> STATS_VSAV_nn. Seen on screen: 0 Bulleta, 1 Demitri,
    # 3 Victor, 4 Lord Raptor, 5 Morrigan, 6 Anakaris, 7 Felicia, 10 Sasquatch,
    # 12 Hsien-Ko, 13 Lilith, 14 Jedah, 15 Q-Bee. Assumed from the series'
    # order: 2 Jon Talbain, 8 Bishamon, 9 Rikuo, 11 unknown.
    ROSTER = [1, 5, 6, 8, 7, 9, 10, 11, 12, 13, 14, None, 4, 3, 0, 2]
    CHAR = (0xFF8782, 0xFF8B82)
    SPEAK_CHAR_AT_SELECT = False
    HEALTH = (0xFF8450, 0xFF8850)
    FULL = 0x120
    METER = (0xFF850A, 0xFF890A)
    METER_SIZE = 2
    METER_FULL = 0x90
    METER_STOCKS = (0xFF8509, 0xFF8909)
    TIMER = 0xFF8109
    TIMER_BCD = False
    CURSOR = 0xFF8403     # P1 select cursor, same numbering as CHAR

    def select_extras(self):
        cursor = self.a.read_byte(self.CURSOR)
        if self.changed("cursor", cursor) and 0 <= cursor < len(self.ROSTER):
            speech.say(self.name(cursor))


class VampireHunter2(VampireSavior):
    """Vampire Hunter 2 (Japan only): Vampire Savior's engine and addresses.
    Select numbers checked on screen 2026-10-04."""

    STATS = "VHUNT2"
    JAPANESE_NAMES = True
    # Seen: 1 Demitri, 2 Gallon, 3 Victor, 4 Zabel, 5 Morrigan, 6 Anakaris,
    # 7 Felicia, 10 Sasquatch, 13 Lei-Lei, 16 Phobos, 17 Pyron, 19 Donovan.
    # Assumed: 8 Bishamon, 9 Aulbath (as in Vampire Savior).
    ROSTER = [None, 0, 6, 3, 4, 1, 2, 7, 10, 8, 9, None, None, 5, None, None, 12, 13, None, 11]


class VampireSavior2(VampireSavior):
    """Vampire Savior 2 (Japan only): Vampire Savior's engine and addresses.
    Select numbers checked on screen 2026-10-04."""

    STATS = "VSAV2"
    JAPANESE_NAMES = True
    # Seen: 0 Bulleta, 1 Demitri, 3 Victor, 4 Zabel, 5 Morrigan, 6 Anakaris,
    # 7 Felicia, 13 Lei-Lei, 14 Jedah? (15 here), 16 Phobos, 17 Pyron,
    # 19 Donovan. Assumed: 8 Bishamon. 15 is Jedah on screen.
    ROSTER = [1, 4, None, 7, 8, 5, 6, 10, 11, None, None, None, None, 9, None, 0, 13, 14, None, 12]


class GemFighter(FightingGame):
    """Super Gem Fighter Mini Mix / Pocket Fighter. Health, meter, timer from
    fbneo-training-mode sgemf.lua; select cursor and characters from our
    tests (2026-10-04)."""

    STATS = "PFIGHT"
    # Arcade numbers (seen): 0 Ryu, 1 Ken, 2 Chun-Li, 3 Sakura, 4 Morrigan,
    # 5 Hsien-Ko, 6 Felicia, 7 Tessa, 8 Ibuki, 9 Zangief; assumed 10 Dan,
    # 11 Akuma (hidden).
    ROSTER = [0, 1, 2, 4, 6, 7, 8, 9, 5, 3, 10, 11]
    CHAR = (0xFF8781, 0xFF8B81)
    HEALTH = (0xFF8440, 0xFF8840)
    FULL = 144
    METER = (0xFF8595, 0xFF8995)
    METER_FULL = 0x60
    METER_STOCKS = (0xFF8594, 0xFF8994)
    TIMER = 0xFF8188


class RedEarth(FightingGame):
    """Red Earth / Warzard (CPS3 board; tested 2026-10-04).

    The CPS3's CPU works in 4-byte units; the emulator keeps its work RAM
    (arcade addresses 0x2000000-0x207FFFF) at block offset 0x80020, each
    4-byte unit in PC byte order. We give addresses the way the emulator
    stores them (as fbneo-training-mode's redearth.lua does), so rb/rw just
    add the shift. Found by pointers in the player blocks that point at
    each other (P1 0x206A784 <-> P2 0x206AA04).
    """

    SHIFT = 0x80020 - 0x2000000
    STATS = "WARZARD"
    # Heroes: 0 Leo, 1 Kenji, 2 Tessa, 3 Mai Ling (STATS_WARZARD has each
    # three times, one per stats page).
    ROSTER = [0, 4, 10, 7]
    # Player 2 is always a boss, numbered separately; names as on screen.
    BOSSES = {3: "Hydron"}
    CHAR = (0x206A886, 0x206AB06)
    HEALTH = (0x206A820, 0x206AAA0)
    FULL_AT = (0x206A8D4, 0x206AB54)  # each fighter's full health (grows with level)
    TIMER = 0x20606E2                 # 3 decimal digits (0x199 = 199)
    PASSWORD = 0x2067904              # two numbers whose hex digits are the password
    PROMPT = 0x206A9A8                # P1 select state: 2 = "Password? Yes / No" showing
    PROMPT_CURSOR = 0x206A9B3         # 0 Yes, 1 No

    def rb(self, address):
        return self.a.read_byte((address + self.SHIFT) ^ 1)  # read_byte undoes the ^1

    def rw(self, address):
        return self.a.read_word(address + self.SHIFT)

    def full(self, p):
        return self.rw(self.FULL_AT[p]) or 1

    def timer(self):
        v = self.rw(self.TIMER)
        return (v >> 8) * 100 + bcd(v & 0xFF)

    def char(self, p):
        c = self.rb(self.CHAR[p])
        return c if p == 0 else 100 + c   # 100+ = boss (see name)

    def name(self, char):
        if char is not None and char >= 100:
            return self.BOSSES.get(char - 100, f"boss {char - 100}")
        return super().name(char)

    def password(self):
        lo = self.rw(self.PASSWORD) | self.rw(self.PASSWORD + 2) << 16
        hi = self.rw(self.PASSWORD + 4) | self.rw(self.PASSWORD + 6) << 16
        return f"{lo:05x}{hi:05x}" if lo or hi else None

    def select_extras(self):
        # After the hero is picked: "Password? Yes / No" (No skips entering
        # one). The cursor remembers the last choice; Right always picks No.
        prompt = self.rb(self.PROMPT) == 2
        choice = "No" if self.rb(self.PROMPT_CURSOR) else "Yes"
        if self.changed("prompt", prompt) and prompt:
            speech.say(f"Password? {choice}. Left Yes, right No")
        elif prompt and self.changed("prompt_choice", choice):
            speech.say(choice)
        if prompt:
            self.last["prompt_choice"] = choice
        pw = self.password()
        if self.changed("password", pw) and pw:
            # Read as single digits, in two groups of five as on screen.
            speech.say("Password " + " ".join(pw[:5]) + ", " + " ".join(pw[5:]))


class PuzzleFighter:
    """Super Puzzle Fighter II Turbo / X (tested 2026-10-04).

    Not a fighting game: each player stacks falling pairs of gems on a board
    6 columns wide and 13 rows high. We say each new pair, where it moves
    and how it turns; number keys read a column, H / G every column's
    height, M the next pair.

    Each board is 13 rows of 16 bytes (a wall word, 6 cells, a wall word),
    top row first; a cell is a 2-byte word:
      low byte 0          empty
      low byte 1-4        a gem: 1 blue, 2 yellow, 3 green, 4 red
      low byte 9-12       a crash gem (8 + colour)
      low byte 7          a counter gem; high byte = colour * 16 + count
    Other codes (diamond, power gems) are logged so we can name them.
    """

    BOARD = (0xFFAB10, 0xFFAF10)
    PAIR = (0xFF8452, 0xFF8852)   # falling pair: pivot (bottom) gem, other gem
    NEXT = (0xFF8456, 0xFF8856)
    COLUMN = 0xFF8310             # pivot gem's column, 0-5
    ROTATION = 0xFF8470           # byte: where the other gem is (0 up, 1 right, 2 down, 3 left)
    CHAR = (0xFF8448, 0xFF8848)   # select-grid number
    LEVEL = 0xFF0C8C              # level select cursor: 0 Easy, 1 Normal, 2 Hard
    CURSOR = 0xFF0C83             # character select cursor (grid number)
    # Grid number (Ryu, Chun-Li, Sakura, Ken / Morrigan, Hsien-Ko, Donovan,
    # Felicia) -> STATS_SPF2X_nn. Hidden characters not seen yet.
    ROSTER = [0, 2, 4, 1, 5, 6, 3, 7]
    COLOURS = {1: "blue", 2: "yellow", 3: "green", 4: "red"}
    PLACES = ["on top", "to the right", "below", "to the left"]
    DANGER_HEIGHT = 10            # columns 3 and 4 this high: nearly lost

    def __init__(self, reader):
        self.r = reader
        self.a = reader.arcade
        self.last = {}
        self.unknown = set()

    # ---- reading ----
    def gem(self, w):
        lo, hi = w & 0xFF, w >> 8
        if lo == 0:
            return None
        if lo in self.COLOURS and hi == 0:
            return self.COLOURS[lo]
        if lo - 8 in self.COLOURS:
            return self.COLOURS[lo - 8] + " crash"
        if lo == 7 and hi >> 4 in self.COLOURS:
            return f"{self.COLOURS[hi >> 4]} counter {hi & 15}"
        if lo in self.COLOURS:
            return "power " + self.COLOURS[lo]
        if w not in self.unknown:
            self.unknown.add(w)
            print(f"PUZZLE: unknown gem code {w:#06x}")
        return "diamond" if lo == 5 else f"gem {w:#x}"

    def column_gems(self, p, c):
        """Gems in column c (0-5), bottom first."""
        base = self.BOARD[p]
        out = []
        for r in range(12, -1, -1):
            g = self.gem(self.a.read_word(base + 0x10 * r + 2 + 2 * c))
            if g is None:
                break
            out.append(g)
        return out

    def heights(self, p):
        return [len(self.column_gems(p, c)) for c in range(6)]

    def pair(self, p, address=None):
        a = address if address is not None else self.PAIR[p]
        return self.gem(self.a.read_word(a)), self.gem(self.a.read_word(a + 2))

    def name(self, grid):
        index = self.ROSTER[grid] if 0 <= grid < len(self.ROSTER) else None
        if index is None:
            return f"character {grid}"
        text = self.r.msg.get(f"STATS_SPF2X_{index:02d}_NAME", "")
        return text.split(" (EN)/")[0] or f"character {grid}"

    def in_match(self):
        pivot, other = self.pair(0)
        return pivot is not None and other is not None

    def changed(self, key, value):
        old = self.last.get(key)
        self.last[key] = value
        return old is not None and old != value

    @staticmethod
    def describe(pivot, other, rotation):
        if rotation == 0:
            return f"{other} over {pivot}"
        if rotation == 2:
            return f"{pivot} over {other}"
        left, right = (pivot, other) if rotation == 1 else (other, pivot)
        return f"{left}, {right}"

    # ---- polling ----
    def poll(self):
        a = self.a
        if not self.in_match():
            self.last.pop("pair", None)
            level = a.read_byte(self.LEVEL)
            if self.changed("level", level) and level <= 2:
                speech.say(["Easy", "Normal", "Hard"][level])
            cursor = a.read_byte(self.CURSOR)
            if self.changed("cursor", cursor):
                speech.say(self.name(cursor))
            self.last["matched"] = False
            return
        if self.last.get("matched") is False:
            speech.say(f"{self.name(a.read_byte(self.CHAR[0]))} versus {self.name(a.read_byte(self.CHAR[1]))}")
        self.last["matched"] = True
        pivot, other = self.pair(0)
        column = a.read_word(self.COLUMN)
        rotation = a.read_byte(self.ROTATION) & 3
        pair = (pivot, other)
        new_pair = self.last.get("pair") != pair
        self.last["pair"] = pair
        moved = self.changed("column", column)
        turned = self.changed("rotation", rotation)
        if new_pair:
            self.last["column"], self.last["rotation"] = column, rotation
            speech.say(self.describe(pivot, other, rotation))
        elif turned:
            speech.say(f"{other} {self.PLACES[rotation]}")
        elif moved:
            speech.say(self.where(column, rotation))
        tall = max(self.heights(0)[2:4])
        danger = tall >= self.DANGER_HEIGHT
        if danger and self.last.get("danger") is False:
            sounds.play("danger")
        self.last["danger"] = danger

    @staticmethod
    def where(column, rotation):
        if rotation == 1:
            return f"columns {column + 1} and {column + 2}"
        if rotation == 3:
            return f"columns {column} and {column + 1}"
        return f"column {column + 1}"

    # ---- hotkey readouts ----
    def read_column(self, n):
        shifted = bool(ctypes.windll.user32.GetAsyncKeyState(0x10) & 0x8000)
        p = 1 if shifted else 0
        gems = self.column_gems(p, n - 1)
        who = "Opponent column" if p else "Column"
        return f"{who} {n}: " + (", ".join(gems) if gems else "empty")

    def your_health(self):
        return "Heights " + ", ".join(str(h) for h in self.heights(0))

    def enemy_health(self):
        return "Opponent heights " + ", ".join(str(h) for h in self.heights(1))

    def meter(self):
        pivot, other = self.pair(0, self.NEXT[0])
        return f"Next {other} over {pivot}"


# First 8 bytes of each game's program (arcade address 0) -> reader class.
GAMES = {
    bytes.fromhex("092c59d660d42b51"): HSF2,
    bytes.fromhex("5cb1db2d2156abe4"): Cyberbots,
    bytes.fromhex("bfdc85c2edbf58d2"): Darkstalkers,
    bytes.fromhex("8697200eb97ecc5f"): NightWarriors,
    bytes.fromhex("faa9173a43f4aec0"): VampireSavior,
    bytes.fromhex("48d3bfd1c6d78d91"): VampireHunter2,
    bytes.fromhex("11ebea2b261726a4"): VampireSavior2,
    bytes.fromhex("7dfe9ab442e79466"): GemFighter,
    # CPS3 games start with the board's own boot program, so this is the
    # same for both Red Earth versions.
    bytes.fromhex("0004000000000802"): RedEarth,
    bytes.fromhex("79b036f011cc1fdf"): PuzzleFighter,
}


class ArcadeReader:
    # hotkey letter -> game reader method name
    KEYS = {"H": "your_health", "G": "enemy_health", "T": "time_left", "M": "meter", "R": "rounds"}

    def __init__(self, game, messages):
        self.msg = messages
        self.arcade = arcade.Arcade(game)
        self.fingerprint = None
        self.game_reader = None

    @property
    def key(self):
        return type(self.game_reader).__name__ if self.game_reader else None

    def speak_stat(self, method, *args):
        g = self.game_reader
        if g is None or not hasattr(g, method) or not g.in_match():
            return  # outside a match these stats aren't on screen: stay silent
        try:
            speech.say(getattr(g, method)(*args))
        except Exception:
            speech.say("Not available")

    def bind_keys(self, hotkeys):
        for key, method in self.KEYS.items():
            hotkeys.bind(key, lambda m=method: self.speak_stat(m))
        # Number keys 1-6: read a board column (Super Puzzle Fighter).
        for n in range(1, 7):
            hotkeys.bind(str(n), lambda n=n: self.speak_stat("read_column", n))

    def poll(self):
        a = self.arcade
        try:
            if a.base is None and not a.locate():
                return
            fingerprint = a.game.pm.read_bytes(a.base, 8)
        except Exception:
            a.base = None
            return
        if fingerprint != self.fingerprint:
            self.fingerprint = fingerprint
            cls = GAMES.get(fingerprint)
            self.game_reader = cls(self) if cls else None
            if cls is None:
                print(f"UNKNOWN ARCADE GAME fingerprint {fingerprint.hex()}")
        if self.game_reader is not None:
            try:
                self.game_reader.poll()
            except Exception:
                a.base = None  # the board moved (game changed): find it again
