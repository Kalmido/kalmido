#!/usr/bin/env python3
# kalmido-suite: fresh
"""#6607 (audit #4818 F2): a read-only member changes nothing of the organisation -- not through the six ways the audit found
and not through the next route somebody forgets. Invented names only, addresses @example.com. freelancer-matrix: lists
 - the six ways, each with its control (a member / an admin / a person without an organisation still may):
   1 POST /api/clients/bulk (archive, unarchive, set, restore, delete, untrash): 403 for the read-only member, a member archives
   2 POST /api/tasks/purge-done: the lists Rita still has owner_id on but only reads (read-only now) are left alone, also with
     others=true; the admin clears the done tasks of her own list
   3 the folder ways (props, agents, owner, public links, people, groups, Playbook, notification template, repositories,
     dissolving, renaming / moving the folder, folder-reset of a list): 403 while the folder holds a project she only reads;
     GET public-links names no link of it any more. Reader job/5762 F1: renaming "Work" under her private folder with its own
     Playbook would have put the organisation's project under that Playbook -> 403, the project's path stays; F4: the same
     through the projects tree (tree/move, PATCH /api/files/nodes/<id> of a private twin folder "Work"). F2: switching
     the public links OFF answers 200 but touches only lists she owns by role (her read-only project keeps its link)
   4 POST /api/lists/<id>/join: read-only joins no organisation-wide project (no member row); a member joins
   5 PATCH /api/office/agents/<id>: an office group with "settings: manage" no longer lifts the read-only role; the admin switches
   6 PATCH /api/clients/<id> {org_id: null}: the member who created the client gets 403 with the "Ask an admin" request, after
     the admin's release it goes private, logged (org_list_log moveout, kind clients); the admin moves one directly
 - the guard: every POST / PUT / PATCH / DELETE route of the areas clients, tasks / projects, folders and office agents from the
   server's route table (tests/routes_ast.py) is called as the read-only member against the organisation's objects (her own
   former project and client too), several bodies each. No 2xx unless the route stands in EXEMPT with its reason (own marks,
   own settings), no 5xx; afterwards the organisation's rows (clients, projects, tasks, members, public links, folder settings,
   shares, the agent's office switch) are exactly as before. A new write route in these areas without a refusal is red here.
   An EXEMPT entry without a route is red too (stale). The other areas: task #7370.
 - P4: a person without an organisation keeps the folder ways and purge-done for her own projects
usage: p21445_c_readonly_guard_test.py <datadir>      (P21445C_NOSTART=1: a running server)"""
import os
import re
import sys

import requests

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
from freelancer_fixture import freelancer  # noqa: E402
from kt import B, H, PASSWORD, check, dbx, docker_logs_on_first_fail, done, fresh, sess  # noqa: E402
from routes_ast import app_routes  # noqa: E402

docker_logs_on_first_fail()

# ---------------------------------------------------------------- the routes in scope and the named exceptions
SCOPE = re.compile(r"^(POST|PUT|PATCH|DELETE) /api/(clients|lists/\{\}|tasks|folders|office/agents)(/|$)")
# route -> (reason, call it?): what a read-only member may still do there (own marks, own settings). Nothing that changes an
# object of the organisation for the others.
EXEMPT = {
    "PUT /api/folders/public-links": ("switching off touches only the lists owned by role (none here: her read-only project "
                                      "keeps its link - rows check below); switching on is refused (way 3)", True),
    "PATCH /api/lists/{}": ("field by field (list_apply): unknown keys are dropped (web_fields), every field of the project "
                            "itself needs the write role - the rows check below proves nothing changed", True),
    "PUT /api/lists/{}/favorite": ("the own favourites (a setting of the person)", True),
    "DELETE /api/lists/{}/favorite": ("the own favourites (a setting of the person)", True),
    "PUT /api/lists/{}/in-mine": ("the own view Mine (a setting of the person)", True),
    "PUT /api/lists/{}/layout": ("the own layout of the project page (mine); its standard layout needs can_std", True),
    "DELETE /api/tasks/{}/enc-note": ("the own encrypted private note of the task (task_enc_notes of the person only)", True),
    "POST /api/tasks/{}/editing": ("the presence mark 'is editing' (nothing of the task is written)", True),
    "POST /api/tasks/{}/typing": ("the presence mark 'is typing' (nothing of the task is written)", True),
    "POST /api/tasks/{}/seen": ("the own read mark of the task", True),
    "POST /api/tasks/{}/watchers": ("following the task oneself (the own subscription); adding somebody else stays the "
                                    "project's owner / admins (user_id of Bob: refused)", True),
    "POST /api/tasks/similar": ("a search for similar tasks (reads only)", True),
    "POST /api/tasks/reorder": ("skips every task without the write role (shifted: []) - rows check below", True),
    "POST /api/tasks/batch": ("answers per task: count 0 with the refusal of each in errors - rows check below", True),
    "POST /api/tasks/purge-done": ("only the projects the person owns by role (#6607): none here, count 0 - rows check below", True),
    "POST /api/clients": ("a new client lands in the own private space (ws_chosen_org offers only organisations where the "
                          "person may add) - checked below", True),
}

