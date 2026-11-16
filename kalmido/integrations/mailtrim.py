"""2.49.0 (#971): shorten a forwarded mail. A pure text function (no database, no request) so every path that takes in mails
can use it (tasks by e-mail now; filing mails with a customer / project later).

md_trim_forward(text) -> text: the forwarding header (marker line + From / Sent / To / Subject lines, German and English,
Gmail / Outlook / Apple Mail / Thunderbird) becomes ONE line "From <sender>, <date>"; the person's own words above it stay on
top; below it signatures, disclaimers and older quoted replies are cut. Text without a forwarding header is returned as it is."""
import re

# marker lines that open a forwarded message
MARKER_RE = re.compile(
    r"^\s*(?:[-_=*]{2,}\s*)?(?:forwarded message|begin forwarded message|original message|weitergeleitete nachricht|"
    r"anfang der weitergeleiteten nachricht|urspr(?:ü|ue)ngliche nachricht|message transf(?:é|e)r(?:é|e)|"
    r"mensaje reenviado|messaggio inoltrato|doorgestuurd bericht)\s*(?::\s*)?(?:[-_=*]{2,}\s*)?$", re.I)
HDR_RE = re.compile(r"^\s*\**(from|von|sent|gesendet|date|datum|to|an|cc|bcc|subject|betreff|reply-to|antwort an|de|envoy(?:é|e)|à|objet)\**\s*:\s*(.*)$", re.I)
FROM_KEYS, DATE_KEYS = ("from", "von", "de"), ("sent", "gesendet", "date", "datum", "envoyé", "envoye")
SUBJ_KEYS = ("subject", "betreff", "objet")
SEP_RE = re.compile(r"^\s*[_\-=*]{5,}\s*$")
# "On <date>, <name> wrote:" and friends (may wrap onto a second line)
QUOTE_RE = re.compile(r"^\s*(?:on .{5,300}wrote\s*|am .{5,300}schrieb.{0,120}|le .{5,300}a (?:é|e)crit\s*|el .{5,300}escribi(?:ó|o)\s*|il .{5,300}ha scritto\s*|op .{5,300}schreef.{0,100}):\s*$", re.I)
QUOTE_HEAD_RE = re.compile(r"^\s*(?:on|am|le|el|il|op)\s.{3,300}$", re.I)
QUOTE_TAIL_RE = re.compile(r"^\s*.{0,120}(?:wrote\s*|schrieb.{0,60}|a (?:é|e)crit\s*|escribi(?:ó|o)\s*|ha scritto\s*|schreef.{0,60}):\s*$", re.I)
SIGN_RE = re.compile(
    r"^\s*(?:--\s?|mit freundlichen gr(?:ü|ue)(?:ß|ss)en|freundliche gr(?:ü|ue)(?:ß|ss)e|viele gr(?:ü|ue)(?:ß|ss)e|beste gr(?:ü|ue)(?:ß|ss)e|"
    r"herzliche gr(?:ü|ue)(?:ß|ss)e|liebe gr(?:ü|ue)(?:ß|ss)e|gr(?:ü|ue)(?:ß|ss)e|best regards|kind regards|warm regards|regards|"
    r"sincerely|yours sincerely|cheers|many thanks|thanks and regards|sent from my .*|gesendet von meinem .*|von meinem .* gesendet|"
    r"get outlook for .*)\s*(?:[,!.]\s*)?$", re.I)
DISCLAIMER_RE = re.compile(
    r"confidential|intended recipient|privileged|disclaimer|this (?:e-?mail|message) (?:and any|may contain|is intended)|"
    r"vertraulich|haftungsausschluss|irrt(?:ü|ue)mlich|nicht f(?:ü|ue)r sie bestimmt|gesch(?:ü|ue)tzte informationen|"
    r"if you have received this|falls sie nicht der (?:richtige )?adressat", re.I)
MAX_HDR = 14
# 2.1269.0 (#6421): a crafted mail must not hold the server. The line patterns above only ever see a stripped line of at most
# LINE_MAX characters (a marker / quote / signature line is short; .{0,120} next to \s* backtracks on long ones), a header
# block is read at most HDR_LINES lines deep, a sender value at most SENDER_MAX characters deep and without a regex
# (^(.*?)\s*<([^>]*)>\s*$ was quadratic on a long value).
LINE_MAX = 1000
HDR_LINES = 40   # header lines with a key of one block ...
HDR_SPAN = 400   # ... within this many lines in all (a long folded To: has many continuation lines; they do not count as header lines)
SENDER_MAX = 1000
VIEW_CACHE_N = 32         # md_trim_view remembers the results of this many texts ...
VIEW_CACHE_TEXT = 50000   # ... of at most this many characters each (a larger text is shortened anew each time)
_VIEW_CACHE = {}


