#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1175.0 (#6165): "Recent steps" -- the steps written over a personal API key are marked and can be hidden.
Invented names only.
 - a write over a person's own API key (Authorization: Bearer) is a step group with via 'token' and the key's name as its device
   (a device header the script sends does not win); a write of the app keeps via '' and its device
 - GET /api/undo hands via out; the user setting undo_show_api is off by default and can be switched (a flag, every device)
 - an app step and a key step never share a group, even with the same X-Kalmido-Undo-Group token
 - POST /api/undo/to/<id> {"hide_api": true} leaves the key's steps as they are and takes back the shown ones below them;
   a shown step on an object a newer hidden step changed stops the run there (stopped.state 'hidden', named in the text)
 - without hide_api (the switch on) everything goes back as before; the recording itself stays complete
freelancer-matrix: undo (a person without an organisation: her key step marked, skipped by "Undo up to here")
usage: p21175_a_api_steps_test.py <datadir>"""
import os
import sys

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
import kt  # noqa: E402
from freelancer_fixture import freelancer  # noqa: E402
from kt import B, check, dbx, done, sess  # noqa: E402

kt.fresh(prefix="P21175A")
A = kt.setup()
A.patch(B + "/api/settings", json={"tour": "done", "lang": "en"})
AL = A.get(B + "/api/state").json()["me"]["id"]
V = B + "/api/v1"
DEV = {"X-Kalmido-Device-Name": "Laptop (Test)"}


def token(s, name):
    r = s.post(B + "/api/me/tokens", json={"name": name, "scopes": ["read", "write"]})
    assert r.ok, r.text[:300]
    return {"Authorization": "Bearer " + r.json()["token"]}


def last(u):
    r = dbx("SELECT id, via, device, state FROM undo_groups WHERE user_id=? ORDER BY id DESC LIMIT 1", (u,))
    return dict(zip(("id", "via", "device", "state"), r[0])) if r else {}


def state(gid):
    r = dbx("SELECT state FROM undo_groups WHERE id=?", (gid,))
    return r[0][0] if r else None


def task(tid):
    r = dbx("SELECT title, priority, deleted_at FROM tasks WHERE id=?", (tid,))
    return dict(zip(("title", "priority", "deleted_at"), r[0])) if r else None


def mk(s, lid, title, hd=None):
    r = s.post(B + "/api/tasks", json={"list_id": lid, "title": title}, headers=hd or DEV)
    assert r.ok, r.text[:300]
    return r.json()["id"]


def scenario(s, uid, lid, key, who):
    """G1 app: t1 created; G2 app: t2 created; G3 app: t1 renamed; H key: t2's priority. -> the ids."""
    t1 = mk(s, lid, f"Alpha {who}")
    t2 = mk(s, lid, f"Beta {who}")
    g2 = last(uid)["id"]
    r = s.patch(B + f"/api/tasks/{t1}", json={"title": f"Alpha {who} 2"}, headers=DEV)
    assert r.ok, r.text[:300]
    g3 = last(uid)
    r = sess().patch(V + f"/tasks/{t2}", json={"priority": 3}, headers={**key, **DEV})
    check(r.ok, f"{who}: a write over the key {r.status_code} {r.text[:200]}")
    h = last(uid)
    return t1, t2, g2, g3, h


# ---------------------------------------------------------------- the mark
KA = token(A, "Script Bot")
L = A.post(B + "/api/lists", json={"name": "Garden", "kind": "project"}).json()["id"]
t1, t2, G2, G3, H = scenario(A, AL, L, KA, "A")
check(G3.get("via") == "" and G3.get("device") == "Laptop (Test)", f"a step of the app: no mark, its device {G3}")
check(H.get("id") != G3.get("id") and H.get("via") == "token" and H.get("device") == "Script Bot",
      f"a step over the key: via token, the key's name as the device (not the header) {H}")
items = A.get(B + "/api/undo").json()["items"]
hi = next((i for i in items if i["id"] == H["id"]), {})
gi = next((i for i in items if i["id"] == G3["id"]), {})
check(hi.get("via") == "token" and hi.get("device") == "Script Bot" and gi.get("via") == "", f"GET /api/undo hands the mark out {hi} {gi}")

# ---------------------------------------------------------------- the switch (a user setting; the list saves it with _auto: no step)
st = A.get(B + "/api/state").json()["settings"]
check(st.get("undo_show_api") == "0", f"the steps over a key are hidden by default ({st.get('undo_show_api')})")
r = A.patch(B + "/api/settings", json={"undo_show_api": "1", "_auto": 1})
check(r.ok and A.get(B + "/api/state").json()["settings"].get("undo_show_api") == "1", f"the switch is kept for the account {r.status_code}")
check(not A.patch(B + "/api/settings", json={"undo_show_api": "maybe", "_auto": 1}).ok, "only 0 / 1")
A.patch(B + "/api/settings", json={"undo_show_api": "0", "_auto": 1})

