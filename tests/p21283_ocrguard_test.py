#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1283.0 (#6427): a slow PDF from outside (form, file request, mail) no longer stalls the text recognition and the
previews of every organisation; a false "picture" never reaches Tesseract. Own container (start.sh), the server's own
text queue is off (KALMIDO_FILE_OCR=off) so the queue's step is driven from here. Invented names only.
freelancer-matrix: n/a (no route new or changed in its answer; the preview route as a person without organisation: p2477_ablagethumb_test.py)
 - the slot per page (docs/ocr.py _Slot, _FairSem): while a five-page document is recognised, another waiting reader gets
   the slot right after page 1 (not after the last page); the slot is held while a page is read
 - the wall clock of one document (OCR_DOC_S, a clock handed in): 30 pages of 50 s each end after 6 pages / 300 s, the
   result is marked truncated, no tool gets more time than the document has left
 - pages cut off WITHOUT a time limit count (a tool killed by its CPU limit): 30 failing pages end after 2, "too_complex";
   one good page before them keeps its text
 - no slot at all -> "busy" (the caller tries again)
 - a picture only by its first bytes: path lines declared image/tiff -> ocr_bytes "unreadable", doc_text no text, Tesseract
   never started; with the real tools the text of a local picture named in such a list does not come back, a real PNG is read
 - the previews have their own slots: with the recognition's slot taken the preview route still answers a JPEG (was 429)
 - the page scan of a stack (docs/split.py) takes the slot per page as well
 - the files' queue (files/textscan.py ts_run_once) goes round the workspaces: A A A B waiting -> A, B, A, A
usage: p21283_ocrguard_test.py <datadir>   (P21283_NOSTART=1: the container runs already)"""
import json
import subprocess
import sys

import kt
from kt import CT, check

kt.fresh(prefix="P21283", env={"KALMIDO_FILE_OCR": "off"})

UNIT = r"""
import io, json, os, subprocess, sys, threading, time
import app
from kalmido.core.db import connect
from kalmido.core.pg import system_ctx
from kalmido.core.access import Denied
from kalmido.core.config import app as FLASK
from kalmido.docs import ocr as O, split as SP
from kalmido.files import textscan as TS, web as W
import kalmido.files.fslock as FL
from PIL import Image, ImageDraw, ImageFont

out = {}
real_run, real_tess, real_avail = O._run, O._tess, dict(O._AVAIL)


class R:
    def __init__(self, rc=0, stdout=b""):
        self.returncode, self.stdout, self.stderr = rc, stdout, b""


st = {}


def fake_run(args, timeout, fsize=0, data=None):
    if args[0] == "pdfinfo":
        return R(0, b"Pages: %d\n" % st["pages"])
    if args[0] == "pdftoppm":
        st["calls"].append((args[0], timeout))
        if st.get("raster_rc"):
            return R(st["raster_rc"])
        open(args[-1] + ".png", "wb").write(b"x")
        return R(0)
    if args[0] == "tesseract" and "--list-langs" in args:
        return R(0, b"deu\neng\n")
    raise AssertionError(args[0])


def reset(pages, tess):
    st.clear()
    st.update(calls=[], pages=pages, tess=0)
    O._run, O._tess = fake_run, tess
    O._AVAIL["ok"] = True


# ---- the slot per page: a waiting reader gets it after page 1
def comp():
    got = O._SEM.acquire(timeout=20)
    st["comp_at"] = st["tess"]
    if got:
        O._SEM.release()


def tess_fair(img, timeout, langs=None):
    st["tess"] += 1
    st.setdefault("held", []).append(not O._SEM.acquire(blocking=False) or bool(O._SEM.release()))
    if st["tess"] == 1:
        st["th"] = threading.Thread(target=comp)
        st["th"].start()
        end = time.monotonic() + 10
        while len(getattr(O._SEM, "_q", ())) < 1 and time.monotonic() < end:  # until the other reader really waits
            time.sleep(0.01)
    return "seite %d" % st["tess"]


reset(5, tess_fair)
r = O.ocr_bytes(b"%PDF-1.4 invented", "pdf")
st["th"].join(25)
out["fair"] = {"comp_at": st.get("comp_at"), "pages_read": r.get("pages_read"), "held": st["held"], "error": r.get("error")}

# ---- the wall clock of one document
now = [1000.0]


