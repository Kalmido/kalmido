"""2.1272.0 (#6422): the one reader for XML that comes from outside (e-invoice, CAMT, DATEV archive, mind map, .xlsx
parts, DAV bodies and answers, RSS / OPML, the listings of an off-site store, SVG pictures).

  sx_events(src, max_bytes=, max_elements=, max_depth=, want=)  -> (event, element) pairs of ET.XMLPullParser
  sx_tree(src, max_bytes=, max_elements=, max_depth=)           -> the root element of the whole tree
  XmlRefused(reason)   reason: "nul" | "dtd" | "size" | "elements" | "depth" | "names"; broken XML stays ET.ParseError

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
  * the same once more at the parser: a second expat parser (the guard) reads every piece BEFORE the tree parser gets
    it and stops AT the DOCTYPE declaration, in whichever encoding expat itself detected. pyexpat stops the parse inside
    the handler; ElementTree's own parser would go on to the end of the piece it was fed (and so unfold the entities of
    a whole document fed at once). The tests (p21272_a_xml) switch the byte search off and still get every DOCTYPE
    refused. With strict=False the byte search ends at the first element (a calendar answer or a feed may carry the
    words "<!DOCTYPE html" inside its content); a real DOCTYPE behind the first element is broken XML for expat.
  * more than max_bytes, max_elements or max_depth -- counted by the guard at the very element, so the tree parser
    never builds the element over the limit. (Counting the tree parser's events is not enough: expat puts off a region
    behind a long unfinished token -- a comment, an attribute -- and then hands over tens of thousands of elements in
    one go, the last ones only in close().)
  * a namespace address longer than SX_URI_MAX ("names"): ElementTree writes the address into every distinct element
    and attribute name, so 30 KB with one long address and many short names took 100 MB without any DTD.

Standard library only and no import from the package: the e-invoice worker (office/einvoice_in.py) loads this file by
its path into a process with a memory limit.
"""
import re
from xml.etree import ElementTree as ET
from xml.parsers import expat

SX_CHUNK = 16384            # bytes fed to the parsers at once
SX_DEPTH = 100              # open elements at once when the caller names no own limit
SX_URI_MAX = 256            # characters of one namespace address (the longest in use have about 120)
_DTD = re.compile(rb"<!\s*(?:DOCTYPE|ENTITY)", re.I)
_DECL = re.compile(r"^\s*<\?xml[^>]*\?>")
_TAIL = 32                  # bytes before a piece that the search sees again (a word cut between two pieces)


class XmlRefused(ValueError):
    """The document is not read: reason is "nul", "dtd", "size", "elements", "depth" or "names"."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


class _Guard:
    """An own expat parser that gets every piece before the tree parser: it ends the parse at a DOCTYPE declaration, at
    the element over max_elements / max_depth and at a namespace address that is too long. expat puts off a token that
    is not complete yet (a long comment over many pieces: "reparse deferral") and reads it with a later piece or at the
    end; both parsers are the same expat and get the same pieces in the same order, this one first, so the tree parser
    never reads a byte this one has not read -- and feed(b"", True) reads what is still put off before the tree parser
    is closed."""

    def __init__(self, max_elements, max_depth):
        self.root_at = None  # the byte where the first element starts, once it has
        self._max, self._deep = max_elements, max_depth
        self._count = self._depth = 0
        self._p = p = expat.ParserCreate(namespace_separator="}")
        p.StartDoctypeDeclHandler = self._dtd
        p.StartNamespaceDeclHandler = self._ns
        p.StartElementHandler = self._start
        p.EndElementHandler = self._end

    def _dtd(self, *a):
        raise XmlRefused("dtd")

    def _ns(self, prefix, uri):
        if uri and len(uri) > SX_URI_MAX:
            raise XmlRefused("names")

    def _start(self, name, attrs):
        if self.root_at is None:
            self.root_at = self._p.CurrentByteIndex
        self._count += 1
        self._depth += 1
        if self._depth > self._deep:
            raise XmlRefused("depth")
        if self._max is not None and self._count > self._max:
            raise XmlRefused("elements")

    def _end(self, name):
        self._depth -= 1

    def feed(self, piece, final=False):
        try:
            self._p.Parse(piece, final)
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


def sx_events(src, *, max_bytes, max_elements=None, max_depth=SX_DEPTH, want=("start", "end"), strict=True):
    """(event, element) pairs of src, read piece by piece with the checks of the module docstring. The caller clears what
    it has read when it streams; stopping early stops reading. max_elements None = the caller counts on its own.
    strict=False: the words DOCTYPE / ENTITY are only searched up to the first element (see the module docstring)."""
    parser = ET.XMLPullParser(want)
    guard = _Guard(max_elements, max_depth)
    seen = 0
    tail = b""
    try:
        for piece in _pieces(src):
            seen += len(piece)
            if seen > max_bytes:
                raise XmlRefused("size")
            if b"\x00" in piece:
                raise XmlRefused("nul")
            if strict and _DTD.search(tail + piece):
                raise XmlRefused("dtd")
            guard.feed(piece)
            if not strict and (guard.root_at is None or guard.root_at > seen - len(piece)):
                # the words only in front of the first element: the guard has read this piece (and refused a DOCTYPE)
                probe = tail + piece
                if _DTD.search(probe if guard.root_at is None else probe[:len(tail) + guard.root_at - (seen - len(piece))]):
                    raise XmlRefused("dtd")
            tail = (tail + piece)[-_TAIL:]  # also after a piece of one byte
            parser.feed(piece)
            yield from parser.read_events()
        guard.feed(b"", True)  # what expat has put off so far, before close() reads it into the tree
        parser.close()
    except UnicodeError as e:  # a str with lone surrogates
        raise ET.ParseError(str(e)) from None
    yield from parser.read_events()


def sx_tree(src, *, max_bytes, max_elements, max_depth=SX_DEPTH, strict=True):
    """The root element of src as a whole tree; XmlRefused / ET.ParseError (also for a document without an element)."""
    root = None
    for _ev, el in sx_events(src, max_bytes=max_bytes, max_elements=max_elements, max_depth=max_depth, want=("start",), strict=strict):
        if root is None:
            root = el
    if root is None:
        raise ET.ParseError("no element found")
    return root
