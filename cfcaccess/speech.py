"""Speech output through Tolk (NVDA, JAWS, or SAPI as a fallback).

Tolk is a C library, so we call it with ctypes: we load the DLL, then tell
Python each function's argument and return types so ctypes converts our
Python strings into the wide-character (UTF-16) strings Tolk expects.
"""
import ctypes
import os
import sys

if getattr(sys, "frozen", False):
    # Running as a PyInstaller exe: the DLLs sit next to the exe.
    NATIVE_DIR = os.path.dirname(sys.executable)
else:
    NATIVE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "native")

_tolk = None


def load():
    """Load Tolk once. Safe to call repeatedly."""
    global _tolk
    if _tolk is not None:
        return
    # Preload the screen reader helper DLLs by full path. When Tolk later asks
    # Windows for them by name, Windows reuses the copies already in memory.
    for helper in ("nvdaControllerClient64.dll", "SAAPI64.dll"):
        path = os.path.join(NATIVE_DIR, helper)
        if os.path.exists(path):
            ctypes.WinDLL(path)
    tolk = ctypes.WinDLL(os.path.join(NATIVE_DIR, "Tolk.dll"))
    tolk.Tolk_Load.restype = None
    tolk.Tolk_TrySAPI.argtypes = [ctypes.c_bool]
    tolk.Tolk_Output.argtypes = [ctypes.c_wchar_p, ctypes.c_bool]
    tolk.Tolk_Output.restype = ctypes.c_bool
    tolk.Tolk_Silence.restype = ctypes.c_bool
    tolk.Tolk_DetectScreenReader.restype = ctypes.c_wchar_p
    tolk.Tolk_TrySAPI(True)  # fall back to SAPI if no screen reader is running
    tolk.Tolk_Load()
    _tolk = tolk


def screen_reader():
    """Name of the active screen reader, e.g. 'NVDA', or None."""
    load()
    return _tolk.Tolk_DetectScreenReader()


def say(text, interrupt=True):
    """Speak (and braille) text. Also printed, so the console is a log."""
    load()
    print("SAY:", text, flush=True)
    _tolk.Tolk_Output(text, interrupt)


def silence():
    load()
    _tolk.Tolk_Silence()
