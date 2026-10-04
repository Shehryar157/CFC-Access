"""Reading text drawn inside the arcade games (story, win quotes, endings).

The arcade boards draw text as tiles in each game's own font, so instead of
decoding ten fonts we let Windows' built-in text recognition (OCR, part of
Windows 10/11, offline) read a picture of the game window.

capture() takes the picture the way tools/win.py's screenshots do
(PrintWindow asks the window for its current image, even behind other
windows); read_text() runs the recognizer on it.
"""
import asyncio
import ctypes
from ctypes import wintypes

from PIL import Image, ImageFilter, ImageOps

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32


def capture(hwnd):
    """The game window's current picture, as a PIL image (or None)."""
    rect = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rect))
    w, h = rect.right, rect.bottom
    if w <= 0 or h <= 0:
        return None
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
    return Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1).convert("RGB")


def prepare(image):
    """The arcade games draw text in bright pixel fonts with gaps between
    the letters, over busy backgrounds. Keep only the bright pixels, as
    black text on white, and thicken the letters so the gaps close."""
    grey = ImageOps.grayscale(image)
    text = grey.point(lambda v: 0 if v > 170 else 255)
    return text.filter(ImageFilter.MinFilter(3)).convert("RGBA")


def prepare_soft(image):
    """Second try for text that isn't bright: grey, scanlines smoothed."""
    image = ImageOps.grayscale(image)
    w, h = image.size
    image = image.resize((w // 2, h // 2), Image.BILINEAR)
    return image.resize((w, h), Image.BILINEAR).convert("RGBA")


ALWAYS_ON_SCREEN = {"FREE PLAY", "FREE", "PLAY", "PLEASE WAIT", "INSERT COIN", "PRESS START"}


def _score(lines):
    return sum(1 for l in lines for w in l.split() if len(w) >= 2 and w.strip(".,!?'\"").isalpha())


async def _recognize(image):
    from winrt.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
    from winrt.windows.media.ocr import OcrEngine
    from winrt.windows.storage.streams import DataWriter
    engine = OcrEngine.try_create_from_user_profile_languages()
    writer = DataWriter()
    writer.write_bytes(image.tobytes("raw", "BGRA"))
    bitmap = SoftwareBitmap.create_copy_from_buffer(
        writer.detach_buffer(), BitmapPixelFormat.BGRA8, image.width, image.height)
    result = await engine.recognize_async(bitmap)
    # The recognizer sometimes splits a line into pieces and lists them out
    # of order, so rebuild the lines from where each word sits.
    words = []
    for line in result.lines:
        for word in line.words:
            r = word.bounding_rect
            words.append((r.y + r.height / 2, r.x, r.height, word.text))
    words.sort()
    lines, current, current_y, current_h = [], [], None, 0
    for y, x, h, text in words:
        if current and abs(y - current_y) > max(h, current_h) * 0.6:
            lines.append(current)
            current = []
        if not current:
            current_y, current_h = y, h
        current.append((x, text))
    if current:
        lines.append(current)
    return [" ".join(t for _, t in sorted(line)) for line in lines]


def read_text(image):
    """Lines of text recognised in the image (top to bottom)."""
    # Only the arcade picture: the collection puts artwork at both sides.
    w, h = image.size
    image = image.crop((int(w * 0.09), 0, int(w * 0.91), h))
    lines = asyncio.run(_recognize(prepare(image)))
    if _score(lines) < 3:
        other = asyncio.run(_recognize(prepare_soft(image)))
        if _score(other) > _score(lines):
            lines = other
    # Labels the arcade shows all the time aren't part of the story.
    return [l for l in lines if l.strip().upper() not in ALWAYS_ON_SCREEN]


def looks_like_sentence(line):
    """Story text is sentences; the rest of the screen (scores, timers,
    logos) comes out as short fragments mixed with digits. Automatic
    reading only speaks lines of three or more real words."""
    words = [w.strip(".,!?'\"-:;()") for w in line.split()]
    real = [w for w in words if len(w) >= 2 and w.isalpha()]
    junk = [w for w in words if any(c.isdigit() for c in w) and any(c.isalpha() for c in w)]
    return len(real) >= 3 and len(real) >= 0.6 * len(words) and not junk


class ScreenReader:
    """Reading the text on the game screen aloud (story, win quotes,
    endings...). Recognition takes about half a second, so it runs on a
    background thread and the mod keeps polling meanwhile.

    read_screen(): Enter in a game with no menu open.
    Automatic reading (Alt+T toggles it): outside fights, the screen
    is checked about once a second; text is spoken once it has stopped
    changing (story text types itself out), and lines already spoken are
    not repeated.
    """
    AUTO_INTERVAL = 1.0

    def __init__(self, hwnd_getter):
        from . import settings
        self.hwnd_getter = hwnd_getter
        self.busy = False
        self.auto = settings.get("auto_read", False)
        self.last_check = 0.0
        self.previous = []     # lines seen at the last automatic check
        self.spoken = set()    # lines already read out automatically

    def _start(self, target):
        import threading
        if self.busy:
            return
        self.busy = True
        threading.Thread(target=target, daemon=True).start()

    def _lines(self):
        hwnd = self.hwnd_getter()
        image = capture(hwnd) if hwnd else None
        return read_text(image) if image else []

    def read_screen(self):
        self._start(self._run)

    def _run(self):
        from . import speech
        try:
            lines = self._lines()
            speech.say(". ".join(lines) if lines else "No text found")
        except Exception as e:
            print(f"screen reading failed: {e!r}")
            speech.say("Screen reading failed")
        finally:
            self.busy = False

    def toggle_auto(self):
        from . import settings, speech
        self.auto = not self.auto
        settings.set("auto_read", self.auto)
        self.previous, self.spoken = [], set()
        speech.say("Auto read on" if self.auto else "Auto read off")

    def poll(self, allowed):
        """Called every loop; allowed = in a game, no menu, not mid-fight."""
        import time
        if not (self.auto and allowed) or self.busy:
            return
        now = time.monotonic()
        if now - self.last_check < self.AUTO_INTERVAL:
            return
        self.last_check = now
        self._start(self._auto_run)

    def _auto_run(self):
        from . import speech
        try:
            lines = [l for l in self._lines() if looks_like_sentence(l)]
            if not lines:
                self.spoken.clear()       # screen cleared: new text may repeat
            elif lines == self.previous:  # finished typing out
                new = [l for l in lines if l not in self.spoken]
                if new:
                    speech.say(". ".join(new), interrupt=False)
                    self.spoken.update(new)
            self.previous = lines
        except Exception as e:
            print(f"auto read failed: {e!r}")
        finally:
            self.busy = False
