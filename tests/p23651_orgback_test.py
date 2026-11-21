#!/usr/bin/env python3
# kalmido-suite: fresh
"""Leaving an organisation (or being removed) after things were brought in from the private space. Decision #935 (back with
#6840, it had been turned round by 2.361.0 #2922 / 2.365.1 #3395): projects and folders of the organisation's area stay with
the organisation and go to an admin of it, only private projects stay the person's; what the person brought in stays too.
Invented names only, addresses @example.com. tenant-matrix: org
 - brought in (move-space private -> organisation): tables, files and folders, knowledge pages, polls, bookmarks and video
   reviews stay in the organisation after leaving; a brought-in project goes to the admin like one made there
 - GET leave-info: no "back" any more; the projects go to the admin (to_heir), what stays is counted per area
 - the answer of the leaving and the person's News name no "back"; removed by an admin: the same
 - a person without an organisation (freelancer-matrix: orgadmin): no preview of another organisation (404)
usage: p23651_orgback_test.py <datadir>      (P23651_NOSTART=1: a running server on KALMIDO_TEST_PORT)"""
import os
import subprocess
import sys

import requests

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
import dbx as dbxm  # noqa: E402
import kt  # noqa: E402  2.1021.0 (#5775): kt.proved
from freelancer_fixture import FEATURES, freelancer, org_join  # noqa: E402

DATA = sys.argv[1] if len(sys.argv) > 1 else os.path.join(N, ".data")
B = "http://127.0.0.1:" + os.environ.get("KALMIDO_TEST_PORT", "3048")
CT = os.environ.get("KALMIDO_TEST_CONTAINER", "kalmido-test")
H = {"X-Requested-With": "kalmido"}
from kt import FAILS, OKS, check, sess  # noqa: E402

TIMES = [{"start": "2031-03-10T10:00"}, {"start": "2031-03-11T14:30"}]
FEAT = FEATURES + ",sheets,wiki,office,clients"

