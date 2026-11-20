#!/usr/bin/env python3
# kalmido-suite: fresh
"""(#7309) API tests of the shared place (kalmido/accounts/wsplace.py): ONE answer for "is module X on for person P in a
workspace" (wsp_spaces, /api/state wsp / wsp_w) and "where does a new X go" (wsp_new: named / the workspace on top / the only
one, else 400 space_needed with spaces; #7385: no transition to "the only organisation" any more). freelancer-matrix: clients
Invented names only. The matrix: organisations 0 / 1 / 1 read-only / 2 x the module on / off in Private and in the
organisation x the workspace named / not named; besides it the PATCH /api/settings answer (fresh lists, F8 still_running),
calendar / address book (#7309: they ask too), the move without a target (F6) and the card's cap of a named org_id (F10).
usage: p21465_a_wsplace_test.py <datadir>      (KMT_NOSTART=1 / P21448_NOSTART=1: a running server)"""
import importlib.util
import json
import os
import sys

import requests

from freelancer_fixture import FEATURES, freelancer, login
from kt import B, check, dbx, done, fresh, setup

fresh(prefix="P21448")
A = setup()
A.patch(B + "/api/settings", json={"lang": "en", "tour": "done", "features": FEATURES})
ALICE = A.get(B + "/api/state").json()["me"]["id"]


def org(name, admin=ALICE):
    r = A.post(B + "/api/admin/orgs", json={"name": name, "admin_id": admin})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def put(s, **kw):
    b = {k: json.dumps(v) if isinstance(v, dict) else v for k, v in kw.items()}
    r = s.patch(B + "/api/settings", json=b)
    assert r.ok, r.text
    return r.json()


def st(s):
    return s.get(B + "/api/state").json()


def new(s, name, **kw):
    return s.post(B + "/api/clients", json={"name": name, **kw})


def where(cid):
    return dbx("SELECT org_id FROM clients WHERE id=?", (cid,))[0][0]


def spaces(r):
    return [w["ws"] for w in (r.json().get("spaces") or [])] if r.status_code == 400 else None


# ================================================================== organisations 0 (P4: a freelancer, nothing asks)
FID, Fr = freelancer(B, A)
j = st(Fr)
check(j.get("wsp", {}).get("clients") == ["private"] and j.get("wsp_w", {}).get("clients") == ["private"],
      f"#7309: alone: wsp / wsp_w = Private only {j.get('wsp', {}).get('clients')} {j.get('wsp_w', {}).get('clients')}")
check(set(j.get("wsp") or {}) >= {"clients", "office", "events", "contacts", "files", "docs", "wiki"}, "#7309: wsp has every module")
r = new(Fr, "Frei Kunde")
check(r.status_code == 201 and where(r.json()["id"]) is None, f"#7309: alone: a new client is private, no question {r.status_code} {r.text[:160]}")
put(Fr, ws_mods_off={"private": ["clients"]})  # a value left from a former membership: alone it switches nothing
r = new(Fr, "Frei Kunde Zwei")
check(r.status_code == 201 and where(r.json()["id"]) is None, f"#7309: alone the per-workspace switches do not apply (Private = the main switches) {r.status_code}")
r = Fr.post(B + "/api/evcals", json={"name": "Frei Kalender"})
check(r.status_code == 201 and r.json().get("org_id") in (None, 0), f"#7309: alone: a new calendar is private {r.status_code} {r.text[:160]}")

# ================================================================== organisation 1 (member)
NORD = org("Studio Nord")
r = A.post(B + "/api/users", json={"username": "bob", "display_name": "Bob Beispiel", "password": "password123", "email": "bob@example.com", "orgs": [NORD]})
assert r.ok, r.text
Bo = login(B, "bob")
put(Bo, lang="en", tour="done", features=FEATURES, workspace="all")
j = st(Bo)
check(j["wsp"]["clients"] == ["private", f"org:{NORD}"] and j["wsp_w"]["clients"] == ["private", f"org:{NORD}"],
      f"#7309: one organisation, all on: Private first, then the organisation {j['wsp']['clients']}")
