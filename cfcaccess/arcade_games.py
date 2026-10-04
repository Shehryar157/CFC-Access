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
    TIMER = None          # byte, two decimal digits
    ROUNDS = (None, None) # byte: rounds won this match
    LOW = 0.25            # "low health" below a quarter
    SPEAK_CHAR_AT_SELECT = True  # say CHAR's name when it changes at select

    def __init__(self, reader):
        self.r = reader
        self.a = reader.arcade
        self.last = {}
        self.last_pair = None
        self.round_started = False

    # ---- reading ----
    def read(self, address, size):
        return self.a.read_word(address) if size == 2 else self.a.read_byte(address)

    def char(self, p):
        return self.a.read_byte(self.CHAR[p]) if self.CHAR[p] is not None else None

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
            text = text.split(" (EN)/")[0]
        return text or f"character {char}"

    def meter_parts(self, p):
        """(full stocks, fraction of the current bar)."""
        bar = self.read(self.METER[p], self.METER_SIZE)
        stocks = self.a.read_byte(self.METER_STOCKS[p]) if self.METER_STOCKS else 0
        return stocks, min(1.0, bar / self.METER_FULL)

    def super_ready(self, p):
        stocks, frac = self.meter_parts(p)
        return stocks > 0 if self.METER_STOCKS else frac >= 1.0

    def timer(self):
        return bcd(self.a.read_byte(self.TIMER)) if self.TIMER is not None else None

    def wins(self, p):
        return self.a.read_byte(self.ROUNDS[p]) if self.ROUNDS[p] is not None else None

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
        return (self.round_started and 0 < h1 <= self.FULL and 0 < h2 <= self.FULL
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
        full = h1 == h2 == self.FULL
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
        low = self.LOW * self.FULL
        if self.crossed("p1_low", in_round and h1 < low):
            sounds.play("low_health")
        if self.crossed("p2_low", in_round and h2 < low):
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
        return f"Health {self.percent(self.health(0), self.FULL)} percent"

    def enemy_health(self):
        return f"{self.name(self.char(1))} {self.percent(self.health(1), self.FULL)} percent"

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


# First 8 bytes of each game's program (arcade address 0) -> reader class.
GAMES = {
    bytes.fromhex("092c59d660d42b51"): HSF2,
    bytes.fromhex("5cb1db2d2156abe4"): Cyberbots,
    bytes.fromhex("bfdc85c2edbf58d2"): Darkstalkers,
    bytes.fromhex("8697200eb97ecc5f"): NightWarriors,
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

    def speak_stat(self, method):
        g = self.game_reader
        if g is None or not hasattr(g, method) or not g.in_match():
            return  # outside a match these stats aren't on screen: stay silent
        try:
            speech.say(getattr(g, method)())
        except Exception:
            speech.say("Not available")

    def bind_keys(self, hotkeys):
        for key, method in self.KEYS.items():
            hotkeys.bind(key, lambda m=method: self.speak_stat(m))

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
