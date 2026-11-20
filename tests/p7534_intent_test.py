#!/usr/bin/env python3
# kalmido-suite: fresh
"""(#7534): the kind of a person's text to an agent -- question, instruction, proposal or note -- on a task comment and a chat
message. Invented people only, as a person WITHOUT an organisation and a personal agent (freelancer-matrix: agents).
 - a comment on a task the agent hears carries intent (stored in the core comment's extra); the 'comment' event has
   comment.intent; the timeline names the agents that hear the task (hears) and the comment awaiting = [the agent]
 - an answer of the agent with reply_to = the comment closes it (awaiting [], answer = its id); a later comment without
   the reference does not
 - a note sends no event (no run), the agent reads it with the task (task.comments[].intent)
 - an unknown kind: 400; an agent's own comment with a kind: 400; no kind: as before (no field)
 - the chat: intent on the message and the 'chat' event; awaiting until the agent answers it with reply_to; a note sends no
   'chat' event; unknown 400
usage: p7534_intent_test.py <datadir>"""
import json
import sys
import time

import requests
import kt
from freelancer_fixture import freelancer
from kt import B, check, done, fresh, setup

V = B + "/api/v1"
fresh(prefix="P7534")
A = setup()
A.patch(B + "/api/settings", json={"lang": "en", "tour": "done"})
assert A.put(B + "/api/admin/agent-policy", json={"user_agents": True}).ok  # personal agents on (as p6453_circle)
FID, F = freelancer(B, A)
r = F.post(B + "/api/my/agents", json={"username": "helfer", "display_name": "Helfer", "scopes": ["read", "tasks:write", "comments"]})
assert r.status_code in (200, 201), r.text
AID, H = r.json()["id"], {"Authorization": "Bearer " + r.json()["token"]}
LID = F.post(B + "/api/lists", json={"name": "Garten"}).json()["id"]
assert F.put(B + f"/api/lists/{LID}/members", json={"user_id": AID, "role": "edit"}).ok
TID = F.post(B + "/api/tasks", json={"title": "Hecke schneiden", "list_id": LID}).json()["id"]
T2 = F.post(B + "/api/tasks", json={"title": "Ohne Agent", "list_id": LID}).json()["id"]
r = F.patch(B + f"/api/tasks/{TID}", json={"assignee_id": AID})
check(r.ok, f"setup: the task assigned to the agent {r.status_code} {r.text[:200]}")


def cursor():
    return requests.get(V + "/agent/events", headers=H, params={"since": "latest"}).json().get("cursor")


def events(since, want, secs=6.0):
    """The agent's events of the kinds want after since (waits up to secs for at least one)."""
    t0, out = time.time(), []
    while time.time() - t0 < secs:
        j = requests.get(V + "/agent/events", headers=H, params={"since": since}).json()
        out = [e for e in j.get("data", []) if e["event"] in want]
        if out:
            return out
        time.sleep(0.3)
    return out


def tl(tid=TID):
    return F.get(B + f"/api/tasks/{tid}/timeline").json()


def cm(j, cid):
    return next((x for x in j.get("comments", []) if x["id"] == cid), {})


# ---------------------------------------------------------------- comments
j = tl()
check(j.get("hears") == [AID], f"the timeline names the agent that hears the task {j.get('hears')}")
check(tl(T2).get("hears") == [], f"a task the agent does not follow: nobody hears it {tl(T2).get('hears')}")
cur = cursor()
r = F.post(B + f"/api/tasks/{TID}/comments", json={"body": "Wie hoch soll die Hecke bleiben?", "intent": "question"})
check(r.status_code in (200, 201) and r.json().get("intent") == "question", f"a question to the agent {r.status_code} {r.text[:200]}")
Q = r.json().get("id", 0)
ev = events(cur, {"comment"})
c0 = (ev[0]["data"].get("comment") or {}) if ev else {}
check(c0.get("id") == Q and c0.get("intent") == "question", f"the comment event carries intent {c0}")
row = kt.dbx("SELECT extra->>'intent', extra->'intent_to' FROM obj_comments WHERE id=?", (Q,))
check(row and row[0][0] == "question" and (json.loads(row[0][1]) if isinstance(row[0][1], str) else row[0][1]) == [AID], f"stored in the core comment's extra (intent, intent_to) {row}")
x = cm(tl(), Q)
check(x.get("intent") == "question" and x.get("awaiting") == [AID] and x.get("answer") is None, f"open: waiting for the agent {x}")
# a later text of the agent without the reference does not close it
r = requests.post(V + f"/tasks/{TID}/comments", headers=H, json={"body": "Ich schaue es mir an"})
check(r.status_code in (200, 201), f"the agent comments without reply_to {r.status_code} {r.text[:200]}")
check(cm(tl(), Q).get("awaiting") == [AID], "a comment without the reference leaves it open")
r = requests.post(V + f"/tasks/{TID}/comments", headers=H, json={"body": "1,80 m", "reply_to": Q})
check(r.status_code in (200, 201), f"the agent answers with reply_to {r.status_code} {r.text[:200]}")
ANS = r.json().get("id")
x = cm(tl(), Q)
check(x.get("awaiting") == [] and x.get("answer") == ANS, f"answered: no longer waiting, the answer as reference {x}")
v1 = next((y for y in requests.get(V + f"/tasks/{TID}/comments", headers=H).json().get("data", []) if y["id"] == Q), {})
check(v1.get("intent") == "question" and v1.get("awaiting") == [] and v1.get("answer") == ANS, f"the API shows the same {v1}")
# a note: no event, no run; the agent reads it with the task
cur = cursor()
r = F.post(B + f"/api/tasks/{TID}/comments", json={"body": "Nur zur Info: Schere liegt im Schuppen", "intent": "note"})
check(r.status_code in (200, 201) and r.json().get("intent") == "note" and r.json().get("awaiting") == [], f"a note {r.status_code} {r.text[:200]}")
NOTE = r.json().get("id", 0)
r = F.post(B + f"/api/tasks/{TID}/comments", json={"body": "Bitte bis Freitag", "intent": "instruction"})
INS = r.json().get("id", 0)
ev = events(cur, {"comment", "mention"})
ids = [(e["data"].get("comment") or {}).get("id") for e in ev]
check(INS in ids and NOTE not in ids, f"the note sends no event, the instruction does {ids}")
tc = (ev[-1]["data"].get("task") or {}).get("comments") or [] if ev else []
check(any(y["id"] == NOTE and y.get("intent") == "note" for y in tc), "the agent reads the note with the task (task.comments)")
check(cm(tl(), NOTE).get("awaiting") == [] and cm(tl(), INS).get("awaiting") == [AID], "a note is never open, the instruction is")
# a note that mentions the agent: no event either
cur = cursor()
F.post(B + f"/api/tasks/{TID}/comments", json={"body": f"<@{AID}> zur Kenntnis", "intent": "note"})
F.post(B + f"/api/tasks/{TID}/comments", json={"body": "Danke"})
ev = events(cur, {"comment", "mention"})
check(ev and all(e["event"] == "comment" and (e["data"].get("comment") or {}).get("body") == "Danke" for e in ev),
      f"a note with a mention: no event either {[e['event'] for e in ev]}")
