#!/usr/bin/env python3
# kalmido-suite: fresh
"""#7292: a client with locations -- a location is a normal client with parent_id = its main client. Own container (start.sh),
invented names only. For an organisation's clients and for a person without an organisation (private clients):
 - parent_id set on create and on PATCH, read back (single client, list, brief list, /api/state, API v1 with a personal key)
 - the label of a location in pickers: "main client · location" (the city when it has the main client's name); a display name
   of its own keeps the first word (#1951)
 - one level only: a location under a location -> 400, a main client with locations cannot become a location -> 400, a client
   cannot be its own main client -> 400; a main client of another workspace (another organisation, someone else's private
   client, the organisation's client for a private one) -> 400
 - GET /api/clients/<main>: sites (each location with its figures, a link id) and group (hours, amounts, budget of the main
   client and all locations together = the sums)
 - the main client in the trash: the locations stand on their own (parent_id null), restored: back under it; deleted for good:
   parent_id NULL in the database, the location stays
 - moving a location into another workspace drops its main client
freelancer-matrix: clients
usage: p7292_client_sites_test.py <datadir>"""
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import requests  # noqa: E402

import kt  # noqa: E402
from freelancer_fixture import freelancer  # noqa: E402
from kt import B, check  # noqa: E402

FEAT = "collab,comments,office,clients,time,budget"
kt.fresh(prefix="P7292")
A = kt.setup()
A.patch(B + "/api/settings", json={"lang": "en", "features": FEAT, "tour": "done"})
ALICE = A.get(B + "/api/state").json()["me"]["id"]
ORG = A.post(B + "/api/admin/orgs", json={"name": "Alpha", "admin_id": ALICE}).json()["id"]
ORG2 = A.post(B + "/api/admin/orgs", json={"name": "Beta", "admin_id": ALICE}).json()["id"]
A.patch(B + "/api/settings", json={"lang": "en", "features": FEAT, "tour": "done", "workspace": f"org:{ORG}"})
YDAY = (date.today() - timedelta(days=1)).isoformat()


def mk(s, who, **b):
    r = s.post(B + "/api/clients", json=b)
    check(r.status_code == 201, f"{who}: client {b.get('name')} ({r.status_code} {r.text[:200]})")
    return r.json()


def track(s, cid, minutes):
    lid = s.post(B + "/api/lists", json={"name": f"Project {cid}"}).json()["id"]
    r = s.patch(B + f"/api/lists/{lid}", json={"client_id": cid, "rate": 100})
    check(r.ok, f"the project gets client {cid} ({r.status_code} {r.text[:200]})")
    r = s.post(B + "/api/time/entries", json={"list_id": lid, "start": YDAY + "T09:00", "minutes": minutes})
    check(r.ok, f"time on client {cid} ({r.status_code} {r.text[:200]})")
    return lid


