#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1385.0 part B1 (#6435, audit #4780 "foreign input and parser safety"): the server's parsers and limits. Every attack
file is made here (tiny files that claim a lot); the code runs in the app container of the group (docker exec, Pillow and
the package there), the routes are called as a person without an organisation.
 - point 1, pictures: core/imgsafe.py opens only the named formats and refuses a picture over IMG_MAX_PIXELS from its header,
   before load() (counted: no load call); at most IMG_BUSY_N decode at once (both places taken = "busy" after the wait).
   Every former own decoder goes through it: profile picture, list icon, list head, office logo, PDF logo, the contact
   photo for the DAV clients, the pictures of a knowledge page as a Word file (header and decode). A contact photo is
   stored only when its first bytes are one of the four picture types (the type the bytes say, not the declared one).
freelancer-matrix: contacts
usage: p21385_b1_haertung_test.py <datadir>"""
import base64
import io
import json
import os
import subprocess
import sys

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
import kt  # noqa: E402
from kt import B, check  # noqa: E402
from freelancer_fixture import freelancer  # noqa: E402

CT = kt.CT


def py(code, timeout=120):
    """code run by the app's python in the container (/app); -> the JSON its last printed line holds ({} when none)."""
    p = subprocess.run(["docker", "exec", "-i", "-w", "/app", CT, "python", "-"], input=code, capture_output=True, text=True,
                       timeout=timeout)
    last = (p.stdout.strip().splitlines() or [""])[-1]
    try:
        return json.loads(last)
    except ValueError:
        print("py: no JSON", p.stdout[-800:], p.stderr[-1500:], flush=True)
        return {}


kt.fresh()
A = kt.setup()
FID, F = freelancer(B, A, "frida")

# ================================================================== point 1: one picture decoder
P1 = r'''
import base64, io, json, threading, time
from PIL import Image, ImageFile
from kalmido.core.config import app
from kalmido.core import imgsafe
from kalmido.core.imgsafe import ImgRefused, img_head, img_open
LOADS = [0]
_load = ImageFile.ImageFile.load
def counting(self, *a, **kw):
    LOADS[0] += 1
    return _load(self, *a, **kw)
ImageFile.ImageFile.load = counting
def save(im, fmt, **kw):
    b = io.BytesIO(); im.save(b, fmt, **kw); return b.getvalue()
BIG = save(Image.new("1", (5000, 4000)), "PNG")          # 20 M pixels in a few kB
BIGJ = save(Image.new("L", (6000, 4000)), "JPEG")         # 24 M pixels as JPEG (drafted to 1/8 it is small)
TIFF = save(Image.new("RGB", (8, 8)), "TIFF")
EPS = b"%!PS-Adobe-3.0 EPSF-3.0\n%%BoundingBox: 0 0 10 10\n"
OK = save(Image.new("RGB", (64, 48), (40, 90, 160)), "PNG")
out = {"sizes": [len(BIG), len(BIGJ)]}
def why(fn, *a, **kw):
    LOADS[0] = 0
    t = time.time()
    try:
        r = fn(*a, **kw)
        res = "ok:" + (type(r).__name__ if r is not None else "None")
    except ImgRefused as e:
        res = "refused:" + e.reason
    except Exception as e:
        res = type(e).__name__ + ":" + str(e)
    return [res, LOADS[0], round(time.time() - t, 2)]
def opened(raw, **kw):
    with img_open(raw, **kw) as im:
        return im.size
with app.test_request_context():
    out["big"] = why(opened, BIG)
    out["bigj"] = why(opened, BIGJ)
    out["bigj_draft"] = why(opened, BIGJ, draft=(256, 256))
    out["tiff"] = why(opened, TIFF)
    out["eps"] = why(opened, EPS)
    out["ok"] = why(opened, OK)
    out["head_tiff"] = why(img_head, TIFF)
    out["head_big"] = why(img_head, BIG)
    # both places taken: the next waits IMG_WAIT_S, then "busy"; the lock is free again afterwards
    imgsafe.IMG_WAIT_S = 0.3
    for _ in range(imgsafe.IMG_BUSY_N):
        imgsafe.IMG_BUSY.acquire()
    out["busy"] = why(opened, OK)
    for _ in range(imgsafe.IMG_BUSY_N):
        imgsafe.IMG_BUSY.release()
    out["after_busy"] = why(opened, OK)
    from kalmido.accounts.pictures import avatar_process, list_icon_process
    from kalmido.lists.listhead import o3c_head_process
    from kalmido.office.pdfweb import opdf_logo_process
    from kalmido.office.pdf import pdf_image_object
    from kalmido.contacts.carddav import _photo_shrink
    from kalmido.contacts.model import _photo_in
    for name, fn in (("avatar", avatar_process), ("icon", list_icon_process), ("head", o3c_head_process), ("logo", opdf_logo_process),
                     ("pdflogo", pdf_image_object)):
        out[name] = {"big": why(fn, BIG), "tiff": why(fn, TIFF), "eps": why(fn, EPS), "ok": why(fn, OK)}
    uri = lambda raw, t="png": f"data:image/{t};base64," + base64.b64encode(raw).decode()
    out["dav"] = {"big": why(_photo_shrink, uri(BIG)), "tiff": why(_photo_shrink, uri(TIFF, "jpeg"))}
    out["dav_big_val"] = _photo_shrink(uri(BIG))
    out["photo_in"] = {"svg_as_png": _photo_in({}, uri(b"<svg xmlns='http://www.w3.org/2000/svg'/>")),
                       "html_as_jpeg": _photo_in({"ENCODING": ["b"], "TYPE": ["JPEG"]}, base64.b64encode(b"<html><script>x</script>").decode()),
                       "png_as_jpeg": _photo_in({}, uri(OK, "jpeg"))[:22],
                       "png_vcard": _photo_in({"ENCODING": ["b"], "TYPE": ["JPEG"]}, base64.b64encode(OK).decode())[:22]}
print(json.dumps(out))
'''
R1 = py(P1)
check(R1.get("big", [""])[0] == "refused:size" and R1["big"][1] == 0,
      f"#6435 1: a PNG of 20 M pixels ({R1.get('sizes')} bytes) is refused from its header, load() never runs {R1.get('big')}")
