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
 - pages cut off WITHOUT a time limit count (a tool killed by its CPU limit, a failure that took half the page time): 30
   such pages end after 2, "too_complex"; one good page before them keeps its text; pages that fail at once (damaged) do
   not count, the pages after them are still read; a cut document says "truncated" (doc_text)
 - no slot at all -> "busy" (the caller tries again)
 - a picture only by its first bytes: path lines declared image/tiff -> ocr_bytes "unreadable", doc_text no text, Tesseract
   never started; with the real tools the text of a local picture named in such a list does not come back, a real PNG is read
 - the previews have their own slots: with the recognition's slot taken the preview route still answers a JPEG (was 429)
 - the page scan of a stack (docs/split.py) takes the slot per page as well
 - the files' queue (files/textscan.py ts_run_once) goes round the workspaces: A A A B waiting -> A, B, A, A
 - 2.1337.0 (#6651): the hour budget of a workspace (ocr_charge / ocr_tired, a clock handed in): used up after its seconds,
   free again an hour later; the files' queue skips a used-up workspace (its file stays waiting, nothing dropped) and takes
   it once the budget frees up; a file marked anonymous (ts_mark_anon) comes with anon and is recognised with the shorter
   clock (OCR_ANON_S), a member's file with the full one; 30 pages of 50 s from an anonymous source end after 2 pages,
   truncated; a document from the mail / a file request gets the shorter clock, "Recognise again" (auto._full) the full one
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
st["raster_rc"] = -24  # SIGXCPU: the tool ran into its CPU limit
r = O.ocr_bytes(b"%PDF-1.4 invented", "pdf")
out["abort"] = {"error": r.get("error"), "raster": sum(1 for a in st["calls"] if a[0] == "pdftoppm")}


def tess_kill(img, timeout, langs=None):
    st["tess"] += 1
    if st["tess"] > 1:
        now[0] += 40  # a failure after 40 s of work (no time limit, no signal)
        raise RuntimeError("tesseract", 1)
    return "erste seite"


reset(30, tess_kill)
r = O.ocr_bytes(b"%PDF-1.4 invented", "pdf", clock=lambda: now[0])
out["abort2"] = {"text": r.get("text", "").strip(), "pages_read": r.get("pages_read"), "truncated": r.get("truncated"), "tess": st["tess"]}


def tess_damaged(img, timeout, langs=None):
    st["tess"] += 1
    if st["tess"] in (3, 5, 7):
        raise RuntimeError("tesseract", 1)  # fails at once
    return "seite %d" % st["tess"]


reset(10, tess_damaged)
r = O.ocr_bytes(b"%PDF-1.4 invented", "pdf")
out["damaged"] = {"pages_read": r.get("pages_read"), "truncated": r.get("truncated"), "last": r.get("text", "")[-8:], "tess": st["tess"]}
reset(O.OCR_PAGES + 5, lambda img, timeout, langs=None: "seite")  # more pages than are read
real_pdf_text, O.pdf_text = O.pdf_text, lambda data: {"no_text_layer": True}
r = O.doc_text("scan.pdf", "application/pdf", b"%PDF-1.4 invented")
O.pdf_text = real_pdf_text
out["doc_trunc"] = [r.get("method"), r.get("truncated")]

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
out["short"] = [O.ocr_is_image(b"\xff\xd8\xff\n/a.png"), O.ocr_bytes(b"\xff\xd8\xff\n/a.png", "image")]
d = O.doc_text("scan.tif", "image/tiff", LIST)
g = O.doc_text("bild.gif", "image/gif", b"GIF89a" + b"\0" * 64)
n0 = st["tess"]
p = O.doc_text("bild.png", "image/png", PNG)
out["image_fake"] = {"ocr": a, "doc": d, "gif": g, "tess_before": n0, "png": p, "tess_after": st["tess"]}
O._run, O._tess = real_run, real_tess
O._AVAIL.clear()
if O.ocr_available():
    d = O.doc_text("scan.tif", "image/tiff", LIST)
    t = O.doc_text("scan.tif", "image/tiff", b"II*\x00" + LIST * 3)  # a TIFF by its first bytes, path lines behind them
    p = O.doc_text("bild.png", "image/png", PNG)
    out["image_real"] = {"list": d, "tiff": t, "png": (p.get("text") or "")[:200], "png_err": p.get("error")}
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


real_proc = TS._process  # 2.1337.0 (#6651): used again below
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

# ---- 2.1337.0 (#6651): the hour budget of a workspace
tick = [5000.0]
clk = lambda: tick[0]  # noqa: E731
O._SPENT.clear()
O.ocr_charge("u900001", O.OCR_WS_HOUR_S - 10, clock=clk)
h1 = O.ocr_tired(clock=clk)
tick[0] += 1800
O.ocr_charge("u900001", 20, clock=clk)
h2 = O.ocr_tired(clock=clk)
tick[0] += 1801  # the first charge is older than an hour
h3 = O.ocr_tired(clock=clk)
out["hour"] = [h1, h2, h3, round(O.ocr_spent("u900001", clock=clk))]

# the files' queue skips a used-up workspace and takes it once its budget frees up; anon comes along
O._SPENT.clear()
O.ocr_charge("u900011", O.OCR_WS_HOUR_S)  # u900011 has used its hour
seen2 = []


def proc2(c, row):
    seen2.append([row["ws"], row["anon"]])
    c.execute("UPDATE file_text SET state='skip' WHERE id=?", (row["id"],))


TS._process = proc2
TS._Q["recent"] = []
c = connect()
with system_ctx(c):
    for ref, ws in ((900011, "u900011"), (900012, "u900012")):
        c.execute("INSERT INTO file_text(kind, ref_id, ws, state, created_at, updated_at) VALUES('att', ?, ?, 'wait', ?, ?)",
                  (ref, ws, TS._now(), TS._now()))
    on, TS.ON = TS.ON, True  # the server's own queue is off here (KALMIDO_FILE_OCR=off): ts_mark_anon writes only while on
    TS.ts_mark_anon(c, "att", 900012)
    TS.ON = on
c.commit()
s1 = [TS.ts_run_once(), TS.ts_run_once()]
with system_ctx(c):
    waiting = c.execute("SELECT state FROM file_text WHERE kind='att' AND ref_id=900011").fetchone()[0]
c.commit()
O._SPENT.clear()  # the hour went by
s1.append(TS.ts_run_once())
with system_ctx(c):
    c.execute("DELETE FROM file_text WHERE ref_id IN (900011, 900012) AND kind='att'")
c.commit()
out["queue_budget"] = {"seen": seen2, "steps": s1, "waiting": waiting}

# the shorter clock of an anonymous file (files/textscan.py _process -> doc_text(doc_s=...)), the budget charged
got = []
TS._ref = lambda c, k, i: {"name": "x.pdf", "mime": "application/pdf", "size": 10, "org_id": None, "owner_id": 1, "ws": "u900021"}
TS._infected = lambda c, k, i: False
TS._read = lambda c, k, i, ref: b"%PDF-1.4 anon " + str(i).encode()
TS.doc_text = lambda name, mime, data, doc_s=None, **kw: got.append(doc_s) or {"error": "too_complex"}
O._SPENT.clear()
with system_ctx(c):
    for ref, anon in ((900021, 1), (900022, 0)):
        fid = c.execute("INSERT INTO file_text(kind, ref_id, ws, state, anon, created_at, updated_at) VALUES('att', ?, 'u900021', 'run', ?, ?, ?) RETURNING id",
                        (ref, anon, TS._now(), TS._now())).fetchone()[0]
        real_proc(c, {"id": fid, "kind": "att", "ref_id": ref, "ws": "u900021", "anon": anon})
    rows = [list(x) for x in c.execute("SELECT ref_id, state, error FROM file_text WHERE ref_id IN (900021, 900022) AND kind='att' ORDER BY ref_id")]
    c.execute("DELETE FROM file_text WHERE ref_id IN (900021, 900022) AND kind='att'")
c.commit()
out["anon_files"] = {"doc_s": got, "anon_s": O.OCR_ANON_S, "charged": "u900021" in O._SPENT, "rows": rows}

# 30 pages of 50 s from an anonymous source end at its clock
reset(30, tess_slow)
t0 = now[0]
r = O.ocr_bytes(b"%PDF-1.4 invented", "pdf", clock=lambda: now[0], doc_s=O.OCR_ANON_S)
out["anon_clock"] = {"pages_read": r.get("pages_read"), "truncated": r.get("truncated"), "took": now[0] - t0, "anon_s": O.OCR_ANON_S}
O._run, O._tess = real_run, real_tess
O._AVAIL.clear()

# the documents: mail / file request -> the shorter clock, "Recognise again" (auto._full) the full one
from kalmido.docs import store as SS
out["doc_clock"] = [SS.anon_clock(c, {"source": s_, "auto": a_, "ws": "u1"}) for s_, a_ in
                    (("mail", ""), ("mailbox", "{}"), ("filereq", ""), ("upload", ""), ("folder", ""), ("mail", '{"_full":1}'))]
c.close()
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
      f"a good page before two that fail after 40 s keeps its text, the rest is not tried {a}")