def sites(s, who, org, foreign):
    """org: the organisation id of the clients (None = private); foreign: a client id of another workspace."""
    o = {"org_id": org} if org else {}
    P = mk(s, who, name="Acme Group", budget_h=10, budget_amount=1000, **o)
    S1 = mk(s, who, name="Acme Group", city="Zurich", parent_id=P["id"], budget_h=4, **o)
    check(S1.get("parent_id") == P["id"], f"{who}: create with parent_id reads it back {S1.get('parent_id')}")
    S2 = mk(s, who, name="Acme Bonn Ltd", **o)
    check(S2.get("parent_id") is None, f"{who}: no main client = null")
    r = s.patch(B + f"/api/clients/{S2['id']}", json={"parent_id": P["id"]})
    check(r.ok and r.json().get("parent_id") == P["id"], f"{who}: PATCH sets parent_id ({r.status_code} {r.text[:200]})")
    D = mk(s, who, name="Acme Dresden", display_name="Acme East", parent_id=P["id"], **o)
    # ---- labels
    st = {c["id"]: c for c in s.get(B + "/api/state").json().get("clients", [])}
    check(st.get(S1["id"], {}).get("label") == "Acme Group · Zurich", f"{who}: same name -> 'main · city': {st.get(S1['id'], {}).get('label')}")
    check(st.get(S2["id"], {}).get("label") == "Acme Group · Acme Bonn Ltd", f"{who}: other name -> 'main · name': {st.get(S2['id'], {}).get('label')}")
    check(st.get(D["id"], {}).get("label") == "Acme East", f"{who}: a display name keeps the first word (#1951): {st.get(D['id'], {}).get('label')}")
    check(st.get(S1["id"], {}).get("parent_id") == P["id"] and st.get(P["id"], {}).get("parent_id") is None, f"{who}: /api/state names the main client")
    lst = {c["id"]: c for c in s.get(B + "/api/clients").json()["clients"]}
    check(lst[S2["id"]]["parent_id"] == P["id"], f"{who}: the list names the main client")
    brief = {c["id"]: c for c in s.get(B + "/api/clients?brief=1").json()["clients"]}
    check(brief[S1["id"]]["parent_id"] == P["id"] and brief[S1["id"]]["label"] == "Acme Group · Zurich", f"{who}: the brief list too")
    # ---- one level, the same workspace
    r = s.post(B + "/api/clients", json={"name": "Acme Zurich Desk", "parent_id": S1["id"], **o})
    check(r.status_code == 400 and "location itself" in r.text, f"{who}: a location under a location -> 400 ({r.status_code} {r.text[:200]})")
    r = s.patch(B + f"/api/clients/{P['id']}", json={"parent_id": S2["id"]})
    check(r.status_code == 400, f"{who}: a location as main client -> 400 ({r.status_code})")
    X = mk(s, who, name="Other Ltd", **o)
    r = s.patch(B + f"/api/clients/{P['id']}", json={"parent_id": X["id"]})
    check(r.status_code == 400 and "has locations itself" in r.text, f"{who}: a main client with locations cannot become one -> 400 ({r.status_code} {r.text[:200]})")
    r = s.patch(B + f"/api/clients/{X['id']}", json={"parent_id": X["id"]})
    check(r.status_code == 400, f"{who}: its own main client -> 400 ({r.status_code})")
    r = s.patch(B + f"/api/clients/{X['id']}", json={"parent_id": foreign})
    check(r.status_code == 400, f"{who}: a main client of another workspace -> 400 ({r.status_code} {r.text[:200]})")
    r = s.post(B + "/api/clients", json={"name": "Wrong", "parent_id": "1", **o})
    check(r.status_code == 400, f"{who}: parent_id must be an id ({r.status_code})")
    check(s.get(B + f"/api/clients/{X['id']}").json().get("parent_id") is None, f"{who}: nothing of the refused changes was written")
    # ---- the sums on the main client
    track(s, P["id"], 60)
    track(s, S1["id"], 30)
    track(s, S2["id"], 90)
    g = s.get(B + f"/api/clients/{P['id']}").json()
    ss = {x["id"]: x for x in g.get("sites") or []}
    check(set(ss) == {S1["id"], S2["id"], D["id"]}, f"{who}: sites names the three locations {sorted(ss)}")
    grp = g.get("group") or {}
    tot = grp.get("stats") or {}
    own = g["stats"]
    check(tot.get("seconds") == own["seconds"] + sum(x["stats"]["seconds"] for x in ss.values()) and tot.get("seconds") == 180 * 60,
          f"{who}: the hours of all together {tot.get('seconds')} = {own['seconds']} + locations")
    check(abs((tot.get("amount") or 0) - (own["amount"] + sum(x["stats"]["amount"] for x in ss.values()))) < 0.01 and (tot.get("amount") or 0) > 0,
          f"{who}: the amounts of all together {tot.get('amount')}")
    check(grp.get("budget_h") == 14 and grp.get("budget_amount") == 1000 and grp.get("budget", {}).get("level") in ("ok", "warn", "over"),
          f"{who}: the budget of all together {grp.get('budget_h')} h / {grp.get('budget_amount')} {grp.get('budget')}")
    check(ss[S1["id"]]["label"] == "Acme Group · Zurich" and ss[S1["id"]]["stats"]["seconds"] == 30 * 60, f"{who}: a location's own figures {ss[S1['id']]}")
    l1 = s.get(B + f"/api/clients/{S1['id']}").json()
    check("sites" not in l1 and "group" not in l1 and l1["stats"]["seconds"] == 30 * 60, f"{who}: a location's page has only its own figures")
    # ---- a location leaves
    r = s.patch(B + f"/api/clients/{D['id']}", json={"parent_id": None})
    check(r.ok and r.json().get("parent_id") is None, f"{who}: parent_id null removes the main client ({r.status_code})")
    check({x["id"] for x in s.get(B + f"/api/clients/{P['id']}").json().get("sites") or []} == {S1["id"], S2["id"]}, f"{who}: two locations left")
    # ---- the trash
    r = s.delete(B + f"/api/clients/{P['id']}")
    check(r.ok and r.json().get("trashed"), f"{who}: the main client into the trash ({r.status_code} {r.text[:200]})")
    j = s.get(B + f"/api/clients/{S1['id']}").json()
    check(j.get("parent_id") is None and j.get("label") in ("Acme Group (Zurich)", "Acme Group"), f"{who}: in the trash, the location stands on its own {j.get('parent_id')} {j.get('label')}")
    r = s.post(B + f"/api/clients/{P['id']}/restore")
    check(r.ok and s.get(B + f"/api/clients/{S1['id']}").json().get("parent_id") == P["id"], f"{who}: restored, the location is under it again ({r.status_code})")
    s.delete(B + f"/api/clients/{P['id']}")
    r = s.delete(B + f"/api/clients/{P['id']}/purge")
    check(r.ok, f"{who}: the main client deleted for good ({r.status_code} {r.text[:200]})")
    raw = kt.dbx("SELECT parent_id FROM clients WHERE id=?", (S1["id"],))
    check(raw and raw[0][0] is None, f"{who}: deleted for good -> parent_id NULL, the location stays {raw}")
    return S2["id"]