def _ln(line):
    """The line stripped for the line patterns, or "" (matches none of them) when it is too long to be such a line."""
    return line.strip() if len(line) <= LINE_MAX else ""


def _is_hdr(line):
    return HDR_RE.match(line) is not None


def _kinds(lines):
    """2.1269.0 (#6421): per line its header key (lower case), "" for a possible continuation line (indented, not empty) or
    None -- each line through HDR_RE once, so looking for a block at every line stays cheap."""
    out = []
    for ln in lines:
        m = HDR_RE.match(ln)
        out.append(m.group(1).lower() if m else ("" if ln[:1] in (" ", "\t") and ln.strip() else None))
    return out


def _hdr_block(lines, i):
    """(fields, next index) of the header lines from i on (continuation lines are indented); fields = {key: value}."""
    f, n = {}, len(lines)
    last, stop, keyed = None, min(n, i + HDR_SPAN), 0  # 2.1269.0 (#6421): at most HDR_LINES keyed lines within HDR_SPAN lines
    while i < stop and len(f) < MAX_HDR and keyed < HDR_LINES:
        m = HDR_RE.match(lines[i])
        if m:
            keyed += 1
            last = m.group(1).lower()
            f.setdefault(last, m.group(2).strip())
        elif last and lines[i][:1] in (" ", "\t") and lines[i].strip():
            f[last] = (f[last] + " " + lines[i].strip()).strip()
        else:
            break
        i += 1
    return f, i


_DS_KEYS = frozenset(DATE_KEYS + SUBJ_KEYS)


def _starts_block(lines, i, kinds=None):
    """A header block (without marker) starts at i: a From / Von line with at least two more header lines and a date or subject.
    2.1269.0 (#6421): the keys _hdr_block would collect, read from kinds (_kinds) without building the values."""
    kinds = kinds if kinds is not None else _kinds(lines[i:i + HDR_SPAN])
    o = 0 if len(kinds) < len(lines) else i
    if kinds[o] not in FROM_KEYS:
        return False
    seen, keyed = set(), 0
    for k in kinds[o:o + HDR_SPAN]:
        if k is None or keyed >= HDR_LINES:
            break
        keyed += bool(k)
        if k and k not in seen:  # a repeated key / continuation line adds nothing (as setdefault there)
            if len(seen) >= MAX_HDR:
                break
            seen.add(k)
            if len(seen) >= 3 and not seen.isdisjoint(_DS_KEYS):
                return True
    return False


def _sender(v):
    v = re.sub(r"\[mailto:[^\]]*\]|mailto:", "", (v or "")[:SENDER_MAX]).replace("*", "").strip()
    if v.endswith(">"):  # 2.1269.0 (#6421): 'Name <address>' read by string search (as ^(.*?)\s*<([^>]*)>\s*$ did)
        gt = len(v) - 1
        lt = v.find("<", v.rfind(">", 0, gt) + 1, gt)
        if lt >= 0:
            v = v[:lt].strip().strip('"\'').strip() or v[lt + 1:gt].strip()
    return v.strip().strip('"\'').strip()


def _cut_quoted(lines):
    """Drops quoted older replies: lines with '>', 'On … wrote:', a second header block, 'Original Message'."""
    out, seen, kinds = [], False, _kinds(lines)
    n = len(lines)
    for i, ln in enumerate(lines):
        if ln.lstrip().startswith(">"):
            continue
        s = _ln(ln)
        if MARKER_RE.match(s) or (seen and _starts_block(lines, i, kinds)):
            break
        if QUOTE_RE.match(s) or (QUOTE_HEAD_RE.match(s) and i + 1 < n and QUOTE_TAIL_RE.match(_ln(lines[i + 1])) and not QUOTE_TAIL_RE.match(s)):
            break
        out.append(ln)
        seen = seen or bool(ln.strip())  # 2.1269.0 (#6421): was any(...) over out per line (quadratic on many blank lines)
    while out and (not out[-1].strip() or SEP_RE.match(_ln(out[-1]))):  # a separator line that opened the cut part
        out.pop()
    return out