ALL, PROBLEMS = app_routes(os.path.join(N, ".."))
OURS = sorted(r for r in ALL if SCOPE.match(r))
check(len(OURS) >= 100, f"the route table names the write routes of the areas ({len(OURS)})")
for r in sorted(set(EXEMPT) - set(OURS)):
    check(False, f"EXEMPT names a route the server does not have (stale): {r}")
check(all(len(v[0]) > 15 for v in EXEMPT.values()), "every exception has its reason")

# ---------------------------------------------------------------- setup
fresh(prefix="P21445C")
s0 = requests.Session()
s0.headers.update(H)
assert s0.post(B + "/api/auth/setup", json={"username": "alice", "display_name": "Alice", "password": PASSWORD}).ok
A = sess("alice")
r = A.post(B + "/api/admin/setup", json={"org_name": "Alpha Studio", "lang": "en", "collab_all": True, "modules": ["comments"]})
assert r.ok, "admin setup " + r.text[:300]
A = sess("alice")
FEAT = "clients,office,collab,docs,comments,time"
A.patch(B + "/api/settings", json={"lang": "en", "tour": "done", "features": FEAT})
A.put(B + "/api/admin/agent-policy", json={"user_agents": True})
ALICE = A.get(B + "/api/state").json()["me"]["id"]
ORG = A.get(B + "/api/state").json()["me"]["workspaces"][0]["id"]
A.patch(B + "/api/settings", json={"workspace": f"org:{ORG}"})
uid, S = {}, {}
for u in ("bob", "rita", "carl"):
    r = A.post(B + "/api/users", json={"orgs": [{"id": ORG, "role": "member"}], "username": u, "display_name": u.title(),
                                       "password": PASSWORD, "email": f"{u}@example.com"})
    assert r.ok, r.text
    uid[u] = r.json()["id"]
    S[u] = sess(u)
    assert S[u].patch(B + "/api/settings", json={"lang": "en", "tour": "done", "features": FEAT, "workspace": f"org:{ORG}"}).ok
Bo, Ri, Ca = S["bob"], S["rita"], S["carl"]
BOB, RITA = uid["bob"], uid["rita"]


def ok(r, what):
    check(r.status_code in (200, 201), f"setup: {what} ({r.status_code} {r.text[:200]})")
    return r.json() if r.status_code in (200, 201) else {}