# input
r = F.post(B + f"/api/tasks/{TID}/comments", json={"body": "x", "intent": "order"})
check(r.status_code == 400, f"an unknown kind: 400 {r.status_code}")
r = F.post(B + f"/api/tasks/{TID}/comments", json={"body": "x", "intent": 3})
check(r.status_code == 400, f"a kind that is no text: 400 {r.status_code}")
r = requests.post(V + f"/tasks/{TID}/comments", headers=H, json={"body": "x", "intent": "question"})
check(r.status_code == 400, f"an agent's own comment has no kind: 400 {r.status_code}")
r = F.post(B + f"/api/tasks/{TID}/comments", data={"body": "mit Datei", "intent": "proposal"}, files={"file": ("a.txt", b"hallo", "text/plain")})
check(r.status_code in (200, 201) and r.json().get("intent") == "proposal", f"a comment with a file takes the kind too {r.status_code} {r.text[:200]}")
r = F.post(B + f"/api/tasks/{TID}/comments", json={"body": "ohne Art"})
check(r.status_code in (200, 201) and "intent" not in r.json(), "no kind: as before (no field)")

# ---------------------------------------------------------------- the agent chat
cur = cursor()
r = F.post(B + f"/api/agents/{AID}/chat", json={"body": "Soll ich Thuja nehmen?", "intent": "proposal"})
check(r.status_code == 201 and r.json().get("intent") == "proposal" and r.json().get("awaiting") is True, f"a proposal in the chat {r.status_code} {r.text[:200]}")
MID = r.json().get("id", 0)
ev = events(cur, {"chat"})
d = ev[0]["data"] if ev else {}
check(d.get("intent") == "proposal" and (d.get("message") or {}).get("intent") == "proposal", f"the chat event carries intent {d.get('intent')}")
r = requests.post(V + f"/agent/chats/{FID}", headers=H, json={"body": "Lieber Hainbuche", "reply_to": MID})
check(r.status_code == 201, f"the agent answers with reply_to {r.status_code} {r.text[:200]}")
AM = r.json().get("id")
msgs = F.get(B + f"/api/agents/{AID}/chat").json().get("messages") or []
m = next((y for y in msgs if y["id"] == MID), {})
check(m.get("awaiting") is False and m.get("answer") == AM, f"answered in the chat {m.get('awaiting')} {m.get('answer')}")
cur = cursor()
r = F.post(B + f"/api/agents/{AID}/chat", json={"body": "Merke dir: Kompost hinten links", "intent": "note"})
check(r.status_code == 201 and r.json().get("awaiting") is False, f"a note in the chat {r.status_code}")
F.post(B + f"/api/agents/{AID}/chat", json={"body": "Wann kommst du dazu?", "intent": "question"})
ev = events(cur, {"chat"})
check([(e["data"].get("message") or {}).get("intent") for e in ev] == ["question"], f"a chat note sends no event {[e['data'].get('intent') for e in ev]}")
check(F.post(B + f"/api/agents/{AID}/chat", json={"body": "x", "intent": "befehl"}).status_code == 400, "the chat: an unknown kind 400")
seen = requests.get(V + "/agent/chats", headers=H).json().get("data") or []
check(any(y.get("intent") == "note" for y in seen), "the agent reads the note with its conversation")

sys.exit(done("p7534_intent"))