check(R1.get("bigj", [""])[0] == "refused:size" and R1["bigj"][1] == 0, f"... a JPEG of 24 M pixels as well {R1.get('bigj')}")
check(R1.get("bigj_draft", [""])[0] == "ok:tuple", f"... unless the caller decodes it small (draft): 1/8 of it is fine {R1.get('bigj_draft')}")
check(R1.get("tiff", [""])[0] == "refused:format" and R1.get("eps", [""])[0] == "refused:format",
      f"#6435 1: TIFF and EPS are not among the formats: refused {R1.get('tiff')} {R1.get('eps')}")
check(R1.get("ok", [""])[0] == "ok:tuple" and R1["ok"][1] >= 1, f"a small PNG opens and is decoded {R1.get('ok')}")
check(R1.get("head_tiff", [""])[0] == "refused:format" and R1.get("head_big", [""])[0] == "ok:tuple" and R1["head_big"][1] == 0,
      f"img_head: the size from the header only, the formats hold there too {R1.get('head_tiff')} {R1.get('head_big')}")
check(R1.get("busy", [""])[0] == "refused:busy" and R1.get("after_busy", [""])[0] == "ok:tuple",
      f"#6435 1: both places taken = busy after the wait, free again afterwards {R1.get('busy')} {R1.get('after_busy')}")
for name in ("avatar", "icon", "head", "logo", "pdflogo"):
    r = R1.get(name) or {}
    bad = [k for k in ("big", "tiff", "eps") if not (r.get(k) or [""])[0].startswith(("BadInput", "ValueError", "ok:None")) or (r.get(k) or [0, 1])[1]]
    check(r and not bad and (r.get("ok") or [""])[0].startswith("ok:") and r["ok"][0] != "ok:None",
          f"#6435 1 {name}: the big PNG, TIFF and EPS refused without decoding, a small PNG works {r}")
check((R1.get("dav") or {}).get("big", [""])[0] == "ok:str" and R1["dav"]["big"][1] == 0 and R1.get("dav_big_val") == "",
      f"#6435 1: the DAV photo of 20 M pixels is not decoded (the stored one goes as it is) {R1.get('dav')}")