# Alice's organisation-wide project with a task and a done task
L1 = ok(A.post(B + "/api/lists", json={"name": "Team board", "org_id": ORG}), "Alice's project")["id"]
ok(A.patch(B + f"/api/lists/{L1}", json={"org_visibility": "org", "org_edit": 1}), "everyone in the organisation")
T1 = ok(A.post(B + "/api/tasks", json={"list_id": L1, "title": "Plan the spring"}), "a task")["id"]
T1D = ok(A.post(B + "/api/tasks", json={"list_id": L1, "title": "Old work"}), "a task to finish")["id"]
ok(A.post(B + f"/api/tasks/{T1D}/complete"), "done")
# Rita, still a member: her own project in her folder "Work" with a done task of hers and one of Bob's, and her client
L2 = ok(Ri.post(B + "/api/lists", json={"name": "Rita's project", "org_id": ORG, "folder": "Work"}), "Rita's project")["id"]
ok(Ri.put(B + f"/api/lists/{L2}/members", json={"user_id": BOB, "role": "edit"}), "Bob in Rita's project")
T2 = ok(Ri.post(B + "/api/tasks", json={"list_id": L2, "title": "Rita's task"}), "Rita's task")["id"]
T2D = ok(Ri.post(B + "/api/tasks", json={"list_id": L2, "title": "Rita's done task"}), "Rita's done task")["id"]
ok(Ri.post(B + f"/api/tasks/{T2D}/complete"), "done")
T2B = ok(Bo.post(B + "/api/tasks", json={"list_id": L2, "title": "Bob's done task"}), "Bob's task")["id"]
ok(Bo.post(B + f"/api/tasks/{T2B}/complete"), "done")
CR = ok(Ri.post(B + "/api/clients", json={"name": "Rita Client", "org_id": ORG}), "Rita's client")["id"]
CA = ok(A.post(B + "/api/clients", json={"name": "Alpha Client", "org_id": ORG}), "Alice's client")["id"]
# the organisation's agent and Rita in the office group of the organisation's admins (settings: manage)
r = A.post(B + "/api/my/agents", json={"username": "officebot", "display_name": "Office Bot", "scopes": ["read", "office"], "org_id": ORG})
AG = ok(r, "the organisation's agent").get("id")
ok(A.put(B + f"/api/office/rights/people/{RITA}", json={"groups": ["tpl:orgadmin"]}), "Rita in the office group Organisation admin")
r = Ri.patch(B + f"/api/office/agents/{AG}", json={"office_drafts": True})
check(r.ok, f"control: as a member in that group Rita switches the agent's office drafts ({r.status_code} {r.text[:160]})")
ok(Ri.patch(B + f"/api/office/agents/{AG}", json={"office_drafts": False}), "and back")
# a public link of her project (the folder's GET must not hand out its address once she only reads)
r = Ri.put(B + "/api/folders/public-links", json={"folder": "Work", "on": True})
check(r.ok and r.json().get("created") == 1, f"control: as a member Rita switches the folder's public links on ({r.status_code} {r.text[:160]})")

# Rita becomes read-only
# 2.1458.0 (#6610): the role change through the API hands her project to Alice (a read-only person owns nothing); these
# guards are for a read-only owner from before that rule (an old database), so the role is set in the table as it stood then
dbx("UPDATE org_members SET role='readonly' WHERE org_id=? AND user_id=?", (ORG, RITA))
st = {x["id"]: x for x in Ri.get(B + "/api/state").json()["lists"]}
check(st.get(L2, {}).get("role") == "view" and st.get(L1, {}).get("role") == "view", "read-only: both projects as view")


def snap():
    """The organisation's rows the guard must leave as they are."""
    q = {
        "clients": ("SELECT * FROM clients WHERE id IN (?, ?) ORDER BY id", (CA, CR)),
        "lists": ("SELECT * FROM lists WHERE id IN (?, ?) ORDER BY id", (L1, L2)),
        "tasks": ("SELECT * FROM tasks WHERE list_id IN (?, ?) ORDER BY id", (L1, L2)),
        "members": ("SELECT * FROM list_members WHERE list_id IN (?, ?) ORDER BY list_id, user_id", (L1, L2)),
        "links": ("SELECT * FROM public_links WHERE list_id IN (?, ?) ORDER BY list_id", (L1, L2)),
        "fprops": ("SELECT * FROM folder_props WHERE owner_id=? ORDER BY folder", (RITA,)),
        "fagents": ("SELECT * FROM folder_agents WHERE owner_id=? ORDER BY folder, agent_id", (RITA,)),
        "shares": ("SELECT * FROM fs_shares ORDER BY id", ()),
        "agent": ("SELECT office_drafts FROM agents WHERE user_id=?", (AG,)),
        "outlog": ("SELECT COUNT(*) FROM org_list_log", ()),
    }
    return {k: [tuple(x) for x in dbx(s, a)] for k, (s, a) in q.items()}


def diff(a, b):
    return ", ".join(k for k in a if a[k] != b[k])


