#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1239.0 (#6261): run_meta -- which model wrote an agent's chat message ({model, effort, klasse, grund}), shown as a small
grey text under the bubble. Invented names only.
 - API v1 POST /api/v1/agent/chats/<uid>: run_meta stored and given back in the answer (the service learns the app keeps it),
   in the person's chat (GET /api/agents/<id>/chat) and in the agent's own read; unknown keys and non-text values dropped,
   spaces folded, texts cut to 80 characters; {} / only unknown keys -> null; not an object (a list, a number, broken JSON
   text) -> 400 and no message; a message without it: null; a multipart form carries it as JSON text; a job message
   (job_id) keeps it too
 - the person's own messages never carry it (null)
 - MCP send_chat: run_meta in its schema, sent through (JSON and with files)
 - freelancer-matrix: agents (a person without an organisation, her personal agent sends run_meta; she gets it)
usage: p21239_runmeta_test.py <datadir>"""
import importlib.util
import json
import os
import sys

import requests

import kt
from kt import B, check, sess
from freelancer_fixture import freelancer

V = B + "/api/v1"
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

kt.fresh()
s0 = sess()
assert s0.post(B + "/api/auth/setup", json={"username": "alice", "display_name": "Alice", "password": "password123"}).ok
A = sess("alice")
A.post(B + "/api/admin/setup", json={"org_name": "Alpha", "lang": "en", "collab_all": True, "modules": ["comments"]})
A.patch(B + "/api/settings", json={"lang": "en", "tour": "done"})
ME = A.get(B + "/api/state").json()["me"]
ORG = ME["workspaces"][0]["id"]


def bearer(tok):
    s = requests.Session()
    s.headers.update({"Authorization": "Bearer " + tok})
    return s


def agent(name, org=None, owner=None):
    body = {"scopes": ["read", "tasks:write", "comments"], "username": name, "display_name": name.title(), "org_id": org}
    if owner:
        body["owner_id"] = owner
    r = A.post(B + "/api/admin/agents", json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"], r.json()["token"]


AID, AGT = agent("modelbot", org=ORG)
ag = bearer(AGT)
L = A.post(B + "/api/lists", json={"name": "Models", "org_id": ORG}).json()["id"]
assert A.put(B + f"/api/lists/{L}/members", json={"user_id": AID, "role": "edit"}).ok


def say(t, uid, **kw):
    return t.post(V + f"/agent/chats/{uid}", json={"body": "Answer.", **kw})


def person_chat(s, aid):
    return s.get(B + f"/api/agents/{aid}/chat").json().get("messages") or []


def pm(s, aid, mid):
    return next((x for x in person_chat(s, aid) if x["id"] == mid), {})


# ---------------------------------------------------------------- refused: only an object
n0 = len(person_chat(A, AID))
for what, v in (("a list", [{"model": "Fable 5.2"}]), ("a number", 5), ("a bare text", "Fable 5.2"), ("broken JSON text", "{\"model\":")):
    r = say(ag, ME["id"], run_meta=v)
    check(r.status_code == 400, f"run_meta {what}: 400 ({r.status_code} {r.text[:120]})")
check(len(person_chat(A, AID)) == n0, "no refused message reached the chat")

# ---------------------------------------------------------------- stored and delivered
FULL = {"model": "Fable 5.2", "effort": "high", "klasse": "gross", "grund": "a security area"}
r = say(ag, ME["id"], run_meta=FULL)
check(r.status_code == 201, f"run_meta: 201 ({r.status_code} {r.text[:200]})")
m = r.json() if r.ok else {}
check(m.get("run_meta") == FULL, f"the answer gives run_meta back (the service knows the app keeps it) {m.get('run_meta')}")
check(pm(A, AID, m.get("id")).get("run_meta") == FULL, "the person's chat carries it")
rows = ag.get(V + "/agent/chats", params={"user_id": ME["id"]}).json().get("data") or []
check(next((x for x in rows if x["id"] == m.get("id")), {}).get("run_meta") == FULL, "the agent reads it back")

r = say(ag, ME["id"], run_meta={"model": "  Opus   5.5 ", "klasse": "klein", "effort": "", "grund": "x" * 200, "secret": "nope", "cost": 3, "effort2": "high"})
check(r.status_code == 201, f"unknown keys and odd values: still 201 ({r.status_code} {r.text[:160]})")
check(r.ok and r.json().get("run_meta") == {"model": "Opus 5.5", "klasse": "klein", "grund": "x" * 80},
      f"unknown keys and non-text values dropped, spaces folded, empty dropped, cut to 80 {r.json().get('run_meta') if r.ok else ''}")
for what, v in (("an empty object", {}), ("only unknown keys", {"foo": "bar"}), ("only empty texts", {"model": " "})):
    r = say(ag, ME["id"], run_meta=v)
    check(r.status_code == 201 and r.json().get("run_meta") is None, f"{what}: 201, run_meta null ({r.status_code})")
plain = say(ag, ME["id"]).json()
check(plain.get("run_meta") is None and pm(A, AID, plain["id"]).get("run_meta") is None, "a message without run_meta: null on both sides")
r = ag.post(V + f"/agent/chats/{ME['id']}", data={"body": "With a form.", "run_meta": json.dumps({"model": "Opus 5.5", "effort": "medium"})},
            files={"file": ("note.txt", b"hello", "text/plain")})
check(r.status_code == 201 and r.json().get("run_meta") == {"model": "Opus 5.5", "effort": "medium"}, f"multipart: run_meta as JSON text ({r.status_code} {r.text[:160]})")

# a job message keeps it
j = ag.post(V + "/agent/jobs", json={"title": "Model job", "user_id": ME["id"]})
if j.status_code in (200, 201):
    jid = j.json()["id"]
    r = say(ag, ME["id"], job_id=jid, job_msg="result", run_meta={"model": "Opus 5.5", "effort": "high"})
    check(r.status_code == 201 and r.json().get("job_id") == jid and r.json().get("run_meta") == {"model": "Opus 5.5", "effort": "high"},
          f"a job message keeps run_meta ({r.status_code} {r.text[:160]})")
else:
    check(False, f"a job for the job message ({j.status_code} {j.text[:160]})")

# the person's messages never carry it
r = A.post(B + f"/api/agents/{AID}/chat", json={"body": "Hello"})
check(r.ok and r.json().get("run_meta") is None, f"the person's own message: run_meta null ({r.status_code})")
r = A.post(B + f"/api/agents/{AID}/chat", json={"body": "Hello", "run_meta": FULL})
check(r.status_code == 400 or (r.ok and r.json().get("run_meta") is None), f"a person cannot set it ({r.status_code})")

# ---------------------------------------------------------------- MCP send_chat
sp = importlib.util.spec_from_file_location("kalmido_mcp_t", os.path.join(ROOT, "mcp", "kalmido_mcp.py"))
mcp = importlib.util.module_from_spec(sp)
sp.loader.exec_module(mcp)
api = mcp.Kalmido(B, AGT)
schema = mcp.TOOL_MAP["send_chat"][2]
check(schema["properties"].get("run_meta", {}).get("type") == "object", "MCP send_chat: run_meta in the schema")
r = mcp.TOOL_MAP["send_chat"][3](api, {"user_id": ME["id"], "body": "Via MCP.", "run_meta": {"model": "Fable 5.2", "effort": "xhigh"}})
check(r.get("run_meta") == {"model": "Fable 5.2", "effort": "xhigh"}, f"MCP send_chat: run_meta sent {r.get('run_meta')}")
r = mcp.TOOL_MAP["send_chat"][3](api, {"user_id": ME["id"], "body": "Via MCP with a file.", "run_meta": {"model": "Opus 5.5"},
                                        "files": [{"name": "a.txt", "base64": "aGk="}]})
check(r.get("run_meta") == {"model": "Opus 5.5"}, f"MCP send_chat with files: run_meta as JSON in the form {r.get('run_meta')}")

# ================================================================ a person without an organisation
# freelancer-matrix: agents
FID, Fl = freelancer(B, A)
FAID, FAGT = agent("fridabot", owner=FID)
fa = bearer(FAGT)
r = say(fa, FID, run_meta={"model": "Opus 5.5", "klasse": "klein"})
check(r.status_code == 201, f"her personal agent sends run_meta: 201 ({r.status_code} {r.text[:160]})")
check(pm(Fl, FAID, r.json().get("id") if r.ok else 0).get("run_meta") == {"model": "Opus 5.5", "klasse": "klein"}, "she gets it in her chat")
check(say(fa, FID, run_meta=[1]).status_code == 400, "her agent: not an object 400")

sys.exit(kt.done("p21239_runmeta"))
