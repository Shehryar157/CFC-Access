"""The mod's own settings, kept in settings.json next to run.py.

Like a tiny dict that remembers itself: get(name, default) reads a value,
set(name, value) changes it and saves the file straight away.
"""
import json
import os
import sys

if getattr(sys, "frozen", False):
    PATH = os.path.join(os.path.dirname(sys.executable), "settings.json")
else:
    PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "settings.json")

_values = None


def _load():
    global _values
    if _values is None:
        try:
            with open(PATH, encoding="utf-8") as f:
                _values = json.load(f)
        except (OSError, ValueError):
            _values = {}
    return _values


def get(name, default=None):
    return _load().get(name, default)


def set(name, value):
    _load()[name] = value
    try:
        with open(PATH, "w", encoding="utf-8") as f:
            json.dump(_values, f, indent=2)
    except OSError as e:
        print(f"could not save settings: {e!r}")
