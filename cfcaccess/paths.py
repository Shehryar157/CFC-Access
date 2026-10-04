"""Where things are: the mod's own folder and the game's install folder."""
import os
import re
import sys

APP_ID = "1685750"                       # Capcom Fighting Collection on Steam
GAME_EXE = "CapcomFightingCollection.exe"


def app_dir():
    """The folder the mod runs from (holds settings, sounds and logs)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def steam_dir():
    """Steam's own folder, from the registry (None if Steam isn't installed)."""
    import winreg
    for root, key, value in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
                             (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath")):
        try:
            with winreg.OpenKey(root, key) as k:
                return os.path.normpath(winreg.QueryValueEx(k, value)[0])
        except OSError:
            continue
    return None


def steam_libraries():
    """Every Steam library folder (games can be on several drives)."""
    steam = steam_dir()
    if not steam:
        return []
    libraries = [steam]
    vdf = os.path.join(steam, "steamapps", "libraryfolders.vdf")
    try:
        with open(vdf, encoding="utf-8", errors="replace") as f:
            for path in re.findall(r'"path"\s+"([^"]+)"', f.read()):
                path = os.path.normpath(path.replace("\\\\", "\\"))
                if os.path.normcase(path) not in map(os.path.normcase, libraries):
                    libraries.append(path)
    except OSError:
        pass
    return libraries


def is_game_dir(path):
    return bool(path) and os.path.isfile(os.path.join(path, GAME_EXE))


def find_game_dir():
    """The game's install folder, or None if it can't be found.

    Installed copies of the mod live in <game>\\CFCAccess, so the parent
    folder is checked first; otherwise Steam's libraries are searched.
    """
    parent = os.path.dirname(app_dir())
    if is_game_dir(parent):
        return parent
    for library in steam_libraries():
        manifest = os.path.join(library, "steamapps", f"appmanifest_{APP_ID}.acf")
        try:
            with open(manifest, encoding="utf-8", errors="replace") as f:
                folder = re.search(r'"installdir"\s+"([^"]+)"', f.read())
        except OSError:
            continue
        if folder:
            path = os.path.join(library, "steamapps", "common", folder.group(1))
            if is_game_dir(path):
                return path
    return None