r = new(Bo, "Bob Eins")
check(r.status_code == 400 and r.json().get("code") == "space_needed" and spaces(r) == ["private", f"org:{NORD}"],
      f"#7385: not named, 1 org, Clients on in Private and there -> 400 space_needed, never the only organisation {r.status_code} {r.text[:200]}")
check(dbx("SELECT count(*) FROM clients WHERE name='Bob Eins'")[0][0] == 0, "#7385: nothing created")
r = Bo.post(B + "/api/evcals", json={"name": "Bob Kalender"})
check(r.status_code == 400 and r.json().get("code") == "space_needed", f"#7385: a new calendar without a name asks too {r.status_code} {r.text[:160]}")
BT = {"Authorization": "Bearer " + Bo.post(B + "/api/me/tokens", json={"name": "bob api", "scopes": ["read", "structure"]}).json()["token"]}
r = requests.post(B + "/api/v1/clients", headers=BT, json={"name": "Bob V1"})
e = r.json().get("error") if r.status_code == 400 else None
check(isinstance(e, dict) and e.get("code") == "space_needed" and [x["ws"] for x in e.get("spaces") or []] == ["private", f"org:{NORD}"],
      f"#7385: API v1 (token) without a name -> 400 space_needed with the choice {r.status_code} {r.text[:200]}")
_spec = importlib.util.spec_from_file_location("kalmido_mcp", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "mcp", "kalmido_mcp.py"))
_mcp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mcp)
m = _mcp.Kalmido._err_msg(_mcp.Kalmido.__new__(_mcp.Kalmido), 400, r.content)
check("space_needed" in m and "private = " in m and f"org:{NORD} = Studio Nord" in m,
      f"#7385: MCP: the error text carries the choice, so the agent can ask the person {m[:200]}")
r = requests.post(B + "/api/v1/clients", headers=BT, json={"name": "Bob V1 Nord", "space": f"org:{NORD}"})
check(r.status_code == 201 and where(r.json()["id"]) == NORD, f"#7385: API v1 names space -> there {r.status_code} {r.text[:160]}")
r = new(Bo, "Bob Privat", space="private")
check(r.status_code == 201 and where(r.json()["id"]) is None, f"#7309: named Private -> Private {r.status_code}")
r = new(Bo, "Bob Nord", org_id=NORD)
check(r.status_code == 201 and where(r.json()["id"]) == NORD, f"#7309: named org_id -> there {r.status_code}")
put(Bo, workspace="private")
r = new(Bo, "Bob Oben Privat")
check(r.status_code == 201 and where(r.json()["id"]) is None, f"#7309: not named, the workspace on top (Private) wins {r.status_code}")
put(Bo, workspace="all")
a = put(Bo, ws_mods_off={f"org:{NORD}": ["clients"]})
check(a.get("wsp", {}).get("clients") == ["private"] and a.get("wsp_w", {}).get("clients") == ["private"],
      f"#7309: the PATCH answer carries the fresh lists {a}")
check("still_running" not in a, "#7309 F8: nothing about the office for another switch")
r = new(Bo, "Bob Zwei")
check(r.status_code == 201 and where(r.json()["id"]) is None, f"#7309: Clients off in the organisation -> the only workspace left, Private {r.status_code}")
r = new(Bo, "Bob Nord Aus", org_id=NORD)
check(r.status_code == 400 and r.json().get("code") == "space_needed" and spaces(r) == ["private"],
      f"#7309: named, but Clients off there -> 400 space_needed with the choice {r.status_code} {r.text[:200]}")
