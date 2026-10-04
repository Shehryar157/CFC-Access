"""Research helpers: find the game window, press keys in it, screenshot it.

Usage:
  python tools/win.py shot [out.png]        screenshot the game window
  python tools/win.py keys down down enter  press keys (with a pause between)
"""
import ctypes
import sys
import time
from ctypes import wintypes

sys.path.insert(0, __file__.rsplit("tools", 1)[0])
from cfcaccess import game as game_mod  # noqa: E402

user32 = ctypes.WinDLL("user32", use_last_error=True)
ctypes.windll.shcore.SetProcessDpiAwareness(2)  # real pixel coordinates

# Scan codes (what the keyboard hardware sends). Arrows etc. are "extended"
# keys, which the hardware sends with an extra E0 prefix byte.
SCAN = {
    "esc": (0x01, False), "enter": (0x1C, False), "space": (0x39, False),
    "backspace": (0x0E, False), "tab": (0x0F, False),
    "up": (0x48, True), "down": (0x50, True), "left": (0x4B, True), "right": (0x4D, True),
    "pgup": (0x49, True), "pgdn": (0x51, True),
    "z": (0x2C, False), "x": (0x2D, False), "c": (0x2E, False), "v": (0x2F, False),
    "a": (0x1E, False), "s": (0x1F, False), "d": (0x20, False), "w": (0x11, False),
    "q": (0x10, False), "e": (0x12, False), "f1": (0x3B, False),
    "ctrl": (0x1D, False), "u": (0x16, False), "i": (0x17, False), "o": (0x18, False),
    "j": (0x24, False), "k": (0x25, False), "l": (0x26, False), "ralt": (0x38, True),
    "g": (0x22, False), "h": (0x23, False), "t": (0x14, False), "m": (0x32, False), "r": (0x13, False), "f2": (0x3C, False), "f3": (0x3D, False), "f4": (0x3E, False),
    "f5": (0x3F, False), "f6": (0x40, False), "f7": (0x41, False), "f8": (0x42, False),
    "f9": (0x43, False), "f10": (0x44, False), "alt": (0x38, False), "rctrl": (0x1D, True), "shift": (0x2A, False), "y": (0x15, False),
}

KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP, KEYEVENTF_SCANCODE = 0x1, 0x2, 0x8


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("pad", ctypes.c_byte * 32)]
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


def find_window(pid):
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(hwnd):
            found.append(hwnd)
        return True

    user32.EnumWindows(callback, 0)
    return found[0] if found else None


def focus(hwnd):
    global _last_hwnd
    _last_hwnd = hwnd
    # Windows only lets the foreground app hand focus around; tapping a key
    # first is the usual workaround for a background script. Not Alt: that's
    # the game's Coin key. F24 exists in Windows but on no real keyboard.
    user32.keybd_event(0x87, 0, 0, 0)
    user32.keybd_event(0x87, 0, KEYEVENTF_KEYUP, 0)
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE: un-minimize
        time.sleep(0.5)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.2)


def _send(scan, extended, up):
    flags = KEYEVENTF_SCANCODE | (KEYEVENTF_EXTENDEDKEY if extended else 0) | (KEYEVENTF_KEYUP if up else 0)
    inp = INPUT(type=1)
    inp.ki = KEYBDINPUT(0, scan, flags, 0, 0)
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


_last_hwnd = None

# ---- Telling the user when the script takes the keyboard ----
# A high beep, then a short wait, before the first key press; the same beep
# lower when the script is done (or pauses for a while between presses).
WARN_PITCH, DONE_PITCH, BEEP_MS = 1200, 700, 90
WARN_LEAD = 1.5          # seconds between the warning beep and the first press
IDLE_GIVE_BACK = 3.0     # no presses for this long hands control back
_holding = False
_last_press = 0.0
_idle_timer = None


