#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1212.0 part B (#6156): the owner takes a person out of a calendar's Share dialog -> the share goes into the core's
obj_revoked (restorable), not deleted; the dialog's Undo puts it back through the core. Own container, invented names only.
freelancer-matrix: pim (the owner frida has no organisation)
 - DELETE /api/evcals/<id>/members/<uid> by the owner: answer {ok, revoked: [ids]}, the person no longer sees the calendar nor
   its events, GET /api/obj/evcal/<id>/shares lists the share under "revoked"
 - POST /api/obj/evcal/<id>/shares/<rid>/restore: the person sees it again with the role they had (view), the calendar's
   members list has them again; a second restore of the same row: 404 (the row is gone)
 - a member with "edit" can neither take another person out (403) nor restore a share (no right to manage: refused)
 - a member leaving on their own: answer revoked [] (nothing to restore), they are out
usage: p21212_b_evshare_test.py <datadir>"""
import os
import sys

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
import kt  # noqa: E402
from freelancer_fixture import freelancer  # noqa: E402
from kt import B, check, sess  # noqa: E402

kt.fresh(prefix="P21212B")
A = kt.setup()
FEAT = "cal,events,collab"
FID, Fr = freelancer(B, A, "frida")
check(Fr.get(B + "/api/state").json()["me"].get("workspaces") in (None, []), "frida: no organisation")
ids = {}
for u, n in (("bob", "Bob"), ("carol", "Carol")):
    r = A.post(B + "/api/users", json={"username": u, "display_name": n, "password": kt.PASSWORD, "orgs": []})
    check(r.ok, f"user {u} " + r.text[:200])
    ids[u] = r.json()["id"]
BOB, CAR = ids["bob"], ids["carol"]
Bo, Ca = sess("bob"), sess("carol")
for s in (Bo, Ca):
    s.patch(B + "/api/settings", json={"lang": "en", "tour": "done", "features": FEAT})

C = Fr.post(B + "/api/evcals", json={"name": "Shoots", "color": "#2dd4bf"}).json()
E = Fr.post(B + "/api/events", json={"title": "Location scout", "cal_id": C["id"], "start": "2026-11-20T10:00", "end": "2026-11-20T11:00", "reminders": []}).json()
check(C.get("id") and E.get("id"), "frida: a calendar with an event")
check(Fr.put(B + f"/api/evcals/{C['id']}/members", json={"user_id": BOB, "role": "view"}).ok, "shared with Bob (view)")
check(Fr.put(B + f"/api/evcals/{C['id']}/members", json={"user_id": CAR, "role": "edit"}).ok, "shared with Carol (edit)")


def sees(s, cid=C["id"]):
    return any(x["id"] == cid for x in s.get(B + "/api/evcals").json().get("items", []))


def members():
    c = next(x for x in Fr.get(B + "/api/evcals").json()["items"] if x["id"] == C["id"])
    return {m["user_id"]: m["role"] for m in c.get("members") or []}


check(sees(Bo) and Bo.get(B + f"/api/events/{E['id']}").ok, "Bob sees the calendar and its event")

# a member with edit cannot take another person out
r = Ca.delete(B + f"/api/evcals/{C['id']}/members/{BOB}")
check(r.status_code == 403 and sees(Bo), "Carol (edit) cannot take Bob out: " + str(r.status_code))

# the owner takes Bob out: restorable
r = Fr.delete(B + f"/api/evcals/{C['id']}/members/{BOB}")
rev = r.json().get("revoked") if r.ok else None
check(r.ok and isinstance(rev, list) and len(rev) == 1, "#6156: the answer names the share taken back " + r.text[:200])
check(not sees(Bo) and Bo.get(B + f"/api/events/{E['id']}").status_code in (403, 404), "#6156: Bob no longer sees the calendar nor its event")
check(BOB not in members(), "#6156: Bob is out of the members")
sh = Fr.get(B + f"/api/obj/evcal/{C['id']}/shares")
check(sh.ok and any(x.get("id") == rev[0] for x in sh.json().get("revoked", [])), "#6156: the core lists the share as taken back (restorable) " + sh.text[:300])

# a member cannot restore it
r = Ca.post(B + f"/api/obj/evcal/{C['id']}/shares/{rev[0]}/restore")
check(r.status_code in (403, 404) and not sees(Bo), "#6156: Carol (edit) cannot restore it: " + str(r.status_code))

# the owner's Undo: restored with the role Bob had
r = Fr.post(B + f"/api/obj/evcal/{C['id']}/shares/{rev[0]}/restore")
check(r.ok, "#6156: the owner restores the share " + r.text[:200])
check(sees(Bo) and Bo.get(B + f"/api/events/{E['id']}").ok, "#6156: Bob sees the calendar and its event again")
check(members().get(BOB) == "view", "#6156: with the role he had (view) " + str(members()))
r = Fr.post(B + f"/api/obj/evcal/{C['id']}/shares/{rev[0]}/restore")
check(r.status_code == 404, "#6156: the same row a second time: 404 " + str(r.status_code))

# fable review: a person with two share rows (an old double, one expired) -> one restorable row, one restore gives the access back
import dbx as dbxm  # noqa: E402
from kt import DATA  # noqa: E402
c = dbxm.connect(os.path.join(DATA, "tasks.db"), timeout=10)
nid = c.execute("SELECT id FROM fs_nodes WHERE kind='ref' AND ref_kind='evcal' AND ref_id=?", (C["id"],)).fetchone()[0]
c.execute("INSERT INTO fs_shares(node_id,user_id,role,expires_at,created_by,created_at) VALUES(?,?,?,?,?,?)",
          (nid, BOB, "edit", "2020-01-01T00:00:00Z", FID, "2020-01-01T00:00:00Z"))
c.commit()
c.close()
r = Fr.delete(B + f"/api/evcals/{C['id']}/members/{BOB}")
rev2 = r.json().get("revoked") if r.ok else None
check(r.ok and rev2 and len(rev2) == 1, "review: two rows of Bob -> one restorable share " + r.text[:200])
r = Fr.post(B + f"/api/obj/evcal/{C['id']}/shares/{rev2[0]}/restore")
check(r.ok and sees(Bo) and members().get(BOB) == "view", "review: one restore gives Bob his live share back (view) " + r.text[:200] + str(members()))

# a member leaving on their own: nothing to restore
r = Ca.delete(B + f"/api/evcals/{C['id']}/members/{CAR}")
check(r.ok and r.json().get("revoked") == [] and not sees(Ca), "#6156: Carol leaves on her own: out, nothing to restore " + r.text[:200])
check(not any(x.get("user_id") == CAR for x in Fr.get(B + f"/api/obj/evcal/{C['id']}/shares").json().get("revoked", [])), "#6156: her leaving is not listed as taken back")

sys.exit(kt.done("p21212_b_evshare"))
