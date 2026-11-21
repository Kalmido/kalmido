#!/usr/bin/env python3
# kalmido-suite:
"""#6610 (audit #4818 F3, decision 16.11.2026, architecture answer 20.11.2026): what an organisation role may hold has one
place (accounts/orgroles.py ROLE_CAPS, org_cap). A role down to guest / accounting / read-only hands what the person owns in
the organisation to the admin changing the role, on the same way as leaving (core/objhooks.person_revoked with heir); the
caps hold at every request, also for an owner demoted before the rule. Invented names only.
 - GET /api/orgs/<id>/leave-info?uid=&down=1 names what goes over (1 project, 1 calendar, 1 address book) and to whom
 - bob (member) owns a project, a calendar and an address book of the organisation and is in an office group; alice makes
   him a guest: all three are alice's now, bob stays in them with edit (writes a task), his office group row is gone (logged)
 - as a guest bob manages nothing: no members (PUT /members 403), no public form, no deleting the project
 - a guest somebody gave the project role admin (carol's project) is capped to edit too (was: added members)
 - dave (member) owns a project and becomes read-only: alice owns it, dave reads it and writes nothing there
 - demoted before the release (the row set to guest in the database, no role change): erna still owns a project, a
   calendar and an address book, and manages none of them (members 403) -- the cap at the request
 - the nightly boundary check counts such an owner; "Clean up" hands it to the organisation's first admin
 - counting: the cap reads the role from the request's memo -- a guest's start-up read grows with more projects by no more
   statements than a person's without an organisation
 - a person without an organisation still manages her own project (no cap outside organisations)
usage: p6610_role_down_test.py <datadir>"""
import re
import sys

from freelancer_fixture import freelancer, login
from kt import B, check, dbx, done, fresh, setup

FEAT = "collab,comments,calendar,events,contacts,office,forms"
fresh(prefix="P6610", env={"KALMIDO_TEST_TIMING_ALL": "1"})  # Server-Timing for every account (the counting)
A = setup()
A.patch(B + "/api/settings", json={"lang": "en", "tour": "done", "features": FEAT})
ALICE = A.get(B + "/api/state").json()["me"]["id"]
r = A.post(B + "/api/admin/orgs", json={"name": "Nordwind", "admin_id": ALICE})
assert r.status_code == 201, r.text
ORG = r.json()["id"]
TIMING = re.compile(r'db;dur=[\d.]+;desc="n=(\d+)"')


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


def project(s, name, org=ORG):
    r = s.post(B + "/api/lists", json={"name": name, "org_id": org})
    check(r.status_code in (200, 201), f"setup: project {name} {r.status_code} {r.text[:160]}")
    return r.json()["id"]


def calendar(s, name):
    r = s.post(B + "/api/evcals", json={"name": name, "org_id": ORG})
    check(r.status_code in (200, 201), f"setup: calendar {name} {r.status_code} {r.text[:160]}")
    return r.json()["id"]


def book(s, name):
    r = s.post(B + "/api/books", json={"name": name, "org_id": ORG})
    check(r.status_code in (200, 201), f"setup: address book {name} {r.status_code} {r.text[:160]}")
    return r.json()["id"]


def owner(table, rid):
    return dbx(f"SELECT owner_id FROM {table} WHERE id=?", (rid,))[0][0]


def nstmt(s):
    m = TIMING.search(s.get(B + "/api/state").headers.get("Server-Timing", ""))
    return int(m.group(1)) if m else -1


BOB, Bo = person("bob")
CAROL, Ca = person("carol")
DAVE, Da = person("dave")
ERNA, Er = person("erna")
L = project(Bo, "Imagefilm Nord")
K = calendar(Bo, "Drehplan")
BK = book(Bo, "Crew")
dbx("DELETE FROM office_rgroup_members WHERE org_id=? AND user_id=?", (ORG, BOB))
dbx("INSERT INTO office_rgroup_members(org_id, user_id, tpl, created_at) VALUES(?,?,'staff',now())", (ORG, BOB))