# ---------------------------------------------------------------- an organisation's clients
FOREIGN_ORG = mk(A, "setup", name="Beta Client", org_id=ORG2)["id"]
sites(A, "org", ORG, FOREIGN_ORG)

# ---- moving a location into another workspace drops its main client
M = mk(A, "move", name="Move Main", org_id=ORG)
L = mk(A, "move", name="Move Site", org_id=ORG, parent_id=M["id"])
r = A.patch(B + f"/api/clients/{L['id']}", json={"org_id": ORG2})
check(r.ok and r.json().get("parent_id") is None and r.json().get("org_id") == ORG2, f"move: into another organisation without its main client ({r.status_code} {r.text[:200]})")
check(kt.dbx("SELECT parent_id FROM clients WHERE id=?", (L["id"],))[0][0] is None, "move: parent_id NULL in the database")

# ---- API v1 with a personal key (the agents' / scripts' way)
pt = A.post(B + "/api/me/tokens", json={"name": "p7292", "scopes": ["read", "structure"]}).json()["token"]
PT = {"Authorization": "Bearer " + pt}
V = B + "/api/v1"
VM = mk(A, "v1", name="V1 Main", org_id=ORG)
r = requests.post(V + "/clients", headers=PT, json={"name": "V1 Site", "org_id": ORG, "parent_id": VM["id"]})
check(r.status_code == 201 and r.json().get("parent_id") == VM["id"], f"v1: POST with parent_id ({r.status_code} {r.text[:200]})")
vs = r.json().get("id")
r = requests.get(V + f"/clients/{VM['id']}", headers=PT)
check(r.ok and [x["id"] for x in r.json().get("sites") or []] == [vs], f"v1: GET of the main client lists the location ({r.status_code})")
r = requests.patch(V + f"/clients/{vs}", headers=PT, json={"parent_id": None})
check(r.ok and r.json().get("parent_id") is None, f"v1: PATCH parent_id null ({r.status_code} {r.text[:200]})")
r = requests.patch(V + f"/clients/{vs}", headers=PT, json={"parent_id": FOREIGN_ORG})
check(r.status_code in (400, 404), f"v1: a main client of another organisation -> refused ({r.status_code})")
spec = A.get(B + "/api/v1/openapi.json")
if spec.ok:
    props = spec.json().get("components", {}).get("schemas", {}).get("Client", {}).get("properties", {})
    check("parent_id" in props and "sites" in props, "OpenAPI: Client documents parent_id and sites")

# ---------------------------------------------------------------- a person without an organisation (freelancer-matrix: clients)
FID, Fr = freelancer(B, A)
FID2, Fr2 = freelancer(B, A, "fiona")
FOREIGN_PRIV = mk(Fr2, "setup", name="Fiona's Client")["id"]
sites(Fr, "freelancer", None, FOREIGN_PRIV)
r = Fr.post(B + "/api/clients", json={"name": "Into Alpha", "parent_id": FOREIGN_ORG})
check(r.status_code == 400, f"freelancer: an organisation's client as main client -> 400 ({r.status_code})")
sys.exit(kt.done("p7292_client_sites_test"))
