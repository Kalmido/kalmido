#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1269 (#6386): a fetched mail is no longer final before its import is.
 - an import cut off (the process ends in the middle) leaves an open attempt: the next round fetches the mail again by its
   UID (it is marked seen already) and takes it in, exactly once
 - an import that ended (committed) and was cut off right after: the next round does not take it in a second time
 - an importer that always fails: MAIL_TRIES (4: the first + 3 more) attempts in four rounds, then the mail is given up (it stays in the
   mailbox), lost() hears it exactly once, later rounds neither try it nor tell again; the other mails arrive all the same;
   the log holds no subject and no sender
 - an open attempt whose mail is gone from the folder ends without a try; the new mails arrive
 - the cut-off of a mailbox over its time (hub/mailbox.py _poll_in_time) leaves an open attempt, not a final one; the next
   round takes the mail in, the cut-off thread that comes back later takes in nothing (no double)
 - the notice: the instance admins (instance address), the owner of a mailbox of a person without organisation (freelancer)
   get one News item "N e-mails could not be taken over" (collab/integfail.py, event "integration")
Runs mail_fetch in processes of the test container (a fake IMAP server whose flags live in a file), no mail server.
usage: p6386_mail_tries_test.py <datadir>"""
import json
import os
import subprocess
import sys

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
from kt import B, CT, check, dbx, done, setup  # noqa: E402
from freelancer_fixture import freelancer  # noqa: E402

PRE = r'''
import inspect, json, os, sys, threading, time
import app
from kalmido.integrations import mail as M
from kalmido.core.db import connect
ST = "/tmp/p6386_%s.json"

class FakeIMAP:
    def __init__(self, name):
        self.p = ST % name
        self.st = json.load(open(self.p))
        self.read = lambda n: b""
    def save(self):
        json.dump(self.st, open(self.p, "w"))
    def select(self, f):
        return "OK", [b"1"]
    def shutdown(self):
        pass
    def uid(self, cmd, *a):
        if cmd == "SEARCH":
            return "OK", [" ".join(u for u in self.st["msgs"] if u not in self.st["seen"]).encode()]
        u = a[0].decode() if isinstance(a[0], bytes) else str(a[0])
        if cmd == "FETCH":
            if u not in self.st["msgs"]:
                return "OK", [None]
            raw = self.st["msgs"][u].encode()
            if "SIZE" in a[1]:
                return "OK", [b"1 (UID %s RFC822.SIZE %d)" % (u.encode(), len(raw))]
            return "OK", [(b"1 (UID %s RFC822 {%d}" % (u.encode(), len(raw)), raw), b")"]
        if cmd == "STORE":
            if a[1].startswith("-"):
                if "Seen" in a[2] and u in self.st["seen"]:
                    self.st["seen"].remove(u)
                    self.save()
            elif "Seen" in a[2] and u not in self.st["seen"]:
                self.st["seen"].append(u)
                self.save()
        return "OK", []

def mailbox(name, msgs):
    json.dump({"msgs": msgs, "seen": []}, open(ST % name, "w"))

def add(name, u, raw):
    st = json.load(open(ST % name))
    st["msgs"][u] = raw
    json.dump(st, open(ST % name, "w"))

def note(name, what):
    open("/tmp/p6386_%s.log" % name, "a").write(what + "\n")

def log(name):
    p = "/tmp/p6386_%s.log" % name
    return open(p).read().split() if os.path.exists(p) else []

def rows(name):
    c = connect()
    try:
        cols = {r[0] for r in c.execute("SELECT column_name FROM information_schema.columns WHERE table_name='mail_in_seen'").fetchall()}
        if "state" not in cols:  # (the version before #6386: no attempts)
            return [["claim", 0] for _ in c.execute("SELECT 1 FROM mail_in_seen WHERE box=?", ("test:p6386:" + name,)).fetchall()]
        return [list(r) for r in c.execute("SELECT state, tries FROM mail_in_seen WHERE box=? ORDER BY imap_uid", ("test:p6386:" + name,)).fetchall()]
    finally:
        c.close()

LOST = []
def fetch(name, imp, **k):
    if "lost" in inspect.signature(M.mail_fetch).parameters:
        k["lost"] = LOST.append
    return M.mail_fetch(FakeIMAP(name), "INBOX", imp, box="test:p6386:" + name, **k)

def mail(n, subject="Invoice", sender="Hidden Sender <hidden.sender@example.test>"):
    return f"Message-ID: <p6386-{n}@example.test>\r\nSubject: {subject} {n}\r\nFrom: {sender}\r\n\r\nBody {n}"

def key(raw):  # "Message-ID: <p6386-21@...>" -> "21"
    return raw.split("\r\n", 1)[0].split("<p6386-")[1].split("@")[0]
'''


def py(code, limit=120):
    """code in a second process of the container (no loops, role web: like p2193_d); -> (the last JSON line or {}, exit code)."""
    r = subprocess.run(["docker", "exec", "-i", "-w", "/app", "-e", "TASKS_WATCHDOG=0", "-e", "KALMIDO_ROLE=web", CT,
                        "timeout", str(limit), "python", "-c", PRE + code], capture_output=True, text=True, timeout=limit + 30)
    out = {}
    for ln in reversed((r.stdout or "").splitlines()):
        if ln.startswith("{"):
            out = json.loads(ln)
            break
    if r.returncode not in (0, 3) or (r.returncode == 0 and not out):
        print("PY FAILED:", r.returncode, r.stdout[-2000:], r.stderr[-3000:], flush=True)
    return out, r.returncode, r.stdout


# ---- 1. cut off in the middle of the import (the process ends): the next round fetches it again, exactly once
CUT = r'''
def imp(c, raw):
    k = key(raw.decode())
    if k == "1" and not os.path.exists("/tmp/p6386_cut.done"):
        open("/tmp/p6386_cut.done", "w").write("x")
        os._exit(3)  # a restart / kill in the middle of the import: nothing committed
    note("cut", k)
    return 1
if os.environ.get("P6386_STEP") == "0":
    mailbox("cut", {"1": mail(1), "2": mail(2)})
n = fetch("cut", imp)
print(json.dumps({"n": n, "log": log("cut"), "rows": rows("cut")}))
'''
_, rc, _ = py("os.environ['P6386_STEP']='0'\n" + CUT)
check(rc == 3, f"cut: the first round ends in the middle of the import (exit 3) {rc}")
j1, _, _ = py(CUT)
j2, _, _ = py(CUT)
check(sorted(j1.get("log") or []) == ["1", "2"], f"cut: the next round takes in the cut-off mail and the other one {j1}")
check(j2.get("n") == 0 and sorted(j2.get("log") or []) == ["1", "2"], f"cut: a third round takes in nothing more (exactly once) {j2}")
check(j1.get("rows") == [["done", 2], ["done", 1]], f"cut: the cut-off mail needed a second attempt, both are done {j1.get('rows')}")

# ---- 2. the import committed, cut off right after it: no second import
AFTER = r'''
def imp(c, raw):
    k = key(raw.decode())
    note("after", k)
    c.commit()  # the import is in the database
    if not os.path.exists("/tmp/p6386_after.done"):
        open("/tmp/p6386_after.done", "w").write("x")
        os._exit(3)  # cut off after the import, before mail_fetch goes on
    return 1
if os.environ.get("P6386_STEP") == "0":
    mailbox("after", {"1": mail(11)})
n = fetch("after", imp)
print(json.dumps({"n": n, "log": log("after"), "rows": rows("after")}))
'''
_, rc, _ = py("os.environ['P6386_STEP']='0'\n" + AFTER)
j, _, _ = py(AFTER)
check(rc == 3 and j.get("n") == 0 and j.get("log") == ["11"], f"after: an import that committed is not taken in a second time {rc} {j}")
check(j.get("rows") == [["done", 1]], f"after: its attempt ended with the import's commit {j.get('rows')}")

# ---- 3. an importer that always fails: three attempts, then given up, one notice; the other mails arrive
POISON = r'''
import io
def imp(c, raw):
    k = key(raw.decode())
    note("poison", "try" + k)
    if k == "21":
        raise RuntimeError("poison")
    return 1
if os.environ.get("P6386_STEP") == "0":
    mailbox("poison", {"1": mail(21), "2": mail(22)})
buf, old = io.StringIO(), sys.stdout
sys.stdout = buf
ns = []
try:
    for r in range(5):
        if r == 1:
            add("poison", "3", mail(23))  # a new mail between the rounds
        ns.append(fetch("poison", imp))
finally:
    sys.stdout = old
seen = json.load(open(ST % "poison"))
print(json.dumps({"n": ns, "log": log("poison"), "rows": rows("poison"), "lost": LOST, "out": buf.getvalue(), "seen": seen["seen"],
                  "left": sorted(seen["msgs"])}))
'''
j, _, _ = py("os.environ['P6386_STEP']='0'\n" + POISON)
lg = j.get("log") or []
check(lg.count("try21") == 4, f"poison: exactly four attempts (the first + 3 more) in five rounds {lg}")
check(lg.count("try22") == 1 and lg.count("try23") == 1 and j.get("n") == [1, 1, 0, 0, 0],
      f"poison: the other mails of the rounds arrive, each once {j.get('n')} {lg}")
check(j.get("lost") == [1], f"poison: given up after the last attempt, lost() hears it exactly once {j.get('lost')}")
check(j.get("rows") == [["gave", 4], ["done", 1], ["done", 1]], f"poison: given up after four, the others done {j.get('rows')}")
check(j.get("left") == ["1", "2", "3"], f"poison: the given-up mail stays in the mailbox {j.get('left')}")
out = j.get("out") or ""
check("RuntimeError" in out and "gave up 1" in out and "Invoice" not in out and "hidden.sender" not in out and "Hidden" not in out,
      f"poison: the log names the error and the count, no subject, no sender {out!r}")

# ---- 3b. an open attempt whose mail was removed by hand: nothing to try, the new mails arrive
GONE = r"""
def imp(c, raw):
    k = key(raw.decode())
    note("gone", k)
    if k == "41":
        raise RuntimeError("first try fails")
    return 1
