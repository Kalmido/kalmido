#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1213.0 (#6166): the earlier versions of a team chat message are rows of the core's history (obj_history, kind
'tchat_msg'), sealed exactly as the message was stored. Own container. Invented names only.
 - plain: every edit keeps the version before (no merge within ten minutes), newest first, with at / replaced_at; the same
   text again makes no version; the row has the room's organisation and action 'edit'
 - readers: a member of the room (also one who only reads) yes, a stranger no (404), a member removed from the project no
   more (404); the REST API v1 the same (GET /api/v1/team/messages/{id}/versions)
 - the trash: a deleted message shows none (404), the restore brings them back; the message deleted for good takes its rows
   with it (trigger kalmido_oh_gone_tchat)
 - an end-to-end encrypted DM: the version is the ciphertext as it was, no text on the server; the other person gets it
 - a project with the lock: a plain version goes with the conversion of its channel (le2c_bulk), a version made under the lock
   is a ciphertext; an API token gets encrypted: true without it
 - a person without an organisation: a DM with another freelancer, the version seen by the other one
freelancer-matrix: team
tenant-matrix: team
usage: p21213_d_tchat_versions_test.py <datadir>"""
import base64
import json
import os
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kt  # noqa: E402
from kt import B, check, dbx  # noqa: E402
from freelancer_fixture import FEATURES, freelancer, org_join  # noqa: E402

FEAT = FEATURES + ",api"


def b64(n):
    return base64.b64encode(os.urandom(n)).decode()


def b64u(n):
    return base64.urlsafe_b64encode(os.urandom(n)).decode().rstrip("=")


def keys():
    return {"pub": {"kty": "EC", "crv": "P-256", "x": b64u(32), "y": b64u(32), "ext": True, "key_ops": []},
            "bundle_pass": {"v": 1, "kdf": "pbkdf2-sha256", "iter": 600000, "salt": b64(16), "iv": b64(12), "ct": b64(200)},
            "bundle_rec": {"v": 1, "kdf": "hkdf-sha256", "salt": b64(16), "iv": b64(12), "ct": b64(200)}}


def blob(n=48):
    return {"v": 1, "iv": b64(12), "ct": b64(n)}


def chan(gen=1, v=1):
    return {"v": v, "g": gen, "iv": b64(12), "ct": b64(64)}


def wrapped():
    return {"v": 1, "iv": b64(12), "ct": b64(48)}


def versions(s, mid):
    """-> (status, items) of GET /api/team/messages/<mid>/versions."""
    r = s.get(B + f"/api/team/messages/{mid}/versions")
    return r.status_code, (r.json().get("items") if r.ok else None)


def hist(mid):
    rows = dbx("SELECT vals_before, org_id, action FROM obj_history WHERE kind='tchat_msg' AND ref_id=? ORDER BY id", (mid,))
    return [(x[0] if isinstance(x[0], dict) else json.loads(x[0] or "{}"), x[1], x[2]) for x in rows]


def token(s):
    r = s.post(B + "/api/me/tokens", json={"name": "script 6166", "scopes": ["read", "write"]})
    check(r.status_code == 201, f"setup: an API token {r.status_code} {r.text[:160]}")
    return {"Authorization": "Bearer " + (r.json().get("token") or "")}


kt.fresh(prefix="P21213D")
r = kt.sess().post(B + "/api/auth/setup", json={"username": "alice", "display_name": "Alice", "password": "password123"})
assert r.ok, r.text
A = kt.sess("alice")
A.post(B + "/api/admin/setup", json={"org_name": "Alpha", "lang": "en", "collab_all": True, "modules": ["comments"]})
ALICE = kt.me_id(A)
A.patch(B + "/api/settings", json={"lang": "en", "features": FEAT, "tour": "done"})
ORG = A.get(B + "/api/state").json()["me"]["workspaces"][0]["id"]
for u in ("bob", "otto"):
    r = A.post(B + "/api/users", json={"orgs": [ORG], "username": u, "display_name": u.title(), "password": "password123",
                                       "email": f"{u}@example.com"})
    assert r.ok, r.text
    org_join(B, u, ORG)
r = A.post(B + "/api/users", json={"username": "erik", "display_name": "Erik", "password": "password123"})  # no organisation
assert r.ok, r.text
Bo, Ot, Er = kt.sess("bob"), kt.sess("otto"), kt.sess("erik")
for s in (Bo, Ot, Er):
    s.patch(B + "/api/settings", json={"lang": "en", "features": FEAT, "tour": "done"})
BOB, OTTO = kt.me_id(Bo), kt.me_id(Ot)

LID = A.post(B + "/api/lists", json={"name": "Dreh", "kind": "project", "org_id": ORG}).json()["id"]
for u, role in ((BOB, "edit"), (OTTO, "view")):
    check(A.put(B + f"/api/lists/{LID}/members", json={"user_id": u, "role": role}).ok, f"setup: member {u} ({role})")
room = next((x for x in A.get(B + "/api/team").json()["rooms"] if x["kind"] == "list" and x["list_id"] == LID), None)
check(room is not None, "setup: the project's channel")
RID = room["id"]
for s in (Bo, Ot):
    s.get(B + "/api/team")

# ================================================================== plain: every edit keeps the version before
r = Bo.post(B + f"/api/team/rooms/{RID}/messages", json={"body": "Drehplan Version eins"})
check(r.status_code == 201, f"bob writes {r.status_code} {r.text[:160]}")
M1, C1 = r.json()["id"], r.json()["created_at"]
check(versions(Bo, M1) == (200, []), "a message never edited has no earlier versions")
r = Bo.patch(B + f"/api/team/messages/{M1}", json={"body": "Drehplan Version zwei"})
check(r.ok and r.json()["edited_at"], f"bob edits it {r.status_code}")
r = Bo.patch(B + f"/api/team/messages/{M1}", json={"body": "Drehplan Version drei", "expect_updated_at": r.json()["edited_at"]})
check(r.ok, f"bob edits it again at once {r.status_code}")
st, items = versions(Ot, M1)
check(st == 200 and [x["body"] for x in (items or [])] == ["Drehplan Version zwei", "Drehplan Version eins"],
      f"otto (only reads, a member of the room) sees both earlier versions, newest first, not merged {st} {items}")
check(items and items[-1]["at"] == C1 and items[-1]["no"] == 1 and items[0]["no"] == 2 and items[0]["at"] == items[-1]["replaced_at"]
      and all(x["enc"] is None for x in items), f"at / replaced_at / no line up {items}")
h = hist(M1)
check(len(h) == 2 and all(o == ORG and a == "edit" for _, o, a in h) and h[0][0] == {"body": "Drehplan Version eins"},
      f"the core's history: kind tchat_msg, the room's organisation, action edit, the text before {h}")
r = Bo.patch(B + f"/api/team/messages/{M1}", json={"body": "Drehplan Version drei"})
check(r.ok and len(hist(M1)) == 2, "the same text again makes no version")
cur = next(m for m in Ot.get(B + f"/api/team/rooms/{RID}/messages").json()["messages"] if m["id"] == M1)
check(cur["body"] == "Drehplan Version drei" and cur["edited_at"], "the conversation shows the newest text, edited")

# ================================================================== readers
check(Er.get(B + f"/api/team/messages/{M1}/versions").status_code == 404, "a stranger (not in the room, no organisation) gets 404")
TB = token(Bo)
r = requests.get(B + f"/api/v1/team/messages/{M1}/versions", headers=TB)
check(r.ok and [x["body"] for x in r.json().get("data", [])] == ["Drehplan Version zwei", "Drehplan Version eins"],
      f"API v1: the versions of a message of the conversation {r.status_code} {r.text[:200]}")
TE = token(Er)
check(requests.get(B + f"/api/v1/team/messages/{M1}/versions", headers=TE).status_code == 404, "API v1: a stranger's token 404")
check(A.delete(B + f"/api/lists/{LID}/members/{OTTO}").ok, "setup: otto leaves the project")
check(versions(Ot, M1)[0] == 404, "otto, removed from the project, sees the versions no more (404)")

# ================================================================== the trash and the delete for good
check(Bo.delete(B + f"/api/team/messages/{M1}").ok, "bob deletes his message")
check(versions(A, M1)[0] == 404 and versions(Bo, M1)[0] == 404, "a message in the trash shows no versions (404)")
check(len(hist(M1)) == 2, "its history rows wait with it in the trash")
r = Bo.post(B + f"/api/team/messages/{M1}/restore")
check(r.ok and versions(A, M1)[1] and len(versions(A, M1)[1]) == 2, f"restored: the versions are back {r.status_code}")
check(Bo.delete(B + f"/api/team/messages/{M1}").ok, "deleted again")
dbx("DELETE FROM tchat_msgs WHERE id=?", (M1,))  # what the core's trash run does after the period (part_trash_purge)
check(hist(M1) == [], "deleted for good: its history rows went with it (trigger)")

# ================================================================== an end-to-end encrypted DM
assert A.put(B + "/api/e2e/keys", json=keys()).ok
assert Bo.put(B + "/api/e2e/keys", json=keys()).ok
DM = A.post(B + "/api/team/dm", json={"user_id": BOB}).json()["id"]
check(A.post(B + f"/api/team/rooms/{DM}/e2e", json={"on": True}).ok, "setup: the DM is encrypted")
mb1, mb2 = blob(64), blob(64)
r = A.post(B + f"/api/team/rooms/{DM}/messages", json={"enc": mb1, "body": ""})
check(r.status_code == 201, f"alice writes an encrypted message {r.status_code} {r.text[:160]}")
M2 = r.json()["id"]
r = A.patch(B + f"/api/team/messages/{M2}", json={"enc": mb2})
check(r.ok and r.json()["enc"] == mb2, f"alice edits it (encrypted again) {r.status_code} {r.text[:160]}")
st, items = versions(Bo, M2)
check(st == 200 and len(items or []) == 1 and items[0]["enc"] == mb1 and items[0]["body"] == "",
      f"bob gets the earlier version as its ciphertext, no text {st} {items}")
h = hist(M2)
check(len(h) == 1 and set(h[0][0]) == {"enc"} and json.loads(h[0][0]["enc"]) == mb1 and h[0][1] is None,
      f"the history keeps the ciphertext as stored (a DM: no organisation) {h}")
check(versions(Ot, M2)[0] == 404, "otto is not in the DM: 404")

# ================================================================== a project with the lock
L2 = A.post(B + "/api/lists", json={"name": "Garten"}).json()["id"]
check(A.put(B + f"/api/lists/{L2}/members", json={"user_id": BOB, "role": "edit"}).ok, "setup: bob in the private project")
R2 = next(x["id"] for x in A.get(B + "/api/team").json()["rooms"] if x["kind"] == "list" and x["list_id"] == L2)
M3 = A.post(B + f"/api/team/rooms/{R2}/messages", json={"body": "Vor dem Schloss"}).json()["id"]
check(A.patch(B + f"/api/team/messages/{M3}", json={"body": "Vor dem Schloss, geaendert"}).ok, "setup: edited while open")
check([x["body"] for x in versions(Bo, M3)[1] or []] == ["Vor dem Schloss"], "an open project: the plain version")
# review job/4658 finding 1: a message the conversion does not touch (text emptied beside a file: body '') kept a plain version
M4 = A.post(B + f"/api/team/rooms/{R2}/messages", json={"body": "Geheim offen"}).json()["id"]
check(A.patch(B + f"/api/team/messages/{M4}", json={"body": "Geheim offen 2"}).ok, "setup: a second message edited while open")
dbx("UPDATE tchat_msgs SET body='' WHERE id=?", (M4,))  # what an edit to an empty text beside a file leaves
check(len(hist(M4)) == 1, "setup: its plain version is kept while open")
r = A.post(B + f"/api/lists/{L2}/e2e/start", json={"keys": [{"user_id": ALICE, "wrapped": wrapped()}, {"user_id": BOB, "wrapped": wrapped()}]})
check(r.ok, f"setup: the lock goes on {r.status_code} {r.text[:200]}")
r = A.post(B + f"/api/lists/{L2}/e2e/bulk", json={"msgs": [{"id": M3, "enc": chan(1)}]})
check(r.ok, f"setup: the channel message converted {r.status_code} {r.text[:200]}")
check(hist(M3) == [] and versions(Bo, M3) == (200, []), "the conversion took the plain version away (no plain copy under the lock)")
r = A.post(B + f"/api/lists/{L2}/e2e/finish")
check(r.ok, f"setup: the lock is on {r.status_code} {r.text[:200]}")
check(hist(M4) == [], "the end of the conversion takes every version of the channel, also of a message it did not convert")
c1 = chan(1)
r = A.patch(B + f"/api/team/messages/{M3}", json={"enc": c1})
check(r.ok, f"alice edits under the lock {r.status_code} {r.text[:200]}")
st, items = versions(Bo, M3)
old = dbx("SELECT vals_before FROM obj_history WHERE kind='tchat_msg' AND ref_id=?", (M3,))
check(st == 200 and len(items or []) == 1 and items[0]["enc"] and items[0]["enc"]["g"] == 1 and items[0]["body"] == "",
      f"under the lock the version is the ciphertext of before {st} {items}")
check(old and "Vor dem Schloss" not in json.dumps(old[0][0]), "no plain text in the history of the locked project")
r = requests.get(B + f"/api/v1/team/messages/{M3}/versions", headers=TB)
d = r.json().get("data", []) if r.ok else []
check(r.ok and len(d) == 1 and d[0]["enc"] is None and d[0]["body"] == "" and d[0].get("encrypted") is True,
      f"an API token gets encrypted: true, no ciphertext {r.status_code} {r.text[:200]}")
# review job/4658 finding 2: a plain leftover under the lock, edited, leaves no plain version behind
M5 = M4  # the message the conversion left alone, now with a plain text again: a leftover
dbx("UPDATE tchat_msgs SET enc=NULL, body='Rest im Klartext' WHERE id=?", (M5,))
r = A.patch(B + f"/api/team/messages/{M5}", json={"enc": chan(1)})
check(r.ok, f"alice edits the leftover under the lock {r.status_code} {r.text[:200]}")
check(hist(M5) == [] and versions(Bo, M5) == (200, []), "no plain version of a leftover under the lock")

# ================================================================== #6232: the versions follow a project that changes its organisation
L2 = A.post(B + "/api/lists", json={"name": "Umzug", "kind": "project", "org_id": ORG}).json()["id"]
R2 = next(x for x in A.get(B + "/api/team").json()["rooms"] if x["kind"] == "list" and x["list_id"] == L2)["id"]
M6 = A.post(B + f"/api/team/rooms/{R2}/messages", json={"body": "Erste Fassung"}).json()["id"]
check(A.patch(B + f"/api/team/messages/{M6}", json={"body": "Zweite Fassung"}).ok and [o for _, o, _ in hist(M6)] == [ORG],
      "setup: a version of the organisation")
r = A.patch(B + f"/api/lists/{L2}", json={"org_id": None})
check(r.ok, f"the project becomes private {r.status_code} {r.text[:200]}")
check([o for _, o, _ in hist(M6)] == [None], f"#6232: its versions follow: no organisation any more {hist(M6)}")
check(versions(A, M6) == (200, versions(A, M6)[1]) and [x["body"] for x in versions(A, M6)[1] or []] == ["Erste Fassung"],
      f"#6232: and are still read {versions(A, M6)}")
r = A.patch(B + f"/api/lists/{L2}", json={"org_id": ORG})
check(r.ok and [o for _, o, _ in hist(M6)] == [ORG], f"#6232: back into the organisation: the versions too {r.status_code} {hist(M6)}")

# ================================================================== a person without an organisation
FID, Fr = freelancer(B, A)
FIO, Fi = freelancer(B, A, "fiona")
dbx("INSERT INTO groups(name, oidc_group, created_at, created_by) VALUES(?,?,?,?)", ("Pool 6166", "", "2026-11-15T08:00:00", ALICE))
GID = dbx("SELECT id FROM groups WHERE name=?", ("Pool 6166",))[0][0]
for x in (FID, FIO):
    dbx("INSERT INTO group_members(group_id, user_id, added_at) VALUES(?,?,?)", (GID, x, "2026-11-15T08:00:00"))
r = Fr.post(B + "/api/team/dm", json={"user_id": FIO})
check(r.ok, f"freelancer: a DM with fiona {r.status_code} {r.text[:160]}")
FDM = r.json().get("id")
FM = Fr.post(B + f"/api/team/rooms/{FDM}/messages", json={"body": "Treffen um neun"}).json()["id"]
check(Fr.patch(B + f"/api/team/messages/{FM}", json={"body": "Treffen um zehn"}).ok, "freelancer: edits her message")
st, items = versions(Fi, FM)
check(st == 200 and [x["body"] for x in items or []] == ["Treffen um neun"], f"freelancer: fiona sees the earlier version {st} {items}")
check(versions(Er, FM)[0] == 404, "freelancer: a stranger does not")

sys.exit(kt.done("p21213_d_tchat_versions"))
