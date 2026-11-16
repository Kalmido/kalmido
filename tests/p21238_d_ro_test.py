#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1238.0 (#6161, Stufe 3): the office document's answer carries can_edit with the person's role (office/docs.py
ofd_role_edit, office/docref.py ofd_get), so the client leaves the write entries out without computing the role itself.
Invented names only, addresses @example.com. freelancer-matrix: office
 - an open draft: can_edit true for the admin, a member, a person without an organisation in the own office
 - false for read-only and accounting (organisation role) and for a member whose office group gives only "view" in
   Quotations & invoices; their changes stay 403 (read-only with the read-only text) - nothing was loosened
 - a guest does not reach the office at all (403, as before)
 - the folder way: a share "view" answers can_edit false, "edit" true; an agent with its share reads, can_edit false,
   and never changes the document
usage: p21238_d_ro_test.py <datadir>      (P21238D_NOSTART=1: a running server)"""
import sys

from freelancer_fixture import freelancer
import requests

from kt import B, H, PASSWORD, check, docker_logs_on_first_fail, done, fresh, sess

docker_logs_on_first_fail()

fresh(prefix="P21238D")
s0 = requests.Session()
s0.headers.update(H)
assert s0.post(B + "/api/auth/setup", json={"username": "alice", "display_name": "Alice", "password": PASSWORD}).ok
A = sess("alice")
r = A.post(B + "/api/admin/setup", json={"org_name": "Alpha Studio", "lang": "en", "collab_all": True, "modules": ["comments"]})
assert r.ok, "admin setup " + r.text[:300]
A = sess("alice")
FEAT = "office,contacts,files,docs,comments"
A.patch(B + "/api/settings", json={"lang": "en", "tour": "done", "features": FEAT})
A.put(B + "/api/admin/agent-policy", json={"user_agents": True})
ORG = A.get(B + "/api/state").json()["me"]["workspaces"][0]["id"]
D, R, REF = "/api/office/docs", "/api/office/rights", "/api/fsref/office_doc"
uid, S = {}, {}
for u, role in (("bob", "member"), ("rita", "readonly"), ("axel", "accounting"), ("vera", "member"), ("gina", "guest"), ("dan", "member")):
    r = A.post(B + "/api/users", json={"orgs": [{"id": ORG, "role": role}], "username": u, "display_name": u.title(),
                                       "password": PASSWORD, "email": f"{u}@example.com"})
    assert r.ok, r.text
    uid[u] = r.json()["id"]
    S[u] = sess(u)
    assert S[u].patch(B + "/api/settings", json={"lang": "en", "tour": "done", "features": FEAT, "workspace": f"org:{ORG}"}).ok
A.patch(B + "/api/settings", json={"workspace": f"org:{ORG}"})
Bo, Ri, Ax, Ve, Gi, Da = S["bob"], S["rita"], S["axel"], S["vera"], S["gina"], S["dan"]

# vera: an office group that only reads Quotations & invoices; dan: the group "Staff" (no Quotations at all)
r = A.post(B + f"{R}/groups", json={"from": "tpl:none", "name": "Readers of quotations"})
check(r.status_code == 201, "setup: group " + r.text[:200])
GID = r.json()["id"]
check(A.patch(B + f"{R}/groups/{GID}", json={"levels": {"offers": "view"}}).ok, "setup: group level offers view")
check(A.put(B + f"{R}/people/{uid['vera']}", json={"groups": [f"g:{GID}"]}).ok, "setup: vera into the group")
check(A.put(B + f"{R}/people/{uid['dan']}", json={"groups": ["tpl:staff"]}).ok, "setup: dan into the group Staff")

r = A.post(B + D, json={"project_title": "Spring campaign"})
check(r.status_code in (200, 201), "admin: a quotation draft " + r.text[:200])
DID = r.json()["id"]
r = A.put(B + f"{D}/{DID}/items", json={"items": [{"title": "Concept", "qty": 2, "rate": 800}]})
check(r.ok and r.json()["can_edit"] is True, "admin: positions saved, can_edit true " + r.text[:200])


def doc(s, did=DID):
    r = s.get(B + f"{D}/{did}")
    assert r.ok, r.text
    return r.json()


check(doc(A)["can_edit"] is True, "admin: can_edit true")
check(doc(Bo)["can_edit"] is True, "member: can_edit true")
for nm, s in (("read-only", Ri), ("accounting", Ax), ("group with offers view", Ve)):
    d = doc(s)
    check(d["can_edit"] is False and not d["locked"] and d["status"] == "draft", f"{nm}: reads the draft, can_edit false {d.get('can_edit')}")
    check([it["title"] for it in d["items"]] == ["Concept"], f"{nm}: sees the positions")
    r = s.patch(B + f"{D}/{DID}", json={"order_ref": "x"})
    check(r.status_code == 403, f"{nm}: a change stays 403 ({r.status_code} {r.text[:150]})")
    r = s.put(B + f"{D}/{DID}/items", json={"items": []})
    check(r.status_code == 403, f"{nm}: positions stay 403 ({r.status_code})")
    check(s.post(B + D, json={"project_title": "x"}).status_code == 403, f"{nm}: no new document")
    check(s.post(B + f"{D}/{DID}/finalize").status_code == 403, f"{nm}: finalising stays 403")
r = Ri.patch(B + f"{D}/{DID}", json={"order_ref": "x"})
check("read-only" in (r.json().get("error") or ""), "read-only: the read-only text " + r.text[:150])
check(Gi.get(B + f"{D}/{DID}").status_code == 403 and Gi.patch(B + f"{D}/{DID}", json={"order_ref": "x"}).status_code == 403,
      "guest: the office stays closed (403 reading and writing)")
check(Da.get(B + f"{D}/{DID}").status_code == 403, "group Staff (no Quotations): the office's document stays closed")
check(doc(A)["items"][0]["title"] == "Concept" and not doc(A).get("order_ref"), "nothing was written by the readers")

# the member saves: the answer of a write carries the same can_edit
r = Bo.patch(B + f"{D}/{DID}", json={"order_ref": "PO-1"})
check(r.ok and r.json()["can_edit"] is True, "member: the save's answer can_edit true " + r.text[:150])

# ---------------------------------------------------------------- the folder way (office/docref.py)
INTRO = doc(A).get("intro")
r = A.post(B + "/api/files/folders", json={"name": "Office", "space": f"org:{ORG}"})
assert r.status_code == 201, r.text
FOLD = r.json()["id"]
r = A.post(B + "/api/files/refs", json={"ref_kind": "office_doc", "ref_id": DID, "parent_id": FOLD})
check(r.ok, "setup: the quotation filed into a folder " + r.text[:200])


def share(nid, **kw):
    r = A.post(B + f"/api/files/nodes/{nid}/shares", json=kw)
    assert r.status_code == 201, r.text
    return r.json()["id"]


SH = share(FOLD, user_id=uid["dan"], role="view")
r = Da.get(B + f"{REF}/{DID}")
check(r.ok and r.json().get("folder_role") == "view" and r.json().get("can_edit") is False,
      f"folder share view: dan reads, can_edit false ({r.status_code} {r.text[:160]})")
check(Da.patch(B + f"{REF}/{DID}", json={"intro": "dan"}).status_code == 403, "folder share view: a change stays 403")
check(A.patch(B + f"/api/files/shares/{SH}", json={"role": "edit"}).ok, "setup: the share becomes edit")
r = Da.get(B + f"{REF}/{DID}")
check(r.ok and r.json().get("folder_role") == "edit" and r.json().get("can_edit") is True,
      f"folder share edit: can_edit true ({r.status_code} {r.text[:160]})")

r = A.post(B + "/api/my/agents", json={"username": "officebot", "display_name": "Office Bot", "scopes": ["read", "files:read", "office"], "org_id": ORG})
check(r.ok, "setup: the organisation's agent " + r.text[:160])
AG, AH = r.json().get("id"), {**H, "Authorization": "Bearer " + r.json().get("token", "")}
share(FOLD, agent_id=AG, role="edit")
check(A.patch(B + f"/api/office/agents/{AG}", json={"office_drafts": True}).ok and A.put(B + "/api/office/settings", json={"agents_read": 1}).ok,
      "setup: the agent's office switch and the area's agents switch on")
r = requests.get(B + f"{REF}/{DID}", headers=AH)
check((r.ok and r.json().get("can_edit") is False) or r.status_code in (401, 403, 404),
      f"agent on the folder way: can_edit false even with a share edit ({r.status_code} {r.text[:160]})")
check(requests.patch(B + f"{REF}/{DID}", headers=AH, json={"intro": "agent"}).status_code in (401, 403, 404), "agent: never changes the document")
check(doc(A).get("intro") == INTRO, "nothing was written by the agent or the readers on the folder way")

# ---------------------------------------------------------------- a freelancer: the own personal office
FID, F = freelancer(B, A, features=FEAT)
r = F.post(B + D, json={"project_title": "Own job"})
check(r.status_code in (200, 201) and r.json()["can_edit"] is True, "freelancer: a draft in the own office, can_edit true " + r.text[:200])
FD = r.json()["id"]
check(F.get(B + f"{D}/{FD}").json()["can_edit"] is True, "freelancer: GET can_edit true")
r = F.patch(B + f"{D}/{FD}", json={"order_ref": "F-1"})
check(r.ok and r.json()["can_edit"] is True, "freelancer: saves, can_edit stays true")

sys.exit(done("p21238_d_ro"))
