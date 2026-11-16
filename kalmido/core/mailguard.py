"""2.1281.0 (#6425): the one way a foreign mail (bytes) becomes an email.message object. Python's parser builds every
MIME part it is given: a mail of 20.000 tiny parts (140 KB) cost 8 MB, one of 40-50 MB gigabytes and many minutes, and it
was taken apart before anyone knew whom it is for (the instance mailbox) and again in the request that opens it. A header
line built for it (a sender with 500 opening brackets) or 2.000 parts inside each other end in a RecursionError, and the
header parser of the standard library needs seconds for 16 KB of commas -- every time the line is asked for.

  mail_parse(raw) -> the message, or raises MailRefused (a ValueError; .code "head" / "parts" / "depth" / "lines")
  mail_head(head) -> the message of a few header lines (what an IMAP server gave for a look), or None when refused

 1. before the parser, on the raw bytes (mail_precheck; plain counting): the head (up to the first empty line) at most
    MAIL_HEAD_MAX with header lines inside the limits of step 2, and at most MAIL_LINES_MAX lines (a megabyte of two-byte
    lines costs 40 MB in the parser).
 2. in the parser, so that what counts is what the parser itself sees (this file follows no MIME grammar of its own):
    - it asks a factory for every part it starts, and the factory counts: part MAIL_PARTS_MAX + 1 or a part deeper than
      MAIL_DEPTH_MAX ends the parsing at once (a boundary written in any way, the blocks of a delivery report);
    - it hands every header line of every part to the policy before it reads it (header_source_parse; the parser reads the
      Content-Type of each part itself). The policy of a checked mail (_Guard) refuses there: a structured line (addresses,
      Content-*, Message-ID, date) over MAIL_HLINE_MAX or with more than MAIL_HNEST_MAX opening brackets, any other line
      over MAIL_HTEXT_MAX, and a mail whose structured lines cost more than MAIL_HCOST_MAX together. The cost of a line
      is what the header parser's time follows: its characters that are no letter or digit (each one ends a token: 120
      semicolons in a Content-Type of 150 bytes take 11 ms), s + s * s / 1024 for s of them in one line, plus 3/8 of
      the length of its base64 encoded words (letters and digits to this count, a token per decoded word to the parser).
      Every header line is parsed once per mail and remembered (the standard library parses it again for every reader).
 3. after the parser, without recursion (mail_postcheck): parts and depth once more.

Only the standard library: every reader of foreign mail uses it (integrations/mail.py, hub/mailbox.py, hub/mailrules.py,
hub/mailview.py)."""
import email.feedparser
import email.policy
import re

MAIL_PARTS_MAX = 2000         # MIME parts of one mail (the decision of #6425)
MAIL_HEAD_MAX = 256 * 1024    # bytes of the head of a mail (the decision of #6425)
MAIL_HLINE_MAX = 32 * 1024    # bytes of one structured header line with its folded lines (its cost is the tighter limit)
MAIL_HTEXT_MAX = 64 * 1024    # bytes of any other header line (References, Received, X-...: read in linear time)
MAIL_HNEST_MAX = 100          # opening brackets in one structured header line (comments inside each other)
MAIL_HCOST_MAX = 48_000       # the cost of all structured header lines of one mail together (see above): a To line of 200
                              # named recipients costs 7.000, a mail of 2.000 attachments 40.000; a mail built to be as
                              # slow as the limit allows takes the header parser about a second
MAIL_DEPTH_MAX = 30           # parts inside each other (a forward of a forward ... as attachments: 14 times)
MAIL_LINES_MAX = 1_000_000    # lines of one mail (50 MB of base64 are 650.000)

# the header lines the standard library parses by a grammar (email.headerregistry); every other line is plain text to it
_STRUCTURED = frozenset((
    "date", "resent-date", "orig-date", "sender", "resent-sender", "to", "resent-to", "cc", "resent-cc", "bcc", "resent-bcc",
    "from", "resent-from", "reply-to", "mime-version", "content-type", "content-disposition", "content-transfer-encoding",
    "message-id"))