# ================================================================ the six ways, one by one
LM = ok(Ri.post(B + "/api/lists", json={"name": "Rita's notes", "folder": "Mine"}), "Rita's private project in her folder Mine")["id"]
# reader job/5762 F1, step 1: a Playbook on her own private folder (allowed: only her private project in it)
r = Ri.put(B + "/api/folders/playbook", json={"folder": "Mine", "text": "Guard playbook"})
check(r.ok, f"way 3: her own private folder's Playbook stays hers ({r.status_code} {r.text[:120]})")
S0 = snap()
# 1 clients, several at once
for body in ({"ids": [CA, CR], "action": "archive"}, {"ids": [CA], "action": "set", "rate": 5}, {"ids": [CR], "action": "delete"},
             {"ids": [CA], "action": "unarchive"}, {"action": "restore", "items": [{"id": CA, "rate": 1}]}):
    r = Ri.post(B + "/api/clients/bulk", json=body)
    check(r.status_code == 403, f"way 1: read-only, clients bulk {body.get('action')} -> 403 ({r.status_code} {r.text[:120]})")
# 2 purge-done
r = Ri.post(B + "/api/tasks/purge-done", json={"dry": True})
check(r.ok and r.json() == {"own": 0, "others": 0}, f"way 2: read-only, nothing to clear in the project she only reads {r.text[:120]}")
r = Ri.post(B + "/api/tasks/purge-done", json={"others": True})
check(r.ok and r.json().get("count") == 0, f"way 2: others=true clears nothing either {r.text[:120]}")
# 3 the folder ways
F = {"folder": "Work"}
for m, p, body in (("PUT", "/api/folders/props", {**F, "props": {"hide_done": True}}),
                   ("PUT", "/api/folders/agents", {**F, "agent_id": AG}),
                   ("DELETE", "/api/folders/agents", {**F, "agent_id": AG}),
                   ("POST", "/api/folders/owner", {**F, "user_id": BOB}),
                   ("PUT", "/api/folders/public-links", {**F, "on": True}),
                   ("PUT", "/api/folders/people", {**F, "user_id": BOB, "role": "admin"}),
                   ("DELETE", "/api/folders/people", {**F, "user_id": BOB, "remove": True}),
                   ("PUT", "/api/folders/playbook", {**F, "text": "Guard"}),
                   ("PUT", "/api/folders/notify-template", {**F, "tpl": "all"}),
                   ("POST", "/api/folders/delete", {"name": "Work"}),
                   ("POST", "/api/folders/rename", {"old": "Work", "new": "Renamed"}),
                   ("POST", "/api/folders/rename", {"old": "Work", "new": "Mine/Work"}),
                   ("POST", f"/api/lists/{L2}/folder-reset", {})):
    r = Ri.request(m, B + p, json=body)
    check(r.status_code == 403, f"way 3: read-only, {m} {p} -> 403 ({r.status_code} {r.text[:120]})")
# reader job/5762 F1, the two steps: a Playbook on her own private folder "Mine" (set up before the snapshot), then "Work"
# moved into it -- refused, the organisation's project stays where it was
r = Ri.post(B + "/api/folders/rename", json={"old": "Work", "new": "Mine/Work"})
check(r.status_code == 403 and dbx("SELECT folder FROM lists WHERE id=?", (L2,))[0][0] == "Work",
      f"way 3: the folder with her read-only project does not move under her Playbook ({r.status_code} {r.text[:120]})")
check(Ri.post(B + "/api/folders/rename", json={"old": "Mine", "new": "Mine 2"}).ok
      and Ri.post(B + "/api/folders/rename", json={"old": "Mine 2", "new": "Mine"}).ok, "way 3: her own private folder renames freely")
# reader job/5762 F4: the same through the projects tree -- a private twin folder "Work" moved under "Mine" (tree/move, the file
# store's node PATCH) would take every path "Work" of hers along (folder_rename_do), the organisation's project too
sp = [x for x in Ri.get(B + "/api/lists/tree").json().get("spaces", []) if not x.get("org_id")]
check(len(sp) == 1, f"way 3: her private projects tree {len(sp)}")
PR = sp[0]["root"] if sp else 0
PR = PR.get("id") if isinstance(PR, dict) else PR
r = Ri.post(B + "/api/lists/folders", json={"parent_id": PR, "name": "Work"})
check(r.status_code in (200, 201), f"way 3: a private twin folder Work ({r.status_code} {r.text[:120]})")
TW = r.json().get("id") if r.status_code in (200, 201) else 0
mine = [f for x in Ri.get(B + "/api/lists/tree").json().get("spaces", []) if not x.get("org_id")
        for f in (x.get("folders") or []) if f.get("path") == "Mine"]
