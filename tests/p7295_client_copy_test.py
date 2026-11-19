#!/usr/bin/env python3
# kalmido-suite: fresh
"""#7295: "Duplicate" and "Add location" of a client page: POST /api/clients/<id>/copy {as_location?, contacts?} (and
/api/v1/clients/<id>/copy). Own container (start.sh), invented names only. For an organisation's client and for a person
without an organisation (private clients):
 - a copy takes over name (+ " (copy)"), name addition, the address fields, country, hourly rate, icon, colour, note; NOT
   projects, time, budget, e-mail / phone, the invoicing fields, the archive state; the contact persons only with contacts
 - a location: parent_id = the client, the same name, the name addition empty; of a location: its main client (one level)
 - another organisation's client / someone else's private client -> 404 (tenant-matrix: client), nothing is created
 - undo = DELETE of the new client: it goes to the trash, the source stays untouched
freelancer-matrix: office
usage: p7295_client_copy_test.py <datadir>"""
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import requests  # noqa: E402

import kt  # noqa: E402
from freelancer_fixture import freelancer  # noqa: E402
from kt import B, check  # noqa: E402

FEAT = "collab,comments,office,clients,time,budget"
kt.fresh(prefix="P7295")
A = kt.setup()
A.patch(B + "/api/settings", json={"lang": "en", "features": FEAT, "tour": "done"})
ALICE = A.get(B + "/api/state").json()["me"]["id"]
ORG = A.post(B + "/api/admin/orgs", json={"name": "Alpha", "admin_id": ALICE}).json()["id"]
ORG2 = A.post(B + "/api/admin/orgs", json={"name": "Beta", "admin_id": ALICE}).json()["id"]
A.patch(B + "/api/settings", json={"lang": "en", "features": FEAT, "tour": "done", "workspace": f"org:{ORG}"})
YDAY = (date.today() - timedelta(days=1)).isoformat()
SRC = {"name": "Nordlicht Studios", "name_extra": "Postproduction", "street": "Hafenweg 3", "address_extra": "Hof 2", "zip": "20457",
       "city": "Hamburg", "country": "DE", "rate": 95, "icon": "🎬", "color": "#336699", "note": "Prefers mornings",
       "email": "info@nordlicht.example", "phone": "+49 40 1234", "budget_h": 40, "budget_amount": 4000, "vat_id": "DE123456789",
       "customer_no": "K-77", "contacts": [{"name": "Mara Kühn", "role": "Producer", "email": "mara@nordlicht.example", "is_default": True},
                                           {"name": "Jonas Weber", "role": "Editor"}]}
TAKEN = ("name_extra", "street", "address_extra", "zip", "city", "rate", "icon", "color", "note")


def get(s, cid):
    r = s.get(B + f"/api/clients/{cid}")
    return r.json() if r.ok else None


def scenario(s, who, org, foreign):
    """org: the organisation of the clients (None = private); foreign: a client id of another workspace."""
    body = dict(SRC, **({"org_id": org} if org else {}))
    r = s.post(B + "/api/clients", json=body)
    check(r.status_code == 201, f"{who}: the source client ({r.status_code} {r.text[:200]})")
    src = r.json()
    lid = s.post(B + "/api/lists", json={"name": f"Project of {who}"}).json()["id"]
    check(s.patch(B + f"/api/lists/{lid}", json={"client_id": src["id"], "rate": 100}).ok, f"{who}: a project of the source")
    s.post(B + "/api/time/entries", json={"list_id": lid, "start": YDAY + "T09:00", "minutes": 90})
    s.post(B + "/api/clients/bulk", json={"action": "archive", "ids": [src["id"]]})
    check(get(s, src["id"])["archived"], f"{who}: the source is archived (the copy must not be)")

    # ---- a copy without contact persons
    r = s.post(B + f"/api/clients/{src['id']}/copy", json={})
    check(r.status_code == 201, f"{who}: copy -> 201 ({r.status_code} {r.text[:200]})")
    cp = r.json()
    full = get(s, cp["id"]) or {}
    bill = full.get("billing") or {}
    check(cp["name"] == "Nordlicht Studios (copy)", f"{who}: the name with (copy): {cp['name']!r}")
    check(all((full.get(k) if k in full else bill.get(k)) == (SRC[k] if k != "rate" else float(SRC[k])) for k in TAKEN)
          and bill.get("country") == "DE",
          f"{who}: name addition, address fields, country, rate, icon, colour, note taken over: "
          + str({k: full.get(k, bill.get(k)) for k in TAKEN + ('country',)}))
    check(not full.get("archived") and full.get("budget_h") is None and full.get("budget_amount") is None
          and not full.get("email") and not full.get("phone") and not bill.get("vat_id") and not bill.get("customer_no"),
          f"{who}: not taken over: archive state, budget, e-mail, phone, invoicing fields")
    check(full.get("lists") == [] and not (full.get("stats") or {}).get("seconds") and full.get("contacts") == [],
          f"{who}: no projects, no time, no contact persons without the tick: {full.get('lists')} {full.get('contacts')}")
    check(full.get("org_id") == org and full.get("parent_id") is None, f"{who}: in the same workspace, no main client")
    check(get(s, src["id"])["lists"] == [lid], f"{who}: the source keeps its project")

    # ---- with the contact persons
    r = s.post(B + f"/api/clients/{src['id']}/copy", json={"contacts": True})
    ks = (get(s, r.json()["id"]) or {}).get("contacts") if r.status_code == 201 else []
    check(r.status_code == 201 and [(k["name"], k["role"], k["is_default"]) for k in ks]
          == [("Mara Kühn", "Producer", True), ("Jonas Weber", "Editor", False)],
          f"{who}: with contacts: the contact persons are copied, the default stays the default {ks}")
    src_ks = {k["id"] for k in get(s, src["id"])["contacts"]}
    check(src_ks.isdisjoint({k["id"] for k in ks}) and len(src_ks) == 2, f"{who}: new contact rows, the source keeps its own")

    # ---- a location of the client, then a location of a location (= of the same main client)
    r = s.post(B + f"/api/clients/{src['id']}/copy", json={"as_location": True})
    loc = r.json() if r.status_code == 201 else {}
    check(r.status_code == 201 and loc.get("parent_id") == src["id"] and loc.get("name") == "Nordlicht Studios"
          and not loc.get("name_extra"), f"{who}: a location: parent_id, the same name, no name addition ({r.status_code} {r.text[:200]})")
    r = s.post(B + f"/api/clients/{loc.get('id')}/copy", json={"as_location": True})
    check(r.status_code == 201 and r.json().get("parent_id") == src["id"],
          f"{who}: a location of a location gets the same main client ({r.status_code} {r.text[:200]})")
    r = s.post(B + f"/api/clients/{loc.get('id')}/copy", json={})
    check(r.status_code == 201 and r.json().get("parent_id") is None, f"{who}: a copy of a location stands on its own")
    check(s.post(B + f"/api/clients/{src['id']}/copy", json={"as_location": "yes"}).status_code == 400, f"{who}: as_location must be a boolean")

    # ---- another workspace's client: 404, nothing created
    n0 = len(s.get(B + "/api/clients?brief=1&archived=1").json()["clients"])
    r = s.post(B + f"/api/clients/{foreign}/copy", json={"contacts": True})
    n1 = len(s.get(B + "/api/clients?brief=1&archived=1").json()["clients"])
    check(r.status_code == 404 and n0 == n1, f"tenant-matrix: client -- {who} cannot copy a client of another workspace ({r.status_code}, {n0} -> {n1})")

    # ---- undo: the new client into the trash, the source untouched
    r = s.delete(B + f"/api/clients/{cp['id']}")
    check(r.ok and r.json().get("trashed") and get(s, cp["id"]) is None and get(s, src["id"])["name"] == "Nordlicht Studios",
          f"{who}: undo = the copy into the trash, the source stays ({r.status_code} {r.text[:200]})")
    return src


