"""Event sounds: play sounds\\<name>.wav, or speak a fallback phrase.

The user supplies the .wav files; until a file exists the mod says a short
phrase instead, so every event is usable from the start. winsound plays
WAV files only, one at a time (a new sound replaces one still playing).
"""
import os
import sys

from . import speech

if getattr(sys, "frozen", False):
    SOUND_DIR = os.path.join(os.path.dirname(sys.executable), "sounds")
else:
    SOUND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sounds")

# event name -> phrase spoken when sounds\<name>.wav doesn't exist
EVENTS = {
    "low_health": "Low health",
    "enemy_low_health": "Enemy low health",
    "super_ready": "Super ready",
    "enemy_super_ready": "Enemy super ready",
    "time_low": "10 seconds",
    "round_won": "Round won",
    "round_lost": "Round lost",
    "danger": "Danger",          # Puzzle Fighter: middle columns nearly full
}


def play(name):
    path = os.path.join(SOUND_DIR, name + ".wav")
    if os.path.exists(path):
        try:
            import winsound
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
            print(f"SOUND: {name}")
            return
        except Exception as e:
            print(f"sound {name} failed: {e!r}")
    speech.say(EVENTS.get(name, name), interrupt=False)