def tess_slow(img, timeout, langs=None):
    st["tess"] += 1
    st.setdefault("tmo", []).append(timeout)
    now[0] += 50
    return "seite %d" % st["tess"]


reset(30, tess_slow)
t0 = now[0]
r = O.ocr_bytes(b"%PDF-1.4 invented", "pdf", clock=lambda: now[0])
out["budget"] = {"pages_read": r.get("pages_read"), "truncated": r.get("truncated"), "took": now[0] - t0, "doc_s": O.OCR_DOC_S,
                 "tmo_max": max(st["tmo"]), "tmo_last": st["tmo"][-1], "page_s": O.OCR_PAGE_S, "text": r.get("text", "")[:20],
                 "error": r.get("error")}

# ---- pages cut off without a time limit count
reset(30, lambda img, timeout, langs=None: "nie")
st["raster_rc"] = 137
r = O.ocr_bytes(b"%PDF-1.4 invented", "pdf")
out["abort"] = {"error": r.get("error"), "raster": sum(1 for a in st["calls"] if a[0] == "pdftoppm")}


def tess_kill(img, timeout, langs=None):
    st["tess"] += 1
    if st["tess"] > 1:
        raise RuntimeError("tesseract")
    return "erste seite"


reset(30, tess_kill)
r = O.ocr_bytes(b"%PDF-1.4 invented", "pdf")
out["abort2"] = {"text": r.get("text", "").strip(), "pages_read": r.get("pages_read"), "truncated": r.get("truncated"), "tess": st["tess"]}

# ---- no slot at all: busy
reset(3, lambda img, timeout, langs=None: "x")
page_s = O.OCR_PAGE_S
O.OCR_PAGE_S = 0.1
O._SEM.acquire()
try:
    out["busy"] = O.ocr_bytes(b"%PDF-1.4 invented", "pdf")
    # ---- the page scan of a stack: the slot per page (none free -> None, never a wait for the whole stack)
    t = time.monotonic()
    out["split_busy"] = [SP.sp_scan(b"%PDF-1.4 invented", 3, "A"), time.monotonic() - t < 5]
finally:
    O._SEM.release()
    O.OCR_PAGE_S = page_s

# ---- a picture only by its first bytes
im = Image.new("RGB", (1400, 400), "white")
ImageDraw.Draw(im).text((60, 120), "Bananenkiste", fill="black", font=ImageFont.load_default(size=150))
b = io.BytesIO()
im.save(b, "PNG")
PNG = b.getvalue()
open("/tmp/k6427.png", "wb").write(PNG)
LIST = b"/tmp/k6427.png\n"
reset(1, lambda img, timeout, langs=None: st.__setitem__("tess", st["tess"] + 1) or "gelesen")
a = O.ocr_bytes(LIST, "image")
d = O.doc_text("scan.tif", "image/tiff", LIST)
g = O.doc_text("bild.gif", "image/gif", b"GIF89a" + b"\0" * 64)
n0 = st["tess"]
p = O.doc_text("bild.png", "image/png", PNG)
out["image_fake"] = {"ocr": a, "doc": d, "gif": g, "tess_before": n0, "png": p, "tess_after": st["tess"]}
O._run, O._tess = real_run, real_tess
O._AVAIL.clear()
if O.ocr_available():
    d = O.doc_text("scan.tif", "image/tiff", LIST)
    p = O.doc_text("bild.png", "image/png", PNG)
    out["image_real"] = {"list": d, "png": (p.get("text") or "")[:200], "png_err": p.get("error")}
else:
    out["image_real"] = None
os.unlink("/tmp/k6427.png")

# ---- the previews have their own slots
W.db = lambda: None
W.need_node = lambda c, nid: {"kind": "file", "mime": "image/png"}
FL.fl_is_locked = lambda c, nid: False
W.fs_version_row = lambda c, nid: {"size": len(PNG), "no": 1}
W.sc_guard = lambda *a, **k: None
W.hit_limit = lambda *a, **k: False
W.me = lambda: 1
W.fs_read = lambda c, nid, no=None: PNG
W.FS_THUMB_WAIT_S = 0.3
O._SEM.acquire()
try:
    with FLASK.test_request_context("/api/files/nodes/1/thumb"):
        try:
            resp = W.files_thumb(1)
            out["thumb"] = [resp.status_code, resp.get_data()[:2] == b"\xff\xd8"]
        except Denied as e:
            out["thumb"] = ["denied", getattr(e, "code", None) or (e.args[0] if e.args else None)]