check(len(mine) == 1, f"way 3: her private folder Mine in the tree {mine}")
MN = mine[0]["id"] if mine else 0
for m, p, body in (("POST", "/api/lists/tree/move", {"node_id": TW, "parent_id": MN}),
                   ("PATCH", f"/api/files/nodes/{TW}", {"parent_id": MN}),
                   ("PATCH", f"/api/files/nodes/{TW}", {"name": "Renamed"})):
    r = Ri.request(m, B + p, json=body)
    check(r.status_code == 403 and dbx("SELECT folder FROM lists WHERE id=?", (L2,))[0][0] == "Work",
          f"way 3: {m} {p} {body} leaves the organisation's project where it was ({r.status_code} {r.text[:120]})")
# reader job/5762 F2: switching the public links off is a taking back -- 200, her read-only project keeps its link (not hers to change)
r = Ri.put(B + "/api/folders/public-links", json={**F, "on": False})
check(r.ok and r.json().get("removed") == 0 and dbx("SELECT 1 FROM public_links WHERE list_id=?", (L2,)),
      f"way 3: links off touches only her own lists ({r.status_code} {r.text[:120]})")
r = Ri.get(B + "/api/folders/public-links", params=F)
check(r.ok and not any(x.get("link") for x in r.json().get("lists", [])), f"way 3: the folder's GET names no link of her read-only project {r.text[:160]}")
# 4 join
r = Ri.post(B + f"/api/lists/{L1}/join")
check(r.status_code == 403, f"way 4: read-only joins no project ({r.status_code} {r.text[:120]})")
check(not dbx("SELECT 1 FROM list_members WHERE list_id=? AND user_id=?", (L1, RITA)), "way 4: no member row")
# 5 the agent's office switch
r = Ri.patch(B + f"/api/office/agents/{AG}", json={"office_drafts": True})
check(r.status_code == 403, f"way 5: read-only in an office group with settings manage -> 403 ({r.status_code} {r.text[:120]})")
# 6 out of the organisation
r = Ri.patch(B + f"/api/clients/{CR}", json={"org_id": None})
check(r.status_code == 403, f"way 6: read-only moves her client nowhere ({r.status_code} {r.text[:120]})")
check(diff(S0, snap()) == "", f"the six ways changed nothing ({diff(S0, snap())})")

# ================================================================ the guard over the route table
SEC = dbx("SELECT id FROM sections WHERE list_id=? ORDER BY id LIMIT 1", (L2,))
SECOND = {"members": BOB, "groups": 999999, "sections": SEC[0][0] if SEC else 999999, "watchers": BOB}
TARGETS = {"lists": (L1, L2), "tasks": (T1, T2D), "clients": (CA, CR), "office": (AG,)}
GEN = [{}, {"name": "Guard"}, {"title": "Guard"}, {"text": "Guard"}, {"org_id": None}, {"user_id": BOB, "role": "edit"},
       {"on": True}, {"status": 1}, {"office_drafts": True}]
FOLD = [{"folder": "Work", **x} for x in ({}, {"on": True}, {"on": False}, {"user_id": BOB, "role": "edit"}, {"agent_id": AG},
                                         {"props": {"hide_done": True}}, {"text": "Guard"}, {"tpl": "all"}, {"repo": "example/guard"})]
SPECIAL = {
    "POST /api/clients/bulk": [{"ids": [CA, CR], "action": a} for a in ("archive", "unarchive", "delete", "untrash")]
                              + [{"ids": [CA], "action": "set", "note_append": "Guard"}, {"action": "restore", "items": [{"id": CR, "rate": 1}]}],
    "POST /api/clients/merge": [{"target": CA, "sources": [CR]}, {"into": CA, "ids": [CR]}],
    "POST /api/tasks": [{"list_id": L1, "title": "Guard"}, {"list_id": L2, "title": "Guard"}],
    "POST /api/tasks/batch": [{"ids": [T1, T2D], "action": a} for a in ("delete", "complete", "move")] + [{"ids": [T1], "data": {"title": "Guard"}}],
    "POST /api/tasks/purge-done": [{}, {"others": True}],
    "POST /api/tasks/reorder": [{"ids": [T2D, T2]}, {"list_id": L2, "ids": [T2D, T2]}],
    "POST /api/folders/delete": [{"name": "Work"}],
    "POST /api/folders/rename": [{"old": "Work", "new": "Renamed"}, {"old": "Work", "new": "Mine/Work"}],
    "DELETE /api/folders/groups/{}": [],
}


