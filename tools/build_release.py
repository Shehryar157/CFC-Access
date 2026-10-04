"""Build the release: the mod as a standalone program, then the installer.

  python tools/build_release.py

1. PyInstaller turns run.py into build/release/CFCAccess/CFCAccess.exe
   (Python and every library included, so users don't need Python).
2. The speech DLLs, the sounds folder and the auto-start loader
   (dinput8.dll) are added next to it.
3. That folder is zipped and packed into the installer, installer/setup.py,
   which PyInstaller turns into dist/CFCAccess-Setup-<version>.exe.
"""
import os
import shutil
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from cfcaccess import VERSION  # noqa: E402

BUILD = os.path.join(ROOT, "build", "release")
APP = os.path.join(BUILD, "CFCAccess")
DIST = os.path.join(ROOT, "dist")
# Imported inside functions, so PyInstaller can't see them by itself.
HIDDEN = ["winrt.windows.media.ocr", "winrt.windows.graphics.imaging",
          "winrt.windows.storage.streams", "winrt.windows.globalization",
          "winrt.windows.foundation", "winrt.windows.foundation.collections"]


def pyinstaller(*args):
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
                    "--workpath", os.path.join(BUILD, "work"),
                    "--specpath", os.path.join(BUILD, "spec"), *args], check=True, cwd=ROOT)


def build_app():
    shutil.rmtree(APP, ignore_errors=True)
    hidden = [a for h in HIDDEN for a in ("--hidden-import", h)]
    pyinstaller("--name", "CFCAccess", "--noconsole", "--onedir",
                "--distpath", BUILD, *hidden, os.path.join(ROOT, "run.py"))
    for dll in os.listdir(os.path.join(ROOT, "native")):
        shutil.copy2(os.path.join(ROOT, "native", dll), APP)
    os.makedirs(os.path.join(APP, "sounds"), exist_ok=True)
    shutil.copy2(os.path.join(ROOT, "sounds", "README.txt"), os.path.join(APP, "sounds"))
    shutil.copy2(os.path.join(ROOT, "loader", "dinput8.dll"), APP)
    shutil.copy2(os.path.join(ROOT, "README.md"), os.path.join(APP, "README.md"))


def build_installer():
    payload = os.path.join(BUILD, "payload.zip")
    with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED) as z:
        for folder, _, files in os.walk(APP):
            for name in files:
                full = os.path.join(folder, name)
                z.write(full, os.path.relpath(full, APP))
    with open(os.path.join(BUILD, "version.txt"), "w") as f:
        f.write(VERSION)
    sep = os.pathsep
    pyinstaller("--name", f"CFCAccess-Setup-{VERSION}", "--onefile", "--noconsole",
                "--uac-admin", "--distpath", DIST, "--paths", ROOT,
                "--add-data", f"{payload}{sep}.",
                "--add-data", f"{os.path.join(BUILD, 'version.txt')}{sep}.",
                os.path.join(ROOT, "installer", "setup.py"))
    print("built", os.path.join(DIST, f"CFCAccess-Setup-{VERSION}.exe"))


if __name__ == "__main__":
    build_app()
    build_installer()
