#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1337.0 (#6600): an organisation that is moving ("Umzug") is read only - one lock in the write path (core/movelock.py).
Invented companies, people and figures only. tenant-matrix: org
 - only an admin of the organisation starts the move (a member 403, an admin of another organisation 404 also for reading the
   state), with the organisation's name typed (else 400); twice = 409; every member's state carries the move (reason, who)
 - while it moves, every way of writing answers 423 "org_moving": a member's new task, the admin's settings of the organisation
   (its own row), a new project, an office document, an agent / API token (/api/v1), the public form (JSON and an HTML page);
   reading stays (the project, its tasks), the members' private things and other organisations go on, the freelancer too
 - the export of the organisation runs on this fixed state; the invoice series of the organisation rests in the watchdog
 - the history of the organisation names the start and the end
 - ending it: a member 403, its admin 200 - writing works again, the series whose period came meanwhile is paused (not made
   late, decision of 16.11.2026) and its admin gets the task "Invoice series ... paused"; the next watchdog run makes nothing
 - 2.1413.0 (#6951): opening the agreements while moving purges nothing of the organisation's trash (after the move it does);
   a queue row added by a writing request is strict (runs inside the lock), by a reading one or after mv_allow not; an instance
   admin who is no member ends a move (noted in the organisation's history), anybody else still 404
usage: p6600_org_moving_test.py <datadir>"""
import os
import re
import subprocess
import sys
import time
from datetime import date

import requests

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
from freelancer_fixture import FEATURES, freelancer  # noqa: E402
from kt import B, H, check, dbx, done, fresh, sess, setup, until  # noqa: E402

CT = os.environ.get("KALMIDO_TEST_CONTAINER", "kalmido-test")
TODAY = date.today().isoformat()
OFF = "/api/office"
COMPANY = {"name": "Alpha Umzug GmbH", "street": "Musterweg 1", "zip": "12345", "city": "Musterstadt", "country": "DE",
           "email": "hallo@alpha.example", "vat_id": "DE123456789", "iban": "DE02120300000000202051", "bic": "BYLADEM1001",
           "bank_name": "Beispielbank"}


def in_ct(code):
    r = subprocess.run(["docker", "exec", CT, "python3", "-c", code], capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout


def tick():
    """One run of the series watchdog in its own process (the container's watchdog does not tick by itself here)."""
    in_ct("import app\nfrom kalmido.core.db import connect\nfrom kalmido.office import recurring as x\n"
          "x._RIN_LAST['at'] = -1e12\nc = connect()\nx.rin_tick(c)\nc.close()\n")


def moving423(r, what):
    try:
        j = r.json()
    except ValueError:
        j = {}
    e = j.get("error") if isinstance(j, dict) else None
    code = e.get("code") if isinstance(e, dict) else (j.get("code") if isinstance(j, dict) else None)
    check(r.status_code == 423 and code == "org_moving", f"{what}: 423 org_moving ({r.status_code} {r.text[:160]})")


def series(sid):
    r = dbx("SELECT active, next_date, pause_why FROM office_inv_series WHERE id=?", (sid,))
    return (bool(r[0][0]), r[0][1], r[0][2]) if r else None


def made(sid):
    return dbx("SELECT id, number FROM office_docs WHERE series_id=? ORDER BY id", (sid,))


fresh({"KALMIDO_INSTANCE_MODE": "workspaces", "TASKS_WATCHDOG_INTERVAL": "3600"})
A = setup()
A.patch(B + "/api/admin/settings", json={"public_links": True})
ALICE = A.get(B + "/api/state").json()["me"]["id"]
CAROL = A.post(B + "/api/users", json={"username": "carol", "display_name": "Carol Beta", "password": "password123",
                                       "email": "carol@example.com", "orgs": []}).json()["id"]
ORG = A.post(B + "/api/admin/orgs", json={"name": "Alpha", "admin_id": ALICE}).json()["id"]
ORG2 = A.post(B + "/api/admin/orgs", json={"name": "Beta", "admin_id": CAROL}).json()["id"]
r = A.post(B + "/api/users", json={"username": "bob", "display_name": "Bob Member", "password": "password123",
                                   "email": "bob@example.com", "orgs": [ORG]})
assert r.ok, r.text
BOB = r.json()["id"]
Bo, Ca = sess("bob"), sess("carol")
for s, ws in ((A, ORG), (Bo, ORG), (Ca, ORG2)):
    assert s.patch(B + "/api/settings", json={"lang": "en", "features": FEATURES, "tour": "done", "workspace": f"org:{ws}"}).ok
FID, Fr = freelancer(B, A)
check(any(w["id"] == ORG for w in Bo.get(B + "/api/state").json()["me"]["workspaces"]), "setup: bob is a member of Alpha")

# the organisation's things before the move: a project with a task, a public form, an office with an invoice series due today
L = A.post(B + "/api/lists", json={"name": "Alpha project", "org_id": ORG}).json()["id"]
assert A.put(B + f"/api/lists/{L}/members", json={"user_id": BOB, "role": "edit"}).ok
T = A.post(B + "/api/tasks", json={"title": "Before the move", "list_id": L}).json()["id"]
FORM = A.post(B + f"/api/lists/{L}/forms", json={"title": "Requests", "access": "public"}).json()
FTOK = FORM["url"].rsplit("/", 1)[1]
assert A.put(B + OFF + "/settings", json={"lang": "de", "company_fields": COMPANY}).ok
CL = A.post(B + "/api/clients", json={"name": "Muster Medien AG", "street": "Marktweg 5", "zip": "50667", "city": "Koeln",
                                      "country": "DE", "email_invoice": "rechnung@muster.example"}).json()["id"]
r = A.post(B + OFF + "/docs", json={"kind": "invoice", "lang": "de", "client_id": CL, "project_title": "Betreuung {month}",
                                    "items": [{"title": "Betreuung", "qty": 1, "rate": 500}]})
assert r.status_code == 201, r.text
r = A.post(B + OFF + "/series", json={"template_id": r.json()["id"], "every": "monthly", "start": TODAY, "auto_send": 0, "title": "Monatlich"})
assert r.status_code == 201, r.text
SER = r.json()["id"]
# 2.1413.0 (#6951): an agreement in the office's trash whose period is over (a reading request must not purge it while moving)
r = A.post(B + OFF + "/agreements", json={"kind": "insurance", "name": "Alte Versicherung", "task": 0})
assert r.status_code == 201, r.text
AGR = r.json()["id"]
dbx("UPDATE office_agreements SET archived=2, updated_at='2000-01-01T00:00:00+00:00' WHERE id=?", (AGR,))
TOKEN = Bo.post(B + "/api/me/tokens", json={"name": "bobs agent", "scopes": ["read", "write"]}).json()["token"]
API = {"Authorization": "Bearer " + TOKEN}
check(requests.post(B + "/api/v1/tasks", headers=API, json={"title": "API before", "list_id": L}).status_code == 201,
      "before: bob's token writes a task into the organisation's project")

# ================================================================== (1) who may start it
M = f"/api/orgs/{ORG}/moving"
check(A.get(B + M).json() == {"moving": False}, "before: not moving")
# tenant: GET /api/orgs/{}/moving
# tenant: POST /api/orgs/{}/moving
# tenant: DELETE /api/orgs/{}/moving
check(Ca.get(B + M).status_code == 404 and Ca.post(B + M, json={"confirm": "Alpha"}).status_code == 404
      and Ca.delete(B + M).status_code == 404, "the admin of another organisation: 404 for the state, start and end")
check(Bo.post(B + M, json={"confirm": "Alpha"}).status_code == 403, "a member who is no admin: 403")
check(A.post(B + M, json={"why": "Umzug zu eigenem Server"}).status_code == 400
      and A.post(B + M, json={"confirm": "Alphx"}).status_code == 400, "without the name typed (or a wrong one): 400, nothing starts")
check(A.get(B + M).json() == {"moving": False}, "... and the organisation is not moving")
r = A.post(B + M, json={"confirm": "alpha ", "why": "Umzug zu eigenem Server"})
check(r.ok and r.json().get("moving") is True and r.json().get("by_name") == "Alice Admin" and r.json().get("why") == "Umzug zu eigenem Server",
      f"its admin starts it with the name typed (case and spaces do not matter) {r.status_code} {r.text[:200]}")
check(A.post(B + M, json={"confirm": "Alpha"}).status_code == 409, "a second start: 409")
ws = {w["id"]: w for w in Bo.get(B + "/api/state").json()["me"]["workspaces"]}
mv = ws.get(ORG, {}).get("moving") or {}
check(mv.get("by_name") == "Alice Admin" and mv.get("why") == "Umzug zu eigenem Server" and mv.get("since"),
      f"every member's state carries the move for the bar (who, why, since): {mv}")
check(Bo.get(B + M).json().get("moving") is True, "a member reads the state")
check("moving" not in {w["id"]: w for w in Ca.get(B + "/api/state").json()["me"]["workspaces"]}.get(ORG2, {}), "another organisation: no bar")

# ================================================================== (2) every way of writing: 423
moving423(Bo.post(B + "/api/tasks", json={"title": "During the move", "list_id": L}), "a member's new task in the organisation")
moving423(Bo.patch(B + f"/api/tasks/{T}", json={"title": "changed"}), "a member changes a task of the organisation")
moving423(A.patch(B + f"/api/orgs/{ORG}", json={"color": "#2dd4bf"}), "the admin changes the organisation's own settings")
moving423(A.post(B + "/api/lists", json={"name": "New project", "org_id": ORG}), "a new project in the organisation")
moving423(A.post(B + OFF + "/docs", json={"kind": "invoice", "lang": "de", "client_id": CL, "items": [{"title": "x", "qty": 1, "rate": 1}]}),
          "a new office document (no new number either)")
r = requests.post(B + "/api/v1/tasks", headers=API, json={"title": "API during", "list_id": L})
moving423(r, "bob's API token (an agent's way in)")
check("read-only" in r.text, f"... with the message ({r.text[:160]})")
anon = requests.Session()
anon.headers.update(H)
def stamp():
    page = anon.get(B + "/f/" + FTOK)
    m = re.search(r'name="stamp" value="([^"]+)"', page.text)
    return page.status_code, (m.group(1) if m else "")


code1, ST1 = stamp()
code2, ST2 = stamp()
check(code1 == 200 and ST1 and ST2, f"the public form still opens (reading) {code1}")
until(lambda: time.time() - int((ST2 or "0").split(".")[0] or 0) > 3.2, 10)  # the stamp's least age (FRM_MIN_S): a real state
r = anon.post(B + "/f/" + FTOK, data={"subject": "Eine Anfrage", "text": "Hallo", "name": "Eve", "stamp": ST1})
moving423(r, "the public form sent by a script (JSON)")
r = anon.post(B + "/f/" + FTOK, data={"subject": "Eine Anfrage", "text": "Hallo", "name": "Eve", "stamp": ST2},
              headers={"Accept": "text/html,application/xhtml+xml,*/*;q=0.8"})
check(r.status_code == 423 and "<html" in r.text and "read-only" in r.text, f"... sent by a browser: a page that says so ({r.status_code})")
check(not dbx("SELECT 1 FROM tasks WHERE list_id=? AND title IN ('During the move', 'API during', 'Eine Anfrage')", (L,)),
      "nothing of it arrived in the project")
# reading stays, other places go on
r = Bo.get(B + f"/api/tasks/{T}")
check(r.ok and r.json().get("title") == "Before the move", f"reading the organisation's task stays possible {r.status_code}")
P = Bo.post(B + "/api/lists", json={"name": "Bob privat", "org_id": None})
check(P.status_code in (200, 201) and Bo.post(B + "/api/tasks", json={"title": "Private", "list_id": P.json()["id"]}).status_code in (200, 201),
      "a member's private project and task: written as before")
LB = Ca.post(B + "/api/lists", json={"name": "Beta project", "org_id": ORG2})
check(LB.status_code in (200, 201), f"another organisation writes as before {LB.status_code}")
FL = Fr.post(B + "/api/lists", json={"name": "Frida", "org_id": None}).json()["id"]
check(Fr.post(B + "/api/tasks", json={"title": "Frida works", "list_id": FL}).status_code in (200, 201), "the freelancer works as before")

# 2.1413.0 (#6951): a reading request with a write of its own (the agreements' trash purge) leaves the moving organisation alone
r = A.get(B + OFF + "/agreements")
check(r.ok and dbx("SELECT 1 FROM office_agreements WHERE id=?", (AGR,)),
      f"#6951: opening the agreements while moving does not purge the organisation's trash {r.status_code} {r.text[:160]}")
# 2.1413.0 (#6951): a queue row runs as strict as the request that added it (a writing request: strict; reading / mv_allow: free)
out = in_ct("import app\nfrom kalmido.core.config import app as fl\nfrom kalmido.core.db import connect\n"
            "from kalmido.core.movelock import mv_allow, mv_strict_now\nfrom kalmido.accounts.bgjobs import bgj_add\nids = []\n"
            "for m, allow in (('DELETE', False), ('GET', False), ('POST', True)):\n"
            "    with fl.test_request_context('/x', method=m):\n"
            "        if allow:\n            mv_allow()\n"
            "        ids.append((mv_strict_now(), bgj_add('office:series_moved', 0, [], delay=3600)))\n"
            "from kalmido.core.pg import system_ctx\nc = connect()\nwith system_ctx(c):\n"
            "    rows = [bool(c.execute('SELECT strict FROM bg_jobs WHERE id=?', (i,)).fetchone()[0]) for _s, i in ids]\n"
            "    c.execute('DELETE FROM bg_jobs WHERE id IN (%s)' % ','.join(str(i) for _s, i in ids))\nc.commit()\n"
            "print('STRICT', [s_ for s_, _i in ids], rows)\n")
check("STRICT [True, False, False] [True, False, False]" in out,
      f"#6951: a writing request's queue row is strict (it runs inside the lock), a reading one's or one after mv_allow not {out[-300:]}")

# ================================================================== (3) the export runs, the series rests, the history
r = A.post(B + f"/api/orgs/{ORG}/export")
check(r.status_code == 202, f"the export of the organisation starts while it moves {r.status_code} {r.text[:160]}")
st = until(lambda: (lambda j: j if j.get("state") in ("done", "failed") else None)(A.get(B + f"/api/orgs/{ORG}/export").json()), 120)
check(st and st.get("state") == "done", f"... and finishes on the fixed state {st}")
tick()
check(made(SER) == [] and series(SER)[:2] == (True, TODAY), f"the watchdog leaves the series of the moving organisation alone {made(SER)} {series(SER)}")
log = A.get(B + f"/api/orgs/{ORG}/lists").json().get("log", [])
check(any(x["action"] == "move_on" and x["by"] == "Alice Admin" for x in log), f"the history names the start {[x['action'] for x in log]}")

# ================================================================== (4) ending it
check(Bo.delete(B + M).status_code == 403, "a member cannot end it")
r = A.delete(B + M)
check(r.ok and r.json().get("moving") is False and r.json().get("paused") == [SER], f"its admin ends it; the due series is paused {r.text[:200]}")
check("moving" not in {w["id"]: w for w in Bo.get(B + "/api/state").json()["me"]["workspaces"]}.get(ORG, {}), "the bar goes")
check(Bo.post(B + "/api/tasks", json={"title": "After the move", "list_id": L}).status_code in (200, 201)
      and requests.post(B + "/api/v1/tasks", headers=API, json={"title": "API after", "list_id": L}).status_code == 201
      and A.patch(B + f"/api/orgs/{ORG}", json={"color": "#2dd4bf"}).ok, "writing works again (member, token, the organisation's settings)")
check(series(SER)[0] is False and series(SER)[2] == "moving", f"the series is paused: 'moving' {series(SER)}")
tk = until(lambda: dbx("SELECT id FROM tasks WHERE assignee_id=? AND deleted_at IS NULL AND title LIKE ?", (ALICE, "%Monatlich%")), 60)
check(bool(tk), "its admin gets the task 'Invoice series ... paused'")
tick()
check(made(SER) == [], "the missed period is not made late")
log = A.get(B + f"/api/orgs/{ORG}/lists").json().get("log", [])
check(any(x["action"] == "move_off" for x in log), "the history names the end")
r = A.post(B + M, json={"confirm": "Alpha"})
check(r.ok and r.json().get("moving") is True and A.delete(B + M).ok, "it can be started and ended again")
check(not dbx("SELECT 1 FROM office_agreements WHERE id=?", (AGR,)) if A.get(B + OFF + "/agreements").ok else False,
      "#6951: after the move the agreements' trash is purged as before")

# ================================================================== (5) 2.1413.0 (#6951): the instance admin ends a move
M2 = f"/api/orgs/{ORG2}/moving"
r = Ca.post(B + M2, json={"confirm": "Beta"})
check(r.ok and r.json().get("moving") is True, f"Beta's admin starts its move {r.text[:160]}")
check(not dbx("SELECT 1 FROM org_members WHERE org_id=? AND user_id=?", (ORG2, ALICE)), "setup: the instance admin is no member of Beta")
check(Bo.delete(B + M2).status_code == 404, "#6951: somebody else (no member, no instance admin) still gets 404")
r = A.delete(B + M2)
check(r.ok and r.json().get("moving") is False, f"#6951: the instance admin ends the move of an organisation he is not in {r.status_code} {r.text[:200]}")
check(Ca.post(B + "/api/lists", json={"name": "Beta after", "org_id": ORG2}).status_code in (200, 201), "#6951: Beta writes again")
lg = dbx("SELECT detail FROM org_list_log WHERE org_id=? AND action='move_off' ORDER BY id DESC LIMIT 1", (ORG2,))
check(lg and "instance_admin" in str(lg[0][0]), f"#6951: the organisation's history notes that the instance admin ended it {lg}")
sys.exit(done("p6600_org_moving"))
