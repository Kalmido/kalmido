#!/usr/bin/env python3
"""2.1282.0 (#6426): the entry limit of every ZIP reader holds BEFORE zipfile builds an object per entry, a zip64 record in
front of the end record no longer passes the check of the shared reader, the JSON parts of the account import and the
Paperless manifest are counted before json.loads, and a new import upload is rate limited. Everything is generated here.
 - unit (core/zipread.py with a stand-in for its tr(), no server): zip_guard counts what zipfile would build (plain,
   with a comment, with data in front, zip64); the attack files (end record says 1 entry, a zip64 record or the directory
   itself holds thousands) are refused without one call of zipfile and within a time limit; zip_read answers a zip64 ZIP
   with "cannot be read"; json_guard counts nodes outside of strings, in linear time
 - guard (static): every function of the app that opens a ZIP for reading calls zip_guard first (the known exceptions
   are named with their reason)
 - server, as a person without an organisation: the attack files through the real routes (documents upload, task
   import, knowledge import, account import, Paperless export) are refused with the limit's message; a good file of each
   kind still works; the rate limit of new import uploads answers 429 on all four routes and leaves another person alone
freelancer-matrix: import
usage: p21282_6426_zip_guard_test.py <datadir>"""
import ast
import hashlib
import importlib.util
import io
import json
import os
import struct
import sys
import time
import types
import zipfile

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
import kt  # noqa: E402
from kt import B, check, until  # noqa: E402
from freelancer_fixture import freelancer  # noqa: E402

SRC = os.environ.get("KALMIDO_SRC") or os.path.join(N, "..")
RATE = 12  # KALMIDO_IMPORT_RATE of this suite's container: the new uploads of the server part stay below it until the rate part


