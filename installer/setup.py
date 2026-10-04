"""CFC Access installer (and uninstaller).

Run CFCAccess-Setup.exe: it finds Capcom Fighting Collection through Steam
(or asks for the folder), copies the mod into <game>\\CFCAccess, and puts
the small auto-start loader (dinput8.dll) and CFCAccess.txt next to the
game, so the mod starts by itself whenever the game does.

The installed copy of this program, "Uninstall CFC Access.exe", removes it
all again. Every message is a standard Windows message box, which screen
readers read in full.
"""
import os
import shutil
import subprocess
import sys
import zipfile

from cfcaccess import paths

TITLE = "CFC Access"
MOD_FOLDER = "CFCAccess"
UNINSTALLER = "Uninstall CFC Access.exe"
LOADER = "dinput8.dll"
CONFIG = "CFCAccess.txt"
BACKUP = "dinput8.dll.before-cfcaccess"
MARKER = "CFCAccess.txt".encode("utf-16-le")   # found only in our loader
KEEP = ("settings.json", "sounds", "logs")      # the user's own files

MB_OK, MB_YESNO, MB_OKCANCEL = 0x0, 0x4, 0x1
MB_ICONINFO, MB_ICONWARN, MB_ICONERROR, MB_ICONQUESTION = 0x40, 0x30, 0x10, 0x20
IDYES, IDOK = 6, 1


def message(text, flags=MB_OK | MB_ICONINFO):
    import ctypes
    return ctypes.windll.user32.MessageBoxW(None, text, TITLE, flags | 0x10000)  # 0x10000: in front


def bundled(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def version():
    try:
        with open(bundled("version.txt")) as f:
            return f.read().strip()
    except OSError:
        return "?"


def is_running(exe):
    out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {exe}", "/NH"],
                         capture_output=True, text=True,
                         creationflags=0x08000000).stdout
    return exe.lower() in out.lower()


def wait_for_game_closed():
    while is_running(paths.GAME_EXE):
        if message("Capcom Fighting Collection is running. Please close it, then press OK.\n\n"
                   "Cancel stops the setup.", MB_OKCANCEL | MB_ICONWARN) != IDOK:
            return False
    # The mod closes with the game; stop a copy that's still running anyway.
    subprocess.run(["taskkill", "/F", "/IM", "CFCAccess.exe"], capture_output=True,
                   creationflags=0x08000000)
    return True


def ask_for_game_dir():
    message("Capcom Fighting Collection wasn't found through Steam.\n\n"
            "Next, choose the game's folder: the one that contains "
            f"{paths.GAME_EXE}.")
    import tkinter
    from tkinter import filedialog
    root = tkinter.Tk()
    root.withdraw()
    while True:
        folder = filedialog.askdirectory(title="Capcom Fighting Collection folder")
        if not folder:
            return None
        folder = os.path.normpath(folder)
        if paths.is_game_dir(folder):
            return folder
        if message(f"{paths.GAME_EXE} isn't in that folder. Choose again?",
                   MB_YESNO | MB_ICONWARN) != IDYES:
            return None


def is_our_loader(path):
    try:
        with open(path, "rb") as f:
            return MARKER in f.read()
    except OSError:
        return False


def install():
    ver = version()
    if message(f"This installs CFC Access {ver}, screen reader support for "
               "Capcom Fighting Collection.\n\nInstall now?",
               MB_YESNO | MB_ICONQUESTION) != IDYES:
        return
    game = paths.find_game_dir() or ask_for_game_dir()
    if not game:
        message("Setup stopped: the game's folder wasn't chosen.", MB_OK | MB_ICONWARN)
        return
    if not wait_for_game_closed():
        return
    target = os.path.join(game, MOD_FOLDER)
    os.makedirs(target, exist_ok=True)
    # Replace the program files; keep the user's settings, sounds and logs.
    for name in os.listdir(target):
        if name in KEEP or name == UNINSTALLER:
            continue
        path = os.path.join(target, name)
        shutil.rmtree(path) if os.path.isdir(path) else os.remove(path)
    with zipfile.ZipFile(bundled("payload.zip")) as z:
        for item in z.infolist():
            if item.filename.startswith("sounds/") and os.path.exists(os.path.join(target, item.filename)):
                continue  # don't overwrite the user's own sounds folder files
            z.extract(item, target)
    # The loader goes next to the game, where the game looks for dinput8.dll.
    loader = os.path.join(game, LOADER)
    if os.path.exists(loader) and not is_our_loader(loader):
        shutil.move(loader, os.path.join(game, BACKUP))   # someone else's: keep it
    shutil.move(os.path.join(target, LOADER), loader)
    exe = os.path.join(target, "CFCAccess.exe")
    with open(os.path.join(game, CONFIG), "w", encoding="utf-8") as f:
        f.write(f'"{exe}" --with-game\n')
    if getattr(sys, "frozen", False):
        shutil.copy2(sys.executable, os.path.join(target, UNINSTALLER))
    message(f"CFC Access {ver} is installed.\n\n"
            "Start Capcom Fighting Collection from Steam as usual; when the mod is "
            f'ready it says "CFC Access version {ver} loaded".\n\n'
            f"To remove it, run \"{UNINSTALLER}\" in:\n{target}")


def uninstall():
    game = os.path.dirname(os.path.dirname(os.path.abspath(sys.executable)))
    if not paths.is_game_dir(game):
        game = paths.find_game_dir()
    if not game:
        message("The game's folder wasn't found, so nothing was removed.", MB_OK | MB_ICONWARN)
        return
    if message("Remove CFC Access from Capcom Fighting Collection?\n\n"
               "Your sound files and settings in the CFCAccess folder are removed too.",
               MB_YESNO | MB_ICONQUESTION) != IDYES:
        return
    if not wait_for_game_closed():
        return
    loader = os.path.join(game, LOADER)
    if is_our_loader(loader):
        os.remove(loader)
    if os.path.exists(os.path.join(game, BACKUP)) and not os.path.exists(loader):
        shutil.move(os.path.join(game, BACKUP), loader)
    for name in (CONFIG, "CFCAccess_loader.log"):
        try:
            os.remove(os.path.join(game, name))
        except OSError:
            pass
    target = os.path.join(game, MOD_FOLDER)
    message("CFC Access has been removed.")
    # This program is inside the folder being deleted: let cmd remove it
    # a moment after we exit.
    subprocess.Popen(f'cmd /c ping -n 3 127.0.0.1 >nul & rmdir /s /q "{target}"',
                     creationflags=0x08000000)


def main():
    name = os.path.basename(sys.executable if getattr(sys, "frozen", False) else sys.argv[0])
    try:
        if "--uninstall" in sys.argv or name.lower().startswith("uninstall"):
            uninstall()
        else:
            install()
    except PermissionError as e:
        message(f"Windows refused to change a file:\n{e}\n\n"
                "Try running the setup again as administrator.", MB_OK | MB_ICONERROR)
    except Exception as e:  # show the problem rather than vanish silently
        message(f"Setup failed:\n{e!r}", MB_OK | MB_ICONERROR)


if __name__ == "__main__":
    main()