class MailRefused(ValueError):
    """A mail that is not taken apart. code: "head" (the head or a header line too large, too many brackets in a header
    line, the header lines too costly together), "parts" (too many parts), "depth" (parts too deep inside each other),
    "lines" (too many lines)."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


_ALNUM = b"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
_B64_WORD = re.compile(rb"=\?[^?\s]{1,40}\?[bB]\?([^?\s]*)\?=")  # (no part of it can match in two ways: one pass)


def _line_cost(name, lines, line_max, text_max=MAIL_HTEXT_MAX):
    """The cost of one header line (name; lines = its bytes, one entry per folded line) towards MAIL_HCOST_MAX; raises
    MailRefused for a line over its limit (line_max a structured line, text_max any other)."""
    n = sum(len(x) for x in lines)
    if name.strip().lower() not in _STRUCTURED:
        if n > text_max:
            raise MailRefused("head")
        return 0
    if n > line_max or sum(x.count(b"(") for x in lines) > MAIL_HNEST_MAX:
        raise MailRefused("head")
    s = sum(len(x.translate(None, _ALNUM)) for x in lines)
    b64 = sum(len(m.group(1)) for x in lines for m in _B64_WORD.finditer(x))
    return s + s * s // 1024 + b64 * 3 // 8


class _Guard(email.policy.EmailPolicy):
    """email.policy.default with the limits of step 2 (see above); one object per mail (its state: the cost so far and the
    long lines parsed already)."""

    def header_source_parse(self, sourcelines):
        st = self.__dict__["_st"]
        st["cost"] += _line_cost(sourcelines[0].split(":", 1)[0], [x.encode("utf-8", "surrogateescape") for x in sourcelines],
                                 st["line_max"], st["text_max"])
        if st["cost"] > MAIL_HCOST_MAX:
            raise MailRefused("head")
        return super().header_source_parse(sourcelines)

    def header_fetch_parse(self, name, value):
        if hasattr(value, "name"):
            return super().header_fetch_parse(name, value)
        # every line a reader asks for, parsed once (the readers ask for To / Delivered-To / Subject several times); what
        # the memo can hold is bounded by MAIL_HCOST_MAX, MAIL_PARTS_MAX and the lines the readers ask for
        memo = self.__dict__["_st"]["memo"]
        key = (name.lower(), value)
        if key not in memo:
            memo[key] = super().header_fetch_parse(name, value)
        return memo[key]


def _policy(line_max=MAIL_HLINE_MAX, text_max=MAIL_HTEXT_MAX):
    p = _Guard()
    object.__setattr__(p, "_st", {"cost": 0, "memo": {}, "line_max": line_max, "text_max": text_max})
    return p


def _lines(raw):
    return raw.count(b"\n") + raw.count(b"\r") - raw.count(b"\r\n")  # (what the parser's feed ends a line at)


def mail_precheck(raw):
    """Step 1 (see above): raises MailRefused("head" / "lines"). A few passes over the bytes; nothing is built."""
    cut = raw[:MAIL_HEAD_MAX + 4]
    ends = [i for i in (cut.find(b"\r\n\r\n"), cut.find(b"\n\n"), cut.find(b"\r\r")) if i >= 0]
    if not ends and len(raw) > MAIL_HEAD_MAX:
        raise MailRefused("head")  # no empty line within the limit: the head is too large (or the mail has none)
    name, lines, cost = "", [], 0
    for ln in (cut[:min(ends)] if ends else cut).replace(b"\r\n", b"\n").replace(b"\r", b"\n").split(b"\n") + [b""]:
        if ln[:1] not in (b" ", b"\t"):  # a new header line (else a folded one: it belongs to the line before)
            cost += _line_cost(name, lines, MAIL_HLINE_MAX)
            name, lines = ln.split(b":", 1)[0].decode("ascii", "replace"), []
        lines.append(ln)
    if cost > MAIL_HCOST_MAX:
        raise MailRefused("head")
    if _lines(raw) > MAIL_LINES_MAX:
        raise MailRefused("lines")


def mail_postcheck(msg):
    """Step 3 (see above) on a parsed message: raises MailRefused("parts" / "depth"). No header line is read here."""
    todo, n = [(msg, 0)], 0
    while todo:
        part, depth = todo.pop()
        n += 1
        if n > MAIL_PARTS_MAX + 1:  # (+ the mail itself)
            raise MailRefused("parts")
        if depth > MAIL_DEPTH_MAX:
            raise MailRefused("depth")
        sub = part.get_payload() if part.is_multipart() else None
        if isinstance(sub, list):
            todo.extend((p, depth + 1) for p in sub)


def _parse(raw, policy):
    count = [0]
    parser = None

    def factory(policy=policy):
        count[0] += 1
        if count[0] > MAIL_PARTS_MAX + 1:  # (+ the mail itself)
            raise MailRefused("parts")
        if parser is not None and len(getattr(parser, "_msgstack", ())) > MAIL_DEPTH_MAX:
            raise MailRefused("depth")  # (the open parts of the parser; without that list the postcheck and the except below)
        return email.policy.EmailPolicy.message_factory(policy=policy)
    parser = email.feedparser.BytesFeedParser(factory, policy=policy)
    count[0] = 0  # (the parser tried the factory once when it was made)
    try:
        for i in range(0, len(raw), 65536):  # in pieces: the factory ends it at the piece with part 2.001, not after the
            parser.feed(raw[i:i + 65536])    # parser has cut the whole mail into lines
        return parser.close()
    except RecursionError:
        raise MailRefused("depth") from None


def mail_parse(raw):
    """The message of the bytes raw (the settings of email.policy.default), counted before, in and after the parser; raises
    MailRefused."""
    mail_precheck(raw)
    msg = _parse(raw, _policy())
    mail_postcheck(msg)
    return msg


def mail_head(head, line_max=2048):
    """The message of a few header lines (bytes: what an IMAP server gave for a look at a mail: sender, subject, date,
    Message-ID), or None when they are refused. line_max: every line of a look is short (one sender, one date, a subject);
    a longer one is refused here, where a mail that fits no rule would be read again in every run."""
    try:
        if len(head) > MAIL_HEAD_MAX or _lines(head) > 1000:
            return None
        return _parse(head, _policy(line_max, line_max))
    except MailRefused:
        return None