# ================================================================== unit: core/zipread.py
def load_zipread():
    pkg = types.ModuleType("zgpkg")
    pkg.__path__ = []
    sys.modules["zgpkg"] = pkg
    i18n = types.ModuleType("zgpkg.i18n")
    i18n.tr = lambda k, *a, **kw: k.format(*a) if a else k
    sys.modules["zgpkg.i18n"] = i18n
    spec = importlib.util.spec_from_file_location("zgpkg.zipread", os.path.join(SRC, "kalmido", "core", "zipread.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def plain_zip(n, comment=b"", zip64=False, ext="txt"):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        for k in range(n):
            if zip64:
                with z.open(zipfile.ZipInfo(f"f{k}.{ext}"), "w", force_zip64=True) as f:
                    f.write(b"x")
            else:
                z.writestr(f"f{k}.{ext}", b"x")
        z.comment = comment
    return b.getvalue()


def directory(n, ext=b""):
    """A central directory of n entries with nothing behind them (zipfile builds an object for each all the same)."""
    return b"".join(struct.pack("<4s4B4HL2L5H2L", b"PK\x01\x02", 20, 3, 20, 0, 0, 0, 0, 0, 0, 0, 0, 8 + len(ext), 0, 0, 0, 0, 0, 0)
                    + b"e%07d" % k + ext for k in range(n))


def zip64_attack(n, ext=b""):
    """The end record says: 1 entry, a directory of 54 bytes. The zip64 record in front of it says the truth: n entries."""
    cd = directory(n, ext)
    rec = struct.pack("<4sQ2H2L4Q", b"PK\x06\x06", 44, 45, 45, 0, 0, n, n, len(cd), 0)
    loc = struct.pack("<4sLQL", b"PK\x06\x07", 0, len(cd), 1)
    return cd + rec + loc + struct.pack("<4s4H2LH", b"PK\x05\x06", 0, 0, 1, 1, 54, 0, 0)


def count_attack(n, ext=b""):
    """No zip64: the end record's count says 1, its size is the true one of a directory of n entries."""
    cd = directory(n, ext)
    return cd + struct.pack("<4s4H2LH", b"PK\x05\x06", 0, 0, 1, 1, len(cd), 0, 0)


def refused(fn, kind):
    try:
        fn()
    except kind:
        return True
    except Exception as x:  # noqa: BLE001 -- the wrong error is the finding
        return f"{type(x).__name__}: {x}"
    return False


zr = load_zipread()
for what, raw in (("plain", plain_zip(7)), ("with a comment", plain_zip(7, comment=b"packed for you")),
                  ("with data in front", b"#!/bin/sh\n" * 50 + plain_zip(7)), ("zip64", plain_zip(7, zip64=True)),
                  ("empty", plain_zip(0)), ("the zip64 attack file", zip64_attack(40)), ("the count attack file", count_attack(40))):
    try:
        built = len(zipfile.ZipFile(io.BytesIO(raw)).infolist())
    except zipfile.BadZipFile:
        built = 0  # a Python that refuses the crafted file itself: the guard may count more, never less
    got = zr.zip_guard(raw, 1000)
    check(got >= built and (got == built or "attack" in what), f"zip_guard counts what zipfile builds ({what}): {got} / {built}")
check(zr.zip_guard(io.BytesIO(plain_zip(3)), 5) == 3, "zip_guard reads a file object like bytes")
check(refused(lambda: zr.zip_guard(plain_zip(11), 10), zr.ZipOver) is True, "zip_guard: one entry over the limit is refused (ZipOver)")
check(zr.zip_guard(plain_zip(10), 10) == 10, "zip_guard: exactly the limit passes")
for bad in (b"", b"PK", b"no zip at all " * 100, plain_zip(3)[:-5]):
    check(refused(lambda: zr.zip_guard(bad, 10), zr.ZipBad) is True, f"zip_guard: {len(bad)} bytes that are no ZIP -> ZipBad")
check(refused(lambda: zr.zip_guard(zip64_attack(2), 10, zip64=False), zr.ZipBad) is True,
      "zip_guard(zip64=False): a zip64 locator is refused whatever it says")

# the attack files: refused BEFORE zipfile is called, fast, whatever the fields say
calls = []
real = zr.zipfile.ZipFile


def counting(*a, **k):
    calls.append(1)
    return real(*a, **k)


zr.zipfile.ZipFile = counting
try:
    for what, raw in (("zip64 record in front of an end record of 1 entry", zip64_attack(3000, b".txt")),
                      ("end record with a count of 1 over a directory of 3000", count_attack(3000, b".txt"))):
        r = refused(lambda: zr.zip_read(raw, (".txt",), 1000), zr.ZipLimit)
        z = None if r is True else zr.zip_read(raw, (".txt",), 1000)
        check(not calls, f"zip_read: {what} -- zipfile is never called ({len(calls)} calls)")
        check(r is True or (z is not None and not z.files and z.errors and "cannot be read" in z.errors[0]["error"]),
              f"zip_read: {what} is refused ({r})")
        del calls[:]
    z = zr.zip_read(zip64_attack(5, b".txt"), (".txt",), 1000)
    check(not calls and not z.files and z.errors and "cannot be read" in z.errors[0]["error"],
          f"zip_read takes no zip64 ZIP at all, also a small one ({z.errors})")
    z = zr.zip_read(plain_zip(3), (".txt",), 1000)
    check(calls and [n for n, _ in z.files] == ["f0.txt", "f1.txt", "f2.txt"], "zip_read still reads a plain ZIP")
finally:
    zr.zipfile.ZipFile = real
big = zip64_attack(1_000_000)  # 54 MB of directory: zipfile needs about 400 MB and many seconds for it
for what, raw, limit in (("a million entries behind a zip64 record", big, 300_000),
                         ("a million entries, the limit of the account import", big, 200_000),
                         ("400 000 entries under a count of 1", count_attack(400_000), 300_000)):
    t = time.monotonic()
    r = refused(lambda: zr.zip_guard(raw, limit), zr.ZipOver)
    t = time.monotonic() - t
    check(r is True and t < 3, f"zip_guard: {what} is refused in {t:.2f} s (limit 3 s) {r}")
del big

# json_guard
check(zr.json_guard(b'{"a":"x,y[{","b":[1,2,{"c":null}]}', 100) == 7, "json_guard: commas and brackets inside a string do not count")
check(refused(lambda: zr.json_guard(b"[" + b"{}," * 1000 + b"{}]", 2000), zr.ZipOver) is True, "json_guard: 1001 empty objects are over 2000 nodes")
check(zr.json_guard(b"[" + b"{}," * 1000 + b"{}]", 2100) == 2003, "json_guard: ... and counted as 2003")
left = [3000]
zr.json_guard(b"[" + b"0," * 999 + b"0]", 5000, left)
check(left[0] == 3000 - 1001, f"json_guard lowers the caller's budget ({left[0]})")
check(refused(lambda: zr.json_guard(b"[" + b"0," * 2500 + b"0]", 5000, left), zr.ZipOver) is True, "json_guard: over what is left of the budget")
row = json.dumps({"id": 1, "title": "A task, with a comma", "note": "text " * 40, "tags": ["a", "b"], "done": False}).encode()
real_rows = b"[" + b",".join([row] * 50_000) + b"]"
n = zr.json_guard(real_rows, 4_000_000)
check(n == len(json.loads(real_rows)) * 8 + 1, f"json_guard: a real part of 50 000 rows ({len(real_rows) >> 20} MB) has {n} nodes and passes")
for what, raw in (("escaped quotes without an end", b'"' + b'\\"' * 4_000_000), ("... and a lone backslash last", b'"' + b'\\"' * 4_000_000 + b"\\"),
                  ("quotes only", b'"' * 8_000_001), ("32 MB of empty objects", b"[" + b"{}," * 10_600_000 + b"{}]")):
    t = time.monotonic()
    r = refused(lambda: zr.json_guard(raw, 4_000_000), zr.ZipOver)
    t = time.monotonic() - t
    check(t < 5 and r in (True, False), f"json_guard: {what} ({len(raw) >> 20} MB) is counted in {t:.2f} s (limit 5 s) {r}")
check(refused(lambda: zr.json_guard(b"[" + b"{}," * 10_600_000 + b"{}]", 4_000_000), zr.ZipOver) is True,
      "json_guard: the 24-times part (32 MB of empty objects) is refused before json.loads")

# ================================================================== guard (static): every reader calls zip_guard first
# who opens a ZIP for reading without the check, and why that is right (files/officeprev.py is not seen here: its reader is
# the text of a child process with memory and time limits of its own, without an import of the app)
NO_GUARD = {
    ("admin/backup.py", None): "the server's own backups, read by the instance admin from the backup folder",
    ("admin/bkstore.py", None): "the server's own backups",
    ("sheets/shbook.py", None): "the bytes the app wrote itself a line before",
    ("sheets/io.py", "_shx_all"): "the same bytes _shx_first checked a line before",
}


def opens_for_reading(call):
    f = call.func
    if not (isinstance(f, ast.Attribute) and f.attr == "ZipFile"):
        return False
    mode = call.args[1] if len(call.args) > 1 else next((k.value for k in call.keywords if k.arg == "mode"), None)
    return mode is None or (isinstance(mode, ast.Constant) and mode.value == "r")


found, missing = 0, []
root = os.path.join(SRC, "kalmido")
for d, _dirs, files in os.walk(root):
    for fn in files:
        if not fn.endswith(".py"):
            continue
        rel = os.path.relpath(os.path.join(d, fn), root).replace(os.sep, "/")
        with open(os.path.join(d, fn), encoding="utf-8") as f:
            text = f.read()
        if "ZipFile(" not in text:
            continue
        tree = ast.parse(text)
        for fun in [x for x in ast.walk(tree) if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef))]:
            own = [c for c in ast.walk(fun) if isinstance(c, ast.Call)]
            inner = {id(c) for sub in ast.walk(fun) if sub is not fun and isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef))
                     for c in ast.walk(sub) if isinstance(c, ast.Call)}
            opens = [c for c in own if id(c) not in inner and opens_for_reading(c)]
            if not opens:
                continue
            found += 1
            guards = [c.lineno for c in own if getattr(c.func, "id", getattr(c.func, "attr", "")) == "zip_guard"]
            if (rel, None) in NO_GUARD or (rel, fun.name) in NO_GUARD:
                continue
            if not guards or min(guards) > min(c.lineno for c in opens):
                missing.append(f"{rel}:{fun.name}")
