#!/usr/bin/env python3
# kalmido-suite: fresh
"""#7505 saving the positions of a quotation writes only what changed. Invented services, positions and amounts only;
an organisation admin plus a person without an organisation (freelancer-matrix: office).
 - the measure: database statements of ONE field change (the quantity of one position) at 50 and 200 positions, counted
   by the server itself (Server-Timing n=, core/reqtime.py) for PUT .../items, PUT .../parts/<pid>/items and
   PATCH .../parts/<pid> (a setting of the part); printed as PERF lines, each held under an upper bound, and the change
   from 50 to 200 positions held small (no statement per position any more)
 - the same result: after the saves GET of the document has the changed quantity, the same totals as the answer, the same
   position ids; the catalogue still fills an empty title / rate of a new service position
usage: p7505_items_stmt_test.py <datadir>"""
import re
import sys

import kt
from kt import B, check, dbx
from freelancer_fixture import freelancer

kt.fresh(env={"KALMIDO_INSTANCE_MODE": "workspaces", "KALMIDO_TEST_TIMING_ALL": "1"}, prefix="P7505")
kt.docker_logs_on_first_fail(tail=120, chars=9000)
FEAT = "office,clients"
D = "/api/office/docs"
A = kt.setup()
A.patch(B + "/api/settings", json={"lang": "en", "features": FEAT, "tour": "done"})
ALICE = A.get(B + "/api/state").json()["me"]["id"]
ORG = A.post(B + "/api/admin/orgs", json={"name": "Alpha Example", "admin_id": ALICE}).json()["id"]
A.patch(B + "/api/settings", json={"workspace": f"org:{ORG}"})
FID, Fr = freelancer(B, A, features=FEAT)
TIMING = re.compile(r'db;dur=[\d.]+;desc="n=(\d+)"')
PERF = {}


def nstmt(r):
    m = TIMING.search(r.headers.get("Server-Timing", ""))
    return int(m.group(1)) if m else -1


def oid_of(s):
    """The office organisation id of the session's workspace (a service row of the catalogue needs it)."""
    did = s.post(B + D, json={"kind": "offer", "lang": "en", "project_title": "Probe"}).json()["id"]
    return dbx("SELECT org_id FROM office_docs WHERE id=?", (did,))[0][0]


def services(oid, n=20):
    for i in range(n):
        dbx("INSERT INTO office_services(org_id, name_de, daily_rate, unit, created_at, updated_at) VALUES(?,?,?,?,now(),now())",
            (oid, f"Example Service {i}", 500 + i, "day"))
    return [x[0] for x in dbx("SELECT id FROM office_services WHERE org_id=? ORDER BY id", (oid,))][-n:]


def body_of(items):
    """What the editor sends back of the positions it holds (office_docs.js ofdItemsBody)."""
    keys = ("id", "kind", "service_id", "title", "detail", "qty", "unit", "rate", "tax", "raw_fee", "producing", "intext", "cost",
            "discountable", "discount_pct", "opt", "in_handling", "in_markup")
    return [{k: it.get(k) for k in keys if k in it} for it in items]


def positions(sv, n):
    return [{"kind": "service", "service_id": sv[i % len(sv)], "title": f"Position {i}", "qty": 1 + i % 3, "unit": "day",
             "rate": 100 + i, "tax": "standard", "cost": 10 + i % 7} for i in range(n)]