check(dbx("SELECT count(*) FROM clients WHERE name='Bob Nord Aus'")[0][0] == 0, "#7309: nothing created")
put(Bo, ws_mods_off={"private": ["clients"]})
r = new(Bo, "Bob Drei")
check(r.status_code == 201 and where(r.json()["id"]) == NORD, f"#7309: Clients off in Private -> the organisation, never silently Private {r.status_code}")
r = new(Bo, "Bob Privat Aus", space="private")
check(r.status_code == 400 and spaces(r) == [f"org:{NORD}"], f"#7309: named Private where Clients is off -> 400 {r.status_code} {r.text[:160]}")
put(Bo, ws_mods_off={"private": ["clients"], f"org:{NORD}": ["clients"]})
r = new(Bo, "Bob Nirgends")
check(r.status_code == 400 and r.json().get("code") == "space_needed" and spaces(r) == [] and r.json().get("error"),
      f"#7309: Clients off everywhere -> 400 with no workspace and a text {r.status_code} {r.text[:200]}")
put(Bo, ws_mods_off={})
r = A.patch(B + f"/api/orgs/{NORD}", json={"areas_off": ["office"]})
check(r.ok, f"the admin switches the office area off in Studio Nord {r.status_code}")
check(st(Bo)["wsp"]["clients"] == ["private"], "#7309: the organisation's areas_off counts (Clients is part of the office area)")
r = new(Bo, "Bob Vier")
check(r.status_code == 201 and where(r.json()["id"]) is None, f"#7309: areas_off -> not into the organisation {r.status_code}")
A.patch(B + f"/api/orgs/{NORD}", json={"areas_off": []})

# ================================================================== organisation 1, read-only (F9)
r = A.post(B + "/api/users", json={"username": "rita", "display_name": "Rita Rot", "password": "password123", "email": "rita@example.com",
                                    "orgs": [{"id": NORD, "role": "readonly"}]})
assert r.ok, r.text
Ri = login(B, "rita")
put(Ri, lang="en", tour="done", features=FEATURES, workspace=f"org:{NORD}")
j = st(Ri)
check(j["wsp"]["clients"] == ["private", f"org:{NORD}"] and j["wsp_w"]["clients"] == ["private"],
      f"#7309 F9: read-only: on in both, writable only in Private {j['wsp']['clients']} {j['wsp_w']['clients']}")
r = new(Ri, "Rita Eins")
check(r.status_code == 201 and where(r.json()["id"]) is None, f"#7309 F9: the one rule - the only writable workspace is Private (the top one is read-only) {r.status_code} {r.text[:160]}")
r = new(Ri, "Rita Nord", space=f"org:{NORD}")
check(r.status_code in (400, 403) and dbx("SELECT count(*) FROM clients WHERE name='Rita Nord'")[0][0] == 0,
      f"#7309 F9: named the read-only organisation -> refused, nothing created {r.status_code} {r.text[:160]}")
put(Ri, ws_mods_off={"private": ["clients"]})
r = new(Ri, "Rita Zwei")
check(r.status_code == 400 and r.json().get("code") == "space_needed" and spaces(r) == [],
      f"#7309 F9: Clients off in Private, read-only in the organisation -> 400, never silently Private {r.status_code} {r.text[:160]}")

# ================================================================== organisations 2 (admin of both)
SUED = org("Atelier Süd")
put(A, workspace="all", ws_mods_off={}, ws_areas_off={})
check(st(A)["wsp_w"]["clients"] == ["private", f"org:{NORD}", f"org:{SUED}"], f"#7309: two organisations: Private, Nord, Süd {st(A)['wsp_w']['clients']}")
r = new(A, "Alice Eins")
check(r.status_code == 400 and r.json().get("code") == "space_needed" and spaces(r) == ["private", f"org:{NORD}", f"org:{SUED}"],
      f"#7309: not named, several -> 400 space_needed with all three {r.status_code} {r.text[:200]}")
check(sorted(x["name"] for x in r.json().get("spaces") or [])[:2] == ["Atelier Süd", "Private"] or "Studio Nord" in str(r.json().get("spaces")),
      f"#7309: the choice carries the names {r.json().get('spaces')}")