check(found >= 9, f"guard: the readers were found ({found})")
check(not missing, f"guard: every function that opens a ZIP for reading calls zip_guard before zipfile.ZipFile "
                   f"(or is named in NO_GUARD with its reason): {missing}")

# ================================================================== server
kt.fresh(env={"KALMIDO_IMPORT_RATE": str(RATE)})
A = kt.setup()
FID, F = freelancer(B, A, "frida")
GID, G = freelancer(B, A, "gustav")
f = F.get(B + "/api/state").json()["settings"].get("features") or ""
if "docs" not in f.split(","):
    F.patch(B + "/api/settings", json={"features": f + ",docs"})
NEW = {"n": 0}  # new import uploads of frida so far (the rate part needs to know)


def alive(what):
    r = F.get(B + "/api/state")
    check(r.status_code == 200, f"{what}: the server still answers ({r.status_code})")


# ---- documents upload (the way of a mail attachment: docs/unpack.py -> zip_read). The test server takes 1 MB per file:
# 15 000 entries (0.9 MB) are far over every limit asked here (2000 / 300 / 8000)
t = time.monotonic()
r = F.post(B + "/api/docs", files={"files": ("scan.zip", zip64_attack(15_000, b".pdf"))}, data={"unzip": "1"})
t = time.monotonic() - t
check(r.status_code < 500 and "cannot be read" in r.text and "too many" not in r.text,
      f"documents: the zip64 attack file is answered as unreadable, not after building 15 000 entries ({r.status_code} {r.text[:160]})")