pi = R1.get("photo_in") or {}
check(pi.get("svg_as_png") == "" and pi.get("html_as_jpeg") == "",
      f"#6435 1: a contact photo whose first bytes are no picture is not taken (SVG as PNG, HTML as JPEG) {pi}")
check(pi.get("png_as_jpeg") == "data:image/png;base64," and pi.get("png_vcard") == "data:image/png;base64,",
      f"... a PNG declared as JPEG is stored as what it is {pi}")
# the route: the freelancer's contact with an SVG claiming to be a PNG -> 400, with a real PNG -> stored
bk = F.post(B + "/api/books", json={"name": "B1 people"}).json().get("id")
svg = "data:image/png;base64," + base64.b64encode(b"<svg xmlns='http://www.w3.org/2000/svg' onload='alert(1)'/>").decode()
r = F.post(B + "/api/contacts", json={"book_id": bk, "fn": "Svg Person", "photo": svg})
check(r.status_code == 400, f"#6435 1: the contacts route refuses an SVG as PNG photo with 400 ({r.status_code} {r.text[:200]})")
buf = io.BytesIO()
buf.write(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="))
r = F.post(B + "/api/contacts", json={"book_id": bk, "fn": "Png Person", "photo": "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()})
check(r.status_code in (200, 201) and F.get(B + f"/api/contacts/{r.json().get('id')}").json().get("photo", "").startswith("data:image/png;base64,"),
      f"... a real PNG is stored ({r.status_code})")

# ================================================================== point 3: MT940 :61: with a booking day no year has
K = "/api/office/bank"
F.put(B + "/api/office/settings", json={"company_fields": {"name": "Beispiel Studio", "street": "Weg 1", "zip": "12345", "city": "Musterstadt",
                                                             "country": "DE"}})


def up(s, url, files, **form):
    fl = [("files", (n, d if isinstance(d, bytes) else d.encode(), "application/octet-stream")) for n, d in files]
    return s.post(B + url, files=fl, data=form)


def mt940(lines, ref="B1"):
    return f":20:{ref}\n:25:DE02120300000000202051\n:60F:C261001EUR0,00\n" + "".join(lines) + ":62F:C261031EUR0,00\n"


BAD_DAY = mt940([":61:2610021399C12,50NMSCNONREF\n:86:166?00Gutschrift?20SVWZ+Monat 13\n",
                 ":61:2610031003D5,00NMSCNONREF\n:86:105?00Lastschrift?20SVWZ+Gut\n"])
r = up(F, K + "/import/preview", [("tag.sta", BAD_DAY)])
rows = (r.json().get("rows") or []) if r.ok else []
check(r.status_code == 200 and len(rows) == 2 and [bool(x.get("error")) for x in rows].count(True) == 1
      and any(not x.get("error") and x.get("day") == "2026-10-03" for x in rows),
      f"#6435 3: a :61: with booking day 1399 is an unreadable row with its hint, the other is read - no 500 ({r.status_code} {r.text[:300]})")
r = up(F, K + "/import", [("tag.sta", BAD_DAY)])
check(r.status_code == 201 and r.json().get("count") == 1 and r.json().get("skipped") == 1,
      f"... and the import takes the good row, skips the bad one ({r.status_code} {r.text[:300]})")

# ================================================================== point 2: rows counted while reading, a file over it stops the import
P2 = r'''
import json
from kalmido.core.config import app
from kalmido.core import csvimport as cx, mt940 as mt
N = 50000
MT = ":20:X\n:25:DE02120300000000202051\n" + "".join(":61:2610021002C1,00NMSCNONREF\n" for _ in range(N))
CAMT = ('<?xml version="1.0"?><Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02"><BkToCstmrStmt><Stmt>'
        + "".join('<Ntry><Amt Ccy="EUR">1.00</Amt><CdtDbtInd>CRDT</CdtDbtInd><BookgDt><Dt>2026-10-02</Dt></BookgDt></Ntry>' for _ in range(N))
        + "</Stmt></BkToCstmrStmt></Document>")
CSV = "Datum;Betrag\n" + "".join("02.10.2026;1,00\n" for _ in range(N))
CALLS = [0]
_entry = mt._entry
def counting(*a, **kw):
    CALLS[0] += 1
    return _entry(*a, **kw)
mt._entry = counting
out = {}
def run(name, fn):
    try:
        fn()
        out[name] = "no error"
    except cx.RowsOver as e:
        out[name] = "RowsOver:" + str(e.args[0])
    except Exception as e:
        out[name] = type(e).__name__ + ":" + str(e)
with app.test_request_context():
    run("mt", lambda: mt.mt_parse(MT, max_rows=3000))
    out["mt_calls"] = CALLS[0]
    run("camt", lambda: cx.camt_rows(CAMT, max_rows=3000))
    run("csv", lambda: cx.csv_table(CSV))
    run("mt_ok", lambda: mt.mt_parse(MT[:5000], max_rows=3000))
print(json.dumps(out))
'''
R2 = py(P2)
check(str(R2.get("mt", "")).startswith("RowsOver:") and R2.get("mt_calls") == 3000,
      f"#6435 2: MT940 with 50,000 bookings stops at the first one over 3,000 (rows built: {R2.get('mt_calls')}) {R2.get('mt')}")
check(str(R2.get("camt", "")).startswith("RowsOver:") and str(R2.get("csv", "")).startswith("RowsOver:"),
      f"... CAMT and CSV the same {R2.get('camt')} {R2.get('csv')}")
check(R2.get("mt_ok") == "no error", f"... a small file reads as before {R2.get('mt_ok')}")
BIGMT = mt940([":61:2610021002C1,00NMSCNONREF\n" for _ in range(3001)], "BIG")
GOOD = mt940([":61:2610051005C7,00NMSCNONREF\n:86:166?00Gutschrift?20SVWZ+Klein\n"], "GOOD")
r = up(F, K + "/import/preview", [("gross.sta", BIGMT), ("klein.sta", GOOD)])
check(r.status_code == 400 and "gross.sta" in r.text and "3000" in r.text.replace(".", "").replace(",", ""),
      f"#6435 2: several files, one over the row limit: the import stops with the file named (was: skipped, read on) ({r.status_code} {r.text[:300]})")
r = up(F, K + "/import/preview", [("klein.sta", GOOD)])
check(r.ok and r.json().get("count") == 1, f"... the small file alone reads ({r.status_code} {r.text[:200]})")

# ================================================================== point 4: FinTS, one answer at most a 2 MB statement
P4 = r'''
import json
from kalmido.core.config import app
from kalmido.office import fints
from kalmido.office.bank import BNK_FILE_MAX
from kalmido.calendars.subscriptions import CalError
out = {"max": fints.FNT_HTTP_MAX, "file": BNK_FILE_MAX}
def conn(size):
    asked = []
    def http(url, method, data, headers, max_bytes=None, timeout=None, until=None):
        asked.append(max_bytes)
        if size > max_bytes:  # like cal_http: stops reading at max_bytes
            raise CalError("too_large")
        return 200, {}, b"QUFB" * (size // 4), url
    class Msg:
        def render_bytes(self):
            return b"HNHBK:1:3+"
    cn = fints._Conn("https://fints.example.com/", http=http, msg_cls=lambda segments: segments)
    try:
        cn.send(Msg())
        return ["ok", asked]
    except fints.FintsError as x:
        return [x.code, asked]
with app.test_request_context():
    out["big"] = conn(3 * 1024 * 1024)
    out["at_limit"] = conn(BNK_FILE_MAX * 4 // 3)
print(json.dumps(out))
'''
R4 = py(P4)
check(R4.get("big", [""])[0] == "too_large" and R4["big"][1] and R4["big"][1][0] <= R4.get("file", 0) * 4 // 3 + 256 * 1024,
      f"#6435 4: a FinTS answer of 3 MB is stopped while it is read (the reader is asked for at most a 2 MB statement as base64) {R4}")
check(R4.get("at_limit", [""])[0] == "ok", f"... a statement at the file limit (2 MB as base64) still comes in {R4.get('at_limit')}")

# ================================================================== point 8: a body over the request limit refused before it is read
def raw_post(path, length, chunked=False, wait=5.0):
    """Only the head (and for chunked one chunk of length bytes) of a POST; -> the status line waitress answers within wait
    seconds, '' when it waits for the body."""
    import socket
    import time
    host, port = B.split("//", 1)[1].split(":")
    sk = socket.create_connection((host, int(port)), timeout=wait)
    try:
        head = f"POST {path} HTTP/1.1\r\nHost: {host}\r\nX-Requested-With: kalmido\r\nContent-Type: application/octet-stream\r\n"
        head += "Transfer-Encoding: chunked\r\n\r\n" if chunked else f"Content-Length: {length}\r\n\r\n"
        sk.sendall(head.encode())
        if chunked:
            piece = b"x" * (1024 * 1024)
            sent, t_end = 0, time.monotonic() + 60
            try:
                while sent < length and time.monotonic() < t_end:
                    sk.sendall(b"%x\r\n" % len(piece) + piece + b"\r\n")
                    sent += len(piece)
            except OSError:  # the server closed the connection after its 413
                pass
        got = b""
        try:
            while b"\r\n" not in got:
                b = sk.recv(4096)
                if not b:
                    break
                got += b
        except (socket.timeout, OSError):
            pass
        return got.split(b"\r\n", 1)[0].decode("latin-1")
    finally:
        sk.close()


LIM = int(py("import json\nfrom kalmido.core.config import app\nprint(json.dumps({'m': app.config['MAX_CONTENT_LENGTH']}))").get("m") or 0)
st = raw_post("/api/office/bank/import", LIM + 2 * 1024 * 1024)
check(" 413 " in st + " ", f"#6435 8: a Content-Length over the request limit ({LIM // 1048576} MB) is answered 413 before its body is read: {st!r}")
st = raw_post("/api/admin/backups/upload", LIM + 2 * 1024 * 1024, wait=2.0)
check(st == "", f"... the restore upload waits for its body (its own 4 GB limit): {st!r}")
st = raw_post("/api/files/upload", LIM + 8 * 1024 * 1024, chunked=True)
check(" 413 " in st + " ", f"#6435 8: a chunked body is stopped once it grows past the limit: {st!r}")
r = F.get(B + "/api/state")
check(r.ok, f"the server serves on afterwards ({r.status_code})")

# ================================================================== point 9: JSON bodies, hit_limit, filter rules
import requests  # noqa: E402

anon = requests.Session()
anon.headers.update(kt.H)
JH = {"Content-Type": "application/json"}
r = anon.post(B + "/api/auth/login", json=["frida", "password123"])
check(r.status_code == 400, f"#6435 9: a JSON list as the body of the sign-in is 400, not 500 ({r.status_code} {r.text[:200]})")
r = anon.post(B + "/api/auth/login", json="frida")
check(r.status_code == 400, f"... a JSON text as well ({r.status_code})")
DEEP = "[" * 100000 + "]" * 100000
r = anon.post(B + "/api/auth/login", data=DEEP, headers=JH)
check(r.status_code == 400, f"#6435 9: JSON nested 100,000 deep at the sign-in is 400, not 500 ({r.status_code} {r.text[:200]})")
r = F.post(B + "/api/filters", data='{"name": "x", "rules": ' + "[" * 50000 + "]" * 50000 + "}", headers=JH)
check(r.status_code == 400, f"... and at any other route ({r.status_code} {r.text[:200]})")
r = F.post(B + "/api/filters", json=[{"name": "x"}])
check(r.status_code == 400, f"#6435 9: a list as the body of a route that reads an object is 400 ({r.status_code} {r.text[:200]})")
r = anon.post(B + "/api/auth/login", json={"username": "frida", "password": "password123"})
check(r.ok, f"... a real sign-in works ({r.status_code})")
# filter rules: size and form
big = {"op": "and", "conds": [{"f": "text", "op": "has", "v": "x" * 1000} for _ in range(100)]}
r = F.post(B + "/api/filters", json={"name": "Big", "rules": big})
check(r.status_code == 400, f"#6435 9: filter rules of 100 KB are refused ({r.status_code} {r.text[:200]})")
deep = {"op": "and", "conds": []}
x = deep
for _ in range(12):
    x["conds"] = [{"f": "text", "v": {}}]
    x = x["conds"][0]["v"]
r = F.post(B + "/api/filters", json={"name": "Deep", "rules": deep})
check(r.status_code == 400, f"... rules nested 12 levels deep too ({r.status_code})")
r = F.post(B + "/api/filters", json={"name": "Odd", "rules": "text"})
check(r.status_code == 400, f"... rules that are no object too (a private filter; was stored) ({r.status_code})")
r = F.post(B + "/api/filters", json={"name": "Good", "rules": {"op": "and", "conds": [{"f": "text", "op": "has", "v": "Rechnung"}]}})
fid = r.json().get("id") if r.ok else None
check(r.ok and fid, f"a normal filter is saved ({r.status_code} {r.text[:200]})")
r = F.patch(B + f"/api/filters/{fid}", json={"rules": big})
check(r.status_code == 400, f"... changing it to rules of 100 KB is refused ({r.status_code})")
P9 = r'''
import json, time
from kalmido.core.config import app
from kalmido.api import common
class Counting(dict):
    scans = 0
    def items(self):
        Counting.scans += 1
        return super().items()
now = time.time()
common._HITS = Counting({f"k{i}": [now] for i in range(25000)})
common._HITS_SWEPT[0] = 0.0
t = time.time()
for i in range(3000):
    common.hit_limit(f"n{i % 50}", 1000)
print(json.dumps({"scans": Counting.scans, "s": round(time.time() - t, 2), "keys": len(common._HITS)}))
'''
R9 = py(P9)
check(R9.get("scans") == 1, f"#6435 9: hit_limit with 25,000 busy keys scans them once per sweep time, not on every call {R9}")

# ================================================================== point 13: the card statement's PDF read in a limited process
P13 = r'''
import json, resource, time, zlib
from kalmido.core.config import app
from kalmido.office import ccread
import pypdf
CALLS = [0]
_R = pypdf.PdfReader
class Counting(_R):
    def __init__(self, *a, **kw):
        CALLS[0] += 1
        super().__init__(*a, **kw)
pypdf.PdfReader = Counting
def pdf(stream, flate=False):
    data = stream
    if flate:  # stream: a list of (bytes, times) - packed piece by piece, never whole in memory
        z, data = zlib.compressobj(9), b""
        for piece, n in stream:
            for _ in range(n):
                data += z.compress(piece)
        data += z.flush()
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
            b"<< /Length " + str(len(data)).encode() + (b" /Filter /FlateDecode" if flate else b"") + b" >>\nstream\n" + data + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offs = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += str(i).encode() + b" 0 obj\n" + o + b"\nendobj\n"
    x = len(out)
    out += b"xref\n0 6\n0000000000 65535 f \n" + b"".join(b"%010d 00000 n \n" % o for o in offs)
    return out + b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n" + str(x).encode() + b"\n%%EOF\n"
GOOD = pdf(b"BT /F1 12 Tf 72 700 Td (01.10.2026 01.10.2026 Kiosk Beispiel 12,50) Tj ET")
BOMB = pdf([(b"BT /F1 12 Tf 72 700 Td (", 1), (b"A" * (1024 * 1024), 600), (b") Tj ET", 1)], flate=True)  # 600 MB of text
out = {"bomb_bytes": len(BOMB)}
with app.test_request_context():
    t = time.time()
    out["good"] = ccread.ccr_text(GOOD)
    out["good_calls"] = CALLS[0]
    rss0 = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    t = time.time()
    out["bomb"] = ccread.ccr_text(BOMB)[:20]
    out["bomb_s"] = round(time.time() - t, 1)
    out["rss_mb_grew"] = (resource.getrusage(resource.RUSAGE_SELF).ru_maxrss - rss0) // 1024
    out["calls"] = CALLS[0]
    out["limit_s"] = ccread.PDF_SECONDS
print(json.dumps(out))
'''
R13 = py(P13, timeout=300)
check("Kiosk Beispiel" in (R13.get("good") or "") and R13.get("good_calls") == 0,
      f"#6435 13: the statement's text layer is read, by pypdf in another process (none in this one) {str(R13)[:300]}")
check(R13.get("bomb") is not None and R13.get("calls") == 0 and (R13.get("rss_mb_grew") or 0) < 200
      and (R13.get("bomb_s") or 999) <= (R13.get("limit_s") or 20) + 10,
      f"#6435 13: a PDF whose text unpacks to 600 MB is read in the limited process (memory / time), this one stays small: {str(R13)[:300]}")

sys.exit(kt.done("p21385_b1_haertung"))
