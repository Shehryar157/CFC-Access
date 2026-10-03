"""Build and install the dinput8.dll loader that starts the mod with the game.

  python tools/build_loader.py build      compile loader/dinput8.dll with zig cc
  python tools/build_loader.py install    build, then copy into the game folder
  python tools/build_loader.py uninstall  remove our files from the game folder
"""
import hashlib
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from cfcaccess.text import GAME_DIR  # noqa: E402

ZIG = r"C:\Users\Administrator\tools\zig\zig.exe"
LOADER = os.path.join(ROOT, "loader")
DLL = os.path.join(LOADER, "dinput8.dll")
OUR_FILES = ["dinput8.dll", "CFCAccess.txt", "CFCAccess_loader.log"]


def build():
    subprocess.run([ZIG, "cc", "-target", "x86_64-windows-gnu", "-shared", "-O2",
                    "-o", DLL, "dinput8.c", "dinput8.def"], cwd=LOADER, check=True)
    print(f"built {DLL}")


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def install():
    build()
    target = os.path.join(GAME_DIR, "dinput8.dll")
    # Never overwrite somebody else's dinput8.dll (e.g. another mod's).
    marker = os.path.join(GAME_DIR, "CFCAccess.txt")
    if os.path.exists(target) and not os.path.exists(marker):
        sys.exit(f"{target} exists and isn't ours; not overwriting it")
    shutil.copyfile(DLL, target)
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    command = f'"{pythonw}" "{os.path.join(ROOT, "run.py")}" --with-game'
    with open(marker, "w", encoding="utf-8") as f:
        f.write(command + "\n")
    print(f"installed {target}\nCFCAccess.txt: {command}")
    assert sha(DLL) == sha(target)


def uninstall():
    for name in OUR_FILES:
        path = os.path.join(GAME_DIR, name)
        if os.path.exists(path):
            os.remove(path)
            print(f"removed {path}")


if __name__ == "__main__":
    {"build": build, "install": install, "uninstall": uninstall}[sys.argv[1]]()
