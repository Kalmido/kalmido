#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1373.0 (#6402) the office reads less: the client list works out the hours of all clients from one time report, the
quotations / invoices area asks only the names, the tile Figures hits its cache. Invented clients, people and figures only;
as a person without an organisation (freelancer-matrix: office) plus an organisation admin.
tenant-matrix: office  freelancer-matrix: office
 - the same answer: every client of GET /api/clients (also ?month= of last month, archived ones) = GET /api/clients/<id>
   (the client alone) without its card-only parts; per_list of the card = client_stats of each list alone; the data reach
   every path (a list rate, the client's rate, an entry just after midnight of the 1st in the person's time zone, an entry
   without a list, a list of no client, estimates open / done, a client without lists, contact persons, an organisation)
 - ratchet: the statements of GET /api/clients stay the same (at most +2) for 20 more clients with lists, time and
   contacts; the card GET /api/clients/<id> the same for 3 more lists (was a report + a query per client / per list)
 - ?brief=1: the names only (no stats, no contacts, no billing), the same clients; the person without an organisation too
 - the time report: lists=<id> brings only that list's entries, lists=0,<id> also the entries without a list (the SQL filter
   keeps the Python rule)
 - the tile: KPI_TTL longer than the tile's minute; two calls 2 minutes apart = one build; a document changed past the app
   (status, date, trash and back, finalised) and a payment changed / deleted / added = built again
