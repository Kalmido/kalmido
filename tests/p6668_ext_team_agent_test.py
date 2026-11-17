#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1325.0 (#6668, rest of #6454 F5): a TEAM agent with its own token (its own starter, its own program) works per request for
ONE person: POST /api/v1/agent/request-token gives a short-lived token of the agent cut to the rights of the person the events
come from (kalmido/agents/reqtoken.py, the same cut as the server's run: agents/srvteam.py srv_run_cut); from the first ask on
the agent's own token reaches only its channel (api/runfor.py req_main_gate).
freelancer-matrix: agents (the person without an organisation: her personal agent gets token null -- its own token is hers --
  and keeps its whole reach after asking)
tenant-matrix: agent (only the agent's own events; the token reaches only what the person reaches themselves)
 (a) member carl (project one only) mentions the agent: his request token reads the task of project one, the task of project two
     is 404 (also not listed); without the fix (no cut) it would be 200
 (b) reader rita (view in project one) asks in the chat: with her request token the agent (role edit) writes no comment, the
     answer is 409 approval_required; carl's token writes it
 (c) an event without a person (the project's own automation): only its project, nothing outside, and every change is a card
     (409 approval_required) -- also with no control level chosen
 (d) an expired request token is refused (401); a request token cannot ask for another one (403 request_token_main); events of
     two people in one call 400 several_people; an unknown event 404 event_gone; no operator chosen 409 no_operator
 (e) the agent's own token after the first ask: content routes 403 request_token_needed, its channel (events, chats, status)
     stays; a card a person answered still runs with it (the replay of an approved request)
 (f) static: the reference starter asks before every run and gives only the request token to the run (child_env), the
     dispatcher works with the chosen person's token; both launchers name the capability
 (i) review F3: the step of a card run with the agent's own token always checks the card and the rights of the person who
     said Yes (a reader's Yes changes nothing)
 (c) review F4: an event older than 24 hours gives no request token any more (404 event_gone)
 (h) review F2: removing a computer of the agent (its long-lived token) ends the request tokens too (401)
 (g) review F1, no server: no request token for a team agent (403 no_order, 400, 404 event_gone, the network) = the run, the
     dispatcher round and their children never start / never get the agent's own token; an older server (plain 404) and a
     personal agent keep it; a job's wake asks with the person's last events
usage: p6668_ext_team_agent_test.py <datadir>      (KMT_NOSTART=1 / P6668_NOSTART=1: a running server)"""
import json
import os
import uuid

import requests

from kt import B, check, dbx, docker_logs_on_first_fail, done, fresh, sess
from freelancer_fixture import freelancer

N = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(N, "..")
V = B + "/api/v1"
SCOPES = ["read", "tasks:write", "comments", "structure"]


def read(*p):
    with open(os.path.join(ROOT, *p), encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------- (f) static: the starter and both launchers
RUN, DISP = read("mcp", "agent_run.py"), read("mcp", "agent_dispatch.py")
check("def run_request" in RUN and "self.run_request(evs, uid)" in RUN, "(f) agent_run.py asks for the request token of every run")
check('env["KALMIDO_TOKEN"] = ra.token' in RUN, "(f) agent_run.py: the run's environment carries only the request token")
check("self.run_api = self.api" in RUN, "(f) agent_run.py: the request token is forgotten after the run")
check("def data_api" in DISP and "api = self.data_api()" in DISP and "read_tasks(api, cfg)" in DISP and 'env["KALMIDO_TOKEN"] = api.token' in DISP and "if api is not self.host.api" in DISP,
      "(f) agent_dispatch.py: the list work and its jobs with the chosen person's token")
for name in ("agent_launcher.sh", "agent_launcher.ps1"):
    check("kalmido-capability: request_token" in read("mcp", name), f"(f) {name} names request_token")


# ---------------------------------------------------------------- (g) review F1: the starter fails closed (no server)
# Without the fix a refused request token (403 no_order, 400 several_people, 409 no_operator, the network) let the run go on with
# the agent's own long-lived token: the model could fetch any person's reach with it. Only an older server (plain 404) keeps it.
def _f1():
    import importlib.util
    import sys
    import tempfile
    os.environ.update(KALMIDO_URL="http://127.0.0.1:9", KALMIDO_TOKEN="abk_" + "m" * 30)
    for nm in ("agent_run", "agent_dispatch"):
        spec = importlib.util.spec_from_file_location(nm, os.path.join(ROOT, "mcp", nm + ".py"))
        m = importlib.util.module_from_spec(spec)
        sys.modules[nm] = m
        spec.loader.exec_module(m)
    ar, ad = sys.modules["agent_run"], sys.modules["agent_dispatch"]
    tmp = tempfile.mkdtemp(prefix="kalmido-p6668f1-")

    def runner(name, answer):
        r = ar.Runner(["claude"], os.path.join(tmp, name))
        r.extras = None
        r.calls, r.started, r.said = [], [], []

        def req(method, path, body=None, query=None, timeout=30, retry=True):
            r.calls.append((path, body, r.api.token))
            if isinstance(answer, Exception):
                raise answer
            return answer
        r.api.req = req
        r.api.status = lambda *a, **k: r.said.append(k.get("key"))
        r.attempt_runs = lambda *a, **k: (r.started.append(1), (None, 1, "stub"))[1]
        return r

    ev = [{"event": "chat", "seq": 41, "data": {"user": {"id": 5}, "message": {"id": 1, "body": "hi"}}}]
    for name, answer in (("no_order", ar.ApiError(403, '{"error": {"code": "no_order"}}')),
                         ("several_people", ar.ApiError(400, '{"error": {"code": "several_people"}}')),
                         ("event_gone", ar.ApiError(404, '{"error": {"code": "event_gone"}}')),
                         ("network", OSError("unreachable"))):
        r = runner(name, answer)
        check(r.run_request(ev, 5) is False and r.run_api is r.api, f"(g) F1 {name}: no request token = the run may not start")
        r = runner(name + "-run", answer)
        r.run(5, [dict(e) for e in ev])
        check(not r.started and "status_no_request" in r.said, f"(g) F1 {name}: the run is skipped with a status line {r.said}")
        if name != "network":
            check("KALMIDO_TOKEN" not in r.child_env(5, None), f"(g) F1 {name}: a child of the team agent never gets its own token")
        r = runner(name + "-op", answer)
        check(r.op_api() is None, f"(g) F1 {name}: the dispatcher gets no client for the chosen person")
        proj = os.path.join(tmp, name + "-proj")
        os.makedirs(proj)
        with open(os.path.join(proj, "KALMIDO-DISPATCH.json"), "w", encoding="utf-8") as f:
            json.dump({"lists": [1]}, f)
        r.agent = {"owner_id": None, "runtime": {"dispatch": "on"}}
        res = ad.Dispatcher(r, proj).tick(force=True, dry=False) or {}
        check("no request token" in str(res.get("problem")) and all(c[0] == "/agent/request-token" for c in r.calls),
              f"(g) F1 {name}: the dispatcher round reads nothing with the agent's own token {res.get('problem')} {r.calls}")
    r = runner("old-server", ar.ApiError(404, '{"error": "Not found"}'))
    check(r.run_request(ev, 5) is True and r.api.request_ok is False and r.child_env(5, None).get("KALMIDO_TOKEN") == "abk_" + "m" * 30,
          "(g) F1: an older server (404 on the route) keeps the agent's own token, as before")
    r = runner("personal", {"token": None, "expires_at": None, "asked_by": 5, "list_ids": None})
    check(r.run_request(ev, 5) is True and r.api.req_personal is True and r.child_env(5, None).get("KALMIDO_TOKEN") == "abk_" + "m" * 30,
          "(g) F1: a personal agent keeps its own token")
    r = runner("ok", {"token": "abk_" + "r" * 30, "expires_at": "2099-01-01T00:00:00Z", "asked_by": 5, "list_ids": [1]})
    check(r.run_request(ev, 5) is True and r.child_env(5, None).get("KALMIDO_TOKEN") == "abk_" + "r" * 30,
          "(g) F1: the run gets the request token only")
    r.run_api = r.api
    wake = [{"event": "job_wake", "seq": "wake-9", "data": {"user": {"id": 5}}}]
    check(r.run_request(wake, 5) is True and r.calls[-1][1] == {"seqs": [41]}, f"(g) F1: a job's wake asks with the person's last events {r.calls[-1]}")
    r.run_api = r.api  # after the run (Runner.handle)
    check("KALMIDO_TOKEN" not in r.child_env(5, None), "(g) F1: outside a request the team agent's children get no token")


_f1()

# ---------------------------------------------------------------- server
fresh(prefix="P6668")
docker_logs_on_first_fail()


def err(r):
    try:
        e = r.json()["error"]
        return e if isinstance(e, dict) else {}
    except (ValueError, KeyError, TypeError):
        return {}


assert sess().post(B + "/api/auth/setup", json={"username": "alice", "display_name": "Alice", "password": "password123"}).ok
A = sess("alice")
A.post(B + "/api/admin/setup", json={"org_name": "Example Studio", "lang": "en", "collab_all": True,
                                    "modules": ["comments", "collab"]})
FEAT = "comments,collab"
A.patch(B + "/api/settings", json={"tour": "done", "lang": "en", "features": FEAT})
ORG = A.get(B + "/api/state").json()["me"]["workspaces"][0]["id"]
check(A.put(B + "/api/admin/agent-policy", json={"user_agents": True}).ok, "setup: personal agents allowed")
uid = {}
for u, rk in (("bob", "admin"), ("carl", "member"), ("rita", "member")):
    r = A.post(B + "/api/users", json={"orgs": [{"id": ORG, "role": rk}], "username": u, "display_name": u.title(),
                                       "password": "password123", "email": f"{u}@example.com"})
    check(r.ok, f"setup: {u} as {rk} " + r.text[:200])
    uid[u] = r.json().get("id")
S = {u: sess(u) for u in uid}
Bo, Ca, Ri = S["bob"], S["carl"], S["rita"]
for s in S.values():
    s.patch(B + "/api/settings", json={"tour": "done", "lang": "en", "features": FEAT})
FID, Fr = freelancer(B, A)

r = A.post(B + "/api/admin/agents", json={"scopes": SCOPES, "username": "extbot", "display_name": "Ext Bot", "org_id": ORG})
check(r.status_code == 201, f"setup: a team agent with its own token {r.status_code} {r.text[:200]}")
XT, XTOK = r.json()["id"], r.json()["token"]
XH = {"Authorization": "Bearer " + XTOK}
check(dbx("SELECT owner_id FROM agents WHERE user_id=?", (XT,)) == [(None,)], "setup: a team agent (no owner)")
X1 = Bo.post(B + "/api/lists", json={"name": "Project one", "org_id": ORG}).json()["id"]
X2 = Bo.post(B + "/api/lists", json={"name": "Project two", "org_id": ORG}).json()["id"]
for u, role in (("carl", "edit"), ("rita", "view")):
    check(Bo.put(B + f"/api/lists/{X1}/members", json={"user_id": uid[u], "role": role}).ok, f"setup: {u} in project one ({role})")
for lid in (X1, X2):
    r = Bo.put(B + f"/api/lists/{lid}/members", json={"user_id": XT, "role": "edit", "bridge_ok": True})
    check(r.ok, f"setup: the agent in project {lid} {r.status_code} {r.text[:160]}")
    check(Bo.patch(B + f"/api/lists/{lid}", json={"agent_members": True}).ok, "setup: members may use the agent")
TX = Bo.post(B + "/api/tasks", json={"title": "Open stork task", "list_id": X1}).json()["id"]
SX = Bo.post(B + "/api/tasks", json={"title": "Secret crane budget", "list_id": X2}).json()["id"]
check(Ca.get(B + f"/api/tasks/{SX}").status_code == 404, "setup: carl does not see the task of project two")
check(requests.get(V + f"/tasks/{SX}", headers=XH, timeout=30).ok, "setup: before any request token the agent's own token reaches all (as before)")


def hdr(tok):
    return {"Authorization": "Bearer " + tok}


def seq_of(mark):
    """The seq of the agent's event whose payload carries mark (its own token, the channel)."""
    r = requests.get(V + "/agent/events", headers=XH, params={"since": 0, "limit": 500}, timeout=30)
    check(r.ok, f"the agent reads its events {r.status_code} {r.text[:160]}")
    hits = [e["seq"] for e in r.json().get("data", []) if mark in json.dumps(e)]
    check(len(hits) == 1, f"one event with {mark}: {hits}")
    return hits[0] if hits else -1


def ask(seqs=None, headers=None, **body):
    return requests.post(V + "/agent/request-token", headers=headers or XH, json={"seqs": seqs, **body} if seqs is not None else body, timeout=30)


# ================================================================ (a) a member of project one only
check(Ca.post(B + f"/api/tasks/{TX}/comments", json={"body": f"<@{XT}> CARL-ASKS tell me about the crane"}).ok, "(a) carl mentions the agent")
SC = seq_of("CARL-ASKS")
r = ask([SC])
check(r.ok and r.json().get("token") and r.json().get("asked_by") == uid["carl"] and r.json().get("list_ids") == [X1],
      f"(a) a request token for carl, cut to project one {r.status_code} {r.text[:200]}")
RC = r.json().get("token") or ""
check(dbx("SELECT asked_by, run_lists, name FROM api_tokens WHERE user_id=? AND asked_by IS NOT NULL", (XT,)) == [(uid["carl"], str(X1), "Agent request")],
      "(a) the token row carries carl and the cut")
check(requests.get(V + f"/tasks/{TX}", headers=hdr(RC), timeout=30).status_code == 200, "(a) carl's request reads the task of project one")
check(requests.get(V + f"/tasks/{SX}", headers=hdr(RC), timeout=30).status_code == 404, "(a) carl's request: the task of project two is 404")
check(SX not in [t["id"] for t in requests.get(V + "/tasks", headers=hdr(RC), params={"limit": 200}, timeout=30).json().get("data", [])],
      "(a) ... and not in the task list")
r = requests.get(V + "/agent", headers=hdr(RC), timeout=30)
check(r.ok, f"(a) the request token reaches the agent's own channel {r.status_code}")

# ================================================================ (e) the agent's own token is its channel now
check(dbx("SELECT per_request FROM agents WHERE user_id=?", (XT,)) == [(True,)], "(e) the agent works per request from the first ask on")
r = requests.get(V + f"/tasks/{SX}", headers=XH, timeout=30)
check(r.status_code == 403 and err(r).get("code") == "request_token_needed", f"(e) its own token: the content of a project 403 {r.status_code} {r.text[:160]}")
r = requests.get(V + f"/tasks/{TX}", headers=XH, timeout=30)
check(r.status_code == 403 and err(r).get("code") == "request_token_needed", f"(e) ... also of project one {r.status_code}")
check(requests.get(V + "/agent/events", headers=XH, params={"since": 0}, timeout=30).ok and requests.get(V + "/agent", headers=XH, timeout=30).ok
      and requests.get(V + "/agent/chats", headers=XH, timeout=30).ok, "(e) its own token keeps its channel: events, the agent, chats")
check(requests.put(V + "/agent/status", headers=XH, json={"status": "idle"}, timeout=30).ok, "(e) ... and its status")

# ================================================================ (b) a reader's order does not write
check(Ri.post(B + f"/api/agents/{XT}/chat", json={"body": "RITA-ASKS please comment on the stork task"}).status_code == 201, "(b) rita (reads project one) asks in the chat")
SR = seq_of("RITA-ASKS")
r = ask([SR])
check(r.ok and r.json().get("asked_by") == uid["rita"] and r.json().get("list_ids") == [X1], f"(b) a request token for rita {r.status_code} {r.text[:200]}")
RR = r.json().get("token") or ""
check(requests.get(V + f"/tasks/{TX}", headers=hdr(RR), timeout=30).ok, "(b) rita's request reads the task she reads herself")
r = requests.post(V + f"/tasks/{TX}/comments", headers=hdr(RR), json={"body": "FOR-RITA"}, timeout=30)
check(r.status_code == 409 and err(r).get("code") == "approval_required", f"(b) the agent (role edit) writes no comment for the reader: a card {r.status_code} {r.text[:200]}")
check(not dbx("SELECT 1 FROM obj_comments WHERE kind='task' AND ref_id=? AND body='FOR-RITA'", (TX,)), "(b) ... nothing written")
ap = err(r).get("approval") or {}
STEP = {k: ap[k] for k in ("method", "path", "body", "if_match") if k in ap}
r = requests.post(V + f"/tasks/{TX}/comments", headers=hdr(RC), json={"body": "FOR-CARL"}, timeout=30)
check(r.status_code == 201, f"(b) carl's request (he writes there) comments {r.status_code} {r.text[:200]}")

# ---- (e) the card of rita's order: carl (writes there) says Yes, the agent runs it with its own token
m = requests.post(V + f"/agent/chats/{uid['carl']}", headers=XH, json={"approval": {"title": "Comment for Rita?", "step": STEP}}, timeout=30)
check(m.status_code == 201, f"(e) its own token sends the card (its channel) {m.status_code} {m.text[:200]}")
MID = m.json().get("id")
check(Ca.post(B + f"/api/agents/{XT}/chat/{MID}/choice", json={"choice_ids": ["yes"]}).ok, "(e) carl says Yes")
r = requests.post(V + f"/agent/approvals/{MID}/run", headers=XH, timeout=60)
check(r.status_code == 201 and dbx("SELECT COUNT(*) FROM obj_comments WHERE kind='task' AND ref_id=? AND body='FOR-RITA'", (TX,)) == [(1,)],
      f"(e) the approved step runs with the agent's own token (the replay) {r.status_code} {r.text[:200]}")

# ---- (i) review F3: the step of a card with the own token always checks the person who said Yes (no control level chosen)
# Without the fix a Yes of a reader ran with the agent's whole reach (a card's step is always a change: approval.step).
m = requests.post(V + f"/agent/chats/{uid['rita']}", headers=XH, json={"approval": {"title": "Comment by Rita's Yes?", "step":
                  {"method": "POST", "path": f"/api/v1/tasks/{TX}/comments", "body": {"body": "RITA-SAID-YES"}}}}, timeout=30)
check(m.status_code == 201, f"(i) a card to rita {m.status_code} {m.text[:200]}")
check(Ri.post(B + f"/api/agents/{XT}/chat/{m.json().get('id')}/choice", json={"choice_ids": ["yes"]}).ok, "(i) rita (reads only) says Yes")
r = requests.post(V + f"/agent/approvals/{m.json().get('id')}/run", headers=XH, timeout=60)
check(r.status_code == 409 and err(r).get("reason") in ("approver_rights", None) and err(r).get("code") == "approval_invalid",
      f"(i) the reader's Yes runs no change in project one {r.status_code} {r.text[:200]}")
check(not dbx("SELECT 1 FROM obj_comments WHERE kind='task' AND ref_id=? AND body='RITA-SAID-YES'", (TX,)), "(i) ... nothing written")

# ================================================================ (c) an event without a person
payload = {"id": str(uuid.uuid4()), "event": "followup_due", "agent_id": XT, "actor": None, "via": "web",
           "data": {"task": {"id": TX, "list_id": X1}, "list_id": X1, "note": "NOBODY-ASKS"}}
SN = dbx("INSERT INTO agent_events(agent_id, uuid, event, payload, created_at) VALUES(?,?,?,CAST(? AS jsonb),now()) RETURNING id",
         (XT, payload["id"], "followup_due", json.dumps(payload)))[0][0]
r = ask([SN])
check(r.ok and r.json().get("asked_by") is None and r.json().get("list_ids") == [X1], f"(c) a request token without a person: its project only {r.status_code} {r.text[:200]}")
RN = r.json().get("token") or ""
check(dbx("SELECT asked_by FROM api_tokens WHERE user_id=? AND asked_by=0", (XT,)) == [(0,)], "(c) the token row: a request without a person (0)")
check(requests.get(V + f"/tasks/{TX}", headers=hdr(RN), timeout=30).ok, "(c) reads the task of its project")
check(requests.get(V + f"/tasks/{SX}", headers=hdr(RN), timeout=30).status_code == 404, "(c) the other project 404")
r = requests.post(V + f"/tasks/{TX}/comments", headers=hdr(RN), json={"body": "FROM-NOBODY"}, timeout=30)
check(r.status_code == 409 and err(r).get("code") == "approval_required", f"(c) every change is a card (no control level chosen) {r.status_code} {r.text[:200]}")
check(not dbx("SELECT 1 FROM obj_comments WHERE kind='task' AND ref_id=? AND body='FROM-NOBODY'", (TX,)), "(c) ... nothing written")
dbx("UPDATE agent_events SET created_at=now() - interval '25 hours' WHERE id=?", (SN,))
r = ask([SN])
check(r.status_code == 404 and err(r).get("code") == "event_gone", f"(c) review F4: an event older than 24 h gives no request token {r.status_code}")

# ================================================================ (d) what is refused
r = ask([SC, SR])
check(r.status_code == 400 and err(r).get("code") == "several_people", f"(d) events of two people: 400 {r.status_code} {r.text[:160]}")
r = requests.post(V + "/agent/request-token", headers=hdr(RC), json={"seqs": [SC]}, timeout=30)
check(r.status_code == 403 and err(r).get("code") == "request_token_main", f"(d) a request token asks for no other one {r.status_code}")
r = Ca.post(B + "/api/v1/agent/request-token", json={"seqs": [SC]})
check(r.status_code in (401, 403), f"(d) a person (no agent) gets none {r.status_code}")
r = ask([SC + 100000])
check(r.status_code == 404 and err(r).get("code") == "event_gone", f"(d) an unknown event 404 {r.status_code}")
r = A.post(B + "/api/admin/agents", json={"scopes": SCOPES, "username": "otherbot", "display_name": "Other Bot", "org_id": ORG})
check(r.status_code == 201, f"setup: another team agent {r.status_code}")
YT, YH = r.json().get("id"), {"Authorization": "Bearer " + r.json().get("token", "")}
r = requests.post(V + "/agent/request-token", headers=YH, json={"seqs": [SC]}, timeout=30)
check(r.status_code == 404 and not r.json().get("token"), f"(d) another agent gets no token for this agent's event (404) {r.status_code}")
r = requests.post(V + "/agent/request-token", headers=YH, json={"seqs": []}, timeout=30)
check(r.status_code == 400, f"(d) no event: 400 {r.status_code}")
check(dbx("SELECT per_request FROM agents WHERE user_id=?", (YT,)) == [(False,)],
      "(d) review F5: refused asks never switch an agent to per request (only an issued request token does)")
r = ask(None, operator=True)
check(r.status_code == 409 and err(r).get("code") == "no_operator", f"(d) nobody chosen for its questions: 409 {r.status_code} {r.text[:160]}")
r = ask([])
check(r.status_code == 400, f"(d) no event: 400 {r.status_code}")
dbx("UPDATE api_tokens SET expires_at=now() - interval '1 minute' WHERE user_id=? AND asked_by=?", (XT, uid["carl"]))
r = requests.get(V + f"/tasks/{TX}", headers=hdr(RC), timeout=30)
check(r.status_code == 401, f"(d) carl's expired request token is refused {r.status_code}")
r = ask([SC])
check(r.ok and not dbx("SELECT 1 FROM api_tokens WHERE user_id=? AND asked_by=? AND expires_at<now()", (XT, uid["carl"])),
      "(d) the next ask clears the expired request tokens")
XA = [a for a in A.get(B + "/api/admin/agents").json().get("agents", []) if a.get("id") == XT]
check(XA and XA[0].get("tokens") and not any(t.get("name") == "Agent request" for t in XA[0]["tokens"]),
      "(d) request tokens are not listed with the agent's tokens")

# ================================================================ (h) review F2: removing the computer ends its request tokens
# Without the fix the request tokens fetched with a removed computer's token lived on for up to 8 h, unlisted and unrevocable.
RC2 = r.json().get("token") or ""
check(requests.get(V + f"/tasks/{TX}", headers=hdr(RC2), timeout=30).ok, "(h) carl's new request token works")
MT = [t["id"] for t in XA[0]["tokens"]] if XA else []
check(len(MT) == 1, f"(h) the agent has one computer (its own token) {MT}")
r = A.delete(B + f"/api/admin/agents/{XT}/machines/{MT[0] if MT else 0}")
check(r.ok, f"(h) the admin removes the computer {r.status_code} {r.text[:160]}")
check(requests.get(V + f"/tasks/{TX}", headers=hdr(RC2), timeout=30).status_code == 401,
      "(h) the request token fetched with it is refused (401)")
check(not dbx("SELECT 1 FROM api_tokens WHERE user_id=? AND name='Agent request'", (XT,)), "(h) no request token of the agent is left")

# ================================================================ the person without an organisation loses nothing
r = Fr.post(B + "/api/my/agents", json={"username": "fridabot", "display_name": "Fridabot", "scopes": SCOPES})
check(r.status_code in (200, 201), f"freelancer: her personal agent {r.status_code} {r.text[:160]}")
FA, FH = r.json()["id"], {"Authorization": "Bearer " + r.json()["token"]}
FL = Fr.post(B + "/api/lists", json={"name": "Frida work"}).json()["id"]
check(Fr.put(B + f"/api/lists/{FL}/members", json={"user_id": FA, "role": "edit"}).ok, "freelancer: her project is shared with her agent")
FT = Fr.post(B + "/api/tasks", json={"title": "Frida's task", "list_id": FL}).json()["id"]
r = requests.post(V + "/agent/request-token", headers=FH, json={"seqs": [1]}, timeout=30)
check(r.ok and r.json().get("token") is None and r.json().get("asked_by") == FID, f"freelancer: her personal agent needs no request token {r.status_code} {r.text[:160]}")
check(dbx("SELECT per_request FROM agents WHERE user_id=?", (FA,)) == [(False,)], "freelancer: her agent does not switch to per request")
check(requests.get(V + f"/tasks/{FT}", headers=FH, timeout=30).ok, "freelancer: her agent's own token reaches her project as before")
r = requests.post(V + f"/tasks/{FT}/comments", headers=FH, json={"body": "from her agent"}, timeout=30)
check(r.status_code == 201, f"freelancer: her agent comments in her project {r.status_code} {r.text[:160]}")

raise SystemExit(done("p6668_ext_team_agent"))