# ---------------------------------------------------------------- an organisation's client
r = A.post(B + "/api/clients", json={"name": "Beta Client", "org_id": ORG2})
check(r.status_code == 201, "setup: a client of the second organisation")
FOREIGN_ORG = r.json()["id"]
FID, Fr = freelancer(B, A)
FID2, Fr2 = freelancer(B, A, "fiona")
FOREIGN_PRIV = Fr2.post(B + "/api/clients", json={"name": "Fiona's Client"}).json()["id"]
ORG_SRC = scenario(A, "organisation", ORG, FOREIGN_PRIV)

# a member of Alpha who is read-only: no copy
r = A.post(B + "/api/users", json={"username": "rita", "display_name": "Rita", "password": "password123", "email": "rita@example.com",
                                    "orgs": [{"id": ORG, "role": "readonly"}]})
check(r.ok, f"setup: Rita read-only in Alpha ({r.status_code} {r.text[:200]})")
Ri = kt.sess("rita")
Ri.patch(B + "/api/settings", json={"lang": "en", "features": FEAT, "tour": "done"})
n0 = len(A.get(B + "/api/clients?brief=1&archived=1").json()["clients"])
r = Ri.post(B + f"/api/clients/{ORG_SRC['id']}/copy", json={})
check(r.status_code == (403 if get(Ri, ORG_SRC["id"]) else 404) and len(A.get(B + "/api/clients?brief=1&archived=1").json()["clients"]) == n0,
      f"a read-only member cannot copy the organisation's client ({r.status_code} {r.text[:200]})")

# ---------------------------------------------------------------- API v1 with a personal key
pt = A.post(B + "/api/me/tokens", json={"name": "p7295", "scopes": ["read", "structure"]}).json()["token"]
PT = {"Authorization": "Bearer " + pt}
r = requests.post(B + f"/api/v1/clients/{ORG_SRC['id']}/copy", headers=PT, json={"as_location": True})
check(r.status_code == 201 and r.json().get("parent_id") == ORG_SRC["id"], f"v1: a location through the API ({r.status_code} {r.text[:200]})")
r = requests.post(B + f"/api/v1/clients/{ORG_SRC['id']}/copy", headers=PT, json={"bogus": 1})
check(r.status_code == 400, f"v1: an unknown field -> 400 ({r.status_code})")
r = requests.post(B + f"/api/v1/clients/{FOREIGN_PRIV}/copy", headers=PT, json={})
check(r.status_code == 404, f"tenant-matrix: client -- v1: someone else's private client -> 404 ({r.status_code})")
ro = A.post(B + "/api/me/tokens", json={"name": "p7295r", "scopes": ["read"]}).json()["token"]
r = requests.post(B + f"/api/v1/clients/{ORG_SRC['id']}/copy", headers={"Authorization": "Bearer " + ro}, json={})
check(r.status_code == 403, f"v1: without the scope structure -> 403 ({r.status_code})")

# ---------------------------------------------------------------- a person without an organisation (freelancer-matrix: office)
scenario(Fr, "freelancer", None, FOREIGN_ORG)
sys.exit(kt.done("p7295_client_copy_test"))