usage: p21373_c_office_perf_test.py <datadir>"""
import json
import re
import subprocess
import sys

import kt
from kt import B, CT, check, dbx
from freelancer_fixture import freelancer

kt.fresh(env={"KALMIDO_INSTANCE_MODE": "workspaces", "KALMIDO_TEST_TIMING_ALL": "1"}, prefix="P21373C")
kt.docker_logs_on_first_fail(tail=120, chars=9000)
FEAT = "office,clients,time"
A = kt.setup()
A.patch(B + "/api/settings", json={"lang": "en", "features": FEAT, "tour": "done"})
ALICE = A.get(B + "/api/state").json()["me"]["id"]
ORG = A.post(B + "/api/admin/orgs", json={"name": "Alpha Example", "admin_id": ALICE}).json()["id"]
A.patch(B + "/api/settings", json={"workspace": f"org:{ORG}"})
FID, Fr = freelancer(B, A, features=FEAT)
TIMING = re.compile(r'db;dur=[\d.]+;desc="n=(\d+)"')
CARD_ONLY = ("per_list", "blocks_off", "tickets", "merges")


def nstmt(r):
    m = TIMING.search(r.headers.get("Server-Timing", ""))
    return int(m.group(1)) if m else -1


def in_app(code):
    r = subprocess.run(["docker", "exec", "-w", "/app", "-e", "TASKS_WATCHDOG=0", CT, "python", "-c", "import app, json\n" + code],
                       capture_output=True, text=True)
    out = r.stdout.strip().splitlines()
    return out[-1] if out else "ERR " + r.stderr[-1500:].replace("\n", " | ")


check(Fr.patch(B + "/api/settings", json={"tz": "Europe/Berlin"}).ok, "setup: frida's time zone")
TODAY = in_app("from kalmido.core.db import local_now\nprint(local_now().date().isoformat())")
check(re.fullmatch(r"\d{4}-\d\d-\d\d", TODAY), "the app's today " + TODAY)
MON = TODAY[:7]
FIRST = f"{MON}-01"
PREV_LAST = in_app(f"from datetime import date, timedelta\nprint((date.fromisoformat('{FIRST}') - timedelta(days=1)).isoformat())")
PREV = PREV_LAST[:7]
SEQ = [0]


def entry(uid, lid, start, sec):
    from datetime import datetime, timedelta
    end = (datetime.fromisoformat(start) + timedelta(seconds=sec)).isoformat()
    dbx("INSERT INTO time_entries(user_id, list_id, task_title, start, \"end\", seconds, note, source, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (uid, lid, "Edit", start, end, sec, "", "manual", end, end))


def client(s, i, rate=None, lists=1, org=None, uid=None):
    """A client with `lists` lists (the first with a rate of its own when rate is None), time last month, this month and
    just after midnight of the 1st in Berlin (the day before in UTC), a contact person, two estimated tasks."""
    SEQ[0] += 1
    n = SEQ[0]
    body = {"name": f"Example Client {n:02d}", "contacts": [{"name": f"Contact {n}", "email": f"c{n}@example.com"}]}
    if rate:
        body["rate"] = rate
    if org:
        body["org_id"] = org
    r = s.post(B + "/api/clients", json=body)
    assert r.ok, r.text
    cid = r.json()["id"]
    uid = uid or FID
    lids = []
    for k in range(lists):
        lid = s.post(B + "/api/lists", json={"name": f"Example project {n}.{k}"}).json()["id"]
        patch = {"client_id": cid} if rate or k else {"client_id": cid, "rate": 70 + i}
        assert s.patch(B + f"/api/lists/{lid}", json=patch).ok
        for start, sec in ((f"{PREV_LAST}T08:00:00+00:00", 7200 + 61 * i), (f"{PREV_LAST}T23:30:00+00:00", 1740 + k),
                           (f"{FIRST}T09:00:00+00:00", 5400 + 7 * i)):
            entry(uid, lid, start, sec)
        for t, st in (("Plan", 0), ("Build", 1)):
            r = s.post(B + "/api/tasks", json={"title": f"{t} {n}", "list_id": lid, "duration": 30 + 15 * k})
            assert r.ok, r.text
            if st:
                assert s.post(B + f"/api/tasks/{r.json()['id']}/complete", json={}).ok
        lids.append(lid)
    return cid, lids


# frida (no organisation): 5 clients - list rate, client rate, two lists, no list; a list of no client, an entry without a list
FC = [client(Fr, 0), client(Fr, 1, rate=95), client(Fr, 2, lists=2), client(Fr, 3, rate=55, lists=0), client(Fr, 4)]
LONE = Fr.post(B + "/api/lists", json={"name": "Example side project"}).json()["id"]
entry(FID, LONE, f"{FIRST}T11:00:00+00:00", 3600)
entry(FID, None, f"{FIRST}T12:00:00+00:00", 1800)
check(Fr.patch(B + f"/api/clients/{FC[4][0]}", json={"archived": True}).ok, "setup: one client archived")
# alice: two clients of her organisation
AC = [client(A, 5, org=ORG, uid=ALICE), client(A, 6, rate=120, org=ORG, uid=ALICE)]


def same_as_alone(s, who, q=""):
    """Every client of the list = the client alone (its card without the card-only parts)."""
    r = s.get(B + "/api/clients" + q)
    check(r.ok, f"{who}: the list {q} " + r.text[:200])
    cl = r.json().get("clients", [])
    bad = []
    for x in cl:
        one = s.get(B + f"/api/clients/{x['id']}" + ("?month=" + q.split("month=")[1].split("&")[0] if "month=" in q else "")).json()
        for k in CARD_ONLY:
            one.pop(k, None)
        if one != x:
            bad.append((x["id"], {k: (x.get(k), one.get(k)) for k in set(x) | set(one) if x.get(k) != one.get(k)}))
    check(cl and not bad, f"#6402 {who}: every client of the list {q} = the client alone ({len(cl)} clients) {bad[:2]}")
    return cl


cl = same_as_alone(Fr, "frida")
same_as_alone(Fr, "frida", f"?month={PREV}&archived=1")
same_as_alone(A, "alice")
# the data reach every path (else the same answer proves little)
by = {x["id"]: x for x in same_as_alone(Fr, "frida", "?archived=1")}
st = [by[c]["stats"] for c, _ in FC]
check(all(x["seconds"] > 0 and x["month_seconds"] > 0 and x["amount"] > 0 for i, x in enumerate(st) if i != 3),
      f"#6402 hours, the month and amounts of every client with lists {[(x['seconds'], x['month_seconds'], x['amount']) for x in st]}")
check(st[3]["seconds"] == 0 and st[3]["estimated"] == 0 and by[FC[3][0]]["lists"] == [], f"the client without lists: zero {st[3]}")
check(st[2]["estimated"] == 4 and st[2]["open"] == 2 and st[2]["done"] == 2 and st[2]["estimate_min"] == 30 * 2 + 45 * 2,
      f"#6402 the estimates of the client with two lists add up {st[2]}")
check(by[FC[1][0]]["stats"]["amount"] > 0 and by[FC[0][0]]["contacts"][0]["name"].startswith("Contact"), "the client's rate and the contacts reach the list")
ala = A.get(B + "/api/clients").json()["clients"]
check(len(ala) == 2 and all(x["org_name"] == "Alpha Example" for x in ala) and not {x["id"] for x in ala} & set(by),
      f"alice sees her organisation's clients with its name, never frida's {[(x['name'], x['org_name']) for x in ala]}")
# per_list of the card = client_stats of each list alone (the function the card used per list)
CID2, LIDS2 = FC[2]
OLD = f'''
from flask import g
from kalmido.core.config import app as fa
from kalmido.core.db import db
from kalmido.team import clients as cl
with fa.test_request_context('/'):
    c = db()
    g.user = c.execute("SELECT * FROM users WHERE id=?", ({FID},)).fetchone()
    out = {{}}
    for m in ({MON!r}, {PREV!r}):
        out[m] = [cl.client_stats(c, {FID}, {CID2}, [l], m) for l in {LIDS2!r}]
    print(json.dumps(out))
'''
out = in_app(OLD)
try:
    old = json.loads(out)
except ValueError:
    old = {}
check(old, "the per-list comparison ran in the app: " + out[-800:])
for m in (MON, PREV):
    card = Fr.get(B + f"/api/clients/{CID2}?month={m}").json()
    new = [{k: x[k] for k in old.get(m, [{}])[0]} for x in card.get("per_list", [])]
    check(old and new == old[m], f"#6402 the card's per_list ({m}) = client_stats of each list alone {new} / {old.get(m)}")

# ---------------------------------------------------------------- the ratchet: 5 -> 25 clients, 1 -> 4 lists on a card
r5 = Fr.get(B + "/api/clients")
n5 = nstmt(r5)
for i in range(20):
    client(Fr, 10 + i, rate=60 if i % 2 else None)
r25 = Fr.get(B + "/api/clients")
n25 = nstmt(r25)
check(r25.ok and len(r25.json()["clients"]) == len(r5.json()["clients"]) + 20, "the 20 new clients are in the list")
check(0 < n5 and n25 <= n5 + 2, f"#6402 ratchet: GET /api/clients {n5} statements with 5 clients, {n25} with 25 (at most +2)")
print(f"PERF /api/clients statements 5 clients {n5}, 25 clients {n25}")
CID0, LIDS0 = FC[0]
c1 = nstmt(Fr.get(B + f"/api/clients/{CID0}"))
for k in range(3):
    lid = Fr.post(B + "/api/lists", json={"name": f"Example extra {k}"}).json()["id"]
    Fr.patch(B + f"/api/lists/{lid}", json={"client_id": CID0})
    entry(FID, lid, f"{FIRST}T13:00:00+00:00", 900)
r = Fr.get(B + f"/api/clients/{CID0}")
check(r.ok and len(r.json()["per_list"]) == 4 and nstmt(r) <= c1 + 2, f"#6402 ratchet: the card {c1} statements with 1 list, {nstmt(r)} with 4")
same_as_alone(Fr, "frida (25 clients)")

# ---------------------------------------------------------------- ?brief=1: names only
full = Fr.get(B + "/api/clients").json()["clients"]
r = Fr.get(B + "/api/clients?brief=1")
br = r.json().get("clients", []) if r.ok else []
check(r.ok and [x["id"] for x in br] == [x["id"] for x in full] and all(x["name"] == y["name"] for x, y in zip(br, full)),
      "#6402 brief: the same clients with their names (person without an organisation) " + r.text[:200])
check(br and not any(k in x for x in br for k in ("stats", "contacts", "billing", "budget", "email")),
      f"#6402 brief: no statistics, contacts or billing {sorted(br[0]) if br else None}")
check(nstmt(r) < nstmt(r25), f"#6402 brief reads less than the full list ({nstmt(r)} / {nstmt(r25)})")
ba = A.get(B + "/api/clients?brief=1&archived=1").json()["clients"]
check({x["id"] for x in ba} == {x["id"] for x in ala} and all(x["org_id"] == ORG for x in ba), "brief: alice's organisation clients with org_id")
check({x["id"] for x in Fr.get(B + "/api/clients?brief=1&archived=1").json()["clients"]} >= {FC[4][0]}, "brief with the archived ones")

# ---------------------------------------------------------------- the time report: the list filter in SQL keeps its rule
L0 = FC[0][1][0]
rep = Fr.get(B + f"/api/time/report?scope=all&lists={L0}").json()
check([x["id"] for x in rep["lists"]] == [L0] and rep["total"]["count"] == 3, f"#6402 lists=<id>: only that list {[(x['id'], x['seconds']) for x in rep['lists']]}")
rep = Fr.get(B + f"/api/time/report?scope=all&lists=0,{L0}").json()
check(sorted(x["id"] for x in rep["lists"]) == [0, L0] and rep["total"]["count"] == 4, f"#6402 lists=0,<id>: the entry without a list too {[x['id'] for x in rep['lists']]}")
ents = Fr.get(B + f"/api/time/entries?lists={LONE}").json()["entries"]
check(len(ents) == 1 and ents[0]["list_id"] == LONE, f"the entry list with lists=<id> {[(e['list_id'], e['seconds']) for e in ents]}")

# ---------------------------------------------------------------- the tile: one build in 2 minutes, a change past the app shows
r = Fr.get(B + "/api/office/docs?kind=invoice")
OID = r.json()["org_id"]
TS = "2020-01-01T00:00:00+00:00"
DOC = dbx("INSERT INTO office_docs(org_id, kind, number, status, lang, currency, client_id, recipient, date, due_date, rights, fields, totals, "
          "created_by, created_at, updated_at, locked_at, trial) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) RETURNING id",
          (OID, "invoice", "RE-1", "issued", "en", "EUR", FC[0][0], json.dumps({"name": "Example Client"}), TODAY, TODAY, "{}", "[]",
           json.dumps({"net": "100", "gross": "119"}), FID, TS, TS, None, 0))[0][0]  # a draft (a finalised one keeps its date, #4598)
PAY = dbx("INSERT INTO office_payments(org_id, doc_id, date, amount, method, note, created_at) VALUES(?,?,?,?,?,?,?) RETURNING id",
          (OID, DOC, TODAY, "19.00", "transfer", "", TS))[0][0]
TILE = f'''
from flask import g
from kalmido.core.config import app as fa
from kalmido.core.db import db, connect
from kalmido.core.pg import system_ctx
from kalmido.office import kpi
w = connect()
builds = []
orig = kpi.kpi_build
kpi.kpi_build = lambda *a, **k: builds.append(1) or orig(*a, **k)
steps = %s
res = []
with fa.test_request_context('/'):
    c = db()
    g.user = c.execute("SELECT * FROM users WHERE id=?", ({FID},)).fetchone()
    t = 1000.0
    kpi.kpi_cached(c, {FID}, {OID}, now=t)
    for sql, dt in steps:
        if sql:  # past the app: another connection, no data version moved
            with system_ctx(w):
                for x in sql.split(";"):
                    w.execute(x)
            w.commit()
        t += dt
        n = len(builds)
        kpi.kpi_cached(c, {FID}, {OID}, now=t)
        res.append(len(builds) - n)
print(json.dumps({{"ttl": kpi.KPI_TTL, "res": res}}))
'''
STEPS = [("", 60), ("", 60),
         (f"UPDATE office_docs SET status='paid' WHERE id={DOC}", 1),
         (f"UPDATE office_docs SET date='{PREV_LAST}' WHERE id={DOC}", 1),
         # a booked payment changes only on a repair (the switch of #6467); a new one through a plain INSERT
         (f"SELECT set_config('kalmido.locked_ok', 'on', true);UPDATE office_payments SET amount=20 WHERE id={PAY}", 1),
         (f"SELECT set_config('kalmido.locked_ok', 'on', true);DELETE FROM office_payments WHERE id={PAY}", 1),
         (f"INSERT INTO office_payments(org_id, doc_id, date, amount, method, note, created_at) VALUES({OID}, {DOC}, '{TODAY}', 5, 'transfer', '', '{TS}')", 1),
         (f"UPDATE office_docs SET deleted_at='{TS}' WHERE id={DOC}", 1),
         (f"UPDATE office_docs SET deleted_at=NULL WHERE id={DOC}", 1),
         (f"UPDATE office_docs SET locked_at='{TS}' WHERE id={DOC}", 1),
         ("", 1)]
out = in_app(TILE % repr(STEPS))
try:
    tile = json.loads(out)
except ValueError:
    tile = {}
check(tile, "the tile ran in the app: " + out[-1500:])
if tile:
    check(tile["ttl"] > 60, f"#6402 KPI_TTL {tile['ttl']} s is longer than the tile's minute (office_kpi.js)")
    res = tile["res"]
    check(res[:2] == [0, 0], f"#6402 the tile twice a minute apart (2 minutes) = one build {res[:2]}")
    names = ["status", "date", "payment changed", "payment deleted", "payment added", "into the trash", "out of the trash", "finalised"]
    check(res[2:10] == [1] * 8, f"#6402 a change past the app is built again: {dict(zip(names, res[2:10]))}")
    check(res[10] == 0, f"nothing changed: from the cache again {res[10]}")

sys.exit(kt.done("p21373_c_office_perf"))
