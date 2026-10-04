"""The game's own menu text, loaded from its message archive.

msg.arc holds ui\\0_system\\00_font\\menu_<lang>, a GMD file mapping keys like
"OFFLINE_PLAY" to text like "Offline Play". Using the game's files means we
never copy text into the mod, and other languages are a different file name.
"""
import os
import re

from . import arc, gmd

MSG_ARC = os.path.join("nativeDX11x64", "arc", "pc", "msg.arc")
GMD_TYPE = 0x242BB29A

# Formatting tags the game uses inside strings, e.g. <SIZE 58> or <ICON DECIDE>.
_TAG = re.compile(r"<[^>]*>")


def clean(text):
    """Make a game string fit for speech: drop tags, join lines."""
    text = _TAG.sub("", text)
    text = text.replace("\r\n", " ").replace("\n", " ")
    return " ".join(text.split())


class Messages:
    def __init__(self, game_dir=None, lang="eng"):
        from .paths import find_game_dir
        game_dir = game_dir or find_game_dir()
        if not game_dir:
            raise FileNotFoundError("Capcom Fighting Collection's folder was not found")
        path = os.path.join(game_dir, MSG_ARC)
        wanted = rf"ui\0_system\00_font\menu_{lang}"
        for entry in arc.read_entries(path):
            if entry["type"] == GMD_TYPE and entry["name"] == wanted:
                pairs = gmd.parse_gmd(arc.read_file(path, entry))
                break
        else:
            raise FileNotFoundError(f"{wanted} not found in {path}")
        self._by_key = {key: text for key, text in pairs if key}
        self._by_index = [text for _, text in pairs]

    def get(self, key, default=None):
        """Cleaned text for a key, or default if the key doesn't exist."""
        text = self._by_key.get(key)
        return clean(text) if text is not None else default

    def raw_by_index(self, index, default=""):
        """Uncleaned text (tags kept) for a message number."""
        if 0 <= index < len(self._by_index):
            return self._by_index[index]
        return default

    def by_index(self, index, default=None):
        """Cleaned text for a message number (the game's tables store these)."""
        if 0 <= index < len(self._by_index):
            return clean(self._by_index[index])
        return default
