#!/usr/bin/env python3
# kalmido-suite: fresh
"""#6610 (audit #4818 F3, decision 16.11.2026): a role change down to guest / accounting / read-only hands what the person
owns in the organisation to the admin changing the role, the way leaving does (accounts/orgs.py org_role_down); guests and
accounting have at most the project role edit (accounts/orgroles.py cap_list_role); a guest / accounting person leaves the
office's rights groups. Invented names only.
 - GET /api/orgs/<id>/leave-info?uid=&down=1 names what goes over (1 project, 1 calendar, 1 address book) and to whom
 - bob (member) owns a project, a calendar and an address book of the organisation and is in an office group; alice makes
   him a guest: all three are alice's now, bob stays in them with edit (writes a task), his office group row is gone (logged)
 - as a guest bob manages nothing: no members (PUT /members 403), no public form, no deleting the project
 - a guest somebody gave the project role admin (carol's project) is capped to edit too (was: added members)
 - dave (member) owns a project and becomes read-only: alice owns it, dave reads it and writes nothing there
 - the preview of carol counts her one project; bob (now a guest) owns nothing any more
 - a person without an organisation still manages her own project (no cap outside organisations)
usage: p6610_role_down_test.py <datadir>"""
import sys

from freelancer_fixture import freelancer, login
from kt import B, check, dbx, done, fresh, setup

FEAT = "collab,comments,calendar,events,contacts,office,forms"
fresh(prefix="P6610")
A = setup()
A.patch(B + "/api/settings", json={"lang": "en", "tour": "done", "features": FEAT})
ALICE = A.get(B + "/api/state").json()["me"]["id"]
r = A.post(B + "/api/admin/orgs", json={"name": "Nordwind", "admin_id": ALICE})
assert r.status_code == 201, r.text
ORG = r.json()["id"]


def person(name):
    r = A.post(B + "/api/users", json={"username": name, "display_name": name.title(), "password": "password123",
                                      "email": f"{name}@example.com", "orgs": [ORG]})
    assert r.ok, r.text
    s = login(B, name)
    s.patch(B + "/api/settings", json={"lang": "en", "tour": "done", "features": FEAT, "workspace": f"org:{ORG}"})
    return r.json()["id"], s


def set_role(uid, role):
    r = A.put(B + f"/api/orgs/{ORG}/members", json={"user_id": uid, "role": role})
    check(r.ok, f"{uid} becomes {role} {r.status_code} {r.text[:200]}")


def project(s, name):
    r = s.post(B + "/api/lists", json={"name": name, "org_id": ORG})
    check(r.status_code in (200, 201), f"setup: project {name} {r.status_code} {r.text[:160]}")
    return r.json()["id"]


def owner(table, rid):
    return dbx(f"SELECT owner_id FROM {table} WHERE id=?", (rid,))[0][0]


BOB, Bo = person("bob")
CAROL, Ca = person("carol")
DAVE, Da = person("dave")
L = project(Bo, "Imagefilm Nord")
r = Bo.post(B + "/api/evcals", json={"name": "Drehplan", "org_id": ORG})
check(r.status_code in (200, 201), f"setup: bob's calendar {r.status_code} {r.text[:160]}")
K = r.json()["id"]
r = Bo.post(B + "/api/books", json={"name": "Crew", "org_id": ORG})
check(r.status_code in (200, 201), f"setup: bob's address book {r.status_code} {r.text[:160]}")
BK = r.json()["id"]
dbx("DELETE FROM office_rgroup_members WHERE org_id=? AND user_id=?", (ORG, BOB))
dbx("INSERT INTO office_rgroup_members(org_id, user_id, tpl, created_at) VALUES(?,?,'staff',now())", (ORG, BOB))

# ---- the preview names what goes over and to whom
r = A.get(B + f"/api/orgs/{ORG}/leave-info", params={"uid": BOB, "down": 1})
j = r.json() if r.ok else {}
check(r.ok and j.get("to_heir") == {"lists": 1, "calendars": 1, "books": 1} and j.get("heir"),
      f"preview: 1 project, 1 calendar, 1 address book to alice {r.status_code} {r.text[:200]}")
r = Bo.get(B + f"/api/orgs/{ORG}/leave-info", params={"uid": CAROL, "down": 1})
check(r.status_code in (403, 404), f"a member does not preview another member {r.status_code}")