if os.environ.get("P23651_NOSTART") != "1":
    env = dict(os.environ, EXTRA=os.environ.get("EXTRA", "") + " -e KALMIDO_INSTANCE_MODE=workspaces")
    r = subprocess.run(["bash", os.path.join(N, "start.sh"), DATA], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
s0 = requests.Session()
s0.headers.update(H)
assert s0.post(B + "/api/auth/setup", json={"username": "alice", "display_name": "Alice Admin", "password": "password123"}).ok
A = sess("alice")
A.post(B + "/api/admin/setup", json={"lang": "en", "collab_all": True, "time_all": True})
ids = {}
for u in ("bob", "carol", "dave", "erin"):
    r = A.post(B + "/api/users", json={"username": u, "display_name": u.title(), "password": "password123", "email": f"{u}@example.com"})
    assert r.ok, r.text
    ids[u] = r.json()["id"]
BOB, CAROL, DAVE, ERIN = (ids[u] for u in ("bob", "carol", "dave", "erin"))


def sql(q, args=(), write=False):
    c = dbxm.connect(os.path.join(DATA, "tasks.db"), timeout=10)
    try:
        cur = c.execute(q, args)
        out = cur.fetchall() if not write else None
        if write:
            c.commit()
        return out
    finally:
        c.close()


def user(u, oid):
    s = sess(u)
    r = s.patch(B + "/api/settings", json={"lang": "en", "tour": "done", "workspace": f"org:{oid}", "features": FEAT})
    assert r.ok, r.text
    return s


r = A.post(B + "/api/admin/orgs", json={"name": "Alpha", "admin_id": BOB})
assert r.status_code == 201, r.text
ORG = r.json()["id"]
SP = f"org:{ORG}"
Bo = user("bob", ORG)
for u in ("carol", "dave", "erin"):
    kt.proved()  # 2.1021.0 (#5775): an organisation admin invites by address only an account that proved it
    check(Bo.put(B + f"/api/orgs/{ORG}/members", json={"email": f"{u}@example.com"}).ok and org_join(B, u, ORG), f"setup: {u} joins")
Ca, Da, Er = user("carol", ORG), user("dave", ORG), user("erin", ORG)


def org_of(table, i):
    return sql(f"SELECT org_id FROM {table} WHERE id=?", (i,))[0][0]


def in_sheet(s, title, space="private"):
    r = s.post(B + "/api/sheets", json={"title": title, "space": space})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def sheet_in(s, sid):
    r = s.post(B + f"/api/sheets/{sid}/move-space", json={"to": SP})
    check(r.ok, f"setup: table {sid} into Alpha ({r.text[:160]})")


def upload(s, name, data, **form):
    r = s.post(B + "/api/files/upload", files={"file": (name, data)}, data=form)
    assert r.status_code in (200, 201), r.text
    return r.json()["items"][0]["id"]


def files_in(s, ids_):
    r = s.post(B + "/api/files/move-space", json={"ids": ids_, "to": SP})
    check(r.ok, f"setup: files into Alpha ({r.text[:160]})")


def page(s, path, text, space="private"):
    r = s.post(B + "/api/wiki/pages", json={"space": space, "path": path, "body": text})
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def pages_in(s, pids):
    r = s.post(B + "/api/wiki/move-space", json={"pages": pids, "space": "private", "to": SP, "dest": ""})
    check(r.ok, f"setup: pages into Alpha ({r.text[:160]})")


def poll(s, title, space=None):
    r = s.post(B + "/api/polls", json={"title": title, "duration": 60, "tz": "Europe/Berlin", "options": TIMES, **({"space": space} if space else {})})
    assert r.status_code in (200, 201), r.text
    j = r.json()
    return (j.get("poll") or j)["id"]


def mark(s, url, title, space=None):
    r = s.post(B + "/api/bookmarks", json={"url": url, "title": title, **({"space": space} if space else {})})
    assert r.status_code in (200, 201), r.text
    return r.json()["bookmark"]["id"]


def video(s, lid, title):
    r = s.post(B + "/api/videos", json={"list_id": lid, "url": "https://example.com/film.webm", "title": title})
    assert r.status_code in (200, 201), r.text
    j = r.json()
    return (j.get("review") or j)["id"]


def alist(s, name, org=None):
    r = s.post(B + "/api/lists", json={"name": name, "org_id": org})
    assert r.ok, r.text
    return r.json()["id"]


# ================================================================ carol brings things in, then leaves
OWNL = alist(Ca, "Carols own")
check(Ca.patch(B + f"/api/lists/{OWNL}", json={"org_id": ORG}).ok, "setup: carol's project into Alpha")
PRIVL = alist(Ca, "Carols private")
MADEL = alist(Ca, "Made in Alpha", ORG)

T1 = in_sheet(Ca, "Brought table")
sheet_in(Ca, T1)
T2 = in_sheet(Ca, "Made in Alpha", SP)
DOC = upload(Ca, "brief.txt", b"carols words")
FOLD = Ca.post(B + "/api/files/folders", json={"name": "Brought folder", "space": "private"}).json()["id"]
INNER = upload(Ca, "inner.txt", b"inside the folder", parent_id=FOLD)
files_in(Ca, [DOC, FOLD])
P1 = page(Ca, "Home", "see [[Second]]")
pages_in(Ca, [P1])
Q1 = poll(Ca, "Team lunch")
check(Ca.post(B + f"/api/polls/{Q1}/move-space", json={"to": SP}).ok, "setup: a poll into Alpha")
M1 = mark(Ca, "https://example.com/one", "One")
check(Ca.post(B + "/api/bookmarks/move-space", json={"ids": [M1], "to": SP}).ok, "setup: a bookmark into Alpha")
V1 = video(Ca, PRIVL, "Rough cut")
check(Ca.post(B + f"/api/videos/{V1}/move-space", json={"to": SP, "place": OWNL}).ok, "setup: a video review into Alpha")

j = Ca.get(B + f"/api/orgs/{ORG}/leave-info").json()
check(not any(k in j for k in ("back", "back_counts", "back_text", "kept")), f"#6840: leave-info names nothing that goes back ({sorted(j)})")
check((j.get("to_heir") or {}).get("lists") == 2 and j.get("heir") == "Bob", f"#6840: both projects of Alpha go to bob, the brought-in one too ({j.get('to_heir')}, {j.get('heir')})")
st = j.get("stays") or {}
check(st.get("tables") == 2 and st.get("files") == 2 and st.get("wiki_pages") == 1 and st.get("polls") == 1 and st.get("bookmarks") == 1 and st.get("videos") == 1,
      f"#6840: what was brought in counts where it stays ({st})")
check(Bo.get(B + f"/api/orgs/{ORG}/leave-info", params={"uid": CAROL}).json().get("stays") == st, "leave-info: the admin sees the same numbers")
check(Da.get(B + f"/api/orgs/{ORG}/leave-info", params={"uid": CAROL}).status_code == 403, "leave-info: another member may not look (403)")
# freelancer-matrix: orgadmin
FID, Fr = freelancer(B, A)
check(Fr.get(B + f"/api/orgs/{ORG}/leave-info").status_code == 404, "freelancer: no leave preview of somebody else's organisation (404)")

r = Ca.delete(B + f"/api/orgs/{ORG}/members/{CAROL}")
check(r.ok and r.json().get("transferred") == 2 and "back" not in r.json(), f"#6840: carol leaves, both projects go to bob, nothing goes back ({r.text[:160]})")
for t, i, what in (("lists", OWNL, "the brought-in project"), ("lists", MADEL, "the project made in Alpha"), ("sheets", T1, "the brought table"),
                   ("sheets", T2, "the table made in Alpha"), ("fs_nodes", DOC, "the brought file"), ("fs_nodes", FOLD, "the brought folder"),
                   ("fs_nodes", INNER, "the file in it"), ("wiki_pages", P1, "the brought page"), ("sched_polls", Q1, "the brought poll"),
                   ("bookmarks", M1, "the brought bookmark"), ("video_reviews", V1, "the brought review")):
    check(org_of(t, i) == ORG, f"#6840: {what} stays in Alpha")
check(sql("SELECT owner_id FROM lists WHERE id=?", (OWNL,))[0][0] == BOB, "#6840: the brought-in project is bob's now")
check(org_of("lists", PRIVL) is None and sql("SELECT owner_id FROM lists WHERE id=?", (PRIVL,))[0][0] == CAROL, "#6840: the private project stays carol's")
d = Bo.get(B + f"/api/files/nodes/{INNER}/content")
check(d.ok and d.content == b"inside the folder", "#6840: the organisation still opens the brought file")
check(not sql("SELECT 1 FROM space_moves WHERE kind='sheet' AND obj_id=? AND to_org IS NULL", (T1,)), "#6840: no move back in the table's history")
check(not any("back" in (x.get("data") or {}) for x in Ca.get(B + "/api/news").json()["items"]), "#6840: carol's News names no things back")

# ================================================================ removed by an admin: the same
T6 = in_sheet(Da, "Daves table")
sheet_in(Da, T6)
D1 = upload(Da, "dave.txt", b"daves words")
files_in(Da, [D1])
r = Bo.delete(B + f"/api/orgs/{ORG}/members/{DAVE}")
check(r.ok and "back" not in r.json(), f"bob removes dave ({r.text[:160]})")
check(org_of("sheets", T6) == ORG and org_of("fs_nodes", D1) == ORG, "#6840: dave's brought table and file stay in Alpha")
un = [x for x in Da.get(B + "/api/news").json()["items"] if x["kind"] == "unshare"]
check(un and "back" not in un[0]["data"], f"#6840: dave's News (removed by bob) names no things back ({[x['data'] for x in un]})")
d = Bo.get(B + f"/api/files/nodes/{D1}/content")
check(d.ok and d.content == b"daves words", "#6840: the organisation still opens dave's file")

print(f"{OKS[0]} ok, {len(FAILS)} failed")
sys.exit(1 if FAILS else 0)