check(t < 20, f"documents: ... within {t:.1f} s")
alive("documents")

# ---- task import (integrations/importers.py imp_zip)
# (a ZIP by its first bytes: an empty local header in front of the directory)
r = F.post(B + "/api/import/notion", files={"file": ("export.zip", b"PK\x03\x04" + bytes(26) + count_attack(15_000, b".md"))}, data={"dry_run": "1"})
check(r.status_code == 400 and "too many files" in r.text, f"task import: the count attack file is refused ({r.status_code} {r.text[:160]})")
alive("task import")

# ---- knowledge import, the single request (wiki/wikiatt.py)
def md_zip(n):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        for k in range(n):
            z.writestr(f"notes/page-{k}.md", f"# Page {k}\n\ntext\n")
    return b.getvalue()


r = F.post(B + "/api/wiki/import", files={"file": ("wiki.zip", md_zip(3))})
NEW["n"] += 1
check(r.status_code == 200 and len(r.json().get("created") or []) == 3,
      f"knowledge import: a good ZIP of 3 pages still comes in ({r.status_code} {r.text[:200]})")
r = F.post(B + "/api/wiki/import", files={"file": ("wiki.zip", zip64_attack(15_000, b".md"))})
NEW["n"] += 1
check(r.status_code == 400 and "Too many files" in r.text, f"knowledge import: the zip64 attack file is refused ({r.status_code} {r.text[:160]})")
alive("knowledge import")


# ---- account import (admin/acctimport.py)
def sha(b):
    return hashlib.sha256(b).hexdigest()


def account_zip(entries):
    """An account export with the given data/<table>.json bytes (stored: the ratio limit is not what is tested here)."""
    entries = {f"data/{t}.json": b for t, b in entries.items()}
    flist = [{"path": p, "size": len(b), "sha256": sha(b)} for p, b in entries.items()]
    m = {"format": "kalmido-account", "v": 1, "kalmido_version": "test", "created_at": "2026-10-20T06:00:00Z",
         "source": {"url": "https://example.com", "hosted": True}, "user": {"id": 1000, "name": "Test Person", "email": "test@example.com"},
         "tables": {}, "files": flist, "client_encrypted": {}, "export_id": os.urandom(16).hex()}
    mb = json.dumps(m).encode()
    cs = f"{sha(mb)}  manifest.json\n" + "".join(f"{x['sha256']}  {x['path']}\n" for x in flist)
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_STORED) as z:
        z.writestr("manifest.json", mb)
        z.writestr("checksum.sha256", cs.encode())
        for p, b in entries.items():
            z.writestr(p, b)
    return bio.getvalue()


