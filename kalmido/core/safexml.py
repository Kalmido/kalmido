"""2.1272.0 (#6422): the one reader for XML that comes from outside (e-invoice, CAMT, DATEV archive, mind map, .xlsx
parts, DAV bodies and answers, RSS / OPML, the listings of an off-site store, SVG pictures).

  sx_events(src, max_bytes=, max_elements=, max_depth=, want=)  -> (event, element) pairs of ET.XMLPullParser
  sx_tree(src, max_bytes=, max_elements=, max_depth=)           -> the root element of the whole tree
  sx_check(src, ...)                                             -> None; reads the document and keeps nothing
  XmlRefused(reason)   reason: "nul" | "dtd" | "size" | "elements" | "depth"; broken XML stays ET.ParseError

src is bytes, a str (text a caller decoded already: a leading XML declaration is dropped, its encoding no longer
holds) or an iterable of bytes pieces (a stream out of an archive).

What it refuses, and why:
  * a NUL byte anywhere. UTF-16 / UTF-32 need NUL for every ASCII character, and a byte search for "<!DOCTYPE" is blind
    in them: UTF-16 without a byte order mark decodes as UTF-8 text with NULs in between, a search on that text sees
    nothing, and expat detects UTF-16 on its own and unfolds the entities. Without NUL only ASCII compatible encodings
    are left (expat refuses every other one), so the byte search below sees what the parser sees. A caller that wants
    to accept UTF-16 with a byte order mark decodes it first and passes the text.
  * a DOCTYPE or an ENTITY anywhere in the document (not only in its first bytes): entities and attribute defaults
    (ATTLIST) exist only inside a DOCTYPE; both make a small file fill the memory.
  * the same once more at the parser: a second expat parser reads the prolog and stops AT the DOCTYPE declaration, in
    whichever encoding expat itself detected. pyexpat stops the parse inside the handler; ElementTree's own parser would
    go on to the end of the piece it was fed (and so unfold the entities of a whole document fed at once). The tests
    (p21272_a_xml) switch the byte search off and still get every DOCTYPE refused, also behind a long comment.
  * more than max_bytes, max_elements or max_depth -- counted while reading, after every piece of SX_CHUNK bytes, so a
    document over its limit is left after a few thousand elements and not after the whole of it.

Standard library only and no import from the package: the e-invoice worker (office/einvoice_in.py) loads this file by
its path into a process with a memory limit.
"""
import re
from xml.etree import ElementTree as ET
from xml.parsers import expat

SX_CHUNK = 16384            # bytes fed to the parser at once: without a DTD at most SX_CHUNK / 4 elements per piece
SX_DEPTH = 100              # open elements at once when the caller names no own limit
_DTD = re.compile(rb"<!\s*(?:DOCTYPE|ENTITY)", re.I)
_DECL = re.compile(r"^\s*<\?xml[^>]*\?>")
_TAIL = 32                  # bytes of the piece before that the search sees again (a word cut between two pieces)


class XmlRefused(ValueError):
    """The document is not read: reason is "nul", "dtd", "size", "elements" or "depth"."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


class _RootSeen(Exception):
    pass


class _Prolog:
    """Reads the pieces up to the first element with an own expat parser: a DOCTYPE declaration ends the parse at once."""

    def __init__(self):
        self.done = False
        self._p = expat.ParserCreate()
        self._p.StartDoctypeDeclHandler = self._dtd
        self._p.StartElementHandler = self._root

    def _dtd(self, *a):
        raise XmlRefused("dtd")

    def _root(self, *a):
        raise _RootSeen()

    def feed(self, piece, final=False):
        """One piece, BEFORE the tree parser gets it. expat puts off a token that is not complete yet (a long comment
        over many pieces: "reparse deferral") and reads it with a later piece or at the end; both parsers are the same
        expat and get the same pieces in the same order, this one first, so the tree parser never reads a byte of the
        prolog this one has not read -- and final=True reads what is still put off before the tree parser is closed."""
        try:
            self._p.Parse(piece, final)
        except _RootSeen:
            self.done = True
        except expat.ExpatError as e:
            raise ET.ParseError(str(e)) from None


def _pieces(src):
    """src as bytes pieces of at most SX_CHUNK bytes."""
    if isinstance(src, str):
        if "\x00" in src:
            raise XmlRefused("nul")
        text = _DECL.sub("", src.lstrip("\ufeff"), count=1)
        # SX_CHUNK characters are at most 4 * SX_CHUNK bytes; cut again below
        src = (text[i:i + SX_CHUNK].encode("utf-8") for i in range(0, len(text), SX_CHUNK))
    elif isinstance(src, (bytes, bytearray, memoryview)):
        src = (bytes(src),)
    for part in src:
        for i in range(0, len(part), SX_CHUNK):
            yield part[i:i + SX_CHUNK]


def sx_events(src, *, max_bytes, max_elements=None, max_depth=SX_DEPTH, want=("start", "end")):
    """(event, element) pairs of src, read piece by piece with the checks of the module docstring. The caller clears what
    it has read when it streams; stopping early stops reading. max_elements None = the caller counts on its own."""
    parser = ET.XMLPullParser(("start", "end"))
    prolog = _Prolog()
    seen = count = depth = 0
    tail = b""
    try:
        for piece in _pieces(src):
            seen += len(piece)
            if seen > max_bytes:
                raise XmlRefused("size")
            if b"\x00" in piece:
                raise XmlRefused("nul")
            if _DTD.search(tail + piece):
                raise XmlRefused("dtd")
            tail = piece[-_TAIL:]
            if not prolog.done:
                prolog.feed(piece)
            parser.feed(piece)
            for ev, el in parser.read_events():
                if ev == "start":
                    count += 1
                    depth += 1
                    if depth > max_depth:
                        raise XmlRefused("depth")
                    if max_elements is not None and count > max_elements:
                        raise XmlRefused("elements")
                else:
                    depth -= 1
                if ev in want:
                    yield ev, el
        if not prolog.done:
            prolog.feed(b"", True)  # what expat has put off so far (see _Prolog.feed), before close() reads it into the tree
        parser.close()
    except UnicodeError as e:  # a str with lone surrogates, a piece the parser cannot decode
        raise ET.ParseError(str(e)) from None
    for ev, el in parser.read_events():
        if ev in want:
            yield ev, el


def sx_tree(src, *, max_bytes, max_elements, max_depth=SX_DEPTH):
    """The root element of src as a whole tree; XmlRefused / ET.ParseError (also for a document without an element)."""
    root = None
    for _ev, el in sx_events(src, max_bytes=max_bytes, max_elements=max_elements, max_depth=max_depth, want=("start",)):
        if root is None:
            root = el
    if root is None:
        raise ET.ParseError("no element found")
    return root


def sx_check(src, *, max_bytes, max_elements, max_depth=SX_DEPTH):
    """Reads src to its end with the same checks and keeps nothing (what was read is cleared): None, or it raises."""
    for _ev, el in sx_events(src, max_bytes=max_bytes, max_elements=max_elements, max_depth=max_depth, want=("end",)):
        el.clear()