put(A, workspace=f"org:{SUED}")
r = new(A, "Alice Oben")
check(r.status_code == 201 and where(r.json()["id"]) == SUED, f"#7309: the workspace on top wins while Clients is on there {r.status_code}")
put(A, ws_mods_off={f"org:{SUED}": ["clients"]})
r = new(A, "Alice Oben Aus")
check(r.status_code == 400 and spaces(r) == ["private", f"org:{NORD}"], f"#7309: top workspace has Clients off -> ask, never there {r.status_code} {r.text[:160]}")
put(A, workspace="all", ws_mods_off={f"org:{SUED}": ["clients"]}, ws_areas_off={"private": ["office"]})
r = new(A, "Alice Nord")
check(r.status_code == 201 and where(r.json()["id"]) == NORD, f"#7309: only Nord left -> Nord {r.status_code}")
put(A, ws_mods_off={}, ws_areas_off={})

# ---- calendar / address book ask too (#7309, Kalender / Adressbuch)
r = A.post(B + "/api/evcals", json={"name": "Kalender Neu"})
check(r.status_code == 400 and r.json().get("code") == "space_needed", f"#7309: a new calendar under All with several workspaces asks {r.status_code} {r.text[:160]}")
r = A.post(B + "/api/evcals", json={"name": "Kalender Nord", "space": f"org:{NORD}"})
check(r.status_code == 201 and r.json().get("org_id") == NORD, f"#7309: space names it {r.status_code} {r.text[:160]}")
put(A, ws_mods_off={"private": ["contacts"], f"org:{SUED}": ["contacts"]})
r = A.post(B + "/api/books", json={"name": "Adressen Neu"})
check(r.status_code == 201 and r.json().get("org_id") == NORD, f"#7309: a new address book goes where Contacts is on (the only one) {r.status_code} {r.text[:160]}")
put(A, ws_mods_off={})

# ---- F8: "Also private" of the office off names what keeps running there (nothing is stopped)
r = A.put(B + "/api/office/bank/noreceipt/reminder", json={"every": "week"}, headers={"X-Kalmido-Office-Space": "private"})
check(r.ok, f"F8: the bank reminder of the private office on {r.status_code} {r.text[:160]}")
a = put(A, ws_mods_off={"private": ["office"]})
check({"kind": "bank_reminder", "count": 1} in (a.get("still_running") or []), f"#7309 F8: the PATCH answer names the reminder that keeps running {a.get('still_running')}")
check("private" not in a.get("wsp", {}).get("office", []), f"#7309: and the office is off in Private in the fresh lists {a.get('wsp', {}).get('office')}")
a = put(A, ws_mods_off={"private": ["office", "clients"]})
check("still_running" not in a, "#7309 F8: said once, when it goes off - not with every later switch")
put(A, ws_mods_off={})

# ---- F6: a move without a target is refused (was: Private)
r = A.post(B + "/api/wiki/move-space", json={"pages": [], "space": f"org:{NORD}"})
check(r.status_code == 400, f"#7309 F6: no 'to' -> 400 {r.status_code} {r.text[:160]}")

# ---- F10: the card's cap counts for a named org_id
r = A.post(B + "/api/modcards", json={"space": f"org:{SUED}", "name": "Nur Zeit", "icon": "clock", "mods": ["time"], "dflt": True})
if r.status_code in (200, 201):
    r = new(A, "Alice Karte", org_id=SUED)
    check(r.status_code in (400, 403) and dbx("SELECT count(*) FROM clients WHERE name='Alice Karte'")[0][0] == 0,
          f"#7309 F10: Clients outside the card's cap in Süd -> refused for a named org_id {r.status_code} {r.text[:160]}")
    check(f"org:{SUED}" not in st(A)["wsp"]["clients"], "#7309: the card's cap counts in wsp")
else:
    check(False, f"F10: the module card could not be made {r.status_code} {r.text[:160]}")
sys.exit(done("p21465_a_wsplace_test"))