def acct_state(s, iid):
    j = s.get(B + f"/api/account/import/{iid}").json()
    return j if j.get("state") not in ("checking", "running", "upload") else None


def acct_upload(s, data):
    r = s.post(B + "/api/account/import", json={"size": len(data), "name": "kalmido-account.zip"})
    assert r.ok, r.text
    NEW["n"] += 1 if s is F else 0
    iid, off, step = r.json()["id"], 0, r.json().get("chunk") or (1 << 20)
    while off < len(data):
        part = data[off:off + step]
        r = s.put(B + f"/api/account/import/{iid}?offset={off}", data=part, headers={"Content-Type": "application/octet-stream"})
        assert r.ok, r.text
        off += len(part)
    return until(lambda: acct_state(s, iid), 180) or {}


j = acct_upload(F, account_zip({"lists": json.dumps([{"id": 1, "name": "Moved list"}]).encode(),
                                "tasks": json.dumps([{"id": 1, "title": "One task", "list_id": 1}]).encode()}))
check(j.get("state") == "preview", f"account import: a good file still reaches the preview ({j.get('state')} {j.get('error')})")
# 100 000 rows, each a dict with 26 empty lists: valid rows, 8 MB of text, 5.4 million nodes (4 million allowed per part)
dense = b"[" + b",".join([b'{"a":[' + b"[]," * 25 + b"[]]}"] * 100_000) + b"]"
check(len(json.loads(dense)) == 100_000 and len(dense) < 16 * 1024 * 1024, "account import: the dense part is valid JSON of 100 000 rows")
j = acct_upload(F, account_zip({"tasks": dense}))
check(j.get("state") == "invalid" and "too large" in json.dumps(j.get("error")) and "data/tasks.json" in json.dumps(j.get("error")),
      f"account import: a part of tiny values is refused by its nodes before it is parsed ({j.get('state')} {j.get('error')})")
# three parts below the limit of one part, together over the budget of the file
part = b"[" + b",".join([b'{"a":[' + b"[]," * 14 + b"[]]}"] * 100_000) + b"]"  # 3.2 million nodes each
j = acct_upload(F, account_zip({"tasks": part, "lists": part, "sections": part}))
check(j.get("state") == "invalid" and "too large" in json.dumps(j.get("error")),
      f"account import: parts that fit one by one are refused over the node budget of the file ({j.get('state')} {j.get('error')})")
j = acct_upload(F, zip64_attack(200_001))
check(j.get("state") == "invalid" and "too many parts" in json.dumps(j.get("error")),
      f"account import: 200 001 entries behind a zip64 record are refused ({j.get('state')} {j.get('error')})")
alive("account import")


# ---- Paperless export (paperless/zipimp.py)
def pl_state(s):
    return s.get(B + "/api/paperless?ws=private").json()


def pl_upload(s, data):
    r = s.post(B + "/api/paperless/zip", json={"ws": "private", "size": len(data), "name": "export.zip"})
    assert r.ok, r.text
    NEW["n"] += 1 if s is F else 0
    z = r.json()["zip"]
    n, chunk = z["next"], z["chunk"]
    while n * chunk < len(data):
        r = s.post(B + "/api/paperless/zip/part", data={"ws": "private", "n": str(n)}, files={"part": ("part", data[n * chunk:(n + 1) * chunk])})
        assert r.ok, r.text
        n += 1
    return until(lambda: (lambda z: z if z.get("state") != "check" else None)(pl_state(s).get("zip") or {}), 120) or {}