# ---- the preview names what goes over and to whom
r = A.get(B + f"/api/orgs/{ORG}/leave-info", params={"uid": BOB, "down": 1})
j = r.json() if r.ok else {}
check(r.ok and j.get("to_heir") == {"lists": 1, "calendars": 1, "books": 1, "objects": 0} and j.get("heir"),
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
sh = dbx("SELECT s.role FROM fs_shares s JOIN fs_nodes n ON n.id=s.node_id WHERE n.kind='ref' AND n.ref_kind='evcal' AND n.ref_id=? "
         "AND s.user_id=?", (K, BOB))
check([x[0] for x in sh] == ["edit"], f"bob keeps a share of the calendar with edit {sh}")
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
st = {x["id"]: x for x in Bo.get(B + "/api/state").json()["lists"]}
check(st.get(L2, {}).get("role") == "edit", f"the start-up read says edit to the client too {st.get(L2, {}).get('role')}")

# ---- read-only: the project goes to alice, dave reads it
L3 = project(Da, "Doku West")
set_role(DAVE, "readonly")
check(owner("lists", L3) == ALICE, "dave's project is alice's")
m = [tuple(x) for x in dbx("SELECT role, own_role FROM list_members WHERE list_id=? AND user_id=?", (L3, DAVE))]
check(m == [("edit", "edit")], f"dave stays in his former project, stored as edit - the cap to reading is org_cap's (F3) {m}")
r = Da.get(B + f"/api/lists/{L3}/overview")
check(r.ok, f"dave reads his former project {r.status_code}")
r = Da.post(B + "/api/tasks", json={"title": "Schnitt", "list_id": L3})
check(r.status_code == 403, f"read-only dave writes nothing {r.status_code} {r.text[:160]}")
# Festlegung 21.11.2026 (Leser #6120 F3): back up to member, dave writes in his former project again
set_role(DAVE, "member")
r = Da.post(B + "/api/tasks", json={"title": "Schnitt", "list_id": L3})
check(r.status_code in (200, 201), f"(F3) dave, a member again, writes in his former project {r.status_code} {r.text[:160]}")
# Leser #6120 F2: the preview of one's own role down (an admin stepping down) names what goes over, too
L4 = project(Da, "Doku Ost")
r = Da.get(B + f"/api/orgs/{ORG}/leave-info", params={"uid": DAVE, "down": 1})
check(r.ok and (r.json().get("to_heir") or {}).get("lists") == 1 and r.json().get("heir"),
      f"(F2) the preview of the own role down: 1 project and who takes it {r.status_code} {r.text[:200]}")

# ---- reader job/6122 F8: the preview names the core's objects too (a saved document view goes to the admin as well);
# accounting (not only guest): the project goes over, and its former owner makes no acceptance link and adds no members
FR, Fr = person("frieda")
LF = project(Fr, "Abnahme Nord")
r = Fr.post(B + "/api/obj/docview", json={"title": "Belege Nord", "query": "q=Nord", "ws": f"org:{ORG}"})
check(r.ok, f"setup: frieda saves a document view {r.status_code} {r.text[:200]}")
# only an admin shares a view with the organisation (#4828): frieda as a former admin who made it -- the row set directly
dbx("UPDATE doc_views SET org_id=? WHERE id=?", (ORG, r.json()["id"]))
r = A.get(B + f"/api/orgs/{ORG}/leave-info", params={"uid": FR, "down": 1})
check(r.ok and r.json()["to_heir"].get("lists") == 1 and r.json()["to_heir"].get("objects") == 1,
      f"(F8) the preview names the project and the saved view {r.text[:200]}")
set_role(FR, "accounting")
check(owner("lists", LF) == ALICE, "(F8) accounting: frieda's project is alice's")
r = Fr.post(B + f"/api/lists/{LF}/signoffs", json={})
check(r.status_code in (403, 404), f"(F8) accounting: no acceptance link on her former project {r.status_code} {r.text[:160]}")
r = Fr.put(B + f"/api/lists/{LF}/members", json={"user_id": CAROL, "role": "edit"})
check(r.status_code == 403, f"(F8) accounting: no members on her former project {r.status_code} {r.text[:160]}")
r = Fr.post(B + "/api/tasks", json={"title": "Pruefen", "list_id": LF})
check(r.status_code in (200, 201), f"(F8) accounting: frieda still edits there {r.status_code} {r.text[:160]}")

# ---- decision 21.11.2026 (reader job/6130 F10): by address a member's role never goes down -- the add field sends no role
# (member by default); typed in for an admin who owns a project, role and project stay, the answer is the one of any address
GR, Gr = person("greta")
set_role(GR, "admin")
LG = project(Gr, "Greta Nord")
r = A.put(B + f"/api/orgs/{ORG}/members", json={"email": "greta@example.com"})
check(r.ok and r.json().get("by_email"), f"(F10) greta's address without a role: the answer of any address {r.status_code} {r.text[:160]}")
check(dbx("SELECT role FROM org_members WHERE org_id=? AND user_id=?", (ORG, GR))[0][0] == "admin" and owner("lists", LG) == GR,
      "(F10) greta stays admin and keeps her project")
r = A.put(B + f"/api/orgs/{ORG}/members", json={"email": "greta@example.com", "role": "guest"})
check(r.ok and dbx("SELECT role FROM org_members WHERE org_id=? AND user_id=?", (ORG, GR))[0][0] == "admin" and owner("lists", LG) == GR,
      f"(F10) not even with role guest by address {r.status_code}")
set_role(GR, "member")
check(owner("lists", LG) == GR, "(F10) down to member by the role selector (user_id): member may own, her project stays hers")

# ---- the preview of another member counts only her own projects; a member without any: nothing to ask
r = A.get(B + f"/api/orgs/{ORG}/leave-info", params={"uid": CAROL, "down": 1})
check(r.ok and r.json()["to_heir"] == {"lists": 1, "calendars": 0, "books": 0, "objects": 0}, f"carol owns her one project {r.text[:160]}")
r = A.get(B + f"/api/orgs/{ORG}/leave-info", params={"uid": BOB, "down": 1})
check(r.ok and not any(r.json()["to_heir"].values()), f"bob owns nothing any more {r.text[:160]}")

# ---- demoted before the release: the row set to guest directly (no role change way) -- the cap at the request holds
LE, KE, BE = project(Er, "Altbestand"), calendar(Er, "Altkalender"), book(Er, "Altbuch")
dbx("UPDATE org_members SET role='guest' WHERE org_id=? AND user_id=?", (ORG, ERNA))
check(owner("lists", LE) == ERNA and owner("ev_cals", KE) == ERNA and owner("books", BE) == ERNA, "legacy: erna still owns all three")
r = Er.put(B + f"/api/lists/{LE}/members", json={"user_id": CAROL, "role": "edit"})
check(r.status_code == 403, f"legacy project: no managing (members) {r.status_code} {r.text[:160]}")
r = Er.post(B + "/api/tasks", json={"title": "Weiter", "list_id": LE})
check(r.status_code in (200, 201), f"legacy project: erna still edits {r.status_code} {r.text[:160]}")
r = Er.put(B + f"/api/evcals/{KE}/members", json={"user_id": CAROL, "role": "view"})
check(r.status_code == 403, f"legacy calendar: no managing (members) {r.status_code} {r.text[:160]}")
r = Er.put(B + f"/api/books/{BE}/members", json={"user_id": CAROL, "role": "view"})
check(r.status_code == 403, f"legacy address book: no managing (members) {r.status_code} {r.text[:160]}")

# ---- the boundary check counts her; "Clean up" hands it to the organisation's first admin
r = A.post(B + "/api/admin/orgs/boundary/repair")
k = r.json().get("kinds", {}) if r.ok else {}
check(r.ok and k.get("list_owner") == 1 and k.get("cal_owner") == 1 and k.get("book_owner") == 1,
      f"clean up: the three owners whose role may not own {r.status_code} {r.text[:300]}")
check(owner("lists", LE) == ALICE and owner("ev_cals", KE) == ALICE and owner("books", BE) == ALICE, "clean up: all three are alice's")
r = Er.post(B + "/api/tasks", json={"title": "Danach", "list_id": LE})
check(r.status_code in (200, 201), f"clean up: erna stays in the project with edit {r.status_code} {r.text[:160]}")
r = A.post(B + "/api/admin/orgs/boundary/repair")
check(r.ok and not {"list_owner", "cal_owner", "book_owner"} & set(r.json().get("kinds", {})), f"clean up again: nothing left {r.text[:200]}")

# ---- counting: the cap reads the role from the request's memo (no statement per object)
uid, F = freelancer(B, A, "frida", FEAT)
for i in range(2):
    project(F, f"Eigen {i}", None)
    Lx = project(Ca, f"Gast {i}")
    check(Ca.put(B + f"/api/lists/{Lx}/members", json={"user_id": ERNA, "role": "edit"}).ok, f"setup: erna in carol's project {i}")
g2, f2 = nstmt(Er), nstmt(F)
for i in range(2, 6):
    project(F, f"Eigen {i}", None)
    Lx = project(Ca, f"Gast {i}")
    check(Ca.put(B + f"/api/lists/{Lx}/members", json={"user_id": ERNA, "role": "edit"}).ok, f"setup: erna in carol's project {i}")
g6, f6 = nstmt(Er), nstmt(F)
check(min(g2, f2, g6, f6) > 0 and g6 - g2 <= f6 - f2,
      f"counting: 4 more projects cost the guest {g6 - g2} statements, a person without an organisation {f6 - f2} ({g2}->{g6}, {f2}->{f6})")

# ---- a person without an organisation keeps managing her own project
FL = project(F, "Eigenes Projekt", None)
r = F.post(B + f"/api/lists/{FL}/forms", json={"title": "Anfrage", "access": "public"})
check(r.status_code in (200, 201), f"frida makes a form in her own project (managing, no cap outside organisations) {r.status_code} {r.text[:160]}")
sys.exit(done("p6610_role_down"))
