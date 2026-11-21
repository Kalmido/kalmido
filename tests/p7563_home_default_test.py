#!/usr/bin/env python3
# kalmido-suite: fresh
"""(#7563, decision of 20.11.2026) API tests: Home (the area "life") is off in every organisation as long as nobody switches it
on there - a default of the existing switch ws_areas_off (kalmido/accounts/wsareas.py wsa_own), no second switch, nothing
written or deleted. Invented names only.
- a new organisation without Home data: /api/state hands ws_areas_off out with {"org:<id>": ["life"]}, wsp (the shared place,
  accounts/wsplace.py) lists Travel / Contracts in Private only; nothing is stored for it (user_settings untouched)
- an organisation with Home data (a trip there) keeps Home: no default for it, Travel is on there
- switched on once (Settings > Modules: the key of the organisation with an empty list) Home stays on, also after a reload;
  switched off again it is off; an organisation's key with an empty list is kept by PATCH /api/settings
- Private as today: Home on there
- freelancer-matrix: a person without an organisation: Private only, no default key (P4)
usage: p7563_home_default_test.py <datadir>"""
import json
import sys

from freelancer_fixture import FEATURES, freelancer
from kt import B, check, dbx, done, fresh, setup

fresh(prefix="P7563")
A = setup()
A.patch(B + "/api/settings", json={"lang": "en", "tour": "done", "features": FEATURES, "workspace": "all"})
ALICE = A.get(B + "/api/state").json()["me"]["id"]


def org(name):
    r = A.post(B + "/api/admin/orgs", json={"name": name, "admin_id": ALICE})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def st():
    return A.get(B + "/api/state").json()


def own(j):
    return json.loads(j["settings"].get("ws_areas_off") or "{}")


def stored():
    r = dbx("SELECT value FROM user_settings WHERE user_id=? AND key='ws_areas_off'", (ALICE,))
    return json.loads(r[0][0]) if r else {}


# ================================================================== two organisations: one with a trip before the change of view
O1 = org("Plain Studio")
O2 = org("Travel Crew")
r = A.post(B + "/api/life/trips", json={"name": "Fair in Lyon", "from": "2027-03-01", "to": "2027-03-04", "space": f"org:{O2}"})
check(r.status_code == 201, f"setup: a trip of Travel Crew {r.status_code} {r.text[:200]}")
tl = r.json().get("list_id")
check(tl and dbx("SELECT org_id FROM lists WHERE id=?", (tl,))[0][0] == O2, "setup: the trip's list belongs to Travel Crew")

j = st()
o = own(j)
check(o.get(f"org:{O1}") == ["life"], f"#7563: an organisation without Home data: Home off by default {o}")
check(o.get(f"org:{O2}") == [], f"#7563: an organisation with Home data keeps Home (no default) {o}")
check("life" not in (o.get("private") or []), f"#7563: Private as today (Home on) {o}")
wsp = j.get("wsp") or {}
check(wsp.get("travel") == ["private", f"org:{O2}"], f"#7563: wsp travel = Private + the organisation with Home data {wsp.get('travel')}")
check(wsp.get("contracts") == ["private", f"org:{O2}"], f"#7563: wsp contracts the same (the area, not the module) {wsp.get('contracts')}")
check(wsp.get("wiki") == ["private", f"org:{O1}", f"org:{O2}"], f"#7563: other areas untouched {wsp.get('wiki')}")
check(stored() == {}, f"#7563: nothing written for the default (a rule, no migration) {stored()}")

# ================================================================== switched on in Plain Studio (Settings > Modules writes the whole map)
o[f"org:{O1}"] = []
r = A.patch(B + "/api/settings", json={"ws_areas_off": json.dumps(o)})
check(r.ok, f"#7563: Home switched on in Plain Studio {r.status_code} {r.text[:200]}")
check(stored().get(f"org:{O1}") == [], f"#7563: the organisation's key with an empty list is kept (= my choice: all on) {stored()}")
check(f"org:{O2}" not in stored(), f"#7563 F4: the whole map sent back does not freeze another organisation's default into a choice {stored()}")
check(f"org:{O1}" in ((r.json().get("wsp") or {}).get("travel") or []), f"#7563: the PATCH answer's fresh lists have Travel in Plain Studio {r.json().get('wsp', {}).get('travel')}")
j = st()
check(own(j).get(f"org:{O1}") == [] and f"org:{O1}" in j["wsp"]["travel"], f"#7563: after a reload Home stays on in Plain Studio {own(j)} {j['wsp']['travel']}")
# and off again
o = own(j)
o[f"org:{O1}"] = ["life"]
A.patch(B + "/api/settings", json={"ws_areas_off": json.dumps(o)})
j = st()
check(f"org:{O1}" not in j["wsp"]["travel"], f"#7563: switched off again {j['wsp']['travel']}")
check(f"org:{O1}" not in stored(), f"#7563 F4: off again equals the default - no own key is kept {stored()}")
# Private keeps its old form: an empty list of Private is dropped
o = own(j)
o["private"] = []
A.patch(B + "/api/settings", json={"ws_areas_off": json.dumps(o)})
check("private" not in stored(), f"#7563: an empty list of Private is dropped as before {stored()}")

# ================================================================== a third organisation joined later: the default without a write
O3 = org("Late Studio")
j = st()
check(own(j).get(f"org:{O3}") == ["life"] and f"org:{O3}" not in j["wsp"]["travel"], f"#7563: a new organisation: Home off at once {own(j)}")
check(f"org:{O3}" not in stored(), "#7563: ... and nothing stored for it")

# ================================================================== P4: a person without an organisation
FID, Fr = freelancer(B, A)
jf = Fr.get(B + "/api/state").json()
check(json.loads(jf["settings"].get("ws_areas_off") or "{}") == {} and jf.get("wsp", {}).get("travel") == ["private"],
      f"#7563 P4: alone: no default key, Travel in Private {jf['settings'].get('ws_areas_off')} {jf.get('wsp', {}).get('travel')}")

sys.exit(done("p7563_home_default_test"))