def _tone(pitch, ms=BEEP_MS, volume=0.25, rate=22050):
    """A short sine-wave beep as WAV bytes, with soft edges so it doesn't click."""
    import io, math, struct, wave
    n = int(rate * ms / 1000)
    fade = max(1, n // 8)
    frames = bytearray()
    for i in range(n):
        env = min(1.0, i / fade, (n - i) / fade)
        frames += struct.pack("<h", int(32767 * volume * env * math.sin(2 * math.pi * pitch * i / rate)))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(bytes(frames))
    return buf.getvalue()


def _beep(pitch):
    """Play through the normal speakers (winsound.Beep needs a PC speaker)."""
    try:
        import winsound
        winsound.PlaySound(_tone(pitch), winsound.SND_MEMORY)
    except Exception:
        pass


def take_keyboard():
    global _holding
    if not _holding:
        _beep(WARN_PITCH)
        time.sleep(WARN_LEAD)
        _holding = True


def release_keyboard():
    global _holding
    if _idle_timer is not None:
        _idle_timer.cancel()
    if _holding:
        _holding = False
        _beep(DONE_PITCH)


import atexit  # noqa: E402
atexit.register(release_keyboard)  # runs when the script finishes, like a finally:


def _restart_idle_timer():
    """Each press restarts a countdown; if it runs out, we're done for now."""
    global _idle_timer
    import threading
    if _idle_timer is not None:
        _idle_timer.cancel()
    _idle_timer = threading.Timer(IDLE_GIVE_BACK, release_keyboard)
    _idle_timer.daemon = True
    _idle_timer.start()


def press(name, hold=0.1):
    global _last_press
    take_keyboard()
    if _idle_timer is not None:
        _idle_timer.cancel()
    # Key presses go to whatever window is in front, so make sure it's the game.
    if _last_hwnd and user32.GetForegroundWindow() != _last_hwnd:
        focus(_last_hwnd)
    scan, extended = SCAN[name]
    _send(scan, extended, False)
    time.sleep(hold)  # games poll input once per frame, so hold for a few frames
    _send(scan, extended, True)
    _last_press = time.time()
    _restart_idle_timer()


def screenshot(hwnd, path):
    """Capture the window with PrintWindow(PW_RENDERFULLCONTENT).

    A plain screen grab often returns black for DirectX games; this flag asks
    the desktop compositor for the window's real image instead.
    """
    from PIL import Image
    gdi32 = ctypes.windll.gdi32
    rect = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rect))
    w, h = rect.right, rect.bottom
    hdc_window = user32.GetDC(hwnd)
    hdc = gdi32.CreateCompatibleDC(hdc_window)
    bmp = gdi32.CreateCompatibleBitmap(hdc_window, w, h)
    gdi32.SelectObject(hdc, bmp)
    user32.PrintWindow(hwnd, hdc, 3)  # PW_CLIENTONLY | PW_RENDERFULLCONTENT
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetBitmapBits(bmp, len(buf), buf)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(hdc)
    user32.ReleaseDC(hwnd, hdc_window)
    im = Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1).convert("RGB")
    # Scripts use 1280x720 coordinates: scale whatever the game resolution is.
    if im.size != (1280, 720):
        im = im.resize((1280, 720))
    im.save(path)
    return path


def wait_for(check, timeout=1.0, interval=0.02):
    """Wait until check() returns something truthy, or timeout. Returns it.

    Faster than a fixed sleep: we continue the moment the game has reacted.
    """
    end = time.time() + timeout
    while True:
        try:
            result = check()
        except Exception:
            result = None
        if result or time.time() > end:
            return result
        time.sleep(interval)


def press_until_changed(name, read, timeout=1.0):
    """Press a key and wait until read() returns something different."""
    before = read()
    press(name)
    return wait_for(lambda: read() != before, timeout)


def game_window():
    game = game_mod.try_attach()
    if game is None:
        sys.exit("game not running")
    hwnd = find_window(game.pid)
    if hwnd is None:
        sys.exit("game window not found")
    return game, hwnd


if __name__ == "__main__":
    _, hwnd = game_window()
    cmd = sys.argv[1]
    if cmd == "shot":
        focus(hwnd)
        print(screenshot(hwnd, sys.argv[2] if len(sys.argv) > 2 else "scratch/shot.png"))
    elif cmd == "keys":
        focus(hwnd)
        for key in sys.argv[2:]:
            press(key)
            time.sleep(0.4)
