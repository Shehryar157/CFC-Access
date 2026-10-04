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

from PIL import Image, ImageOps

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
    """Make pixel-font text easier to recognise: grey, with the CRT-style
    scanlines smoothed away, scaled to a size the recognizer likes."""
    image = ImageOps.grayscale(image)
    w, h = image.size
    image = image.resize((w // 2, h // 2), Image.BILINEAR)   # blends scanlines
    return image.resize((w, h), Image.BILINEAR).convert("RGBA")


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
    return asyncio.run(_recognize(prepare(image)))


class ScreenReader:
    """Enter (in a game, no menu open): read the text on the game screen aloud (story, win quotes,
    endings...). Recognition takes about half a second, so it runs on a
    background thread and the mod keeps polling meanwhile."""

    def __init__(self, hwnd_getter):
        self.hwnd_getter = hwnd_getter
        self.busy = False

    def read_screen(self):
        import threading
        if self.busy:
            return
        self.busy = True
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        from . import speech
        try:
            hwnd = self.hwnd_getter()
            image = capture(hwnd) if hwnd else None
            lines = read_text(image) if image else []
            speech.say(". ".join(lines) if lines else "No text found")
        except Exception as e:
            print(f"screen reading failed: {e!r}")
            speech.say("Screen reading failed")
        finally:
            self.busy = False
