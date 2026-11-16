"""2.1281.0 (#6425): the one way a foreign mail (bytes) becomes an email.message object. Python's parser builds every
MIME part it is given: a mail of 20.000 tiny parts (140 KB) cost 8 MB, one of 40-50 MB gigabytes and many minutes, and it
was taken apart before anyone knew whom it is for (the instance mailbox) and again in the request that opens it. A header
line built for it (a sender with 500 opening brackets) or 2.000 parts inside each other end in a RecursionError.

  mail_parse(raw) -> the message, or raises MailRefused (a ValueError; .code "head" / "parts" / "depth")

 1. before the parser, on the raw bytes: the head (up to the first empty line) at most MAIL_HEAD_MAX; the lines that can be
    a part boundary (they start with "--") at most MAIL_PARTS_MAX. Only a mail with more such lines (a text with many "--"
    lines: a patch, an SQL file) is counted exactly: the lines that are one of the boundaries the mail declares. A mail
    that declares more than MAIL_DEPTH_MAX boundaries (a digest does) is followed line by line: how deep its boundaries
    open inside each other (the parser of Python 3.12 took 33 s for 2.000 of them before it gave up).
 2. after the parser, exactly and without recursion: parts, depth, the header size of every part; the header lines are read
    once here, so one that breaks the header parser refuses the mail in one place (never somewhere in an importer).

Only the standard library: every reader of foreign mail uses it (integrations/mail.py, hub/mailbox.py, hub/mailrules.py,
hub/mailview.py)."""
import email
import email.policy
import re
from itertools import islice

MAIL_PARTS_MAX = 2000         # MIME parts of one mail (the decision of #6425)
MAIL_HEAD_MAX = 256 * 1024    # bytes of the head of a mail and of the header lines of one part
MAIL_DEPTH_MAX = 50           # parts inside each other (a forwarded forward of a forward ... stays far below)
MAIL_BOUNDS_MAX = 2000        # declared boundaries looked at in the exact count (each one is a part itself)

# what the parser takes as the end of a line: its feed splits with str.splitlines, which knows more than \r and \n
_EOL = rb"\n\r\x0b\x0c\x1c\x1d\x1e"
_DELIM = re.compile(rb"(?:^|[" + _EOL + rb"])--([^" + _EOL + rb"]*)")
_HEAD_END = re.compile(rb"\r?\n\r?\n|\r\r")
_BOUND_ANY = re.compile(rb"(?i)boundary[ \t\r\n]*(\*[0-9*]*)?[ \t\r\n]*=")
_BOUND = re.compile(rb'(?i)boundary[ \t\r\n]*=[ \t\r\n]*(?:"([^"\r\n]{1,300})"|([^\s;"]{1,300}))(?=[\s;]|$)')


class MailRefused(ValueError):
    """A mail that is not taken apart. code: "head" (the head or a part's header lines too large, a header line the parser
    breaks on), "parts" (too many parts), "depth" (parts too deep inside each other)."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


def _declared(raw):
    """The boundaries the mail declares (bytes), or None when one of them is written in a way this reader does not follow
    exactly (RFC 2231 pieces, a quoted pair, a comment): then every "--" line counts."""
    out, n = set(), 0
    for m in _BOUND_ANY.finditer(raw):
        n += 1
        if m.group(1) or n > MAIL_BOUNDS_MAX:
            return None
    got = 0
    for m in _BOUND.finditer(raw):
        got += 1
        b = m.group(1) if m.group(1) is not None else m.group(2)
        if b"\\" in b or (m.group(1) is None and b"(" in b):
            return None
        out.add(b.rstrip(b" \t"))  # (the parser drops the white space at the end of a quoted boundary as well)
        out.add(b)
    return out if got == n else None


def mail_precheck(raw):
    """Step 1 (see above): raises MailRefused for a head over MAIL_HEAD_MAX, more than MAIL_PARTS_MAX boundary lines or
    boundaries that open more than MAIL_DEPTH_MAX deep inside each other. Passes over the bytes; nothing is built."""
    if len(raw) > MAIL_HEAD_MAX and not _HEAD_END.search(raw, 0, MAIL_HEAD_MAX + 4):
        raise MailRefused("head")
    few_lines = sum(1 for _ in islice(_DELIM.finditer(raw), MAIL_PARTS_MAX + 1)) <= MAIL_PARTS_MAX
    few_bounds = sum(1 for _ in islice(_BOUND_ANY.finditer(raw), MAIL_DEPTH_MAX + 1)) <= MAIL_DEPTH_MAX
    if few_lines and few_bounds:
        return  # (every part needs a boundary line, every level a boundary of its own)
    bounds = _declared(raw)
    if bounds is None:
        raise MailRefused("parts" if not few_lines else "depth")
    n, open_ = 0, []
    for m in _DELIM.finditer(raw):
        ln = m.group(1).rstrip(b" \t")
        end = ln not in bounds and ln.endswith(b"--") and ln[:-2] in bounds
        if end:
            ln = ln[:-2]
        elif ln not in bounds:
            continue
        n += 1
        if n > MAIL_PARTS_MAX:
            raise MailRefused("parts")
        # the boundaries open at this line: one that is open already closes everything opened after it
        if ln in open_:
            del open_[open_.index(ln) + (0 if end else 1):]
        elif not end:
            open_.append(ln)
            if len(open_) > MAIL_DEPTH_MAX:
                raise MailRefused("depth")


def mail_postcheck(msg, top=True):
    """Step 2 (see above) on a parsed message: raises MailRefused. top False = the header lines of the mail itself are not
    read (a caller that only looks at the parts)."""
    todo, n = [(msg, 0)], 0
    while todo:
        part, depth = todo.pop()
        n += 1
        if n > MAIL_PARTS_MAX:
            raise MailRefused("parts")
        if depth > MAIL_DEPTH_MAX:
            raise MailRefused("depth")
        if sum(len(k) + len(v) for k, v in part.raw_items()) > MAIL_HEAD_MAX:
            raise MailRefused("head")
        if top or depth:
            try:
                part.items()  # every header line through the header parser once
            except RecursionError:
                raise MailRefused("head") from None
            except Exception:  # noqa: BLE001 -- any other broken line is the reader's as before (it asks for single lines)
                pass
        sub = part.get_payload() if part.is_multipart() else None
        if isinstance(sub, list):
            todo.extend((p, depth + 1) for p in sub)


def mail_parse(raw, top=True):
    """The message of the bytes raw (email.policy.default), checked before and after the parser; raises MailRefused."""
    mail_precheck(raw)
    try:
        msg = email.message_from_bytes(raw, policy=email.policy.default)
    except RecursionError:
        raise MailRefused("depth") from None
    mail_postcheck(msg, top)
    return msg