finally:
    O._SEM.release()

# ---- the files' queue goes round the workspaces
seen = []
TS._rehome = lambda c, org_id=None: None
TS._docs_busy = lambda c: False
TS._backfill = lambda c: None


def proc(c, row):
    seen.append(row["ws"])
    c.execute("UPDATE file_text SET state='skip' WHERE id=?", (row["id"],))


TS._process = proc
c = connect()
with system_ctx(c):
    for i, ws in enumerate(("u900001", "u900001", "u900001", "u900002")):
        c.execute("INSERT INTO file_text(kind, ref_id, ws, state, created_at, updated_at) VALUES('att', ?, ?, 'wait', ?, ?)",
                  (900001 + i, ws, TS._now(), TS._now()))
c.commit()
steps = [TS.ts_run_once() for _ in range(5)]
with system_ctx(c):
    c.execute("DELETE FROM file_text WHERE ref_id BETWEEN 900001 AND 900004 AND kind='att'")
c.commit()
c.close()
out["queue"] = {"seen": seen, "steps": steps}
print("RESULT " + json.dumps(out, default=str))
"""

p = subprocess.run(["docker", "exec", CT, "python", "-c", UNIT], capture_output=True, text=True, timeout=600)
line = [x for x in p.stdout.splitlines() if x.startswith("RESULT ")]
check(p.returncode == 0 and line, "the unit part runs in the container " + p.stderr[-1500:])
u = json.loads(line[-1][7:]) if line else {}

f = u.get("fair") or {}
check(f.get("comp_at") == 1 and f.get("pages_read") == 5,
      f"the slot per page: a waiting reader gets it right after page 1 of 5 (not after the document) {f}")
check(f.get("held") == [True] * 5, f"the slot is held while a page is read {f}")

b = u.get("budget") or {}
check(b.get("pages_read") == 6 and b.get("truncated") is True and b.get("took", 9999) <= b.get("doc_s", 0) + 50,
      f"30 pages of 50 s each: the document ends at its wall clock (6 pages, about 300 s instead of 25 min), truncated {b}")
check(b.get("tmo_max", 9999) <= b.get("page_s", 0) and b.get("tmo_last", 9999) <= 50 and b.get("text", "").startswith("seite 1"),
      f"no tool gets more time than the document has left, the pages read keep their text {b}")

a = u.get("abort") or {}
check(a == {"error": "too_complex", "raster": 2}, f"30 pages whose tool is killed (no time limit): the document ends after 2 pages {a}")
a = u.get("abort2") or {}
check(a.get("text") == "erste seite" and a.get("pages_read") == 3 and a.get("truncated") is True and a.get("tess") == 3,
      f"a good page before two cut-off ones keeps its text, the rest is not tried {a}")

check(u.get("busy") == {"error": "busy"}, f"no slot within the waiting time -> busy (the caller tries again) {u.get('busy')}")
check(u.get("split_busy") == [None, True], f"the page scan of a stack asks for the slot per page: none free -> no plan, no long wait {u.get('split_busy')}")

i = u.get("image_fake") or {}
check(i.get("ocr") == {"error": "unreadable"} and (i.get("doc") or {}).get("method") == "none" and (i.get("doc") or {}).get("text") == ""
      and (i.get("gif") or {}).get("method") == "none" and i.get("tess_before") == 0,
      f"path lines declared image/tiff (and a GIF) never reach Tesseract {i}")
check((i.get("png") or {}).get("text") == "gelesen" and i.get("tess_after") == 1, f"a real PNG is still recognised {i}")
i = u.get("image_real")
if i is None:
    print("  .. no Tesseract in this image: the check with the real tools is skipped")
else:
    check("ananenkiste" not in json.dumps(i.get("list")), f"real tools: the text of a local picture named in a 'TIFF' of path lines does not come back {i.get('list')}")
    check("ananenkiste" in (i.get("png") or ""), f"real tools: the PNG itself is read {i}")

check(u.get("thumb") == [200, True], f"with the recognition's slot taken the preview of a picture still answers a JPEG (was 429) {u.get('thumb')}")

q = u.get("queue") or {}
check(q.get("seen") == ["u900001", "u900002", "u900001", "u900001"] and q.get("steps") == [1, 1, 1, 1, 0],
      f"the files' queue goes round the workspaces: A A A B waiting -> A, B, A, A {q}")

sys.exit(kt.done("p21283_ocrguard"))
