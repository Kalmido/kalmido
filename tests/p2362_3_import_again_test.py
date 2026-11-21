#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.362.3 (#3098 #3101): an account import twice from one source creates nothing twice; an export carrying lists of an
organisation is told to its admins. Invented names only (example.com).
 - #3098 (a person without organisation, P4): the export of a project with section, task, comment, habit, contact and event
   imported twice: without the confirmation 409, with it nothing new (no empty project, no second contact / event / habit),
   the preview names the earlier import; a NEWER export of the same account counts as the same source and brings only the
   new task, into the project of the first import; a row deleted since comes back; into an organisation the same file is a
   wanted copy (another target); a project that went to somebody else gets nothing more, one in the trash is not there;
   after the undo the file counts as new
 - 2.452.0 (#3810): the account import stays remembered after more than 20 other imports, through both places that tidy up
 - #3101: bob exports his project of the organisation: its admin gets ONE News (the count, no name), the log has the row, a
   second export of the day tells nobody again; bob's private project does not count
Starts its OWN container (start.sh). usage: p2362_3_import_again_test.py <datadir>"""
# freelancer-matrix: own
# tenant-matrix: own
import os
import subprocess
import sys
import time

import requests

import dbx as dbxm
from freelancer_fixture import FEATURES, freelancer
from kt import FAILS, OKS, check, sess, su_get

N = os.path.dirname(os.path.abspath(__file__))
DATA = sys.argv[1]
B = "http://127.0.0.1:" + os.environ.get("KALMIDO_TEST_PORT", "3048")
H = {"X-Requested-With": "kalmido"}


def ok(r, what, codes=(200, 201, 202, 204)):
    check(r.status_code in codes, f"{what}: {r.status_code} {r.text[:200]}")
    try:
        return r.json()
    except ValueError:
        return {}


def one(sql, args=()):
    r = dbxm.connect(DATA).execute(sql, args).fetchall()
    return r[0][0] if r else None


def export(s):
    ok(s.post(B + "/api/account/export"), "the export starts")
    st = ""
    for _ in range(240 * 4):
        st = s.get(B + "/api/account/export").json().get("state")
        if st != "running":
            break
        time.sleep(0.25)
    check(st == "done", f"the export is done: {st}")
    return su_get(s, B + "/api/account/export/file").content


def upload(s, data):
    r = s.post(B + "/api/account/import", json={"size": len(data), "name": "probe.kalmido-export"})
    assert r.ok, r.text
    iid, off = r.json()["id"], 0
    while off < len(data):
        part = data[off:off + (1 << 20)]
        assert s.put(B + f"/api/account/import/{iid}?offset={off}", data=part, headers={"Content-Type": "application/octet-stream"}).ok
        off += len(part)
    return iid, wait(s, iid)


def wait(s, iid):
    j = {}
    for _ in range(240 * 4):
        j = s.get(B + f"/api/account/import/{iid}").json()
        if j.get("state") not in ("checking", "running", "upload"):
            return j
        time.sleep(0.25)
    return j


def run(s, iid, target="private", again=True):
    r = s.post(B + f"/api/account/import/{iid}/run", json={"target": target, "people": {}, **({"again": True} if again else {})})
    check(r.status_code == 202, f"run starts {r.status_code} {r.text[:200]}")
    return wait(s, iid)


def counts(uid, name="Umzug Probe"):
    return {"lists": one("SELECT COUNT(*) FROM lists WHERE owner_id=? AND name=?", (uid, name)),
            "tasks": one("SELECT COUNT(*) FROM tasks WHERE created_by=? AND title='Erste Aufgabe'", (uid,)),
            # 2.972.0 (#5272): the task comments are rows of the core's obj_comments (kind 'task', ref_id = the task)
            "comments": one("SELECT COUNT(*) FROM obj_comments WHERE body='Eine Notiz' AND user_id=?", (uid,)),
            "sections": one("SELECT COUNT(*) FROM sections s JOIN lists l ON l.id=s.list_id WHERE l.owner_id=? AND s.name='Abschnitt'", (uid,)),
            "habits": one("SELECT COUNT(*) FROM habits WHERE user_id=? AND name='Laufen'", (uid,)),
            "contacts": one("SELECT COUNT(*) FROM contacts c JOIN books b ON b.id=c.book_id WHERE b.owner_id=? AND c.fn='Kim Kontakt'", (uid,)),
            "books": one("SELECT COUNT(*) FROM books WHERE owner_id=? AND name='Meine Kontakte'", (uid,)),
            "events": one("SELECT COUNT(*) FROM events e JOIN ev_cals k ON k.id=e.cal_id WHERE k.owner_id=? AND e.title='Termin Probe'", (uid,)),
            "cals": one("SELECT COUNT(*) FROM ev_cals WHERE owner_id=? AND name='Mein Kalender'", (uid,))}


if not os.environ.get("P23623_NOSTART"):
    r = subprocess.run(["bash", os.path.join(N, "start.sh"), DATA], env=dict(os.environ, EXTRA="-e KALMIDO_INSTANCE_MODE=workspaces"),
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    s0 = requests.Session()
    s0.headers.update(H)
    assert s0.post(B + "/api/auth/setup", json={"username": "alice", "display_name": "Alice Admin", "password": "password123"}).ok
A = sess("alice")
A.post(B + "/api/admin/setup", json={"lang": "en", "collab_all": True, "time_all": True})
ALICE = A.get(B + "/api/state").json()["me"]["id"]
A.patch(B + f"/api/users/{ALICE}", json={"email": "alice@example.com"})
A.patch(B + "/api/settings", json={"lang": "en", "features": FEATURES, "tour": "done"})
BOB = ok(A.post(B + "/api/users", json={"username": "bob", "display_name": "Bob Mitglied", "password": "password123",
                                         "email": "bob@example.com"}), "bob").get("id")
Bo = sess("bob")
Bo.patch(B + "/api/settings", json={"lang": "en", "features": FEATURES, "tour": "done"})
ORG = A.post(B + "/api/admin/orgs", json={"name": "Alpha Team", "admin_id": ALICE}).json()["id"]
assert A.put(B + f"/api/orgs/{ORG}/members", json={"email": "bob@example.com", "role": "member"}).ok

# ---------------------------------------------------------------- #3098: a person without organisation
FID, F = freelancer(B, A)
LID = ok(F.post(B + "/api/lists", json={"name": "Umzug Probe"}), "a project")["id"]
SID = ok(F.post(B + "/api/sections", json={"list_id": LID, "name": "Abschnitt"}), "a section")["id"]
TID = ok(F.post(B + "/api/tasks", json={"title": "Erste Aufgabe", "list_id": LID, "section_id": SID}), "a task")["id"]
ok(F.post(B + f"/api/tasks/{TID}/comments", json={"body": "Eine Notiz"}), "a comment")
ok(F.post(B + "/api/habits", json={"name": "Laufen", "goal": 1}), "a habit")
BK = ok(F.post(B + "/api/books", json={"name": "Meine Kontakte"}), "an address book")["id"]
ok(F.post(B + "/api/contacts", json={"book_id": BK, "fn": "Kim Kontakt"}), "a contact")
CAL = ok(F.post(B + "/api/evcals", json={"name": "Mein Kalender"}), "a calendar")["id"]
ok(F.post(B + "/api/events", json={"cal_id": CAL, "title": "Termin Probe", "start": "2026-11-02T10:00", "end": "2026-11-02T11:00"}), "an event")
# 2.1235.0 (#6240): a task of the inbox - the inbox of a file always goes into my private inbox, whatever the target
INB = ok(F.post(B + "/api/tasks", json={"title": "Eingang Probe"}), "an inbox task")["id"]
ok(F.post(B + f"/api/tasks/{INB}/decisions", json={"text": "Probe Entscheidung"}), "(#6358, reader F6) a decision of the inbox task")
# (#6358): a Home & life project (stays private whatever the target) with a task, and a private knowledge page (umz_private)
LIFE = ok(F.post(B + "/api/lists", json={"name": "Vertrag Probe"}), "a Home & life project")["id"]
dbxm.connect(DATA).execute("UPDATE lists SET life='contracts' WHERE id=?", (LIFE,))
ok(F.post(B + "/api/tasks", json={"title": "Vertrag Aufgabe", "list_id": LIFE}), "a task of the Home & life project")
ok(F.post(B + "/api/wiki/pages", json={"space": "private", "path": "Privat Seite", "body": "Nur meins"}), "a private knowledge page")
# (#6358, reader F1 / F2): what hangs on the project and must reach its copy in another workspace
ok(F.post(B + f"/api/lists/{LID}/notepads", json={"title": "Probe Block", "body": "- fix"}), "a notepad of the project")
ok(F.put(B + f"/api/lists/{LID}/playbook", json={"text": "Probe Ablauf: erst schneiden."}), "the project's playbook")
ok(F.post(B + "/api/filters", json={"name": "Probe Ansicht", "list_id": LID, "rules": {"prios": [5]}}), "a shared view of the project")
FILE1 = export(F)
base = counts(FID)
check(all(v == 1 for v in base.values()), f"the data as it starts {base}")

iid, j = upload(F, FILE1)
check(j.get("state") == "preview" and j["preview"]["again"] is False and not j["preview"].get("earlier"), f"first upload: new {j.get('state')}")
j = run(F, iid, again=False)
check(j.get("state") == "done", f"first import done {j}")
first = counts(FID)
check(all(v == 2 for v in first.values()), f"the first import takes everything over {first}")
IMP = (j.get("result") or {}).get("import_id")

iid, j = upload(F, FILE1)
p = j["preview"]
check(p["again"] is True and (p.get("earlier") or {}).get("id") == IMP and p["earlier"].get("undo_until"),
      f"the preview names the earlier import and its undo {p.get('earlier')}")
r = F.post(B + f"/api/account/import/{iid}/run", json={"target": "private", "people": {}})
check(r.status_code == 409, f"without the confirmation no run {r.status_code}")
j = run(F, iid)
res = j.get("result") or {}
check(j.get("state") == "done" and counts(FID) == first, f"the same file again creates nothing {counts(FID)} {res}")
check(not res.get("import_id") and any("skipped" in w["text"] for w in res.get("warnings") or []), f"the result names what was skipped {res}")
check(not any("could not be imported" in w["text"] for w in res.get("warnings") or []), f"no false alarm for the tasks {res}")

# a newer export of the same account: a new export id, the same source; only the new task comes, into the imported project
NEW = ok(F.post(B + "/api/tasks", json={"title": "Neue Aufgabe", "list_id": LID}), "a new task")["id"]
FILE2 = export(F)
iid, j = upload(F, FILE2)
check(j["preview"]["again"] is True and (j["preview"].get("earlier") or {}).get("id") == IMP, "a newer export of the account: the same source")
j = run(F, iid)
now = counts(FID)
LIMP = one("SELECT MAX(id) FROM lists WHERE owner_id=? AND name='Umzug Probe'", (FID,))
check(j.get("state") == "done" and {k: v for k, v in now.items()} == first, f"a newer export doubles nothing {now}")
check(one("SELECT list_id FROM tasks WHERE created_by=? AND title='Neue Aufgabe' AND id!=?", (FID, NEW)) == LIMP,
      "the new task lands in the project of the first import")
check(one("SELECT COUNT(*) FROM tasks WHERE created_by=? AND title='Neue Aufgabe'", (FID,)) == 2, "the new task came once")

# deleted for good since: not there any more, it comes back
dbxm.connect(DATA).execute("DELETE FROM habits WHERE user_id=? AND name='Laufen' AND id=(SELECT MAX(id) FROM habits WHERE user_id=? AND name='Laufen')", (FID, FID))
iid, j = upload(F, FILE1)
j = run(F, iid)
now = counts(FID)
check(now == first, f"a row deleted since comes back, nothing else {now}")

# another target: a copy is wanted
F.post(B + "/api/orgs", json={"name": "Frida Studio"})
FORG = one("SELECT org_id FROM org_members WHERE user_id=?", (FID,))
check(FORG, "#6358 (reader F4): Frida has her own organisation (the second workspace of the import)")
if FORG:
    inbox_n = one("SELECT COUNT(*) FROM tasks WHERE created_by=? AND title='Eingang Probe' AND deleted_at IS NULL", (FID,))
    DEC = "SELECT COUNT(*) FROM task_decisions d JOIN tasks t ON t.id=d.task_id WHERE t.created_by=? AND d.text='Probe Entscheidung'"
    dec0 = one(DEC, (FID,))
    PRIV = ("SELECT (SELECT COUNT(*) FROM lists WHERE owner_id=? AND name='Vertrag Probe' AND deleted_at IS NULL), "
            "(SELECT COUNT(*) FROM tasks WHERE created_by=? AND title='Vertrag Aufgabe' AND deleted_at IS NULL), "
            "(SELECT COUNT(*) FROM wiki_pages WHERE owner_id=? AND org_id IS NULL AND path LIKE '%Privat Seite%' AND deleted_at IS NULL)")
    priv0 = tuple(dbxm.connect(DATA).execute(PRIV, (FID, FID, FID)).fetchall()[0])
    check(priv0[0] >= 2 and priv0[1] >= 2 and priv0[2] >= 1, f"#6358: the private import brought the Home & life project and its task {priv0}")
    iid, j = upload(F, FILE1)
    j = run(F, iid, target=FORG)
    check(j.get("state") == "done" and counts(FID)["lists"] == first["lists"] + 1, f"into another workspace it is a copy {counts(FID)}")
    check(one("SELECT COUNT(*) FROM lists WHERE org_id=? AND name='Umzug Probe'", (FORG,)) == 1, "the copy is in the organisation")
    # 2.1235.0 (#6240): the copy has its tasks (tt_id carries the workspace), the private inbox task is not taken twice
    check(one("SELECT COUNT(*) FROM tasks t JOIN lists l ON l.id=t.list_id WHERE l.org_id=? AND t.title='Erste Aufgabe' AND t.deleted_at IS NULL",
              (FORG,)) == 1, "#6240: the task came along into the copy")
    check(one("SELECT COUNT(*) FROM tasks WHERE created_by=? AND title='Eingang Probe' AND deleted_at IS NULL", (FID,)) == inbox_n,
          f"#6240: the inbox task is not doubled by the copy {inbox_n}")
    # (#6358, audit #4773 F10): what lands private whatever the target is matched against the private import before: habits,
    # address books with contacts, calendars with events, the Home & life project with its task, the knowledge page - nothing twice
    after, res = counts(FID), j.get("result") or {}
    check({k: after[k] for k in after if k not in ("lists", "tasks", "comments", "sections")} == {k: first[k] for k in first if k not in ("lists", "tasks", "comments", "sections")},
          f"#6358: the private parts are not doubled by the copy {after} {first}")
    priv1 = tuple(dbxm.connect(DATA).execute(PRIV, (FID, FID, FID)).fetchall()[0])
    check(priv1 == priv0 and not one("SELECT COUNT(*) FROM lists WHERE org_id=? AND name='Vertrag Probe'", (FORG,)),
          f"#6358: the Home & life project (no empty second one), its task and the private knowledge page are not doubled {priv0} -> {priv1}")
    check(not any("could not be imported" in w["text"] for w in res.get("warnings") or []), f"#6358: no warning for the private tasks {res.get('warnings')}")
    check(one(DEC, (FID,)) == dec0, f"#6358 F6: the decision of the inbox task is not doubled {dec0} -> {one(DEC, (FID,))}")
    check((res.get("stats") or res.get("counts") or {}).get("skipped", 0) > 0 or any("skipped" in w["text"] for w in res.get("warnings") or []),
          f"#6358: they count as skipped {res}")
    # (#6358, reader F1 / F2): the project's copy in the organisation keeps its notepad, playbook and shared view
    COPY = one("SELECT id FROM lists WHERE org_id=? AND name='Umzug Probe'", (FORG,))
    check(one("SELECT COUNT(*) FROM list_notepads WHERE list_id=? AND title='Probe Block'", (COPY,)) == 1, "#6358 F1: the copy has its notepad")
    check(one("SELECT COUNT(*) FROM playbooks p JOIN obj_versions v ON v.kind='playbook' AND v.ref_id=p.id WHERE p.list_id=?", (COPY,)) >= 1, "#6358 F1: the copy has its playbook")
    check(one("SELECT COUNT(*) FROM filters WHERE list_id=? AND name='Probe Ansicht'", (COPY,)) == 1, "#6358 F2: the copy has its shared view")
    dbxm.connect(DATA).execute("DELETE FROM lists WHERE org_id=?", (FORG,))

# (#6358, reader F4): the other way round - first into the own organisation, then into the private space: nothing private twice;
# (reader F3) a run that only skipped the private parts does not mark them: after the undo of the import that brought them, a
# private import brings them again
GID, G = freelancer(B, A, "greta")
ok(G.post(B + "/api/habits", json={"name": "Lesen", "goal": 1}), "greta: a habit")
GBK = ok(G.post(B + "/api/books", json={"name": "Gretas Kontakte"}), "greta: an address book")["id"]
ok(G.post(B + "/api/contacts", json={"book_id": GBK, "fn": "Gil Kontakt"}), "greta: a contact")
ok(G.post(B + "/api/filters", json={"name": "Greta Filter", "rules": {"prios": [5]}}), "greta: a private filter")
fd = {"file": ("greta-notiz.txt", b"Gretas Datei"), "space": (None, "private")}
check(G.post(B + "/api/files/upload", files=fd).ok, "greta: a private file")
GFILE = export(G)
G.post(B + "/api/orgs", json={"name": "Greta Studio"})
GORG = one("SELECT org_id FROM org_members WHERE user_id=?", (GID,))
check(GORG, "#6358 F4: Greta has her own organisation")
GQ = {"habits": "SELECT COUNT(*) FROM habits WHERE user_id=? AND name='Lesen'",
      "contacts": "SELECT COUNT(*) FROM contacts c JOIN books b ON b.id=c.book_id WHERE b.owner_id=? AND c.fn='Gil Kontakt'",
      "filters": "SELECT COUNT(*) FROM filters WHERE user_id=? AND name='Greta Filter'",
      "files": "SELECT COUNT(*) FROM fs_nodes WHERE owner_id=? AND org_id IS NULL AND name LIKE 'greta-notiz%' AND deleted_at IS NULL"}


def gc():
    return {k: one(q, (GID,)) for k, q in GQ.items()}


g0 = gc()
if GORG:
    iid, j = upload(G, GFILE)
    j = run(G, iid, target=GORG, again=False)
    check(j.get("state") == "done", f"greta: into her organisation first {j.get('state')}")
    GIMP = (j.get("result") or {}).get("import_id")
    g1 = gc()
    check(all(g1[k] == g0[k] + 1 for k in g1), f"#6358: the private parts came once, into her private space {g0} -> {g1}")
    iid, j = upload(G, GFILE)
    j = run(G, iid, again=False)  # another target: no confirmation asked
    res = j.get("result") or {}
    check(j.get("state") == "done" and gc() == g1, f"#6358 F4: then into the private space: nothing private twice {g1} -> {gc()}")
    check(not any("could not be imported" in w["text"] for w in res.get("warnings") or []), f"#6358 F4: no false alarm {res.get('warnings')}")
    ok(G.post(B + f"/api/imports/{GIMP}/undo"), "greta: the import into the organisation is undone", codes=(200, 201, 202, 204))
    g2 = gc()
    check(g2["files"] == g0["files"], f"the undo took its private file away {g2}")
    iid, j = upload(G, GFILE)
    j = run(G, iid)
    check(j.get("state") == "done" and gc()["files"] == g0["files"] + 1,
          f"#6358 F3: the skipping run did not mark the private parts: after the undo they come again {gc()}")

# review: the imported project went to somebody else: nothing more is written into it; a project in the trash is not there
ok(F.post(B + f"/api/tasks/{TID}/comments", json={"body": "Spaeter"}), "a later comment")
FILE3 = export(F)
db = dbxm.connect(DATA)
db.execute("UPDATE lists SET owner_id=? WHERE id=?", (ALICE, LIMP))
iid, j = upload(F, FILE3)
j = run(F, iid)
check(j.get("state") == "done", f"import with the project handed over {j.get('state')}")
# 2.972.0 (#5272): the task comments are rows of the core's obj_comments (kind 'task', ref_id = the task)
check(not one("""SELECT COUNT(*) FROM obj_comments c JOIN tasks t ON t.id=c.ref_id AND c.kind='task' WHERE t.list_id=? AND c.body='Spaeter'""", (LIMP,)),
      "nothing lands in the project that went to somebody else")
db.execute("UPDATE lists SET owner_id=? WHERE id=?", (FID, LIMP))
NEWEST = one("SELECT MAX(id) FROM lists WHERE owner_id=? AND name='Umzug Probe'", (FID,))
check(NEWEST != LIMP, "that project was taken over anew instead")
db.execute("UPDATE lists SET deleted_at=created_at WHERE owner_id=? AND name='Umzug Probe' AND id>?", (FID, LID))
iid, j = upload(F, FILE3)
j = run(F, iid)
check(one("SELECT COUNT(*) FROM lists WHERE owner_id=? AND name='Umzug Probe' AND id>? AND deleted_at IS NULL", (FID, LID)) >= 1,
      "a project in the trash is not there: it comes back")

# 2.452.0 (#3810): 20 other imports later the source is still known; both places that tidy up (the list import, the account import)
def others(n=25):
    db = dbxm.connect(DATA)
    db.execute("INSERT INTO imports(user_id,source,file_name,created,report,created_at,undone_at) VALUES(?,?,?,?,?,?,?)",
               (FID, "Kalmido", "undone.kalmido-export", "{}", "{}", "2026-01-01T00:00:00", "2026-01-02T00:00:00"))
    for i in range(n):
        db.execute("INSERT INTO imports(user_id,source,file_name,created,report,created_at) VALUES(?,?,?,?,?,?)",
                   (FID, "todoist", f"other{i}.csv", "{}", "{}", "2026-01-01T00:00:00"))


kept = one("SELECT COUNT(*) FROM imports WHERE user_id=? AND source='Kalmido' AND undone_at IS NULL", (FID,))
check(kept >= 1, f"account imports on record {kept}")
others()
ok(F.post(B + "/api/import/todoist", files={"file": ("Andere Liste.csv", b"TYPE,CONTENT\ntask,Eine Zeile\n")}), "a list import")
check(one("SELECT COUNT(*) FROM imports WHERE user_id=? AND source='Kalmido' AND undone_at IS NULL", (FID,)) == kept, "the list import tidies up, the account imports stay")
check(one("SELECT COUNT(*) FROM imports WHERE user_id=? AND undone_at IS NOT NULL", (FID,)) == 0, "an undone account import goes like any other")
check(one("SELECT COUNT(*) FROM imports WHERE user_id=? AND source<>'Kalmido'", (FID,)) <= 20, "the others stay limited")
iid, j = upload(F, FILE1)
check(j["preview"]["again"] is True, "the file still counts as imported before")
F.delete(B + f"/api/account/import/{iid}")
others()
dbxm.connect(DATA).execute("UPDATE lists SET deleted_at=created_at WHERE owner_id=? AND name='Umzug Probe' AND id>? AND deleted_at IS NULL", (FID, LID))
iid, j = upload(F, FILE3)
j = run(F, iid)
check(one("SELECT COUNT(*) FROM imports WHERE user_id=? AND source='Kalmido' AND undone_at IS NULL", (FID,)) == kept + 1, "the account import tidies up, the earlier ones stay")
iid, j = upload(F, FILE1)
check(j["preview"]["again"] is True, "still known after that")
F.delete(B + f"/api/account/import/{iid}")

# after the undo the file counts as new
for x in dbxm.connect(DATA).execute("SELECT id FROM imports WHERE user_id=? AND source='Kalmido' AND undone_at IS NULL", (FID,)).fetchall():  # 2.452.0 (#3810): also those beyond the shown list
    ok(F.post(B + f"/api/imports/{x[0]}/undo"), "undo", codes=(200, 201, 202, 204, 409))
iid, j = upload(F, FILE1)
check(j["preview"]["again"] is False, "after the undo the file is new again")
F.delete(B + f"/api/account/import/{iid}")

# ---------------------------------------------------------------- #3101: the account export of a member
Bo.patch(B + "/api/settings", json={"workspace": f"org:{ORG}"})
LO = ok(Bo.post(B + "/api/lists", json={"name": "Geheimes Teamprojekt", "org_id": ORG}), "bob's project of the organisation")["id"]
ok(Bo.post(B + "/api/lists", json={"name": "Bob Privat", "org_id": None}), "bob's private project")


def told():
    return dbxm.connect(DATA).execute("SELECT data FROM notifications WHERE user_id=? AND kind='orglist' AND actor_id=? AND data::text LIKE '%\"export\"%'",
                                      (ALICE, BOB)).fetchall()


export(Bo)
rows = told()
check(len(rows) == 1 and '"count": 1' in str(rows[0][0]) and "Alpha Team" in str(rows[0][0]), f"the admin is told once {rows}")
check("Geheimes" not in str(rows), "the News carries the count, not the name of a project")
check(one("SELECT COUNT(*) FROM org_list_log WHERE org_id=? AND list_id=? AND action='export' AND by_id=?", (ORG, LO, BOB)) == 1, "the list history has it")
ok(su_get(Bo, B + "/api/export.json"), "export.json")
check(len(told()) == 1, f"a second export of the day tells nobody again {told()}")

if FAILS:
    ct = os.environ.get("KALMIDO_TEST_CONTAINER", "kalmido-test")
    print(subprocess.run(["docker", "logs", "--tail", "60", ct], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True).stdout[-6000:], flush=True)
print(f"p2362_3_import_again: {OKS[0]} ok, {len(FAILS)} failed")
sys.exit(1 if FAILS else 0)