def _cut_signature(lines):
    for i, ln in enumerate(lines):
        if SIGN_RE.match(_ln(ln)):  # the pattern needs the whole line, so a greeting inside a sentence stays
            return lines[:i]
    return lines


def _drop_disclaimers(lines):
    paras, cur = [], []
    for ln in lines + [""]:
        if ln.strip():
            cur.append(ln)
        else:
            if cur:
                paras.append(cur)
            cur = []
            paras.append(None)
    out = []
    for p in paras:
        if p is None:
            out.append("")
            continue
        j = " ".join(p)
        if not (len(j) < 2500 and DISCLAIMER_RE.search(j)):
            out.extend(p)
    return out


def md_trim_forward(text):
    """The shortened text, or text itself when it holds no forwarding header."""
    if not text:
        return text
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    n, start, hdr_at, f, end = len(lines), None, None, None, None
    kinds = _kinds(lines)  # 2.1269.0 (#6421): each line through HDR_RE once
    for i in range(n):
        if MARKER_RE.match(_ln(lines[i])):
            j = i + 1
            while j < n and not lines[j].strip():
                j += 1
            if j < n and _is_hdr(lines[j]):
                start, hdr_at = i, j
                break
        elif _starts_block(lines, i, kinds):
            start, hdr_at = i, i
            if i and SEP_RE.match(_ln(lines[i - 1])):
                start = i - 1
            break
    if start is None:
        return text
    f, end = _hdr_block(lines, hdr_at)
    de = any(k in f for k in ("von", "gesendet", "datum", "betreff", "an"))
    before = lines[:start]
    while before and not before[-1].strip():
        before.pop()
    body = lines[end:]
    body = _cut_quoted(body)
    body = _cut_signature(body)
    body = _drop_disclaimers(body)
    body = "\n".join(body).strip("\n")
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    who = _sender(next((f[k] for k in FROM_KEYS if k in f), ""))
    when = next((f[k] for k in DATE_KEYS if k in f), "").strip()
    head = (("Von " if de else "From ") + who + (", " + when if when else "")) if who else when
    parts = ["\n".join(before).strip("\n"), head, body]
    return "\n\n".join(p for p in parts if p).strip()


ADDR_RE = re.compile(r"[\w.!#$%&'*+/=?^`{|}~-]+@[\w-]+(?:\.[\w-]+)+")


def md_forward_from(text):
    """2.84.0 (#1198): (name, address) of the original sender in the first forwarding header of text, ("", "") without one."""
    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    kinds = _kinds(lines)  # 2.1269.0 (#6421): each line through HDR_RE once
    for i in range(len(lines)):
        at = None
        if MARKER_RE.match(_ln(lines[i])):
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            at = j if j < len(lines) and _is_hdr(lines[j]) else None
        elif _starts_block(lines, i, kinds):
            at = i
        if at is None:
            continue
        f, _ = _hdr_block(lines, at)
        v = next((f[k] for k in FROM_KEYS if k in f), "")[:SENDER_MAX]  # 2.1269.0 (#6421): ADDR_RE backtracks on a long value
        m = ADDR_RE.search(v)
        return (_sender(v) if m and _sender(v) != m.group(0) else ""), (m.group(0).lower() if m else "")
    return "", ""


def md_trim_view(text):
    """2.352.0 D (#2754): the shortened text of a filed mail for the reading view: a forwarded mail as md_trim_forward does;
    a plain mail loses its older quoted replies, its signature and legal notices. Display only -- the original stays as it is.
    2.1269.0 (#6421): the reading view asks on every open; the results of the last VIEW_CACHE_N texts of at most
    VIEW_CACHE_TEXT characters are remembered."""
    if not text:
        return text
    if len(text) > VIEW_CACHE_TEXT:
        return _trim_view(text)
    hit = _VIEW_CACHE.get(text)
    if hit is None:
        hit = _trim_view(text)
        while len(_VIEW_CACHE) >= VIEW_CACHE_N:
            try:
                _VIEW_CACHE.pop(next(iter(_VIEW_CACHE)))
            except (KeyError, RuntimeError, StopIteration):  # another thread took it first
                break
        _VIEW_CACHE[text] = hit
    return hit


def _trim_view(text):
    short = md_trim_forward(text)
    if short != text:
        return short
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    lines = _drop_disclaimers(_cut_signature(_cut_quoted(lines)))
    out = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return out or text
