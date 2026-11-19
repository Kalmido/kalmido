#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1445 API tests (#6430, audit #4780): a sort value is a finite number within fixed bounds (core/errors.sort_value) at
every input, and a JSON answer never carries a bare NaN / Infinity (core/config.FiniteJSONProvider writes null). Before,
float() took "nan" / NaN / Infinity / 1e400, the DOUBLE PRECISION column kept it, /api/state wrote a bare NaN and JSON.parse
in the browser refused it -- the app stopped loading for everyone who saw the project. Invented names only.
 - each input refuses NaN, "nan", Infinity, -Infinity, "inf", 1e400 with a 400 and keeps the old value: a project's field, a
   field of the organisation, the place of a task in a further project (link and its change), a saved filter, a section,
   a project, a task, an appointment type, a deal of the pipeline; a plain number still goes through
 - the net: a NaN written straight into the database (a field, a filter) -> /api/state stays valid JSON (strict parse),
   the value comes as null
 - freelancer-matrix: lists. A person without an organisation: her own field and filter refuse NaN, her state stays valid
usage: p21445_a_sortnan_test.py <datadir>"""
import json
import os
import sys

import dbx as dbxm
import kt
from kt import B, check, done, sess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from freelancer_fixture import FEATURES, freelancer  # noqa: E402

kt.fresh()
assert kt.sess(None).post(B + "/api/auth/setup", json={"username": "alice", "display_name": "Alice", "password": kt.PASSWORD}).ok
A = sess("alice")
A.post(B + "/api/admin/setup", json={"org_name": "Alpha", "lang": "en", "collab_all": True, "modules": ["cal", "comments", "collab"]})
A = sess("alice")
ORG = A.get(B + "/api/state").json()["me"]["workspaces"][0]["id"]
assert A.patch(B + "/api/settings", json={"lang": "en", "tour": "done", "features": FEATURES, "workspace": f"org:{ORG}"}).ok
FU, F = freelancer(B, A, "frida")
F.patch(B + "/api/settings", json={"lang": "en", "tour": "done", "features": FEATURES})

# raw JSON tokens: requests' json= would write NaN / Infinity too, but not 1e400 (a float overflows to inf first)
BAD = ("NaN", '"nan"', "Infinity", "-Infinity", '"inf"', "1e400", '"-1e400"', "1e308", "1e16")


def raw(s, method, path, extra, tok):
    body = json.dumps(extra)[:-1] + (", " if extra else "") + f'"sort": {tok}}}'
    return s.request(method, B + path, data=body, headers={"Content-Type": "application/json"})


def strict(text):
    """json.loads as JSON.parse: NaN / Infinity are no JSON."""
    def no(x):
        raise ValueError(f"not JSON: {x}")
    return json.loads(text, parse_constant=no)


def refuses(s, method, path, what, extra=None, read=None):
    """Every bad token -> 400 and (read given) the stored value unchanged."""
    before = read() if read else None
    bad = []
    for tok in BAD:
        r = raw(s, method, path, extra or {}, tok)
        if r.status_code != 400:
            bad.append((tok, r.status_code, r.text[:120]))
    check(not bad, f"{what}: NaN / inf / out of bounds refused with 400 {bad}")
    if read:
        check(read() == before, f"{what}: the stored value unchanged {read()} {before}")


def state_ok(s, what):
    r = s.get(B + "/api/state")
    try:
        st = strict(r.text)
    except ValueError as e:
        check(False, f"{what}: /api/state is valid JSON ({e})")
        return {}
    check(r.ok, f"{what}: /api/state is valid JSON {r.status_code}")
    return st


def one(sql, args=()):
    rows = kt.dbx(sql, args)
    return rows[0][0] if rows else None


def dbw(sql, args=()):
    c = dbxm.connect(os.path.join(kt.DATA, "tasks.db"), timeout=10)
    c.execute(sql, args)
    c.commit()
    c.close()


def mklist(s, name, org=None):
    r = s.post(B + "/api/lists", json={"name": name, "kind": "project", "org_id": org})
    assert r.ok, r.text
    return r.json()["id"]


# ---- a project's field (lists/fields.py)
L1, L2 = mklist(A, "Erstes Projekt", ORG), mklist(A, "Zweites Projekt", ORG)
r = A.post(B + f"/api/lists/{L1}/fields", json={"name": "Budget", "type": "number"})
check(r.ok, f"setup: a field {r.status_code} {r.text[:160]}")
FID = r.json()["id"]
refuses(A, "PATCH", f"/api/fields/{FID}", "field", read=lambda: one("SELECT sort FROM list_fields WHERE id=?", (FID,)))
r = A.patch(B + f"/api/fields/{FID}", json={"sort": 2.5})
check(r.ok and one("SELECT sort FROM list_fields WHERE id=?", (FID,)) == 2.5, f"field: a plain number goes through {r.text[:160]}")
r = A.patch(B + f"/api/fields/{FID}", json={"sort": "3"})
check(r.ok and one("SELECT sort FROM list_fields WHERE id=?", (FID,)) == 3.0, f"field: a number as text goes through as before {r.text[:160]}")

# ---- a field of the organisation (lists/orgfields.py)
r = A.post(B + "/api/org-fields", json={"space": f"org:{ORG}", "name": "Kunde", "type": "text"})
check(r.ok, f"setup: a field of the organisation {r.status_code} {r.text[:160]}")
OF = r.json()["id"]
refuses(A, "PATCH", f"/api/org-fields/{OF}", "org field", read=lambda: one("SELECT sort FROM org_fields WHERE id=?", (OF,)))

# ---- a task's place in a further project (tasks/multilist.py)
r = A.post(B + "/api/tasks", json={"title": "Verknüpft", "list_id": L1})
assert r.ok, r.text
TID = r.json()["id"]
refuses(A, "POST", f"/api/tasks/{TID}/links", "link", extra={"list_id": L2})
check(one("SELECT COUNT(*) FROM task_links WHERE task_id=?", (TID,)) == 0, "link: no link stored by a refused request")
r = A.post(B + f"/api/tasks/{TID}/links", json={"list_id": L2, "sort": 4})
check(r.ok and one("SELECT sort FROM task_links WHERE task_id=? AND list_id=?", (TID, L2)) == 4.0, f"link: a plain number goes through {r.text[:160]}")
refuses(A, "PATCH", f"/api/tasks/{TID}/links/{L2}", "link place",
        read=lambda: one("SELECT sort FROM task_links WHERE task_id=? AND list_id=?", (TID, L2)))

# ---- a task's own place (tasks/validation.py: finite before, now bounded too)
refuses(A, "PATCH", f"/api/tasks/{TID}", "task", read=lambda: one("SELECT sort FROM tasks WHERE id=?", (TID,)))
r = A.patch(B + f"/api/tasks/{TID}", json={"sort": 12})
check(r.ok and one("SELECT sort FROM tasks WHERE id=?", (TID,)) == 12, f"task: a plain number goes through {r.text[:160]}")

# ---- a saved filter (lists/sections.py filter_update; the API's PATCH /v1/filters goes the same way)
r = A.post(B + "/api/filters", json={"name": "Meins", "rules": {}})
check(r.ok, f"setup: a filter {r.status_code} {r.text[:160]}")
FLT = r.json()["id"]
refuses(A, "PATCH", f"/api/filters/{FLT}", "filter", read=lambda: one("SELECT sort FROM filters WHERE id=?", (FLT,)))

# ---- a section and a project (they checked finiteness before; now bounded, too)
r = A.post(B + "/api/sections", json={"list_id": L1, "name": "Spalte"})
check(r.ok, f"setup: a section {r.status_code} {r.text[:160]}")
SID = r.json()["id"]
refuses(A, "PATCH", f"/api/sections/{SID}", "section", read=lambda: one("SELECT sort FROM sections WHERE id=?", (SID,)))
refuses(A, "PATCH", f"/api/lists/{L1}", "project", read=lambda: one("SELECT sort FROM lists WHERE id=?", (L1,)))

# ---- an appointment type (calendars/apptbook.py)
r = A.post(B + "/api/appt/types", json={"name": "Gespräch"})
check(r.status_code in (200, 201), f"setup: an appointment type {r.status_code} {r.text[:160]}")
AT = r.json()["id"]
refuses(A, "PATCH", f"/api/appt/types/{AT}", "appointment type", read=lambda: one("SELECT sort FROM appt_types WHERE id=?", (AT,)))

# ---- a deal of the pipeline (office/pipeline.py: abs(NaN) > 1e12 was false, NaN went through)
r = A.post(B + "/api/office/deals", json={"title": "Beispiel-Deal"})
check(r.status_code == 201, f"setup: a deal {r.status_code} {r.text[:160]}")
DEAL = r.json()["id"]
refuses(A, "PATCH", f"/api/office/deals/{DEAL}", "deal", read=lambda: one("SELECT sort FROM office_deals WHERE id=?", (DEAL,)))

# ---- the net: a NaN straight in the database -> /api/state stays valid JSON, the value comes as null
dbw("UPDATE list_fields SET sort='NaN'::float8 WHERE id=?", (FID,))
dbw("UPDATE filters SET sort='Infinity'::float8 WHERE id=?", (FLT,))
st = state_ok(A, "net")
f = next((x for x in st.get("fields") or [] if x["id"] == FID), {})
flt = next((x for x in st.get("filters") or [] if x["id"] == FLT), {})
check(f.get("sort", "missing") is None and flt.get("sort", "missing") is None, f"net: NaN / Infinity come as null {f.get('sort')} {flt.get('sort')}")
dbw("UPDATE list_fields SET sort=1 WHERE id=?", (FID,))
dbw("UPDATE filters SET sort=1 WHERE id=?", (FLT,))

# ---- a person without an organisation (freelancer-matrix: lists)
PL = mklist(F, "Fridas Projekt")
r = F.post(B + f"/api/lists/{PL}/fields", json={"name": "Stunden", "type": "number"})
check(r.ok, f"freelancer: her field {r.status_code} {r.text[:160]}")
PF = r.json()["id"]
refuses(F, "PATCH", f"/api/fields/{PF}", "freelancer field", read=lambda: one("SELECT sort FROM list_fields WHERE id=?", (PF,)))
r = F.post(B + "/api/filters", json={"name": "Fridas Filter", "rules": {}})
check(r.ok, f"freelancer: her filter {r.status_code} {r.text[:160]}")
PFL = r.json()["id"]
refuses(F, "PATCH", f"/api/filters/{PFL}", "freelancer filter", read=lambda: one("SELECT sort FROM filters WHERE id=?", (PFL,)))
r = F.patch(B + f"/api/filters/{PFL}", json={"sort": 7})
check(r.ok and one("SELECT sort FROM filters WHERE id=?", (PFL,)) == 7.0, f"freelancer: a plain number goes through {r.text[:160]}")
dbw("UPDATE list_fields SET sort='NaN'::float8 WHERE id=?", (PF,))
st = state_ok(F, "freelancer net")
check(next((x for x in st.get("fields") or [] if x["id"] == PF), {}).get("sort", "missing") is None, "freelancer net: her NaN comes as null")

sys.exit(done("p21445_a_sortnan"))