def url(route, obj):
    path = route.split(" ", 1)[1]
    head, rest = path.split("{}", 1) if "{}" in path else (path, None)
    if rest is None:
        return B + path
    out = B + head + str(obj)
    for seg in re.split(r"(\{\})", rest):
        if seg == "{}":
            prev = re.findall(r"/([a-z-]+)/$", out + "/")
            out += str(SECOND.get(prev[-1] if prev else "", 999999))
        else:
            out += seg
    return out


def targets(route):
    p = route.split(" ", 1)[1]
    if "{}" not in p or p.startswith("/api/folders"):
        return [None]
    key = "lists" if p.startswith("/api/lists") else "tasks" if p.startswith("/api/tasks") else "clients" if p.startswith("/api/clients") else "office"
    return TARGETS[key]


def bodies(route):
    if route in SPECIAL:
        return SPECIAL[route]
    if "/api/folders" in route:
        return FOLD
    return GEN


order = sorted(OURS, key=lambda r: (r.startswith("DELETE /api/lists/{} ") or r == "DELETE /api/lists/{}" or r == "DELETE /api/clients/{}", r))
bad, calls = [], 0
for route in order:
    if route in EXEMPT and not EXEMPT[route][1]:
        continue
    m = route.split(" ", 1)[0]
    for obj in targets(route):
        for body in bodies(route):
            u = url(route, obj)
            if route == "DELETE /api/folders/groups/{}":
                u += "?folder=Work"
            r = Ri.request(m, u, json=body if m != "DELETE" or body else None)
            calls += 1
            if r.status_code >= 500:
                bad.append(f"{route} {obj} {body}: {r.status_code}")
            elif 200 <= r.status_code < 300 and route not in EXEMPT:
                bad.append(f"{route} {obj} {body}: {r.status_code} {r.text[:100]}")
            if m == "DELETE" and not body:
                break
for x in bad:
    check(False, f"guard: a read-only write answered {x}")
check(calls > 300 and not bad, f"guard: {calls} calls of {len(OURS)} write routes, every one refused or a named exception")
d = diff(S0, snap())
check(d == "", f"guard: the organisation's rows are as before ({d})")
r = dbx("SELECT id FROM clients WHERE created_by=? AND org_id=? ORDER BY id", (RITA, ORG))
check([x[0] for x in r] == [CR], f"guard: the clients the read-only member made are private, none in the organisation {r}")

# ================================================================ the controls: who may, still may
# 1 a member archives the organisation's clients
r = Bo.post(B + "/api/clients/bulk", json={"ids": [CA, CR], "action": "archive"})
check(r.ok and r.json().get("changed") == 2, f"way 1: a member archives ({r.status_code} {r.text[:120]})")
check(Bo.post(B + "/api/clients/bulk", json={"ids": [CA, CR], "action": "unarchive"}).ok, "way 1: and back")
# 4 a member joins
r = Ca.post(B + f"/api/lists/{L1}/join")
check(r.ok and dbx("SELECT 1 FROM list_members WHERE list_id=? AND user_id=?", (L1, uid["carl"])), f"way 4: a member joins ({r.status_code} {r.text[:120]})")
# 5 the admin switches the agent
r = A.patch(B + f"/api/office/agents/{AG}", json={"office_drafts": True})
check(r.ok and dbx("SELECT office_drafts FROM agents WHERE user_id=?", (AG,))[0][0] == 1, f"way 5: the admin switches ({r.status_code} {r.text[:120]})")
# 6 the member who created a client asks, the admin releases, then it goes private -- logged
CB = ok(Bo.post(B + "/api/clients", json={"name": "Bob Client", "org_id": ORG}), "Bob's client")["id"]
n0 = dbx("SELECT COUNT(*) FROM org_list_log WHERE action='moveout'")[0][0]
r = Bo.patch(B + f"/api/clients/{CB}", json={"org_id": None})
check(r.status_code == 403 and (r.json().get("out_request") or {}).get("id") == CB,
      f"way 6: the creator alone gets 403 with the request to ask an admin ({r.status_code} {r.text[:200]})")
