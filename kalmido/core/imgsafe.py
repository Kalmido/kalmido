"""2.1385.0 (#6435 point 1): one way to decode a foreign picture inside the app process.

Before, every place that took a picture (profile picture, list icon, list head, office logo, PDF logo, contact photo for the
address book clients, the pictures of a knowledge page as a Word file) opened it with Pillow on its own: every format Pillow
knows (EPS, TIFF, ...), a pixel limit of its own (up to 60 M) and no limit on how many decode at once. Here instead:
 - Image.open(..., formats=...): only the formats the caller names (default IMG_FORMATS), the rest is "not a picture"
 - the pixels come from the header and are checked against max_pixels (default IMG_MAX_PIXELS) BEFORE load(); a JPEG the
   caller wants small (draft=(w, h)) is checked at its full size against IMG_MAX_FULL, then at the reduced scale Pillow
   will decode it at
 - at most IMG_BUSY_N pictures decode at once in a process (one shared lock); a caller waits up to IMG_WAIT_S, then "busy"
The lock is held for the whole `with` block, so the caller's resizing and saving counts too.
Standard library + Pillow only, no package imports: kalmido/office/pdf.py also runs as a single file (tests) and loads this
file by its path then. Every refusal is an ImgRefused with .reason in format / size / broken / busy; the caller turns it into its
own message. An ImportError (no Pillow) is left to the caller as before."""
import contextlib
import io
import threading

IMG_FORMATS = ("JPEG", "PNG", "WEBP", "GIF", "BMP")
IMG_MAX_PIXELS = 16_000_000  # #6435: 12-20 M; a 12 MP phone photo (4032 x 3024) passes, a 48 MP one is refused undrafted
IMG_MAX_FULL = 60_000_000  # a drafted JPEG's full size (its decoder may still hold that much), the old 60 M of the photo routes
IMG_BUSY_N = 2
IMG_BUSY = threading.BoundedSemaphore(IMG_BUSY_N)
IMG_WAIT_S = 20


class ImgRefused(ValueError):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def _open(raw, formats):
    from PIL import Image
    try:
        return Image.open(io.BytesIO(raw), formats=list(formats))  # reads the header only
    except Image.DecompressionBombError:  # Pillow's own hard limit (twice its process-wide one) already at the header
        raise ImgRefused("size") from None
    except Exception:  # noqa: BLE001  (not one of the formats, not a picture at all)
        raise ImgRefused("format") from None


def img_head(raw, formats=IMG_FORMATS):
    """(width, height, format) from the header only - nothing is decoded, no lock. ImgRefused("format")."""
    im = _open(raw, formats)
    try:
        return im.width, im.height, im.format
    finally:
        im.close()


@contextlib.contextmanager
def img_open(raw, formats=IMG_FORMATS, max_pixels=IMG_MAX_PIXELS, draft=None):
    """`with img_open(raw) as im:` - the picture decoded (load() done) under the shared lock; ImgRefused when it is not one
    of formats, larger than max_pixels (after a JPEG's draft), broken, or the lock stays taken for IMG_WAIT_S."""
    from PIL import Image  # noqa: F401  (ImportError to the caller: "no Pillow on this server")
    if not IMG_BUSY.acquire(timeout=IMG_WAIT_S):
        raise ImgRefused("busy")
    try:
        im = _open(raw, formats)
        if draft and im.format == "JPEG":
            if im.width * im.height > max(max_pixels, IMG_MAX_FULL):  # reader F1 of 2.1385: the full size first, then the draft
                raise ImgRefused("size")
            im.draft("RGB", tuple(draft))  # decode at a reduced scale (fast, little memory); the size below is the reduced one
        if im.width * im.height > max_pixels:
            raise ImgRefused("size")
        try:
            im.load()
        except Exception:  # noqa: BLE001  (truncated, broken)
            raise ImgRefused("broken") from None
        yield im
    finally:
        IMG_BUSY.release()