mailbox("gone", {"1": mail(41)})
a = fetch("gone", imp)
st = json.load(open(ST % "gone"))
del st["msgs"]["1"]
st["msgs"]["2"] = mail(42)
json.dump(st, open(ST % "gone", "w"))
b = fetch("gone", imp)
print(json.dumps({"n": [a, b], "log": log("gone"), "rows": rows("gone")}))
"""
j, _, _ = py(GONE)
check(j.get("n") == [0, 1] and j.get("log") == ["41", "42"] and j.get("rows") == [["done", 1], ["done", 1]],
      f"gone: an open attempt of a removed mail ends, the new mail arrives {j}")

# ---- 3c. the UID of an open attempt names another mail now (UIDVALIDITY changed): the old attempt is lost and told, nothing is imported
OTHER = r"""
def imp(c, raw):
    note("other", key(raw.decode()))
    raise RuntimeError("fails")
mailbox("other", {"1": mail(51)})
a = fetch("other", imp)
st = json.load(open(ST % "other"))
st["msgs"]["1"] = mail(52)
json.dump(st, open(ST % "other", "w"))
b = fetch("other", imp)
b2 = fetch("other", imp)
print(json.dumps({"n": [a, b], "log": log("other"), "rows": rows("other"), "lost": LOST}))
"""
j, _, _ = py(OTHER)
check(j.get("n") == [0, 0] and j.get("log") == ["51"] and j.get("rows") == [["gave", 1]] and j.get("lost") == [1],
      f"other: an open attempt whose UID names another mail counts as lost (told once, not fetched again, the other mail not imported) {j}")

# ---- 3d. no database when the attempt is to be noted: the mail does not stay seen without an attempt, the next round takes it in
NODB = r"""
def imp(c, raw):
    note("nodb", key(raw.decode()))
    return 1
