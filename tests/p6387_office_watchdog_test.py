#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1265.0 (#6387): the office in the watchdog -- the invoice series speak up instead of only writing to the log.
Invented companies, people and figures only. Its own container with the SMTP stub and a watchdog that does not tick by itself
(TASKS_WATCHDOG_INTERVAL=3600): every run is started here (rin_tick in its own process in the container), so the counts are exact.
 - a series that throws: the admin alert of the watchdog ("invoice series|<error class>", its id), the next series of the same run
   still makes and mails its invoice; the failed runs are counted at the series
 - three failed runs in a row pause the series and its admin gets the task "Invoice series ... paused" with the reason; a run that
   works in between sets the count back to 0
 - a series whose area has no admin with the office on: paused at once (no silent return every run) and, nobody to tell, the
   operator's admin alert
 - the mail after the invoice's commit: the process stops in between (os._exit in the container's process, like an update) ->
   the next run mails it once, a third run mails nothing; stopped again in that one try -> no second mail, a task "send it by hand"
 - a person without an organisation (freelancer, own admin of the personal office): her series run and fail the same way
2.1289.0 (#6629):
 - paused for nobody: the series stays off, but once the area has an admin with the office on again, that admin gets the task
   "Invoice series ... paused" with the reason, once (also the freelancer who switches her office off and on again)
 - (a) a database error in post() (after the invoice's commit) leaves no session lock on the connection: another connection's
   run mails the invoice
 - (b) a mail still due is never overwritten by the next period's invoice ("make now", a run while another connection still sends)
 - (c) the failed runs are counted strictly in a row: a run that works after a failure in post() sets the count back
 - a paused series with a mail still due: the mail goes out, the series stays paused
usage: p6387_office_watchdog_test.py <datadir>"""
import json
import os
import shutil
import subprocess
import sys
from datetime import date

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
from freelancer_fixture import FEATURES, freelancer  # noqa: E402
from kt import B, DATA, check, dbx, done, fresh, sess, setup  # noqa: E402

CT = os.environ.get("KALMIDO_TEST_CONTAINER", "kalmido-test")
OFF_API = "/api/office"
D = OFF_API + "/docs"
S = OFF_API + "/series"
TODAY = date.today().isoformat()
COMPANY = {"name": "Beispiel Film GmbH", "street": "Musterweg 1", "zip": "12345", "city": "Musterstadt", "country": "DE", "email": "hallo@beispiel.example",
           "vat_id": "DE123456789", "iban": "DE02120300000000202051", "bic": "BYLADEM1001", "bank_name": "Beispielbank"}


def in_ct(code):
    r = subprocess.run(["docker", "exec", CT, "python3", "-c", code], capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout


def tick(before="", after=""):
    """One run of the series watchdog in its own process; before = code run first (a hook of this test), after = code run
    after it while its connection c is still open (2.1289.0 #6629). -> the watchdog alerts it counted ({key: [ids]}),
    printed by the process when it got to the end."""
    out = in_ct("import json, os\nimport app\nfrom kalmido.core.db import connect\nfrom kalmido.office import recurring as x\n"
                "from kalmido.notify import alerts\nx._RIN_LAST['at'] = -1e12\n" + before +
                "\nc = connect()\nx.rin_tick(c)\n" + after + "\nc.close()\n"
                "print('AA=' + json.dumps({k[1]: sorted(v['items']) for k, v in alerts._AA['b'].items() if k[0] == 'watchdog'}))")
    line = [x for x in out.splitlines() if x.startswith("AA=")]
    return json.loads(line[-1][3:]) if line else None


CRASH = "x.rin_mail = lambda *a, **k: os._exit(0)"  # the process ends right before the customer mail, like an update would


def mails(to):
    try:
        rows = [json.loads(x) for x in open(os.path.join(DATA, "mail", "out.jsonl"), encoding="utf-8") if x.strip()]
    except FileNotFoundError:
        return []
    return [m for m in rows if to in json.dumps(m["to"])]


def office(s, name):
    assert s.put(B + OFF_API + "/settings", json={"lang": "de", "company_fields": {**COMPANY, "name": name}}).ok


def client(s, name, mail):
    r = s.post(B + "/api/clients", json={"name": name, "street": "Marktweg 5", "zip": "50667", "city": "Koeln", "country": "DE", "email_invoice": mail})
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def series(s, cl, title, start=TODAY):
    r = s.post(B + D, json={"kind": "invoice", "lang": "de", "client_id": cl, "project_title": title + " {month}",
                            "items": [{"title": "Betreuung", "qty": 1, "rate": 500}]})
    assert r.status_code == 201, r.text
    r = s.post(B + S, json={"template_id": r.json()["id"], "every": "monthly", "start": start, "auto_send": 1, "title": title})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def row(sid):
    try:
        r = dbx("SELECT active, fail_count FROM office_inv_series WHERE id=?", (sid,))
    except Exception as e:  # noqa: BLE001 -- a server without the column: the check says so
        return {"error": str(e)[:120]}
    return {"active": bool(r[0][0]), "fails": r[0][1]} if r else {}


def made(sid):
    return dbx("SELECT id, number, status FROM office_docs WHERE series_id=? ORDER BY id", (sid,))


def task(uid, *parts):
    like = "%" + "%".join(parts) + "%"
    return dbx("SELECT id FROM tasks WHERE assignee_id=? AND deleted_at IS NULL AND (title || ' ' || COALESCE(content, '')) LIKE ?", (uid, like))


def why(sid):
    r = dbx("SELECT pause_why FROM office_inv_series WHERE id=?", (sid,))
    return r[0][0] if r else "?"


def broken(sid):
    dbx("UPDATE office_inv_series SET start='kaputt' WHERE id=?", (sid,))  # a row the series code cannot read: rin_nth throws


fresh({"KALMIDO_INSTANCE_MODE": "workspaces", "KALMIDO_SMTP_HOST": "127.0.0.1", "KALMIDO_SMTP_PORT": "1025", "KALMIDO_SMTP_TLS": "none",
       "KALMIDO_MAIL_FROM": "kalmido@example.test", "TASKS_WATCHDOG_INTERVAL": "3600"})
shutil.copy(os.path.join(N, "stub_mail.py"), DATA)
subprocess.run(["docker", "exec", "-d", CT, "python", "/data/stub_mail.py"])
A = setup()
ALICE = A.get(B + "/api/state").json()["me"]["id"]
BOB = A.post(B + "/api/users", json={"username": "bob", "display_name": "Bob", "password": "password123", "email": "bob@example.com"}).json()["id"]
ORG = A.post(B + "/api/admin/orgs", json={"name": "Alpha", "admin_id": ALICE}).json()["id"]
ORG2 = A.post(B + "/api/admin/orgs", json={"name": "Beta", "admin_id": BOB}).json()["id"]
Bo = sess("bob")
assert A.patch(B + "/api/settings", json={"lang": "en", "features": FEATURES, "tour": "done", "workspace": f"org:{ORG}"}).ok
assert Bo.patch(B + "/api/settings", json={"lang": "en", "features": FEATURES, "tour": "done", "workspace": f"org:{ORG2}"}).ok
FID, Fr = freelancer(B, A)
office(A, "Alpha GmbH")
office(Bo, "Beta GmbH")
office(Fr, "Frida Schnitt")
CL = client(A, "Muster Medien AG", "rechnung@muster.example")
CLB = client(Bo, "Beta Kunde AG", "rechnung@beta.example")
CLF = client(Fr, "Studio Kunde", "rechnung@studio.example")
S_BAD = series(A, CL, "Kaputt")
S_FIX = series(A, CL, "Wackelt")
S_OK = series(A, CL, "Laeuft")
F_BAD = series(Fr, CLF, "Frida kaputt")
F_OK = series(Fr, CLF, "Frida laeuft")
S_NOBODY = series(Bo, CLB, "Ohne Admin")
for sid in (S_BAD, S_FIX, F_BAD):
    broken(sid)
fix_start = TODAY
# Beta's only admin switches the office off: nobody may make its series any more
assert Bo.patch(B + "/api/settings", json={"features": ",".join(x for x in FEATURES.split(",") if x != "office")}).ok

# ================================================================== (1) a series that throws is reported, the others run
aa = tick() or {}
fail = aa.get("invoice series|ValueError", [])
check(str(S_BAD) in fail and str(S_FIX) in fail, f"(1) the broken series are in the watchdog's admin alert {aa}")
check(str(F_BAD) in fail, f"(1) P4: the freelancer's broken series too {aa}")
ok = made(S_OK)
check(len(ok) == 1 and ok[0][1] and ok[0][2] == "sent", f"(1) the series after the broken one still makes and sends its invoice {ok}")
check(len(mails("rechnung@muster.example")) == 1, "(1) its mail went out once")
fk = made(F_OK)
check(len(fk) == 1 and fk[0][2] == "sent" and len(mails("rechnung@studio.example")) == 1, f"(1) P4: the freelancer's series runs and mails {fk}")
check(row(S_BAD) == {"active": True, "fails": 1} and row(F_BAD) == {"active": True, "fails": 1}, f"(2) one failed run counted {row(S_BAD)} {row(F_BAD)}")
check(row(S_OK).get("fails") == 0, f"(2) a series that works counts nothing {row(S_OK)}")

# ================================================================== (2) no admin: paused at once, the operator hears of it
check(row(S_NOBODY).get("active") is False, f"(2) a series without an admin with the office on is paused {row(S_NOBODY)}")
check(f"{ORG2}:{S_NOBODY}" in aa.get("invoice series without an admin|paused", []), f"(2) nobody to tell: the operator's admin alert {aa}")
check(not made(S_NOBODY) and not mails("rechnung@beta.example"), "(2) and no invoice")
aa = tick() or {}
check(f"{ORG2}:{S_NOBODY}" not in aa.get("invoice series without an admin|paused", []), f"(2) paused once: the next run is quiet {aa}")

# ================================================================== (2) three failed runs pause; a run that works sets the count back
check(row(S_BAD) == {"active": True, "fails": 2}, f"(2) the second failed run {row(S_BAD)}")
dbx("UPDATE office_inv_series SET start=? WHERE id=?", (fix_start, S_FIX))
check(row(S_FIX).get("fails") == 2, f"(2) the wobbly series failed twice {row(S_FIX)}")
tick()
fx = made(S_FIX)
check(len(fx) == 1 and fx[0][2] == "sent" and row(S_FIX) == {"active": True, "fails": 0}, f"(2) repaired: its invoice, the count back to 0 {fx} {row(S_FIX)}")
check(row(S_BAD) == {"active": False, "fails": 0}, f"(2) the third failed run in a row pauses the series {row(S_BAD)}")
check(bool(task(ALICE, "Invoice series Kaputt paused", "could not be made 3 times in a row")), "(2) its admin gets the task with the reason")
check(row(F_BAD) == {"active": False, "fails": 0} and bool(task(FID, "Invoice series Frida kaputt paused", "could not be made 3 times")),
      f"(2) P4: the freelancer's series is paused and she gets the task {row(F_BAD)}")
aa = tick() or {}
check(str(S_BAD) not in aa.get("invoice series|ValueError", []), f"(2) a paused series is left alone (no alert every run) {aa}")
check(len(task(ALICE, "Invoice series Kaputt paused")) == 1, "(2) and told once")

# ================================================================== 2.1289.0 (#6629): the admin comes back and is told, once
check(why(S_NOBODY) == "nobody", f"(6629) the reason is kept: nobody {why(S_NOBODY)}")
check(not task(BOB, "Invoice series Ohne Admin paused"), "(6629) nobody with the office on yet: no task")
assert Bo.patch(B + "/api/settings", json={"features": FEATURES}).ok  # Beta's admin switches the office on again
tick()
check(len(task(BOB, "Invoice series Ohne Admin paused", "had no admin with the office switched on")) == 1,
      "(6629) the admin who is back gets the task 'paused' with the reason")
check(row(S_NOBODY).get("active") is False and not made(S_NOBODY) and not mails("rechnung@beta.example"),
      f"(6629) the series does not start again by itself {row(S_NOBODY)}")
tick()
check(len(task(BOB, "Invoice series Ohne Admin paused")) == 1, "(6629) told once")
li = Bo.get(B + S).json()["items"]
check([x.get("pause_why") for x in li if x["id"] == S_NOBODY] == ["nobody_told"], f"(6629) the series list names the reason {li}")
r = Bo.patch(B + S + f"/{S_NOBODY}", json={"active": 1})
check(r.ok and r.json().get("active") == 1 and r.json().get("pause_why") is None and why(S_NOBODY) is None,
      f"(6629) switched on by the person: the reason is gone {r.text[:200]}")
tick()
check(len(made(S_NOBODY)) == 1 and len(mails("rechnung@beta.example")) == 1, f"(6629) and it runs again {made(S_NOBODY)}")

# ================================================================== (3) the mail after the invoice's commit
CLM = client(A, "Nachhol Medien AG", "rechnung@nachhol.example")
S_MAIL = series(A, CLM, "Neustart")
tick(CRASH)  # the invoice is committed (number, finalised), the process ends before its mail
m1 = made(S_MAIL)
check(len(m1) == 1 and m1[0][1] and m1[0][2] == "issued" and not mails("rechnung@nachhol.example"),
      f"(3) stopped between the commit and the mail: a finalised invoice with its number, no mail yet {m1}")
check(dbx("SELECT mail_doc FROM office_inv_series WHERE id=?", (S_MAIL,)) == [(m1[0][0],)] if m1 else False, "(3) the mail is marked as still due")
tick()
m2 = made(S_MAIL)
check(len(mails("rechnung@nachhol.example")) == 1 and len(m2) == 1 and m2[0][2] == "sent", f"(3) the next run mails it once {m2}")
check(dbx("SELECT mail_doc, mail_try FROM office_inv_series WHERE id=?", (S_MAIL,)) == [(None, 0)], "(3) the mark is gone")
tick()
check(len(mails("rechnung@nachhol.example")) == 1 and len(made(S_MAIL)) == 1, "(3) a third run mails nothing again, no second invoice")

CLH = client(A, "Zweimal Weg AG", "rechnung@zweimal.example")
S_HAND = series(A, CLH, "Zweimal")
tick(CRASH)
tick(CRASH)  # the one more try stops as well
tick()
h = made(S_HAND)
check(len(h) == 1 and h[0][2] == "issued" and not mails("rechnung@zweimal.example"), f"(3) stopped in the one more try too: no second try, no mail {h}")
check(bool(task(ALICE, "Invoice of series Zweimal not sent", f"Invoice {h[0][1] if h else '?'} is finalised", "Send it by hand")),
      "(3) a task: send it by hand")
check(dbx("SELECT mail_doc FROM office_inv_series WHERE id=?", (S_HAND,)) == [(None,)], "(3) the mark is gone")
tick()
check(not mails("rechnung@zweimal.example"), "(3) and later runs mail nothing")

# ================================================================== 2.1289.0 (#6629): a paused series with a mail still due
CLQ = client(A, "Pause Post AG", "rechnung@pausepost.example")
S_PM = series(A, CLQ, "Pausepost")
tick(CRASH)
assert A.patch(B + S + f"/{S_PM}", json={"active": 0}).ok  # the person pauses it while its mail is still due
tick()
pm = made(S_PM)
check(len(pm) == 1 and pm[0][2] == "sent" and len(mails("rechnung@pausepost.example")) == 1 and row(S_PM).get("active") is False,
      f"(6629) a paused series still mails the invoice it made, once, and stays paused {pm} {row(S_PM)}")

# ================================================================== 2.1289.0 (#6629 a): a database error in post() keeps no lock
CLP = client(A, "Post Fehler AG", "rechnung@postfehler.example")
S_POST = series(A, CLP, "Postfehler")
# the mail is refused and the task about it hits a database error (the transaction is aborted); then, with this connection
# still open, another connection's run: it must mail the invoice (was: the lock stayed, "still being sent", silent every run)
aa = tick("_m, _b = x.rin_mail, x.rin_bundle\nx.rin_mail = lambda *a, **k: (False, ['unknown'])\n"
          "x.rin_bundle = lambda c, *a, **k: c.execute('SELECT 1/0').fetchone()",
          "x.rin_mail, x.rin_bundle = _m, _b\nx._RIN_LAST['at'] = -1e12\nc2 = connect()\nx.rin_tick(c2)\nc2.close()") or {}
check(any(str(S_POST) in v for k, v in aa.items() if k.startswith("invoice series|")),
      f"(6629 a) the error in post() is the watchdog's alert {aa}")
po = made(S_POST)
check(len(po) == 1 and po[0][2] == "sent" and len(mails("rechnung@postfehler.example")) == 1,
      f"(6629 a) no lock left on the connection: the other connection's run mails it {po}")

# ================================================================== 2.1289.0 (#6629 b): a mail still due is never overwritten
CLR = client(A, "Jetzt Medien AG", "rechnung@jetzt.example")
S_RUN = series(A, CLR, "Jetzt")
tick(CRASH)  # the first invoice: finalised, its mail still due
r = A.post(B + S + f"/{S_RUN}/run", json={})
check(r.ok, f"(6629 b) make now {r.status_code} {r.text[:200]}")
rr = made(S_RUN)
check(len(rr) == 2 and all(x[2] == "sent" for x in rr) and len(mails("rechnung@jetzt.example")) == 2,
      f"(6629 b) 'make now' first mails the invoice still due, then the new one (was: its mark overwritten, never mailed) {rr}")
check(dbx("SELECT mail_doc FROM office_inv_series WHERE id=?", (S_RUN,)) == [(None,)], "(6629 b) no mark left")

CLL = client(A, "Halte Medien AG", "rechnung@halte.example")
_t = date.today()
past = date(_t.year - (_t.month <= 2), (_t.month - 3) % 12 + 1, min(_t.day, 28)).isoformat()  # two months back: three periods due
S_LOCK = series(A, CLL, "Halte", past)
tick(CRASH)  # period 1: finalised, mail still due; the next periods are due as well
h1 = made(S_LOCK)
assert len(h1) == 1, h1
# another connection still sends it (holds the lock): this run must not make the next period over its mark
tick(f"_h = connect()\n_h.execute('SELECT pg_advisory_lock(hashtext(?))', ('office_series_mail_{h1[0][0]}',)).fetchone()")
check(len(made(S_LOCK)) == 1, f"(6629 b) the run waits while the mail still due is being sent {made(S_LOCK)}")
tick()
hl = made(S_LOCK)
check(len(hl) == 2 and all(x[2] == "sent" for x in hl) and len(mails("rechnung@halte.example")) == 2,
      f"(6629 b) then the mail still due goes out and the next period is made and mailed {hl}")

# ================================================================== 2.1289.0 (#6629): the freelancer switches her office off and on
F_AUS = series(Fr, CLF, "Frida aus")
assert Fr.patch(B + "/api/settings", json={"features": ",".join(x for x in FEATURES.split(",") if x != "office")}).ok
tick()
check(row(F_AUS).get("active") is False and why(F_AUS) == "nobody" and not made(F_AUS), f"(6629) P4: her office off: paused for nobody {row(F_AUS)}")
assert Fr.patch(B + "/api/settings", json={"features": FEATURES}).ok
tick()
tick()
check(len(task(FID, "Invoice series Frida aus paused", "had no admin")) == 1 and row(F_AUS).get("active") is False,
      "(6629) P4: her office on again: she gets the task once, the series stays off")

check(dbx("SELECT COUNT(*) FROM office_docs WHERE series_id IS NOT NULL GROUP BY series_id, series_period HAVING COUNT(*) > 1") == [], "never two invoices for one period")

sys.exit(done("p6387_office_watchdog"))