# ---------------------------------------------------------------- one bundle token: app and key stay apart
TOK = {"X-Kalmido-Undo-Group": "a1b2c3d4e5f60718"}
t9 = mk(A, L, "Gamma A")
g9 = last(AL)["id"]
A.patch(B + f"/api/tasks/{t9}", json={"title": "Gamma A 2"}, headers={**DEV, **TOK})
ga = last(AL)
r = sess().patch(V + f"/tasks/{t9}", json={"priority": 1}, headers={**KA, **TOK})
check(r.ok, f"the key's write with the bundle token {r.status_code} {r.text[:300]}")
gk = last(AL)
check(ga["id"] != gk["id"] and ga["via"] == "" and gk["via"] == "token", f"the same bundle token: two groups {ga} {gk}")
# take these three steps back with everything shown (no hide_api): the key's step goes too
r = A.post(B + f"/api/undo/to/{g9}")
j = r.json() if r.ok else {}
check(r.ok and {gk["id"], ga["id"], g9} <= set(j.get("undone", [])), f"switch on: the key's step goes back as well {r.text[:300]}")
check(task(t9) is None or task(t9)["deleted_at"] is not None, f"Gamma is gone again {task(t9)}")
# now H is the newest step still done (the undone ones above it stay undone)

# ---------------------------------------------------------------- "Undo up to here" over the shown steps only
r = A.post(B + f"/api/undo/to/{G3['id']}", json={"hide_api": True})
j = r.json() if r.ok else {}
check(r.ok and j.get("undone") == [G3["id"]] and not j.get("stopped"), f"hidden: the key's step stays, the shown one goes {r.status_code} {str(j)[:300]}")
check(task(t1)["title"] == "Alpha A" and task(t2)["priority"] == 3, f"t1 back, t2 keeps the key's priority {task(t1)} {task(t2)}")
check(state(H["id"]) == "done", f"the key's step is still done ({state(H['id'])})")

# the same object: G2 created t2, the hidden H changed it later -> the run stops there and says it
r = A.post(B + f"/api/undo/to/{G2}", json={"hide_api": True})
j = r.json() if r.ok else {}
stp = j.get("stopped") or {}
check(r.ok and stp.get("id") == G2 and stp.get("state") == "hidden" and G2 not in (j.get("undone") or []),
      f"a hidden later step on the same object: stopped there {r.status_code} {str(j)[:300]}")
check("API key" in (j.get("text") or "") and "Beta A" in (j.get("text") or ""), f"the answer says why ({j.get('text')})")
check(task(t2)["deleted_at"] is None and task(t2)["priority"] == 3 and state(G2) == "done" and state(H["id"]) == "done",
      f"nothing of it went {task(t2)} {state(G2)} {state(H['id'])}")
# Rückfall: without hide_api the same run takes the key's step and the creation back (as before #6165)
r = A.post(B + f"/api/undo/to/{G2}")
j = r.json() if r.ok else {}
check(r.ok and H["id"] in j.get("undone", []) and G2 in j.get("undone", []) and not j.get("stopped"), f"switch on: all of it back {str(j)[:300]}")
check(task(t2) is None or task(t2)["deleted_at"] is not None, f"t2 is gone again {task(t2)}")

# a key of another person never marks alice's steps; bob's own step is his
A.post(B + "/api/users", json={"username": "bob", "display_name": "Bob", "password": "password123"}).json()["id"]
Bo = sess("bob")
check(not any(i["id"] == H["id"] for i in Bo.get(B + "/api/undo").json().get("items", [])), "bob does not see alice's key step")

# ---------------------------------------------------------------- a person without an organisation
FID, Fr = freelancer(B, A)
KF = token(Fr, "Frida Sync")
FL = Fr.post(B + "/api/lists", json={"name": "Own work"}).json()["id"]
f1, f2, FG2, FG3, FH = scenario(Fr, FID, FL, KF, "F")
check(FH.get("via") == "token" and FH.get("device") == "Frida Sync", f"frida: her key step marked {FH}")
r = Fr.post(B + f"/api/undo/to/{FG3['id']}", json={"hide_api": True})
check(r.ok and r.json().get("undone") == [FG3["id"]] and state(FH["id"]) == "done", f"frida: the shown step back, the key's stays {r.text[:300]}")
r = Fr.post(B + f"/api/undo/to/{FG2}", json={"hide_api": True})
check(r.ok and (r.json().get("stopped") or {}).get("state") == "hidden" and state(FG2) == "done", f"frida: stopped at the same object {r.text[:300]}")

sys.exit(done("p21175_a_api_steps"))