mailbox("nodb", {"1": mail(61)})
real = M.mail_try_start
def down(*a, **k):
    raise OSError("database is away")
M.mail_try_start = down
err = ""
try:
    fetch("nodb", imp)
except OSError as e:
    err = str(e)
seen = json.load(open(ST % "nodb"))["seen"]
M.mail_try_start = real
b = fetch("nodb", imp)
print(json.dumps({"err": err, "seen": seen, "n": b, "log": log("nodb"), "rows": rows("nodb")}))
"""
j, _, _ = py(NODB)
check(j.get("err") == "database is away" and j.get("seen") == [], f"nodb: the round ends, the mail is unseen again {j}")
check(j.get("n") == 1 and j.get("log") == ["61"] and j.get("rows") == [["done", 1]], f"nodb: the next round takes the mail in {j}")

# ---- 4. the cut-off of a mailbox over its time leaves an open attempt; no double when the cut-off thread comes back
OVER = r'''
from kalmido.hub import mailbox as MB
mailbox("over", {"1": mail(31)})
hold_up = threading.Event()
block = [True]
def imp(c, raw, pre=None):
    if c is None:  # the prefetch step (the invoice link downloads): the slow part
        if block[0]:
            hold_up.wait(120)
        return None
    note("over", key(raw.decode()))
    return 1
def poll_one(box, hold):
    f = FakeIMAP("over")
    hold.append(f)
    return M.mail_fetch(f, "INBOX", imp, box="test:p6386:over", prefetch=True)
MB.mbx_poll_one, MB.MBX_BOX_S = poll_one, 1
MB._poll_in_time({"ws": "p6386", "id": 0})  # over its time: cut off, the thread still waits in the downloads
cut = rows("over")
block[0] = False
n = poll_one({}, [])  # the next round
hold_up.set()  # the cut-off thread comes back
for t in threading.enumerate():
    if t.name == "mailbox-poll":
        t.join(60)
print(json.dumps({"cut": cut, "n": n, "log": log("over"), "rows": rows("over")}))
'''
j, _, _ = py(OVER, limit=200)
check(j.get("cut") == [["open", 1]], f"over time: the cut-off leaves an open attempt, not a final one {j.get('cut')}")
check(j.get("n") == 1 and j.get("log") == ["31"] and j.get("rows") == [["done", 2]],
      f"over time: the next round takes it in, the returning cut-off thread adds nothing {j}")

# ---- 5. the notice: instance admins, the owner of a freelancer's mailbox (a person without organisation)
A = setup()
FID, Fr = freelancer(B, A)
TELL = r'''
from kalmido.hub import mailbox as MB
M.IMAP.update(user="tasks@example.test")
M.mail_lost_instance(2)
MB._mbx_lost({"org_id": None, "owner_id": %d, "created_by": %d, "imap_user": "frida@example.test", "imap_host": "imap.example.test",
              "ws": ""}, 3)
c = connect()
r = [[x[0], x[1] if isinstance(x[1], dict) else json.loads(x[1])] for x in c.execute("SELECT user_id, data FROM notifications WHERE kind='integfail' ORDER BY id").fetchall()]
c.close()
print(json.dumps({"n": r}))
''' % (FID, FID)
j, _, _ = py(TELL)
got = {u: d for u, d in (j.get("n") or []) if d.get("what") == "maillost"}
admin = dbx("SELECT id FROM users WHERE username='alice'")[0][0]
check(len(j.get("n") or []) == 2 and set(got) == {admin, FID}, f"notice: one News item each for the instance admin and the freelancer {j}")
check("e-mails could not be taken over (2)" in got.get(admin, {}).get("text", "") and "tasks@example.test" in got.get(admin, {}).get("text", ""),
      f"notice: the instance address and the count {got.get(admin)}")
check("e-mails could not be taken over (3); they are still in the mailbox" in got.get(FID, {}).get("text", ""),
      f"notice: the freelancer's mailbox and its count {got.get(FID)}")
r = Fr.get(B + "/api/news")
check(r.ok and "could not be taken over" in r.text, f"notice: the freelancer sees it in the News {r.status_code}")

sys.exit(done("p6386_mail_tries"))
