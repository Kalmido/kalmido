"""2.1281.0 (#6425): the one way a foreign mail (bytes) becomes an email.message object. Python's parser builds every
MIME part it is given: a mail of 20.000 tiny parts (140 KB) cost 8 MB, one of 40-50 MB gigabytes and many minutes, and it
was taken apart before anyone knew whom it is for (the instance mailbox) and again in the request that opens it. A header
line built for it (a sender with 500 opening brackets) or 2.000 parts inside each other end in a RecursionError.

  mail_parse(raw) -> the message, or raises MailRefused (a ValueError; .code "head" / "parts" / "depth" / "lines")

 1. before the parser, on the raw bytes (mail_precheck; plain counting, no pattern that could be led astray): the head (up to
    the first empty line) at most MAIL_HEAD_MAX, each of its header lines at most MAIL_HLINE_MAX with at most MAIL_HNEST_MAX
    opening brackets (the header parser of the standard library needs seconds for 16 KB of commas and gives up on nested
    brackets), and at most MAIL_LINES_MAX lines (a megabyte of two-byte lines costs 40 MB in the parser).
 2. in the parser: it asks a factory for every part it starts, and the factory counts -- part MAIL_PARTS_MAX + 1 or a part
    deeper than MAIL_DEPTH_MAX ends the parsing at once. So what counts as a part is what the parser itself takes for one
    (a boundary written in any way, the blocks of a delivery report); this file follows no MIME grammar of its own.
 3. after the parser, without recursion (mail_postcheck): depth again, and the header lines of every part like the head.

Only the standard library: every reader of foreign mail uses it (integrations/mail.py, hub/mailbox.py, hub/mailrules.py,
hub/mailview.py)."""
import email.feedparser
import email.policy

MAIL_PARTS_MAX = 2000         # MIME parts of one mail (the decision of #6425)
MAIL_HEAD_MAX = 256 * 1024    # bytes of the head of a mail and of the header lines of one part (the decision of #6425)
MAIL_HLINE_MAX = 8 * 1024     # bytes of one header line (with its folded lines): about 200 recipients in one To line
MAIL_HNEST_MAX = 100          # opening brackets in one header line (comments inside each other)
MAIL_DEPTH_MAX = 20           # parts inside each other (a forward of a forward of a forward ... stays below)
MAIL_LINES_MAX = 1_000_000    # lines of one mail (50 MB of base64 are 650.000)

_EOLS = (b"\n", b"\r", b"\x0b", b"\x0c", b"\x1c", b"\x1d", b"\x1e")  # what the parser's feed (str.splitlines) ends a line at


class MailRefused(ValueError):
    """A mail that is not taken apart. code: "head" (the head, one header line or a part's header lines too large, too many
    brackets in a header line), "parts" (too many parts), "depth" (parts too deep inside each other), "lines" (too many lines)."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


def _line_ok(n, brackets):
    return n <= MAIL_HLINE_MAX and brackets <= MAIL_HNEST_MAX


def mail_head_ok(head):
    """The header lines head (bytes: a mail up to its first empty line, or the lines an IMAP server gave) may go to the
    header parser: at most MAIL_HEAD_MAX together, every line with its folded lines within MAIL_HLINE_MAX / MAIL_HNEST_MAX."""
    if len(head) > MAIL_HEAD_MAX:
        return False
    n = brackets = 0
    for ln in head.replace(b"\r\n", b"\n").replace(b"\r", b"\n").split(b"\n"):
        if ln[:1] not in (b" ", b"\t"):  # a new header line (else a folded one: it belongs to the line before)
            n = brackets = 0
        n += len(ln) + 1
        brackets += ln.count(b"(")
        if not _line_ok(n, brackets):
            return False
    return True


def mail_precheck(raw):
    """Step 1 (see above): raises MailRefused("head" / "lines"). A few passes over the bytes; nothing is built."""
    cut = raw[:MAIL_HEAD_MAX + 4]
    ends = [i for i in (cut.find(b"\r\n\r\n"), cut.find(b"\n\n"), cut.find(b"\r\r")) if i >= 0]
    if not ends and len(raw) > MAIL_HEAD_MAX:
        raise MailRefused("head")  # no empty line within the limit: the head is too large (or the mail has none)
    if not mail_head_ok(cut[:min(ends)] if ends else cut):
        raise MailRefused("head")
    if sum(raw.count(c) for c in _EOLS) - raw.count(b"\r\n") > MAIL_LINES_MAX:
        raise MailRefused("lines")


def mail_postcheck(msg):
    """Step 3 (see above) on a parsed message: raises MailRefused. No header line is parsed here (the readers ask for the
    ones they need; their size is bounded here and in mail_precheck)."""
    todo, n = [(msg, 0)], 0
    while todo:
        part, depth = todo.pop()
        n += 1
        if n > MAIL_PARTS_MAX + 1:  # (+ the mail itself)
            raise MailRefused("parts")
        if depth > MAIL_DEPTH_MAX:
            raise MailRefused("depth")
        total = 0
        for k, v in part.raw_items():
            total += len(k) + len(v)
            if total > MAIL_HEAD_MAX or not _line_ok(len(k) + len(v), v.count("(")):
                raise MailRefused("head")
        sub = part.get_payload() if part.is_multipart() else None
        if isinstance(sub, list):
            todo.extend((p, depth + 1) for p in sub)


def mail_parse(raw):
    """The message of the bytes raw (email.policy.default), counted before, in and after the parser; raises MailRefused."""
    mail_precheck(raw)
    policy = email.policy.default
    count = [0]
    parser = None

    def factory(policy=policy):
        count[0] += 1
        if count[0] > MAIL_PARTS_MAX + 1:  # (+ the mail itself)
            raise MailRefused("parts")
        if parser is not None and len(getattr(parser, "_msgstack", ())) > MAIL_DEPTH_MAX:
            raise MailRefused("depth")  # (the open parts of the parser; without that list the postcheck and the except below)
        return policy.message_factory(policy=policy)
    parser = email.feedparser.BytesFeedParser(factory, policy=policy)
    count[0] = 0  # (the parser tried the factory once when it was made)
    try:
        for i in range(0, len(raw), 65536):  # in pieces: the factory ends it at the piece with part 2.001, not after the
            parser.feed(raw[i:i + 65536])    # parser has cut the whole mail into lines
        msg = parser.close()
    except RecursionError:
        raise MailRefused("depth") from None
    mail_postcheck(msg)
    return msg