def pl_zip(manifest):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_STORED) as z:
        z.writestr("manifest.json", manifest)
        z.writestr("metadata.json", json.dumps({"version": "2.17.1"}))
    return b.getvalue()


z = pl_upload(F, pl_zip(json.dumps([{"model": "documents.tag", "pk": 1, "fields": {"name": "Tax"}}]).encode()))
check(z.get("error") != "zip_large", f"Paperless: a small export is not refused for its size ({z})")
z = pl_upload(F, pl_zip(b"[" + b"[]," * 4_100_000 + b"[]]"))  # 12 MB of text (64 MB allowed), 8.2 million nodes (8 million allowed)
check(z.get("state") == "bad" and z.get("error") == "zip_large",
      f"Paperless: a manifest of tiny values is refused by its nodes before it is parsed ({z})")
z = pl_upload(F, zip64_attack(300_001))
check(z.get("state") == "bad" and z.get("error") == "zip_large", f"Paperless: 300 001 entries behind a zip64 record are refused ({z})")
alive("Paperless")
# the upload counts against the storage when it is announced (it was only refused once the storage was full already)
check(A.patch(B + f"/api/users/{GID}", json={"storage_quota_mb": 1}).ok, "Paperless: gustav's storage is limited to 1 MB")
r = G.post(B + "/api/paperless/zip", json={"ws": "private", "size": 5 * 1024 * 1024, "name": "export.zip"})
check(r.status_code == 413 and r.json().get("code") == "quota_exceeded",
      f"Paperless: an upload larger than the free storage is refused when it is announced ({r.status_code} {r.text[:160]})")
r = G.post(B + "/api/paperless/zip", json={"ws": "private", "size": 200 * 1024, "name": "export.zip"})
check(r.status_code == 200, f"Paperless: one that fits is taken ({r.status_code} {r.text[:160]})")
check(A.patch(B + f"/api/users/{GID}", json={"storage_quota_mb": None}).ok, "Paperless: no limit again")

# ---- the rate limit of new import uploads: one counter for the four routes, per person
check(NEW["n"] < RATE, f"rate: the suite stayed below the limit so far ({NEW['n']} of {RATE})")
codes = []
for _ in range(RATE + 2):
    codes.append(F.post(B + "/api/account/import", json={"size": 1000, "name": "kalmido-account.zip"}).status_code)
    if codes[-1] != 200:
        break
check(codes[-1] == 429 and len(codes) == RATE + 1 - NEW["n"],
      f"rate: after {RATE} new uploads within 10 minutes ({NEW['n']} of them above) the next one is answered with 429 ({codes})")
r = F.post(B + "/api/wiki/import/upload", json={"size": 1000, "name": "wiki.zip"})
check(r.status_code == 429, f"rate: the knowledge upload of the same person: 429 ({r.status_code} {r.text[:120]})")
r = F.post(B + "/api/wiki/import", files={"file": ("wiki.zip", md_zip(1))})
check(r.status_code == 429, f"rate: the single knowledge import: 429 ({r.status_code} {r.text[:120]})")
r = F.post(B + "/api/paperless/zip", json={"ws": "private", "size": 1000, "name": "export.zip"})
check(r.status_code == 429, f"rate: the Paperless upload: 429 ({r.status_code} {r.text[:120]})")
r = F.post(B + "/api/import/markdown", files={"file": ("a.md", b"- [ ] one task\n")}, data={"dry_run": "1"})
check(r.status_code == 200, f"rate: a preview of the task import has its own counter ({r.status_code} {r.text[:120]})")
r = G.post(B + "/api/account/import", json={"size": 1000, "name": "kalmido-account.zip"})
check(r.status_code == 200, f"rate: another person is not held ({r.status_code} {r.text[:120]})")
r = G.post(B + "/api/wiki/import/upload", json={"size": 1000, "name": "wiki.zip"})
check(r.status_code == 200, f"rate: ... on the knowledge upload either ({r.status_code} {r.text[:120]})")

sys.exit(kt.done("p21282_6426_zip_guard"))
