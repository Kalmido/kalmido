#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1281.0 (#6425): a foreign mail is counted before it is taken apart, and a documents mail has one budget.
 - core/mailguard.py mail_parse: a mail of 200.000 tiny parts (1.4 MB; the parser alone took seconds and 80 MB for it), of
   3 million parts, with bare CR / VT line ends, an unquoted or RFC 2231 boundary, 2.000 parts inside each other, 3.000
   mails inside each other, a sender line of 500 opening brackets, a head of 300 KB (also folded, also of one part) is
   refused (MailRefused with its code) fast and without building it; a normal mail, 1.999 parts, a patch of 50.000 "--" lines,
   a head of 200 KB and 40 mails inside each other go through as before
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
import json, time, tracemalloc, app
from kalmido.core import mailguard as G
def run(raw, top=True):
    tracemalloc.start()
    t = time.monotonic()
    try:
        G.mail_parse(raw, top); r = "ok"
    except G.MailRefused as e:
        r = e.code
    dt = time.monotonic() - t
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    return [r, round(dt, 2), peak // (1024 * 1024)]
out = {}
for name, raw in (
    ("parts 200.000", multi(200_000)), ("parts 3 million", multi(3_000_000)), ("parts bare CR", multi(20_000, b"\r")),
    ("parts VT", multi(20_000, b"\x0b")), ("parts 2.001", multi(2_001)),
    ("parts unquoted boundary", H + b"Content-Type: multipart/mixed; boundary=--=_x\r\n\r\n" + b"----=_x\r\n\r\nx\r\n" * 20_000),
    ("parts rfc2231 boundary", H + b"Content-Type: multipart/mixed; boundary*0=a; boundary*1=b\r\n\r\n" + b"--ab\r\n\r\nx\r\n" * 20_000),
    ("depth 2.000 parts inside each other", nested(2_000)), ("depth 300 parts inside each other", nested(300)),
    ("depth 3.000 mails inside each other", inside(3_000)), ("depth 100 mails inside each other", inside(100)),
    ("head 500 brackets", BRACKETS),
    ("head of a part 500 brackets", multi(2).replace(b"--b\r\n\r\n", b"--b\r\nContent-Disposition: " + b"(" * 500 + b"\r\n\r\n", 1)),
    ("head 300 KB", b"From: a@example.com\r\nX-A: " + b"a" * 300_000 + b"\r\n\r\nhi"),
    ("head 300 KB folded", b"From: a@example.com\r\nX-A: a\r\n" + b" aaaaaaaa\r\n" * 30_000 + b"\r\nhi"),
    ("head of a part 300 KB", multi(2).replace(b"--b\r\n\r\n", b"--b\r\nX-A: " + b"a" * 300_000 + b"\r\n\r\n", 1)),
    ("ok normal", multi(3)), ("ok 1.999 parts", multi(1_999)),
    ("ok patch of 50.000 dash lines", multi(3).replace(b"x\r\n", b"-- comment\r\n--- a/f\r\n" * 25_000, 1)),
    ("ok head 200 KB", b"From: a@example.com\r\nX-A: " + b"a" * 200_000 + b"\r\n\r\nhi"),
    ("ok 40 mails inside each other", inside(40)),
):
    out[name] = run(raw)
out["limits"] = [G.MAIL_PARTS_MAX, G.MAIL_HEAD_MAX]
print(json.dumps(out))
"""
j = py(GUARD)
check(j.get("limits") == [2000, 256 * 1024], f"the limits: 2.000 parts, 256 KB head ({j.get('limits')})")
for k, v in sorted(j.items()):
    if k == "limits":
        continue
    want = k.split(" ", 1)[0]
    # (the 3 million parts are 21 MB of bytes that are read once; nothing of a refused mail is built: under 8 MB)
    check(v[0] == want and v[1] < (5 if want != "ok" else 20) and (want == "ok" or k.startswith("depth") or v[2] < 8),
          f"mail_parse {k}: {v[0]} in {v[1]} s, {v[2]} MB built")
check(len(j) == 22, f"all mails were tried ({len(j)})")

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
seen = []
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
print(json.dumps({"n": n, "ev": ev, "dt": round(dt, 2), "peak": peak, "log": buf.getvalue(), "seen": len(seen), "view": view,
                  "view_dt": round(time.monotonic() - t, 2)}))
"""
j = py(FETCH)
log = j.get("log") or ""
check(j.get("seen") == 6 and j.get("dt", 99) < 10 and j.get("peak", 999) < 20,
      f"mail_fetch: all three mails went to the importer, fast and without building the big one ({j.get('seen')}, {j.get('dt')} s, {j.get('peak')} MB)")
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
def take(files):
    # like _docs_mail_into: the files of one attachment are used and dropped before the next attachment is asked for
    docs = total = cand = 0
    for _i, parts in I._mail_parts(files, ei_is, "m"):
        cand += 1
        for name, mime, data, ext in parts:
            docs += 1
            total += len(data)
        parts = name = mime = data = ext = None
    return docs, total, cand
out = {}
big = zipped(6, 10 * 1024 * 1024, "big")  # 60 MB unpacked, a few KB packed
files = [(f"b{i}.zip", "application/zip", big) for i in range(20)]
tracemalloc.start()
t = time.monotonic()
has = I._mail_has_parts(files, ei_is)
out["has"] = [has, tracemalloc.get_traced_memory()[1] // (1024 * 1024)]
docs, total, cand = take(files)
out["big"] = [docs, total // (1024 * 1024), cand, tracemalloc.get_traced_memory()[1] // (1024 * 1024), round(time.monotonic() - t, 1)]
tracemalloc.stop()
small = [(f"s{i}.zip", "application/zip", zipped(45, 100, f"s{i}")) for i in range(3)]
pdfs = [(f"p{i}.pdf", "application/pdf", b"%PDF-1.4 x") for i in range(15)]
out["many"] = list(take(small + pdfs))
out["plain"] = list(take([("a.pdf", "application/pdf", b"%PDF-1.4 x"), ("n.txt", "text/plain", b"x"), ("i.png", "image/png", b"x")]))
out["none"] = I._mail_has_parts([("n.txt", "text/plain", b"x")], ei_is)
out["limits"] = [I.MAIL_DOCS, I.MAIL_BYTES // (1024 * 1024)]
print(json.dumps(out))
"""
j = py(BUDGET, 400)
check(j.get("limits") == [100, 100], f"the budget of one mail: 100 documents, 100 MB ({j.get('limits')})")
b = j.get("big") or [0, 999, 0, 9999, 0]
check(b[0] == 6 and b[1] <= 100 and b[2] == 20, f"20 ZIPs of 60 MB each: only what fits into 100 MB becomes documents ({b[0]} files, {b[1]} MB)")
check(b[3] < 250, f"20 ZIPs of 60 MB each: never more than one archive unpacked at a time ({b[3]} MB at most, 1.200 MB before)")
check(j.get("has") and j["has"][0] is True and j["has"][1] < 5, f"'has the mail a file of its own' unpacks nothing ({j.get('has')})")
m = j.get("many") or [0, 0, 0]
check(m[0] == 100 and m[2] == 18, f"3 ZIPs of 45 files + 15 PDFs: 100 documents, the third ZIP refused whole, 5 PDFs left out ({m})")
check(j.get("plain") == [2, 11, 2] and j.get("none") is False, f"a plain mail as before: the PDF and the image, not the text file ({j.get('plain')}, {j.get('none')})")

sys.exit(done("p21281_a_mailguard"))