# ---- bob becomes a guest: everything goes to alice, bob stays in with edit
set_role(BOB, "guest")
check(owner("lists", L) == ALICE, "the project is alice's")
m = [tuple(x) for x in dbx("SELECT role, own_role FROM list_members WHERE list_id=? AND user_id=?", (L, BOB))]
check(m == [("edit", "edit")], f"bob stays in the project with edit {m}")
check(owner("ev_cals", K) == ALICE, "the calendar is alice's")
check(owner("books", BK) == ALICE, "the address book is alice's")
check(not dbx("SELECT 1 FROM office_rgroup_members WHERE org_id=? AND user_id=?", (ORG, BOB)), "bob left the office group")
check(dbx("SELECT 1 FROM office_rights_log WHERE org_id=? AND target_user=? AND action='member_groups' AND after='[]'", (ORG, BOB)),
      "the office rights log has it")
r = Bo.post(B + "/api/tasks", json={"title": "Drehorte prüfen", "list_id": L})
check(r.status_code in (200, 201), f"bob still writes in the project {r.status_code} {r.text[:200]}")
r = Bo.get(B + "/api/evcals")
check(r.ok and K in [x.get("id") for x in (r.json() if isinstance(r.json(), list) else r.json().get("calendars", r.json().get("items", [])))],
      f"bob still sees the calendar {r.status_code} {r.text[:200]}")

# ---- as a guest bob manages nothing
r = Bo.put(B + f"/api/lists/{L}/members", json={"user_id": CAROL, "role": "admin"})
check(r.status_code == 403, f"no members added by a guest {r.status_code} {r.text[:160]}")
r = Bo.post(B + f"/api/lists/{L}/forms", json={"title": "Bewerbung", "access": "public"})
check(r.status_code == 403, f"no public form by a guest {r.status_code} {r.text[:160]}")
r = Bo.delete(B + f"/api/lists/{L}")
check(r.status_code == 403 and not dbx("SELECT deleted_at FROM lists WHERE id=?", (L,))[0][0], f"no deleting by a guest {r.status_code}")

# ---- a guest with the project role admin (given by carol) is capped to edit
L2 = project(Ca, "Werbespot Süd")
r = Ca.put(B + f"/api/lists/{L2}/members", json={"user_id": BOB, "role": "admin"})
check(r.ok, f"setup: carol makes bob a project admin {r.status_code} {r.text[:160]}")
r = Bo.put(B + f"/api/lists/{L2}/members", json={"user_id": DAVE, "role": "edit"})
check(r.status_code == 403, f"the guest's project admin role is capped: no members {r.status_code} {r.text[:160]}")
r = Bo.post(B + "/api/tasks", json={"title": "Storyboard", "list_id": L2})
check(r.status_code in (200, 201), f"... and writes as edit {r.status_code} {r.text[:160]}")

# ---- read-only: the project goes to alice, dave reads it
L3 = project(Da, "Doku West")
set_role(DAVE, "readonly")
check(owner("lists", L3) == ALICE, "dave's project is alice's")
r = Da.get(B + f"/api/lists/{L3}/overview")
check(r.ok, f"dave reads his former project {r.status_code}")
r = Da.post(B + "/api/tasks", json={"title": "Schnitt", "list_id": L3})
check(r.status_code == 403, f"read-only dave writes nothing {r.status_code} {r.text[:160]}")

# ---- the preview of another member counts only her own projects; a member without any: nothing to ask
r = A.get(B + f"/api/orgs/{ORG}/leave-info", params={"uid": CAROL, "down": 1})
check(r.ok and r.json()["to_heir"] == {"lists": 1, "calendars": 0, "books": 0}, f"carol owns her one project {r.text[:160]}")
r = A.get(B + f"/api/orgs/{ORG}/leave-info", params={"uid": BOB, "down": 1})
check(r.ok and not any(r.json()["to_heir"].values()), f"bob owns nothing any more {r.text[:160]}")

# ---- a person without an organisation keeps managing her own project
uid, F = freelancer(B, A, "frida", FEAT)
r = F.post(B + "/api/lists", json={"name": "Eigenes Projekt", "org_id": None})
check(r.status_code in (200, 201), f"frida's private project {r.status_code}")
FL = r.json()["id"]
r = F.post(B + f"/api/lists/{FL}/forms", json={"title": "Anfrage", "access": "public"})
check(r.status_code in (200, 201), f"frida makes a form in her own project (managing, no cap outside organisations) {r.status_code} {r.text[:160]}")
sys.exit(done("p6610_role_down"))
