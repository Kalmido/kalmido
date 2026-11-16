#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1281.0 (#6425): a foreign mail is counted before it is taken apart, and a documents mail has one budget.
 - core/mailguard.py mail_parse: a mail of 200.000 tiny parts (1.4 MB; the parser alone took seconds and 80 MB for it), of
   3 million parts, with bare CR line ends, a boundary declared in ways only the parser follows (RFC 2231 pieces,
   a comment before "=", an encoded word), a delivery report of 400.000 blocks (parts without any boundary), 2.000 parts
   inside each other (33 s in the parser of Python 3.12 before), 3.000 mails inside each other, a sender line of 500
   opening brackets, a To line of 16 KB commas (seconds in the header parser, every time it is read), header lines of a
   part that the parser itself reads while it takes the mail apart (a Content-Type of 32 KB semicolons: 84 s; 3 MB of
   brackets: 2.8 GB), many small costly lines (400 parts with 120 semicolons each), a head of 300 KB and 4 MB of two-byte
   lines are refused (MailRefused with its code) fast and without building them; a normal mail, 1.999 parts, a patch of
   50.000 "--" lines that talks about boundaries, a head of 200 KB, 300 recipients, 300 attachments, a digest of 200 mails
   and 8 mails inside each other go through as before
 - the instance mailbox (mail_fetch with mail_import): the mail of 200.000 parts is refused before any token is looked up,
   marked seen, and the mail after it is still handled
 - the reading view (hub/mailview.py mh_parts, in the request thread) refuses it as well instead of taking it apart
 - the documents mail (docs/ingest.py _mail_parts): 20 ZIPs of 60 MB unpacked each (1.2 GB together before) stay under
   250 MB at any time and give at most 100 MB of files; ZIPs of many small files plus single files end at 100 documents;
   the question "has the mail a file of its own" unpacks nothing
Runs the functions inside the test container (fake IMAP object, no mail server); invented addresses only.
usage: p21281_a_mailguard_test.py <datadir>"""
import json
import os
import subprocess
import sys

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
from kt import CT, check, done  # noqa: E402


def py(code, limit=240):
    """code in the container, killed there after limit seconds (the unguarded parser ran for minutes)."""
    try:
        r = subprocess.run(["docker", "exec", "-i", CT, "timeout", str(limit), "python", "-c", code], capture_output=True, text=True,
                           timeout=limit + 30)
    except subprocess.TimeoutExpired:
        return {}
    if r.returncode:
        print("PY FAILED:", r.returncode, r.stdout[-2000:], r.stderr[-3000:], flush=True)
    for ln in reversed((r.stdout or "").splitlines()):
        if ln.startswith("{"):
            return json.loads(ln)
    return {}


MAILS = r"""
H = b"From: a@example.com\r\nSubject: s\r\nMIME-Version: 1.0\r\n"
def multi(n, sep=b"\r\n", b=b"b"):
    return (H + b'Content-Type: multipart/mixed; boundary="' + b + b'"\r\n\r\n' + (b"--" + b + sep + sep + b"x" + sep) * n
            + b"--" + b + b"--\r\n")
def nested(n):
    return H + b"".join(b'Content-Type: multipart/mixed; boundary="n%d"\r\n\r\n--n%d\r\n' % (i, i) for i in range(n)) + b"\r\nx\r\n"
def inside(n):
    return H + b"Content-Type: message/rfc822\r\n\r\n" * n + b"Subject: x\r\n\r\nhi\r\n"