check(dbx("SELECT org_id FROM clients WHERE id=?", (CB,))[0][0] == ORG, "way 6: the client is still in the organisation")
r = Bo.post(B + f"/api/orgs/{ORG}/out-requests", json={"kind": "clients", "id": CB})
check(r.ok, f"way 6: Bob asks the admins ({r.status_code} {r.text[:160]})")
r = A.post(B + f"/api/orgs/{ORG}/out-requests/{r.json().get('id')}", json={"decision": "approve"})
check(r.ok, f"way 6: Alice releases it ({r.status_code} {r.text[:160]})")
r = Bo.patch(B + f"/api/clients/{CB}", json={"org_id": None})
check(r.ok and dbx("SELECT org_id FROM clients WHERE id=?", (CB,))[0][0] is None, f"way 6: after the release it goes private ({r.status_code} {r.text[:160]})")
log = dbx("SELECT detail FROM org_list_log WHERE action='moveout' ORDER BY id DESC LIMIT 1")
check(dbx("SELECT COUNT(*) FROM org_list_log WHERE action='moveout'")[0][0] == n0 + 1 and '"clients"' in (log[0][0] if log else ""),
      f"way 6: the move is logged (kind clients) {log}")
CC = ok(A.post(B + "/api/clients", json={"name": "Admin Client", "org_id": ORG}), "Alice's second client")["id"]
r = A.patch(B + f"/api/clients/{CC}", json={"org_id": None})
check(r.ok and dbx("SELECT org_id FROM clients WHERE id=?", (CC,))[0][0] is None, f"way 6: the admin moves it directly ({r.status_code} {r.text[:160]})")
# 2 the admin clears her own project's done tasks
r = A.post(B + "/api/tasks/purge-done", json={"others": True})
check(r.ok and r.json().get("count") == 1 and dbx("SELECT deleted_at FROM tasks WHERE id=?", (T1D,))[0][0], f"way 2: the owner clears her own project ({r.text[:120]})")
check(dbx("SELECT deleted_at FROM tasks WHERE id=?", (T2D,))[0][0] is None and dbx("SELECT deleted_at FROM tasks WHERE id=?", (T2B,))[0][0] is None,
      "way 2: Rita's project untouched")
# back to member: Rita's folder ways work again
ok(A.put(B + f"/api/orgs/{ORG}/members", json={"user_id": RITA, "role": "member"}), "Rita a member again")
r = Ri.put(B + "/api/folders/props", json={"folder": "Work", "props": {"hide_done": True}})
check(r.ok, f"way 3: as a member again Rita sets her folder ({r.status_code} {r.text[:120]})")
r = Ri.post(B + "/api/tasks/purge-done", json={"dry": True})
check(r.ok and r.json() == {"own": 1, "others": 1}, f"way 2: as a member again her project counts {r.text[:120]}")

# ================================================================ P4: a person without an organisation
FID, Fr = freelancer(B, A)
FL = ok(Fr.post(B + "/api/lists", json={"name": "Own job", "folder": "Jobs"}), "freelancer: a project in a folder")["id"]
FT = ok(Fr.post(B + "/api/tasks", json={"list_id": FL, "title": "Cut"}), "freelancer: a task")["id"]
ok(Fr.post(B + f"/api/tasks/{FT}/complete"), "done")
check(Fr.put(B + "/api/folders/props", json={"folder": "Jobs", "props": {"hide_done": True}}).ok, "freelancer: the folder's settings")
r = Fr.put(B + "/api/folders/public-links", json={"folder": "Jobs", "on": True})
check(r.ok and r.json().get("created") == 1, f"freelancer: the folder's public links ({r.status_code} {r.text[:120]})")
check(Fr.post(B + f"/api/lists/{FL}/folder-reset", json={}).ok, "freelancer: back to the folder")
r = Fr.post(B + "/api/tasks/purge-done", json={})
check(r.ok and r.json().get("count") == 1, f"freelancer: clears her done task ({r.text[:120]})")
FC = ok(Fr.post(B + "/api/clients", json={"name": "Own Client", "org_id": None}), "freelancer: a client")["id"]
check(Fr.post(B + "/api/clients/bulk", json={"ids": [FC], "action": "archive"}).ok, "freelancer: archives her client")

sys.exit(done("p21445_c_readonly_guard"))
