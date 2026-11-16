#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1258.0 (#6296, audit #4741 Z4-F1): a linked schema field belongs to the schema only while its project lies in the
schema's space. Own container (start.sh, restarted once with the data kept). Invented names only.
 - (a) a project leaves the organisation: its field lets go of the link (the field and its values stay, the owner may rename
   it now); a change of the organisation's field reaches only the projects still in the organisation (a removed option no
   longer clears values in the moved project)
 - (b) a private project with the person's own linked field handed to another person: the link goes, the former owner's
   change of the field no longer reaches it; an organisation's project handed to another member keeps its link
 - (c) a link left over from before 2.1258 (written straight into the database): the change of the field skips it, the next
   start of the server lets go of it, the projects in the space keep theirs
 - freelancer-matrix: orgschema. A person without an organisation: her own field reaches her project; her project changing
   hands in the database (any path) lets go of the link
usage: p6296_orgfield_space_api_test.py <datadir>"""
import os
import sys

import dbx as dbxm
import kt
from kt import B, check, done, sess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from freelancer_fixture import freelancer  # noqa: E402

kt.fresh()
assert kt.sess(None).post(B + "/api/auth/setup", json={"username": "alice", "display_name": "Alice", "password": kt.PASSWORD}).ok
A = sess("alice")
A.post(B + "/api/admin/setup", json={"org_name": "Alpha", "lang": "en", "collab_all": True, "modules": ["comments"]})
A = sess("alice")
ORG = A.get(B + "/api/state").json()["me"]["workspaces"][0]["id"]
r = A.post(B + "/api/users", json={"orgs": [ORG], "username": "bob", "display_name": "Bob", "password": kt.PASSWORD,
                                   "email": "bob@example.com"})
assert r.ok, r.text
BOB = r.json()["id"]
Bo = sess("bob")
FEAT = "collab,comments,fields"
for s in (A, Bo):
    assert s.patch(B + "/api/settings", json={"lang": "en", "tour": "done", "features": FEAT}).ok
FU, F = freelancer(B, A, "frida")
SEL = {"options": [{"id": "acme", "name": "Acme"}, {"id": "glob", "name": "Globex"}]}


def st(s):
    return s.get(B + "/api/state").json()


def fld(s, fid):
    return next((f for f in st(s)["fields"] if f["id"] == fid), None)


def link_of(fid):
    return kt.dbx("SELECT org_field_id FROM list_fields WHERE id=?", (fid,))[0][0]


def dbw(sql, args=()):
    c = dbxm.connect(os.path.join(kt.DATA, "tasks.db"), timeout=10)
    c.execute(sql, args)
    c.commit()
    c.close()


def mklist(s, name, org=None):
    r = s.post(B + "/api/lists", json={"name": name, "kind": "project", "org_id": org})  # None: private (not the default workspace)
    assert r.ok, r.text
    return r.json()["id"]


def task(s, lid, title, fid, v):
    r = s.post(B + "/api/tasks", json={"title": title, "list_id": lid, "fields": {str(fid): v}})
    assert r.ok, r.text
    return r.json()["id"]


def val(s, tid, fid):
    return next(t for t in st(s)["tasks"] if t["id"] == tid)["fields"].get(str(fid))


# ================================================================== (a) a project leaves the organisation
OF = A.post(B + "/api/org-fields", json={"space": f"org:{ORG}", "name": "Client", "type": "select", "options": SEL}).json()["id"]
P1, P2 = mklist(A, "Moves out", ORG), mklist(A, "Stays", ORG)
F1 = A.put(B + f"/api/lists/{P1}/org-fields/{OF}", json={"on": True}).json()["field_id"]
F2 = A.put(B + f"/api/lists/{P2}/org-fields/{OF}", json={"on": True}).json()["field_id"]
T1, T2 = task(A, P1, "Moved task", F1, "glob"), task(A, P2, "Staying task", F2, "glob")
check(F1 and F2 and link_of(F1) == OF and link_of(F2) == OF, "setup: both projects link the field")
r = A.patch(B + f"/api/lists/{P1}", json={"org_id": None})
check(r.ok, f"(a) the owner moves the project out of the organisation {r.status_code} {r.text[:200]}")
check(link_of(F1) is None and fld(A, F1) and fld(A, F1)["org_field_id"] is None, "(a) its field lets go of the link, the field stays")
check(link_of(F2) == OF, "(a) the project still in the organisation keeps its link")
r = A.patch(B + f"/api/org-fields/{OF}", json={"name": "Customer", "options": {"options": SEL["options"][:1]}})
check(r.ok and r.json()["lists"] == 1, f"(a) the change of the field reaches one project {r.text[:200]}")
check(fld(A, F1)["name"] == "Client" and len(fld(A, F1)["options"]["options"]) == 2, "(a) the moved project keeps name and options")
check(val(A, T1, F1) == "glob", f"(a) the removed option leaves the moved project's value alone {val(A, T1, F1)}")
check(fld(A, F2)["name"] == "Customer" and not val(A, T2, F2), "(a) the project in the organisation follows the change")
r = A.patch(B + f"/api/fields/{F1}", json={"name": "Kunde"})
check(r.ok and fld(A, F1)["name"] == "Kunde", f"(a) the owner renames the moved project's field now (was 409) {r.status_code}")

# ================================================================== (b) a project changes hands
OWN = A.post(B + "/api/org-fields", json={"space": "private", "name": "Rate", "type": "text"}).json()["id"]
P3 = mklist(A, "Handed over")
F3 = A.put(B + f"/api/lists/{P3}/org-fields/{OWN}", json={"on": True}).json().get("field_id")
check(F3 and link_of(F3) == OWN and not kt.dbx("SELECT org_id FROM lists WHERE id=?", (P3,))[0][0],
      "setup: the private project links the person's own field")
r = A.post(B + f"/api/lists/{P3}/owner", json={"user_id": BOB})
check(r.ok, f"(b) handed over to bob {r.status_code} {r.text[:200]}")
check(link_of(F3) is None, "(b) the new owner's project lets go of the former owner's own field")
r = A.patch(B + f"/api/org-fields/{OWN}", json={"name": "Rate old"})
check(r.ok and r.json()["lists"] == 0 and fld(Bo, F3)["name"] == "Rate", f"(b) the former owner's change no longer reaches it {r.text[:200]}")
r = A.post(B + f"/api/lists/{P2}/owner", json={"user_id": BOB})
check(r.ok and link_of(F2) == OF, f"(b) an organisation's project handed to a member keeps its link {r.status_code}")

# ================================================================== (c) a link left over from before 2.1258
dbw("UPDATE list_fields SET org_field_id=? WHERE id=?", (OF, F1))  # the project is private: outside the organisation
r = A.patch(B + f"/api/org-fields/{OF}", json={"name": "Account"})
check(r.ok and r.json()["lists"] == 1 and fld(A, F1)["name"] == "Kunde", f"(c) the change skips the left-over link {r.text[:200]}")
kt.fresh(keep=True)
A, Bo, F = sess("alice"), sess("bob"), sess("frida")
check(link_of(F1) is None and link_of(F2) == OF, "(c) the next start lets go of the left-over link only")

# ================================================================== freelancer-matrix: orgschema
FF = F.post(B + "/api/org-fields", json={"name": "Venue", "type": "text"}).json()["id"]
PF = mklist(F, "Gigs")
FPF = F.put(B + f"/api/lists/{PF}/org-fields/{FF}", json={"on": True}).json()["field_id"]
r = F.patch(B + f"/api/org-fields/{FF}", json={"name": "Place"})
check(r.ok and r.json()["lists"] == 1 and fld(F, FPF)["name"] == "Place", f"freelancer: her own field reaches her project {r.text[:200]}")
dbw("UPDATE lists SET owner_id=? WHERE id=?", (BOB, PF))
check(link_of(FPF) is None, "freelancer: her project changing hands (any path, the trigger) lets go of the link")

sys.exit(done("p6296_orgfield_space_api"))