def measure(s, who, sv, n):
    doc = s.post(B + D, json={"kind": "offer", "lang": "en", "project_title": f"Example {n}", "items": positions(sv, n)}).json()
    did = doc["id"]
    full = s.get(B + f"{D}/{did}").json()
    items = body_of(full["items"])
    check(len(items) == n, f"{who} {n}: the quotation has {n} positions ({len(items)})")
    ids = [x["id"] for x in items]
    items[10]["qty"] = 7
    r = s.put(B + f"{D}/{did}/items", json={"items": items, "expect_updated_at": full["updated_at"]})
    check(r.ok, f"{who} {n}: PUT items {r.status_code} {r.text[:200]}")
    k_items = nstmt(r)
    got = s.get(B + f"{D}/{did}").json()
    check([x["id"] for x in got["items"]] == ids and got["items"][10]["qty"] == 7, f"{who} {n}: the change is saved, the ids stay")
    check(r.json()["totals"] == got["totals"] and r.json()["updated_at"] == got["updated_at"],
          f"{who} {n}: the answer carries the totals and the version of the saved document")
    # a part with n positions
    p = s.post(B + f"{D}/{did}/parts", json={"title": "Module"}).json()["part"]["id"]
    ver = s.get(B + f"{D}/{did}").json()["updated_at"]
    r = s.put(B + f"{D}/{did}/parts/{p}/items", json={"items": positions(sv, n), "expect_updated_at": ver})
    check(r.ok, f"{who} {n}: PUT part items {r.status_code} {r.text[:200]}")
    pitems = body_of(r.json()["part"]["items"]) if r.json().get("part", {}).get("items") else body_of(s.get(B + f"{D}/{did}").json()["parts"][0]["items"])
    pitems[5]["qty"] = 9
    r = s.put(B + f"{D}/{did}/parts/{p}/items", json={"items": pitems, "expect_updated_at": r.json()["updated_at"]})
    check(r.ok, f"{who} {n}: PUT part items again {r.status_code} {r.text[:200]}")
    k_part = nstmt(r)
    got = s.get(B + f"{D}/{did}").json()
    gp = next(x for x in got["parts"] if x["id"] == p)
    check(gp["items"][5]["qty"] == 9 and r.json()["doc_totals"] == got["totals"], f"{who} {n}: the part's change is saved, the totals match")
    r = s.patch(B + f"{D}/{did}/parts/{p}", json={"print": 0, "expect_updated_at": r.json()["updated_at"]})
    check(r.ok, f"{who} {n}: PATCH part {r.status_code} {r.text[:200]}")
    k_patch = nstmt(r)
    got = s.get(B + f"{D}/{did}").json()
    check(r.json()["doc_totals"] == got["totals"] and r.json()["updated_at"] == got["updated_at"], f"{who} {n}: PATCH part answers the saved totals")
    PERF[(who, n)] = (k_items, k_part, k_patch)
    print(f"PERF #7505 {who} positions={n}: PUT items {k_items}, PUT part items {k_part}, PATCH part {k_patch} statements", flush=True)
    return k_items, k_part, k_patch


for who, s in (("org", A), ("freelancer", Fr)):
    sv = services(oid_of(s))
    m50, m200 = measure(s, who, sv, 50), measure(s, who, sv, 200)
    check(min(m50 + m200) > 0, f"{who}: the server counted ({m50} {m200})")
    # 150 positions more cost (almost) nothing more: no statement per position (was one UPDATE + one catalogue read each)
    for i, what in enumerate(("PUT items", "PUT part items", "PATCH part")):
        check(m200[i] - m50[i] <= 6, f"#7505 {who}: {what} at 200 positions costs at most 6 statements more than at 50 ({m50[i]} -> {m200[i]})")
    check(max(m200) <= 120, f"#7505 {who}: at most 120 statements for one field change at 200 positions ({m200})")

# a new service position without title / rate still takes them from the catalogue (one read for all positions)
sv = services(oid_of(A), 3)
r = A.post(B + D, json={"kind": "offer", "lang": "en", "project_title": "Catalogue"})
did = r.json()["id"]
r = A.put(B + f"{D}/{did}/items", json={"items": [{"kind": "service", "service_id": sv[0]}, {"kind": "service", "service_id": sv[2], "qty": 2}]})
got = A.get(B + f"{D}/{did}").json()["items"]
check([x["title"] for x in got] == ["Example Service 0", "Example Service 2"] and [float(x["rate"]) for x in got] == [500.0, 502.0],
      f"#7505: the catalogue fills title and rate ({[(x['title'], x['rate']) for x in got]})")
check(A.put(B + f"{D}/{did}/items", json={"items": [{"kind": "service", "service_id": 99999999}]}).status_code == 404,
      "#7505: an unknown service is still 404")
sys.exit(kt.done("p7505_items_stmt"))
