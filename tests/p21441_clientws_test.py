#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1441.0 API tests (#7298); (#7309): the shared place (accounts/wsplace.py wsp_new) - a named workspace only where Clients is
on; nothing named: the workspace on top, the ONE workspace, the transition (the only organisation, Clients on), else 400 space_needed: a new client without org_id never lands silently in a workspace where Clients is off for the
person (team/clients.py cl_ws_default, accounts/modcards.py mod_ws_on = the server twin of areas.js mod_spaces), so the list
under "All workspaces" (clientpage.js ms_inWs) never hides the client just added. freelancer-matrix: clients
Invented names only.
 - several organisations, the office (area) off in Private, workspace "All" (the reported case): no silent Private; with two
   workspaces on a 400 code ws_choose naming both; Clients off in the second one -> the client lands in the only one left
 - one organisation where Clients is off for the person, Private on (the mirror case): the client lands in Private, not in
   the organisation (before: ws_chosen_org took the only organisation)
 - an organisation's admin switched the office area off for its members (orgs.areas_off) -> not there either
 - Clients off everywhere -> 400 ws_choose with no workspace, nothing created
 - an explicit org_id stays as sent (the office's quick dialog names its area)
 - a person without an organisation: unchanged (her client is private, 201)
usage: p21441_clientws_test.py <datadir>      (KMT_NOSTART=1 / P21441_NOSTART=1: a running server)"""
import json
import sys

from freelancer_fixture import FEATURES, freelancer, login
from kt import B, check, dbx, done, fresh, setup

fresh(prefix="P21441")
A = setup()
A.patch(B + "/api/settings", json={"lang": "en", "tour": "done", "features": FEATURES})
ALICE = A.get(B + "/api/state").json()["me"]["id"]


def org(name):
    r = A.post(B + "/api/admin/orgs", json={"name": name, "admin_id": ALICE})
    assert r.status_code == 201, r.text
    return r.json()["id"]


NORD, SUED = org("Studio Nord"), org("Atelier Süd")


def put(s, **kw):
    b = {k: json.dumps(v) if isinstance(v, dict) else v for k, v in kw.items()}
    r = s.patch(B + "/api/settings", json=b)
    assert r.ok, r.text


def new(s, name, **kw):
    return s.post(B + "/api/clients", json={"name": name, **kw})


def where(cid):
    return dbx("SELECT org_id FROM clients WHERE id=?", (cid,))[0][0]


# ================================================================== several organisations, the office off in Private (#7298)
put(A, workspace="all", ws_areas_off={"private": ["office"]}, ws_mods_off={})
r = new(A, "Kunde Eins")
j = r.json()
check(r.status_code == 400 and j.get("code") == "space_needed", f"#7298/#7309: under All, Private off, two organisations on: 400 space_needed (never silently Private) {r.status_code} {r.text[:200]}")
check(sorted(w["ws"] for w in j.get("spaces") or []) == sorted([f"org:{NORD}", f"org:{SUED}"]), f"#7309: spaces names both {j.get('spaces')}")
check(sorted(w["org_id"] for w in j.get("workspaces") or []) == sorted([NORD, SUED]), f"#7298: the answer names both organisations {j.get('workspaces')}")
check(sorted(w["name"] for w in j.get("spaces") or []) == ["Atelier Süd", "Studio Nord"] and j.get("error"), f"#7298/#7309: a text and the names to choose from {j}")
check(dbx("SELECT count(*) FROM clients WHERE name='Kunde Eins'")[0][0] == 0, "#7298: nothing created")
put(A, ws_mods_off={f"org:{SUED}": ["clients"]})
r = new(A, "Kunde Zwei")
check(r.status_code == 201 and r.json().get("org_id") == NORD and where(r.json()["id"]) == NORD,
      f"#7298: Clients on only in Studio Nord -> the client lands there without a question {r.status_code} {r.text[:200]}")
r = new(A, "Kunde Privat", org_id=None)
check(r.status_code == 400 and r.json().get("code") == "space_needed" and [w["ws"] for w in r.json().get("spaces") or []] == [f"org:{NORD}"],
      f"#7309: a named Private where Clients is off for me -> 400 space_needed with the one workspace left (was: kept as sent) {r.status_code} {r.text[:200]}")
r = new(A, "Kunde Süd", org_id=SUED)
check(r.status_code == 400 and r.json().get("code") == "space_needed", f"#7309: a named organisation where Clients is off for me -> 400 (was: kept as sent) {r.status_code}")
r = new(A, "Kunde Nord", space=f"org:{NORD}")
check(r.status_code == 201 and where(r.json()["id"]) == NORD, f"#7309: space org:<id> names it like org_id {r.status_code} {r.text[:160]}")

# ================================================================== the admin switched the office off for the organisation
put(A, ws_mods_off={})
r = A.patch(B + f"/api/orgs/{SUED}", json={"areas_off": ["office"]})
check(r.ok, f"#7298: the admin switches the office area off in Atelier Süd {r.status_code} {r.text[:160]}")
r = new(A, "Kunde Drei")
check(r.status_code == 201 and where(r.json()["id"]) == NORD, f"#7298: orgs.areas_off counts too -> Studio Nord {r.status_code} {r.text[:200]}")
A.patch(B + f"/api/orgs/{SUED}", json={"areas_off": []})

# ================================================================== Clients off everywhere
put(A, ws_mods_off={f"org:{NORD}": ["clients"], f"org:{SUED}": ["clients"]})
r = new(A, "Kunde Nirgends")
check(r.status_code == 400 and r.json().get("code") == "space_needed" and r.json().get("spaces") == [] and r.json().get("workspaces") == [],
      f"#7298: Clients off in every workspace -> 400, no workspace offered {r.status_code} {r.text[:200]}")
check(dbx("SELECT count(*) FROM clients WHERE name='Kunde Nirgends'")[0][0] == 0, "#7298: nothing created")
put(A, ws_areas_off={}, ws_mods_off={})

# ================================================================== one organisation, Clients off there, Private on (mirror case)
r = A.post(B + "/api/users", json={"username": "bob", "display_name": "Bob Beispiel", "password": "password123", "email": "bob@example.com", "orgs": [NORD]})
assert r.ok, r.text
Bo = login(B, "bob")
put(Bo, lang="en", tour="done", features=FEATURES, workspace="all")
r = new(Bo, "Kunde Bob")
check(r.status_code == 201 and where(r.json()["id"]) == NORD, f"#7298/#7309: bob, one organisation, all on: the only organisation (transition of wsp_new for calls without a name) {r.status_code} {r.text[:200]}")
r = new(Bo, "Kunde Bob Privat genannt", space="private")
check(r.status_code == 201 and where(r.json()["id"]) is None, f"#7309: named Private, Clients on there -> Private {r.status_code}")
put(Bo, ws_mods_off={f"org:{NORD}": ["clients"]})
r = new(Bo, "Kunde Bob Privat")
check(r.status_code == 201 and where(r.json()["id"]) is None,
      f"#7298: Clients off for bob in his only organisation -> Private, not the organisation where his list hides it {r.status_code} {r.text[:200]}")

# ================================================================== a person without an organisation (P4)
FID, Fr = freelancer(B, A)
r = new(Fr, "Kunde Frei")
check(r.status_code == 201 and where(r.json()["id"]) is None, f"#7298: freelancer: her client is private as before {r.status_code} {r.text[:160]}")
sys.exit(done("p21441_clientws_test"))
