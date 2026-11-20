#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1494.0 (#7528): "Confirm as an order" / "Reject" -- a decider's yes bound to the text of a task (tasks/boundyes.py),
own container (start.sh). Invented people and texts only.
freelancer-matrix: tasks
 - frida (no organisation) owns the project; gert is a member with edit rights (no decider), an agent of hers writes tasks
 - a stranger (xena): 404 on all three routes, nothing changed
 - the role: gert 403 (confirm and reject), the agent 403 on the web route, and the API never sets it (PATCH confirmed: refused,
   nothing set); frida 200, the API shows confirmed {by, at} read only, the timeline may_yes / the history line "confirmed"
 - bound to the text: frida's own change of title or description keeps it; gert's change (or the agent's) ends it, with the
   history line "confirmed_lapsed"; a change outside the hook (straight in the database) ends it too (the text state)
 - taking it back: DELETE, logged "confirmed_off"
 - reject: without a reason 400 (and nothing closes), with one: won't do, the history line "rejected" with the reason;
   a closed task can be neither confirmed nor rejected (409); an agent's task (locked from the start) is unlocked by the no
 - the template hint: a bug ticket whose sections are empty names them in the timeline (tpl_empty), a filled one none
 - the one-way yes stands on the same block: still only a decider, a new reason ends it
usage: p7528_confirm_api_test.py <datadir>"""
import os
import sys
import time

import requests

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
from freelancer_fixture import freelancer  # noqa: E402
import kt  # noqa: E402
from kt import check, B, dbx, H, done  # noqa: E402

V = B + "/api/v1"


def hdr(tok):
    return {"Authorization": "Bearer " + tok, **H}


def agent(s, name, lid, role="edit"):
    r = s.post(B + "/api/my/agents", json={"username": name, "display_name": name.title(), "scopes": ["read", "tasks:write", "comments", "delete"]})
    assert r.status_code in (200, 201), r.text
    aid = r.json()["id"]
    assert s.put(B + f"/api/lists/{lid}/members", json={"user_id": aid, "role": role}).ok
    return aid, hdr(s.post(B + f"/api/my/agents/{aid}/token").json()["token"])


def tl(s, tid):
    return s.get(B + f"/api/tasks/{tid}/timeline").json()


def acts(s, tid, kind):
    return [a for a in tl(s, tid)["activity"] if a["kind"] == kind]


def seen(s, tid):
    t = s.get(B + f"/api/tasks/{tid}").json()
    return {"title": t.get("title"), "content": t.get("content") or ""}


def yes(s, tid, ver=True):
    """POST confirm with the text as the decider reads it (reader F2); ver False = none, a dict = that one."""
    return s.post(B + f"/api/tasks/{tid}/confirm", json=seen(s, tid) if ver is True else (ver or {}))


def conf(tid, h):
    return requests.get(V + f"/tasks/{tid}", headers=h).json().get("confirmed")


kt.fresh()
A = kt.setup()
A.put(B + "/api/admin/agent-policy", json={"user_agents": True})
FU, F = freelancer(B, A, "frida")
GU, G = freelancer(B, A, "gert")
XU, X = freelancer(B, A, "xena")  # a stranger
L = F.post(B + "/api/lists", json={"name": "Orders", "kind": "project", "ptype": "software"}).json()["id"]
check(F.put(B + f"/api/lists/{L}/members", json={"user_id": GU, "role": "edit"}).ok, "setup: a member without the decider role")
AID, AH = agent(F, "fridabot", L)

# ================================================================== the role
r = requests.post(V + "/tasks", headers=AH, json={"list_id": L, "title": "Rebuild the export", "notes": "Every format"})
check(r.status_code in (200, 201), "setup: the agent writes a task " + r.text[:200])
T1 = r.json()["id"]
check(conf(T1, AH) is None, "not confirmed by default (API)")
check(tl(F, T1).get("may_yes") is True and tl(G, T1).get("may_yes") is False, "the timeline: frida decides, gert not")
check(X.post(B + f"/api/tasks/{T1}/confirm").status_code == 404, "a stranger: POST confirm 404")
check(X.delete(B + f"/api/tasks/{T1}/confirm").status_code == 404, "a stranger: DELETE confirm 404")
check(X.post(B + f"/api/tasks/{T1}/reject", json={"reason": "no"}).status_code == 404, "a stranger: POST reject 404")
check(conf(T1, AH) is None and requests.get(V + f"/tasks/{T1}", headers=AH).json()["status"] == "open", "... nothing changed")
r = yes(G, T1, ver={"title": "x", "content": ""})
check(r.status_code == 403, "a member without the decider role: 403 " + str(r.status_code))
r = G.post(B + f"/api/tasks/{T1}/reject", json={"reason": "no"})
check(r.status_code == 403, "... rejecting neither: 403 " + str(r.status_code))
r = requests.post(B + f"/api/tasks/{T1}/confirm", headers=AH)
check(r.status_code in (401, 403), "the agent's token on the web route: refused " + str(r.status_code))
r = requests.patch(V + f"/tasks/{T1}", headers=AH, json={"confirmed": {"by": FU, "at": "2026-11-20T10:00:00Z"}})
check(r.status_code == 400 and conf(T1, AH) is None, "the API never sets it (unknown field), nothing set " + str(r.status_code))
check(dbx("SELECT confirmed_at FROM tasks WHERE id=?", (T1,)) == [(None,)], "nothing in the database either")

r = yes(F, T1)
check(r.ok and (r.json().get("confirmed") or {}).get("by") == FU, "frida confirms " + r.text[:200])
c = conf(T1, AH)
check(c and c["by"] == FU and c["at"], "the API shows confirmed {by, at} " + str(c))
check(len(acts(F, T1, "confirmed")) == 1 and acts(F, T1, "confirmed")[0]["user_id"] == FU, "the history: frida confirmed")
st = F.get(B + "/api/state").json()
check(any(t["id"] == T1 and (t.get("confirmed") or {}).get("by") == FU and "confirmed_sig" not in t for t in st["tasks"]),
      "the app's state carries confirmed, never the text state")

# ================================================================== bound to the text
check(F.patch(B + f"/api/tasks/{T1}", json={"locked": False}).ok and conf(T1, AH), "setup: unlocked (an agent's task starts locked); unlocking keeps the yes")
r = F.patch(B + f"/api/tasks/{T1}", json={"title": "Rebuild the export (CSV first)"})
check(r.ok and conf(T1, AH), "#7528 (d): frida's direct edit of the title keeps it")
r = F.patch(B + f"/api/tasks/{T1}", json={"content": "Every format, CSV first"})
check(r.ok and conf(T1, AH), "... of the description too")
check(not acts(F, T1, "confirmed_lapsed"), "no line that it ended")
# (c) decision 25398: only the direct edit carries it - frida's undo of her own description change ends it
u = [x for x in F.get(B + "/api/undo").json().get("items") or [] if x.get("kind") == "task" and x.get("ref_id") == T1]
r = F.post(B + f"/api/undo/to/{max(u, key=lambda x: x['id'])['id']}") if u else None
check(r is not None and r.ok and F.get(B + f"/api/tasks/{T1}").json().get("content") == "Every format",
      f"(c) setup: frida undoes her description change {r.status_code if r is not None else u}")
check(conf(T1, AH) is None, "#7528 (c): an undo ends the confirmation (only the direct edit carries it)")
check(yes(F, T1).ok and conf(T1, AH), "confirmed again")
r = G.patch(B + f"/api/tasks/{T1}", json={"content": "Every format, PDF first"})
check(r.ok and conf(T1, AH) is None, "gert's change ends it " + r.text[:120])
la = acts(F, T1, "confirmed_lapsed")
check(any(a["user_id"] == GU for a in la), "the history names who changed the text " + str(la))
# reader F2: the yes goes to the text frida read - a change between her look and her click gives 409, nothing confirmed
s1 = seen(F, T1)
check(bool(s1["title"]), "frida reads the task")
check(G.patch(B + f"/api/tasks/{T1}", json={"content": "Every format, PDF first, then CSV"}).ok, "setup: gert changes it meanwhile")
r = yes(F, T1, ver=s1)
check(r.status_code == 409 and conf(T1, AH) is None, "F2: a confirm of the text read before the change: 409 " + str(r.status_code))
check(yes(F, T1, ver=False).status_code == 409 and conf(T1, AH) is None, "F2: without the text: 409")
check(yes(F, T1).ok and conf(T1, AH), "confirmed again")
ua = requests.get(V + f"/tasks/{T1}", headers=AH).json()["updated_at"]
r = requests.patch(V + f"/tasks/{T1}", headers=AH, json={"title": "Rebuild the export (all at once)", "expect_updated_at": ua})
check(r.ok and conf(T1, AH) is None, "the agent's change ends it as well " + r.text[:160])
check(yes(F, T1).ok and conf(T1, AH), "confirmed again")
# reader F4: frida's own token cannot give the yes, so its change does not carry the yes onto the new text either
FT = hdr(F.post(B + "/api/me/tokens", json={"name": "script", "scopes": ["read", "tasks:write"]}).json()["token"])
check(yes(F, T1).ok and conf(T1, AH), "confirmed again")
ua = requests.get(V + f"/tasks/{T1}", headers=FT).json()["updated_at"]
r = requests.patch(V + f"/tasks/{T1}", headers=FT, json={"title": "Rebuild the export (by script)", "expect_updated_at": ua})
check(r.ok and conf(T1, AH) is None, "F4: a change through frida's own token ends it " + r.text[:160])
check(yes(F, T1).ok and conf(T1, AH), "confirmed again")
dbx("UPDATE tasks SET title='Changed outside' WHERE id=?", (T1,))
check(conf(T1, AH) is None, "a change outside the hook ends it too (the text state)")

# ================================================================== take it back
check(yes(F, T1).ok and conf(T1, AH), "confirmed again")
dbx("UPDATE tasks SET updated_at=updated_at - INTERVAL '1 hour' WHERE id=?", (T1,))  # an older state, no wait for the clock
u0 = requests.get(V + f"/tasks/{T1}", headers=AH).json().get("updated_at")
r = F.delete(B + f"/api/tasks/{T1}/confirm")
u1 = requests.get(V + f"/tasks/{T1}", headers=AH).json().get("updated_at")
check(u0 and u1 and u1 > u0, f"reader F8 (job/6017): taking it back moves updated_at (updated_since sees it) {u0} -> {u1}")
check(r.ok and r.json().get("confirmed") is None and conf(T1, AH) is None, "frida takes it back")
check(len(acts(F, T1, "confirmed_off")) == 1, "logged")

# ================================================================== reject
r = F.post(B + f"/api/tasks/{T1}/reject", json={})
check(r.status_code == 400, "rejecting without a reason: 400 " + str(r.status_code))
r = F.post(B + f"/api/tasks/{T1}/reject", json={"reason": "   "})
check(r.status_code == 400, "... a blank one too")
check(requests.get(V + f"/tasks/{T1}", headers=AH).json()["status"] == "open", "nothing closed")
r = F.post(B + f"/api/tasks/{T1}/reject", json={"reason": "We keep the old export"})
check(r.ok and r.json()["status"] == -1, "with a reason: closed as won't do " + r.text[:120])
check(requests.get(V + f"/tasks/{T1}", headers=AH).json()["status"] == "wont_do", "the API: wont_do")
rj = acts(F, T1, "rejected")
check(len(rj) == 1 and rj[0]["data"].get("reason") == "We keep the old export" and rj[0]["user_id"] == FU, "the history keeps the reason " + str(rj))
check(yes(F, T1).status_code == 409 and F.post(B + f"/api/tasks/{T1}/reject", json={"reason": "x"}).status_code == 409,
      "a closed task: neither confirmed nor rejected again (409)")

T4 = requests.post(V + "/tasks", headers=AH, json={"list_id": L, "title": "Delete old invoices"}).json()["id"]
r = F.post(B + f"/api/tasks/{T4}/reject", json={"reason": "Never"})
if not r.ok:  # the server's side of it
    import subprocess
    print(subprocess.run(["docker", "logs", "--tail", "60", kt.CT], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True).stdout[-6000:], flush=True)
check(r.ok and r.json()["status"] == -1 and not r.json().get("locked"), "an agent's locked task: the no unlocks and closes it " + r.text[:120])

# reader F3 (job/6017): a list with the lock keeps no plain text in its history -- there the no goes without a reason
L3 = F.post(B + "/api/lists", json={"name": "Sealed", "kind": "project"}).json()["id"]
T5 = F.post(B + "/api/tasks", json={"list_id": L3, "title": "Sealed order"}).json()["id"]
T7 = F.post(B + "/api/tasks", json={"list_id": L3, "title": "Sealed order two"}).json()["id"]
dbx("UPDATE lists SET e2e='on' WHERE id=?", (L3,))
r = F.post(B + f"/api/tasks/{T5}/reject", json={})
check(r.ok and r.json()["status"] == -1, "a list with the lock: the no without a reason closes the task " + r.text[:160])
r = F.post(B + f"/api/tasks/{T7}/reject", json={"reason": "Plain words"})
check(r.ok and not [a for a in acts(F, T7, "rejected") if (a.get("data") or {}).get("reason")], "a reason sent there is not kept " + str(acts(F, T7, "rejected")))
dbx("UPDATE lists SET e2e=NULL WHERE id=?", (L3,))

# reader F2 (job/6017): "Restore description" from the history brings back an earlier text -- no own edit: the yes ends
T6 = requests.post(V + "/tasks", headers=AH, json={"list_id": L, "title": "Paint the shop", "notes": "Blue walls"}).json()["id"]
check(F.patch(B + f"/api/tasks/{T6}", json={"locked": False}).ok, "setup: unlocked")
check(F.patch(B + f"/api/tasks/{T6}", json={"content": "Blue walls, white door"}).ok, "setup: frida writes the description")
check(yes(F, T6).ok and conf(T6, AH), "setup: frida confirms her text")
check(F.patch(B + f"/api/tasks/{T6}", json={"content": "Blue walls", "_act": "restore"}).ok, "frida restores the earlier description")
check(conf(T6, AH) is None and acts(F, T6, "confirmed_lapsed"), "restoring an earlier text ends the confirmation (history line)")

# ================================================================== the template hint
check(F.patch(B + f"/api/lists/{L}", json={"tickets": True}).ok, "setup: ticket types on")
r = requests.post(V + "/tasks", headers=AH, json={"list_id": L, "title": "Crash on save", "type": "bug"})
T2 = r.json()["id"]
check(F.patch(B + f"/api/tasks/{T2}", json={"locked": False}).ok, "setup: unlocked")
te = tl(F, T2).get("tpl_empty")
check(isinstance(te, list) and len(te) >= 3, "a bug ticket with its template empty: the sections are named " + str(te))
G.patch(B + f"/api/tasks/{T2}", json={"content": "**Steps to reproduce**\n1. Open a task\n\n**Expected**\nSaved\n\n**Actual**\nCrash\n\n**Environment**\nFirefox\n\n**Version / found in**\n2.1494\n"})
check(tl(F, T2).get("tpl_empty") == [], "filled in: none " + str(tl(F, T2).get("tpl_empty")))
# reader F1: a long line in the description costs linear time (was quadratic: 40,000 characters took 30 s per look)
check(G.patch(B + f"/api/tasks/{T2}", json={"content": "# x" + " " * 40000 + "y\n**Steps to reproduce**\n- [ ] " + " " * 40000 + "z"}).ok, "setup: long lines")
t0 = time.monotonic()
te = tl(F, T2).get("tpl_empty")
check(time.monotonic() - t0 < 5 and isinstance(te, list), f"F1: the timeline of a long description answers at once ({time.monotonic() - t0:.1f} s)")
T3 = F.post(B + "/api/tasks", json={"title": "Plain task", "list_id": L}).json()["id"]
check(tl(F, T3).get("tpl_empty") == [], "a task without a template: none")

# ================================================================== the one-way yes on the same block
r = requests.patch(V + f"/tasks/{T3}", headers=AH, json={"irreversible": {"reason": "Drops a column"}})
check(r.ok, "setup: marked")
check(G.post(B + f"/api/tasks/{T3}/irreversible-yes").status_code == 403, "the one-way yes: gert 403")
check(requests.post(B + f"/api/tasks/{T3}/irreversible-yes", headers=AH).status_code in (401, 403), "the agent: refused")
r = F.post(B + f"/api/tasks/{T3}/irreversible-yes")
check(r.ok and r.json()["irreversible"]["yes_by"] == FU, "frida gives it " + r.text[:120])
requests.patch(V + f"/tasks/{T3}", headers=AH, json={"irreversible": {"reason": "Drops two columns"}})
check(requests.get(V + f"/tasks/{T3}", headers=AH).json()["irreversible"]["yes_at"] is None, "a new reason ends it")
sys.exit(done("p7528_confirm_api"))
