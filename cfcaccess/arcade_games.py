"""Speaking what happens inside the emulated arcade games.

ArcadeReader polls the emulated board's memory (see arcade.py), works out
which game is running from a fingerprint of its program, and hands the
memory to that game's reader. Game readers speak changes only: the
character under the cursor, the chosen game speed, the match-up when a
fight starts.

Addresses for Hyper Street Fighter II come from fbneo-training-mode's
hsf2.lua (health, positions, fight phase) and from our own tests at the
select screens (2026-10-04, see the comments below).
"""
from . import arcade, speech

# First 8 bytes of each game's program (arcade address 0) -> game key.
FINGERPRINTS = {
    bytes.fromhex("092c59d660d42b51"): "hsf2",
}


class HSF2:
    """Hyper Street Fighter II: The Anniversary Edition."""

    PHASE = 0xFF8008      # word: 0 on select screens, 2 during a fight
    SPEED = 0xFF8B63      # byte: 0, 1, 2 = game speed 1, 2, 3
    P1, P2 = 0xFF8300, 0xFF8700   # player blocks
    CHAR = 0x367          # byte in a player block: character (arcade order)
    PLTYPE = 0xCC         # byte in a player block: 0 Super X ... 4 Normal
    HEALTH = 0x66         # word in a player block: health
    FULL = 144
    METER = 0x2F0         # byte in a player block: super meter, 48 = full
    METER_FULL = 48       # (fbneo-training-mode hsf2.lua: p1meter / p1maxmeter)
    TIMER = 0xFF8BFC      # byte, two decimal digits (0x99 = 99)
    ROUNDS = 0x385        # byte in a player block: rounds won this match
    PLTYPES = ["Super X", "Super", "Turbo", "Dash", "Normal"]
    # Arcade character order -> the collection's roster (STATS_HSF2_nn).
    ROSTER = [0, 2, 4, 6, 1, 3, 5, 7, 15, 14, 12, 13, 9, 8, 10, 11, 16]

    def __init__(self, reader):
        self.r = reader
        self.last = {}
        self.last_pair = None

    def name(self, char):
        msg = self.r.msg
        if 0 <= char < len(self.ROSTER):
            text = msg.get(f"STATS_HSF2_{self.ROSTER[char]:02d}_NAME", "")
            # Three bosses have different names in Japan and elsewhere; the
            # text file gives both ("Balrog (EN)/M. Bison (JP)"). Use English.
            if "(EN)/" in text:
                text = text.split(" (EN)/")[0]
            return text
        return f"character {char}"

    def changed(self, key, value):
        old = self.last.get(key)
        self.last[key] = value
        return old is not None and old != value

    def poll(self):
        a = self.r.arcade
        phase = a.read_word(self.PHASE)
        p1_char = a.read_byte(self.P1 + self.CHAR)
        p2_char = a.read_byte(self.P2 + self.CHAR)
        speed = a.read_byte(self.SPEED)
        pltype = a.read_byte(self.P1 + self.PLTYPE)
        if phase == 0:
            if self.changed("speed", speed) and speed <= 2:
                speech.say(f"Speed {speed + 1}")
            if self.changed("pltype", pltype) and pltype < len(self.PLTYPES):
                speech.say(self.PLTYPES[pltype])
            if self.changed("p1", p1_char):
                speech.say(self.name(p1_char))
        else:
            self.changed("speed", speed)
            self.changed("pltype", pltype)
            self.changed("p1", p1_char)
        # A round starts when both health values jump to full (they are 0
        # during the versus screen, and the opponent is filled in by then).
        h1, h2 = self.health(self.P1), self.health(self.P2)
        full = h1 == h2 == self.FULL
        if full and self.last.get("full") is False:
            pair = (p1_char, p2_char)
            if pair != self.last_pair:
                speech.say(f"{self.name(p1_char)} versus {self.name(p2_char)}")
                self.last_pair = pair
            else:
                speech.say("Next round")
        self.last["full"] = full


    # ---- hotkey readouts ----
    def percent(self, value, full):
        return max(0, min(100, round(100 * value / full)))

    def health(self, block):
        value = self.r.arcade.read_word(block + self.HEALTH)
        return value - 0x10000 if value >= 0x8000 else value  # it can dip below 0

    def health_text(self, block):
        return f"{self.percent(self.health(block), self.FULL)} percent"

    def your_health(self):
        return f"Health {self.health_text(self.P1)}"

    def enemy_health(self):
        name = self.name(self.r.arcade.read_byte(self.P2 + self.CHAR))
        return f"{name} {self.health_text(self.P2)}"

    def meter(self):
        value = self.r.arcade.read_byte(self.P1 + self.METER)
        if value >= self.METER_FULL:
            return "Super ready"
        return f"Meter {self.percent(value, self.METER_FULL)} percent"

    def time_left(self):
        if self.TIMER is None:
            return "Round time not available yet"
        v = self.r.arcade.read_byte(self.TIMER)
        return f"Time {(v >> 4) * 10 + (v & 15)}"

    def rounds(self):
        if self.ROUNDS is None:
            return "Rounds not available yet"
        a = self.r.arcade
        return f"Rounds won: you {a.read_byte(self.P1 + self.ROUNDS)}, opponent {a.read_byte(self.P2 + self.ROUNDS)}"


GAME_READERS = {"hsf2": HSF2}


class ArcadeReader:
    # hotkey letter -> game reader method name
    KEYS = {"H": "your_health", "G": "enemy_health", "T": "time_left", "M": "meter", "R": "rounds"}

    def speak_stat(self, method):
        if self.game_reader is None or not hasattr(self.game_reader, method):
            speech.say("Not in a fight")
            return
        try:
            speech.say(getattr(self.game_reader, method)())
        except Exception:
            speech.say("Not available")

    def bind_keys(self, hotkeys):
        for key, method in self.KEYS.items():
            hotkeys.bind(key, lambda m=method: self.speak_stat(m))

    def __init__(self, game, messages):
        self.msg = messages
        self.arcade = arcade.Arcade(game)
        self.key = None
        self.game_reader = None

    def poll(self):
        a = self.arcade
        try:
            if a.base is None and not a.locate():
                return
            print_ = a.game.pm.read_bytes(a.base, 8)
        except Exception:
            a.base = None
            return
        key = FINGERPRINTS.get(print_)
        if key != self.key:
            self.key = key
            self.game_reader = GAME_READERS[key](self) if key in GAME_READERS else None
        if self.game_reader is not None:
            try:
                self.game_reader.poll()
            except Exception:
                a.base = None  # the board moved (game changed): find it again