a = u.get("damaged") or {}
check(a == {"pages_read": 10, "truncated": False, "last": "seite 10", "tess": 10},
      f"three damaged pages that fail at once do not end the document: all 10 pages are tried {a}")
check(u.get("doc_trunc") == ["ocr", True], f"doc_text says when not every page was read (truncated) {u.get('doc_trunc')}")
check(u.get("short") == [False, {"error": "unreadable"}], f"a 'JPEG' of a few bytes (too short for a header) never reaches Tesseract {u.get('short')}")

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
    check("ananenkiste" not in json.dumps(i.get("tiff")), f"real tools: TIFF bytes at the start and path lines behind them read no local picture either {i.get('tiff')}")
    check("ananenkiste" in (i.get("png") or ""), f"real tools: the PNG itself is read {i}")

check(u.get("thumb") == [200, True], f"with the recognition's slot taken the preview of a picture still answers a JPEG (was 429) {u.get('thumb')}")

q = u.get("queue") or {}
check(q.get("seen") == ["u900001", "u900002", "u900001", "u900001"] and q.get("steps") == [1, 1, 1, 1, 0],
      f"the files' queue goes round the workspaces: A A A B waiting -> A, B, A, A {q}")

h = u.get("hour") or []
check(h[:3] == [[], ["u900001"], []] and h[3] == 20,
      f"#6651: a workspace's hour budget: used up after its seconds, free again once they are older than an hour {h}")
q = u.get("queue_budget") or {}
check(q.get("seen") == [["u900012", 1], ["u900011", 0]] and q.get("steps") == [1, 0, 1] and q.get("waiting") == "wait",
      f"#6651: the files' queue skips a used-up workspace (its file waits, not dropped) and takes it once the budget frees up; "
      f"a file marked anonymous comes with anon {q}")
a = u.get("anon_files") or {}
check(a.get("doc_s") == [a.get("anon_s"), None] and a.get("charged") is True,
      f"#6651: an anonymous file is recognised with the shorter clock, a member's with the full one; the time is charged {a}")
a = u.get("anon_clock") or {}
check(a.get("pages_read") == 2 and a.get("truncated") is True and a.get("took", 9999) <= a.get("anon_s", 0) + 50,
      f"#6651: 30 pages of 50 s from an anonymous source end at its shorter clock (2 pages), truncated {a}")
dc = u.get("doc_clock") or []
check(len(dc) == 6 and dc[:3] == [dc[0]] * 3 and dc[0] and dc[3:] == [None, None, None],
      f"#6651: documents from the mail / a file request get the shorter clock; uploads, folders and 'Recognise again' the full one {dc}")

sys.exit(kt.done("p21283_ocrguard"))
