#!/usr/bin/env python3
# kalmido-suite: fresh
"""#7505 saving the positions of a quotation writes only what changed. Invented services, positions and amounts only;
an organisation admin plus a person without an organisation (freelancer-matrix: office).
 - the measure: database statements of ONE field change (the quantity of one position) at 50 and 200 positions, counted
   by the server itself (Server-Timing n=, core/reqtime.py) for PUT .../items, PUT .../parts/<pid>/items and
   PATCH .../parts/<pid> (a setting of the part), with the whole answer and with the short one ({lite: true}); printed as
   PERF lines, held under upper bounds, and the change from 50 to 200 positions held small (no statement per position)
 - the same result: after the saves GET of the document has the changed quantity, the same ids; the short answer carries
   the same version, totals, positions, parts' totals, missing / language gaps as GET and nothing else of the document;
   without lite the whole document as before; the catalogue still fills an empty title / rate of a new service position
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
            "discountable", "discount_pct", "opt", "in_handling", "in_markup", "ref_part_id")
    return [{k: it.get(k) for k in keys if k in it} for it in items]


def positions(sv, n):
    return [{"kind": "service", "service_id": sv[i % len(sv)], "title": f"Position {i}", "qty": 1 + i % 3, "unit": "day",
             "rate": 100 + i, "tax": "standard", "cost": 10 + i % 7} for i in range(n)]


def same_as_get(who, n, what, j, got, part=None):
    """The short answer carries the same values as GET of the saved document (version, totals, positions, parts' totals)."""
    check(j.get("lite") is True and j["updated_at"] == got["updated_at"] and j["totals"] == got["totals"], f"{who} {n} {what}: lite: version and totals as GET")
    check(j["items"] == got["items"], f"{who} {n} {what}: lite: the positions as GET")
    check(j.get("missing") == got.get("missing") and j.get("lang_gaps") == got.get("lang_gaps"), f"{who} {n} {what}: lite: missing and language gaps as GET")
    check([(x["id"], x["totals"]) for x in j["parts"]] == [(x["id"], x["totals"]) for x in got["parts"]],
          f"{who} {n} {what}: lite: the parts' totals as GET")
    check("client_contacts" not in j and "recipient" not in j, f"{who} {n} {what}: lite: nothing else of the document")
    if part is not None:
        gp = next(x for x in got["parts"] if x["id"] == part)
        check(j["part"]["items"] == gp["items"] and j["doc_totals"] == got["totals"], f"{who} {n} {what}: lite: the part's positions as GET")


def measure(s, who, sv, n):
    """-> (full, lite) statements of one field change: PUT items, PUT part items, PATCH part."""
    doc = s.post(B + D, json={"kind": "offer", "lang": "en", "project_title": f"Example {n}", "items": positions(sv, n)}).json()
    did = doc["id"]
    p = s.post(B + f"{D}/{did}/parts", json={"title": "Module"}).json()["part"]["id"]
    full = s.get(B + f"{D}/{did}").json()
    r = s.put(B + f"{D}/{did}/parts/{p}/items", json={"items": positions(sv, n), "expect_updated_at": full["updated_at"]})
    check(r.ok, f"{who} {n}: setup: the part's positions {r.status_code} {r.text[:200]}")
    full = s.get(B + f"{D}/{did}").json()
    items = body_of(full["items"])
    check(len(items) == n + 1, f"{who} {n}: the quotation has {n} positions and the part's line ({len(items)})")
    ids = [x["id"] for x in items]
    out, size = {}, {}
    for lite in (False, True):
        items[10]["qty"] = 7 if not lite else 8
        r = s.put(B + f"{D}/{did}/items", json={"items": items, "expect_updated_at": full["updated_at"], **({"lite": True} if lite else {})})
        check(r.ok, f"{who} {n}: PUT items {r.status_code} {r.text[:200]}")
        k_items = nstmt(r)
        size[lite] = len(r.content)
        got = s.get(B + f"{D}/{did}").json()
        check([x["id"] for x in got["items"]] == ids and float(got["items"][10]["qty"]) == items[10]["qty"], f"{who} {n}: the change is saved, the ids stay")
        if lite:
            same_as_get(who, n, "PUT items", r.json(), got)
        else:
            check(r.json()["totals"] == got["totals"] and r.json()["updated_at"] == got["updated_at"] and "client_contacts" in r.json(),
                  f"{who} {n}: without lite the whole document as before")
        pitems = body_of(next(x for x in got["parts"] if x["id"] == p)["items"])
        pitems[5]["qty"] = 9 if not lite else 4
        r = s.put(B + f"{D}/{did}/parts/{p}/items", json={"items": pitems, "expect_updated_at": got["updated_at"], **({"lite": True} if lite else {})})
        check(r.ok, f"{who} {n}: PUT part items {r.status_code} {r.text[:200]}")
        k_part = nstmt(r)
        got = s.get(B + f"{D}/{did}").json()
        gp = next(x for x in got["parts"] if x["id"] == p)
        check(float(gp["items"][5]["qty"]) == pitems[5]["qty"] and r.json()["doc_totals"] == got["totals"], f"{who} {n}: the part's change is saved, the totals match")
        if lite:
            same_as_get(who, n, "PUT part items", r.json(), got, p)
        r = s.patch(B + f"{D}/{did}/parts/{p}", json={"print": 0 if not lite else 1, "expect_updated_at": got["updated_at"], **({"lite": True} if lite else {})})
        check(r.ok, f"{who} {n}: PATCH part {r.status_code} {r.text[:200]}")
        k_patch = nstmt(r)
        got = s.get(B + f"{D}/{did}").json()
        check(r.json()["doc_totals"] == got["totals"] and r.json()["updated_at"] == got["updated_at"], f"{who} {n}: PATCH part answers the saved totals")
        if lite:
            same_as_get(who, n, "PATCH part", r.json(), got, p)
        out[lite] = (k_items, k_part, k_patch)
        full = got
    k_get = nstmt(s.get(B + f"{D}/{did}"))  # the whole document alone, for the report
    print(f"PERF #7505 {who} positions={n}: PUT items {out[False][0]} / lite {out[True][0]}, PUT part items {out[False][1]} / lite {out[True][1]}, "
          f"PATCH part {out[False][2]} / lite {out[True][2]}, (GET {k_get}) statements; PUT items answer {size[False]} / lite {size[True]} bytes", flush=True)
    return out[False], out[True]


for who, s in (("org", A), ("freelancer", Fr)):
    sv = services(oid_of(s))
    (f50, l50), (f200, l200) = measure(s, who, sv, 50), measure(s, who, sv, 200)
    check(min(f50 + l50 + f200 + l200) > 0, f"{who}: the server counted ({f50} {l50} {f200} {l200})")
    # 150 positions more cost (almost) nothing more: no statement per position any more (was one UPDATE + one catalogue read each:
    # PUT items 266 at 50, 566 at 200 positions before #7505)
    for i, what in enumerate(("PUT items", "PUT part items", "PATCH part")):
        check(f200[i] - f50[i] <= 6 and l200[i] - l50[i] <= 6, f"#7505 {who}: {what} at 200 positions costs at most 6 statements more than at 50 ({f50[i]} -> {f200[i]}, lite {l50[i]} -> {l200[i]})")
        check(l200[i] < f200[i], f"#7505 {who}: {what}: the short answer reads less than the whole document ({l200[i]} < {f200[i]})")
    check(max(f200) <= 185 and max(l200) <= 160, f"#7505 {who}: upper bounds at 200 positions: whole answer <= 185, short <= 160 ({f200} {l200})")

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