BRACKETS = b"From: " + b"(" * 500 + b" a@example.com\r\nSubject: s\r\n\r\nhi\r\n"
"""

# ---- 1. mail_parse: what is refused (with its code, fast, nothing built) and what still goes through
GUARD = MAILS + r"""
import base64, json, time, tracemalloc, app
from kalmido.core import mailguard as G
def run(raw):
    tracemalloc.start()
    t = time.monotonic()
    try:
        G.mail_parse(raw); r = "ok"
    except G.MailRefused as e:
        r = e.code
    dt = time.monotonic() - t
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    return [r, round(dt, 2), peak // (1024 * 1024)]
def decl(d, n=100_000):
    return H + b"Content-Type: multipart/mixed; " + d + b"\r\n\r\n" + b"--XYZ\r\n\r\nx\r\n" * n
out = {}
for name, raw in (
    ("parts 200.000", multi(200_000)), ("lines 3 million parts", multi(3_000_000)), ("parts bare CR", multi(20_000, b"\r")),
    ("parts 2.001", multi(2_001)),
    ("ok an unquoted boundary the parser itself does not follow (one part)", H + b"Content-Type: multipart/mixed; boundary=--=_x\r\n\r\n" + b"----=_x\r\n\r\nx\r\n" * 20_000),
    ("parts rfc2231 boundary", decl(b"boundary*0=XY; boundary*1=Z")),
    ("parts comment before the equals sign", decl(b"boundary(c)=XYZ")),
    ("parts encoded word boundary", decl(b'boundary="=?us-ascii?q?XYZ?="')),
    ("parts boundary cut at a comma", decl(b"boundary=XYZ,foo")),
    ("parts delivery report of 400.000 blocks", H + b"Content-Type: message/delivery-status\r\n\r\n" + b"a:b\n\n" * 400_000),
    ("depth 2.000 parts inside each other", nested(2_000)), ("depth 300 parts inside each other", nested(300)),
    ("depth 3.000 mails inside each other", inside(3_000)), ("depth 33.000 mails inside each other", inside(33_000)),
    ("depth 40 parts inside each other", nested(40)),
    ("head 500 brackets", BRACKETS),
    ("head 101 brackets over folded lines", b"From: " + b"(\r\n " * 101 + b" a@example.com\r\n\r\nhi"),
    ("head of a part 500 brackets", multi(2).replace(b"--b\r\n\r\n", b"--b\r\nContent-Disposition: " + b"(" * 500 + b"\r\n\r\n", 1)),
    ("head To line of 16 KB commas", b"To: " + b"," * 16_000 + b"\r\nFrom: a@example.com\r\n\r\nhi"),
    ("head 300 KB", b"From: a@example.com\r\n" + b"X-A: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\r\n" * 6_000 + b"\r\nhi"),
    ("head without an empty line 300 KB", b"a" * 300_000),
    ("head of a part Content-Type of 32 KB semicolons", multi(2).replace(b"--b\r\n\r\n", b"--b\r\nContent-Type: text/plain" + b";" * 32_000 + b"\r\n\r\n", 1)),
    ("head of a part 3 MB of brackets", multi(2).replace(b"--b\r\n\r\n", b"--b\r\nContent-Type: text/plain " + b"(" * 3_000_000 + b"\r\n\r\n", 1)),
    ("head of a part one plain line of 70 KB", multi(2).replace(b"--b\r\n\r\n", b"--b\r\nX-A: " + b"a" * 70_000 + b"\r\n\r\n", 1)),
    ("head 400 parts with 120 semicolons in each Content-Type", H + b'Content-Type: multipart/mixed; boundary="b"\r\n\r\n' + b"".join(
        b"--b\r\nContent-Type: text/plain; a=%d" % i + b";" * 120 + b"\r\n\r\nx\r\n" for i in range(400)) + b"--b--\r\n"),
    ("head 2.000 children under a Content-Type of 8 KB semicolons", H + b'Content-Type: multipart/mixed; boundary="b"' + b";" * 8_100
     + b"\r\n\r\n" + b"--b\r\n\r\n" * 2_000 + b"--b--\r\n"),
    ("head 100 file names of base64 words (5.900 words each to the parser)", H + b'Content-Type: multipart/mixed; boundary="b"\r\n\r\n' + b"".join(
        b'--b\r\nContent-Disposition: attachment; filename="=?utf-8?b?' + base64.b64encode(b"a%d " % i + b"a " * 5_900) + b'?="\r\n\r\nx\r\n'
        for i in range(100)) + b"--b--\r\n"),
    ("head 31 To lines of 8 KB", b"".join(b"To: " + b"\\a" * 4_080 + b"\r\n" for _ in range(31)) + b"From: a@example.com\r\n\r\nhi"),
    ("lines 4 MB of two-byte lines", H + b"\r\n" + b"a\n" * 2_000_000),
    ("ok normal", multi(3)), ("ok 1.999 parts", multi(1_999)),
    ("ok patch of 50.000 dash lines that talks about boundaries",
     multi(3).replace(b"x\r\n", b"-- comment\r\n--- a/f\r\n" * 25_000 + b'$boundary = "--".md5(time());\r\nboundary = make(x)\r\n' * 60, 1)),
    ("ok the word boundary and 40 KB of blanks", H + b"\r\nboundary" + b" " * 40_000 + b"x\r\n"),
    ("ok head 200 KB", b"From: a@example.com\r\n" + b"X-A: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\r\n" * 4_000 + b"\r\nhi"),
    ("ok 200 recipients with base64 names", b"To: " + b", ".join(
        b"=?utf-8?b?" + base64.b64encode(("Jürgen Müller %d" % i).encode()) + b"?= <person%d@example.com>" % i for i in range(200)) + b"\r\n\r\nhi"),
    ("ok 300 recipients with names", b"To: " + b", ".join(b'"Person %d" <person%d@example.com>' % (i, i) for i in range(300)) + b"\r\n\r\nhi"),
    ("ok References of 30 KB", b"References: " + b" ".join(b"<%040d@mail.example.org>" % i for i in range(600)) + b"\r\nFrom: a@example.com\r\n\r\nhi"),
    ("ok a body of a million form feeds", H + b"\r\n" + b"\x0c" * 1_200_000),
    ("ok 300 attachments", H + b'Content-Type: multipart/mixed; boundary="b"\r\n\r\n' + b"".join(
        b'--b\r\nContent-Type: application/pdf; name="file%d.pdf"\r\nContent-Disposition: attachment; filename="file%d.pdf"\r\n'
        b"Content-Transfer-Encoding: base64\r\n\r\nJVBERi0=\r\n" % (i, i) for i in range(300)) + b"--b--\r\n"),
    ("ok 8 mails inside each other", inside(8)), ("ok 18 parts inside each other", nested(18)),
    ("ok digest of 200 mails with two parts each", H + b'Content-Type: multipart/digest; boundary="d"\r\n\r\n' + b"".join(
        b'--d\r\n\r\nSubject: m\r\nContent-Type: multipart/alternative; boundary="a%d"\r\n\r\n--a%d\r\n\r\nx\r\n--a%d\r\n\r\ny\r\n--a%d--\r\n'
        % (i, i, i, i) for i in range(200)) + b"--d--\r\n"),
):
    out[name] = run(raw)
out["limits"] = [G.MAIL_PARTS_MAX, G.MAIL_HEAD_MAX, G.MAIL_HLINE_MAX, G.MAIL_DEPTH_MAX, G.MAIL_LINES_MAX]
t = time.monotonic()
look = [G.mail_head(b"From: Shop <a@example.com>\r\nSubject: Invoice\r\n\r\n") is not None,
        G.mail_head(b"From: a@example.com\r\nSubject: " + b"a " * 30_000 + b"\r\n\r\n") is None,
        G.mail_head(b"From: " + b"," * 3_000 + b"\r\nSubject: s\r\n\r\n") is None]
out["look"] = look + [round(time.monotonic() - t, 2)]
print(json.dumps(out))
"""
j = py(GUARD)
check(j.get("limits") == [2000, 256 * 1024, 32768, 30, 1_000_000],
      f"the limits: 2.000 parts, 256 KB head, 32 KB per structured header line, 30 levels, a million lines ({j.get('limits')})")
lk = j.pop("look", None) or [0, 0, 0, 99]
check(lk[:3] == [True, True, True] and lk[3] < 1,
      f"the look of the mailbox rules: plain lines are read, a subject of 60 KB and a sender of 3 KB commas are refused unread ({lk})")
print("mail_parse [result, seconds, MB built]:", json.dumps(j), flush=True)
for k, v in sorted(j.items()):
    if k == "limits":
        continue
    want = k.split(" ", 1)[0]
    # (a refused mail builds next to nothing; the most is the mail of many small costly lines: it is read until the
    # budget of the header lines is spent, 36 MB of parsed lines -- gigabytes before)
    check(v[0] == want and v[1] < (5 if want != "ok" else 20) and (want == "ok" or v[2] < 60),
          f"mail_parse {k}: {v[0]} in {v[1]} s, {v[2]} MB built")
check(len(j) == 43, f"all mails were tried ({len(j)})")

# ---- 2. the instance mailbox and the reading view
FETCH = MAILS + r"""
import contextlib, io, json, time, tracemalloc, app
from kalmido.integrations import mail as M
from kalmido.hub import mailview as V
from kalmido.core.mailguard import MailRefused
BIG = multi(200_000)
MAILS_ = {b"5": BIG, b"6": BRACKETS, b"7": b"From: a@example.com\r\nTo: nobody@example.com\r\nSubject: s\r\nMessage-ID: <p21281-7@example.org>\r\n\r\nhi\r\n"}
ev = []
class FakeIMAP:
    def read(self, n): return b""
    def select(self, folder): return "OK", [b"3"]
    def uid(self, cmd, *a):
        if cmd == "SEARCH": return "OK", [b"5 6 7"]
        if cmd == "FETCH":
            if "SIZE" in a[1]: return "OK", [b"1 (UID %s RFC822.SIZE %d)" % (a[0], len(MAILS_[a[0]]))]
            return "OK", [(b"1 (UID %s RFC822 {%d}" % (a[0], len(MAILS_[a[0]])), MAILS_[a[0]]), b")"]
        if cmd == "STORE": ev.append([a[0].decode(), a[2]])
        return "OK", []
seen, parsed = [], []
real = M.mail_parse
def counting(raw):
    m = real(raw)
    parsed.append(len(raw))
    return m
M.mail_parse = counting
def importer(c, raw, pre=None):
    seen.append(len(raw))
    return M.mail_import(c, raw, pre)
buf = io.StringIO()
tracemalloc.start()
t = time.monotonic()
with contextlib.redirect_stdout(buf):
    n = M.mail_fetch(FakeIMAP(), "INBOX", importer, prefetch=True)
dt = time.monotonic() - t
peak = tracemalloc.get_traced_memory()[1] // (1024 * 1024)
tracemalloc.stop()
t = time.monotonic()
try:
    V.mh_parts(BIG); view = "taken apart"
except MailRefused as e:
    view = e.code
print(json.dumps({"n": n, "ev": ev, "once": len(parsed), "dt": round(dt, 2), "peak": peak, "log": buf.getvalue(), "seen": len(seen), "view": view,
                  "view_dt": round(time.monotonic() - t, 2)}))
"""
j = py(FETCH)
log = j.get("log") or ""
# (the importer sees the mail of 200.000 parts twice -- the step before the transaction and the import, both refuse it --,
# the bracket mail never: its head is refused on the bytes; the plain mail twice)
check(j.get("seen") == 4 and j.get("dt", 99) < 10 and j.get("peak", 999) < 20,
      f"mail_fetch: the round over the three mails is fast and builds nothing big ({j.get('seen')}, {j.get('dt')} s, {j.get('peak')} MB)")
check(j.get("once") == 1, f"mail_fetch: a mail is taken apart once for both steps of its import ({j.get('once')})")
check("mail: refused one mail: parts" in log, f"the mail of 200.000 parts is refused with its reason ({log[-300:]!r})")
check("mail: refused one mail: head" in log, f"the mail with the bracket sender is refused with its reason ({log[-300:]!r})")
check(sorted(e[0] for e in j.get("ev") or []) == ["5", "6", "7"] and all(e[1] == "(\\Seen)" for e in j.get("ev") or []),
      f"all three are marked seen, the mail after the refused ones included ({j.get('ev')})")
check(j.get("view") == "parts" and j.get("view_dt", 99) < 2, f"the reading view refuses it too ({j.get('view')}, {j.get('view_dt')} s)")

# ---- 3. the documents mail: one budget per mail, attachment by attachment
BUDGET = r"""
import io, json, time, tracemalloc, zipfile, app
from kalmido.docs import ingest as I
from kalmido.office.einvoice_in import ei_is
def zipped(n, size, tag):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
        for i in range(n):
            z.writestr(f"{tag}-{i}.pdf", b"%PDF-1.4 " + bytes(size))
    return b.getvalue()
CUT, WHY = [], []
def take(files):
    # like _docs_mail_into: the files of one attachment are used and dropped before the next attachment is asked for
    docs = total = cand = 0
    del CUT[:], WHY[:]
    for _i, parts in I._mail_parts(files, ei_is, "m", WHY, CUT):
        cand += 1
        for name, mime, data, ext in parts:
            docs += 1
            total += len(data)
        parts = name = mime = data = ext = None
    return docs, total, cand
out = {}
# one archive just under its own limits (60 MB unpacked, the server's file size limit, 50 files), a few KB packed
from kalmido.docs.unpack import DOC_FILE_MAX, DOC_UNPACKED_MAX
size = min(DOC_FILE_MAX - 16, 9_900_000)
k = min(I.MAIL_UNPACKED, (DOC_UNPACKED_MAX - 1024 * 1024) // (size + 16))
out["zip"] = [k, k * (size + 9) // (1024 * 1024)]
big = zipped(k, size, "big")
files = [(f"b{i}.zip", "application/zip", big) for i in range(20)]
tracemalloc.start()
t = time.monotonic()
has = I._mail_has_parts(files, ei_is)
out["has"] = [has, tracemalloc.get_traced_memory()[1] // (1024 * 1024)]
docs, total, cand = take(files)
out["big"] = [docs, total // (1024 * 1024), cand, tracemalloc.get_traced_memory()[1] // (1024 * 1024), round(time.monotonic() - t, 1), len(CUT)]
tracemalloc.stop()
small = [(f"s{i}.zip", "application/zip", zipped(45, 100, f"s{i}")) for i in range(3)]
pdfs = [(f"p{i}.pdf", "application/pdf", b"%PDF-1.4 x") for i in range(15)]
out["many"] = list(take(small + pdfs)) + [len(CUT)]
out["plain"] = list(take([("a.pdf", "application/pdf", b"%PDF-1.4 x"), ("n.txt", "text/plain", b"x"), ("i.png", "image/png", b"x")])) + [len(CUT), len(WHY)]
out["late"] = list(take([(f"p{i}.pdf", "application/pdf", b"%PDF-1.4 x") for i in range(25)])) + [CUT[:]]
out["late2"] = list(take([(f"n{i}.txt", "text/plain", b"x") for i in range(45)] + [("z.pdf", "application/pdf", b"%PDF-1.4 x")])) + [CUT[:]]
bad = [("broken.zip", "application/zip", b"PK\x03\x04 no archive")]
out["broken"] = list(take(small[:2] + bad)) + [len(CUT), WHY[:]]
xb = io.BytesIO()
with zipfile.ZipFile(xb, "w", zipfile.ZIP_DEFLATED) as z:
    for i in range(3):
        z.writestr(f"other-{i}.xml", b"<?xml version='1.0'?><note>" + bytes(1000) + b"</note>")
out["xml"] = list(take([("x.zip", "application/zip", xb.getvalue())])) + [len(CUT), WHY[:]]
out["none"] = I._mail_has_parts([("n.txt", "text/plain", b"x")], ei_is)
out["limits"] = [I.MAIL_DOCS, I.MAIL_BYTES // (1024 * 1024)]
print(json.dumps(out))
"""
j = py(BUDGET, 400)
check(j.get("limits") == [100, 100], f"the budget of one mail: 100 documents, 100 MB ({j.get('limits')})")
b = j.get("big") or [0, 999, 0, 9999, 0, 0]
z = j.get("zip") or [0, 0]
check(z[1] >= 45 and z[0] <= b[0] <= 100 and z[1] <= b[1] <= 100 and b[0] % z[0] == 0 and b[2] == 20,
      f"20 ZIPs of {z[1]} MB ({z[0]} files) each: only what fits into 100 MB becomes documents ({b[0]} files, {b[1]} MB)")
check(b[3] < 250, f"20 ZIPs of 60 MB each: never more than one archive unpacked at a time ({b[3]} MB at most, 1.200 MB before)")
check(j.get("has") and j["has"][0] is True and j["has"][1] < 5, f"'has the mail a file of its own' unpacks nothing ({j.get('has')})")
check(b[5] >= 18, f"20 ZIPs: every archive the budget left out is reported, so the mail is kept in the mailbox ({b[5]})")
m = j.get("many") or [0, 0, 0, 0]
check(m[0] == 100 and m[2] == 18 and m[3] == 6,
      f"3 ZIPs of 45 files + 15 PDFs: 100 documents, the third ZIP refused whole, 5 PDFs left out, all 6 reported ({m})")
check(j.get("plain") == [2, 11, 2, 0, 0] and j.get("none") is False,
      f"a plain mail as before: the PDF and the image, not the text file, nothing left out ({j.get('plain')}, {j.get('none')})")
check(j.get("late") == [20, 200, 20, ["more attachments"]],
      f"25 PDFs: 20 become documents as before, and the mail is reported as cut (kept in the mailbox) ({j.get('late')})")
check(j.get("late2") == [0, 0, 0, ["more attachments"]],
      f"a PDF as attachment 46 behind text files: not looked at as before, but the mail is reported as cut ({j.get('late2')})")
k = j.get("broken") or []
check(k[:1] == [90] and k[3:] == [0, ["ValueError"]],
      f"an unreadable ZIP after two full ones: refused for what it is, not reported as a budget cut ({k})")
check(j.get("xml") == [0, 0, 1, 0, ["ValueError"]],
      f"a ZIP of other XML files: no document, refused for what it is (never tried again), not a budget cut ({j.get('xml')})")

sys.exit(done("p21281_a_mailguard"))
