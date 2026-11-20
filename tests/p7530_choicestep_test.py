#!/usr/bin/env python3
# kalmido-suite: fresh
"""(#7530): answer buttons with a bound step -- an option of an agent's question carries `do` (section, state, wont, park,
wait, tag); Kalmido runs it after the person's click with the person's rights, once, only on the task of the question.
Invented people only, as people WITHOUT an organisation and a personal agent (freelancer-matrix: agents).
 - posting: another object in the step (task_id, a column of another project), an unknown kind, a missing reason, multi
   with a step, a chat message with a step but no task: 400; the stored option keeps its step (the column's name)
 - a person who may not change the task (a viewer): 403, nothing stored, nothing changed
 - every step: section, state done / in_progress, wont, park, wait, tag; the answer and the task's history name the step,
   the agent's event carries answer.step
 - exactly once: a second click 409, the history has one answer
 - a task that moved on (a job works on it / done): the answer is stored and reaches the agent, the state stays, step skipped
 - an answer in words: the question leaves "Waiting for me" (kind question), its buttons stay answerable
 - the chat: a step on the message's task, the same rules
usage: p7530_choicestep_test.py <datadir>"""
import sys
import time

import requests
import kt
from freelancer_fixture import freelancer
from kt import B, check, done, fresh, setup
from testclock import now

V = B + "/api/v1"
fresh(prefix="P7530")
A = setup()
A.patch(B + "/api/settings", json={"lang": "en", "tour": "done"})
assert A.put(B + "/api/admin/agent-policy", json={"user_agents": True}).ok
FID, F = freelancer(B, A)
OID, OT = freelancer(B, A, "otto")
r = F.post(B + "/api/my/agents", json={"username": "planer", "display_name": "Planer", "scopes": ["read", "tasks:write", "comments"]})
assert r.status_code in (200, 201), r.text
AID, H = r.json()["id"], {"Authorization": "Bearer " + r.json()["token"]}
TS = now().isoformat(timespec="seconds")


def project(name):
    lid = F.post(B + "/api/lists", json={"name": name}).json()["id"]
    assert F.put(B + f"/api/lists/{lid}/members", json={"user_id": AID, "role": "edit"}).ok
    # otto reads both projects (view): the same circle of people in both, the circle rule stays quiet
    kt.dbx("INSERT INTO list_members(list_id,user_id,role,added_at) VALUES(?,?,'view',?) ON CONFLICT DO NOTHING", (lid, OID, TS))
    return lid


L, L2 = project("Umzug"), project("Anderes")
S1 = F.post(B + "/api/sections", json={"list_id": L, "name": "In Arbeit"}).json()["id"]
SX = F.post(B + "/api/sections", json={"list_id": L2, "name": "Fremd"}).json()["id"]


def task(title, lid=L):
    t = F.post(B + "/api/tasks", json={"title": title, "list_id": lid}).json()["id"]
    assert F.patch(B + f"/api/tasks/{t}", json={"assignee_id": AID}).ok
    return t


def ask(tid, choices, **kw):
    return requests.post(V + f"/tasks/{tid}/comments", headers=H, json={"body": "Wie weiter?", "choices": choices, **kw})


def row(tid):
    return kt.dbx("SELECT status, section_id, delivery, delivery_note, wait_until FROM tasks WHERE id=?", (tid,))[0]


def click(s, cid, ids):
    return s.post(B + f"/api/comments/{cid}/choice", json={"choice_ids": ids})


def cursor():
    return requests.get(V + "/agent/events", headers=H, params={"since": "latest"}).json().get("cursor")


def events(since, want, secs=6.0):
    t0, out = time.time(), []
    while time.time() - t0 < secs:
        out = [e for e in requests.get(V + "/agent/events", headers=H, params={"since": since}).json().get("data", []) if e["event"] in want]
        if out:
            return out
        time.sleep(0.3)
    return out


T = task("Kisten packen")
TX = task("Fremde Aufgabe", L2)
# ---------------------------------------------------------------- posting: only the fixed list, only this task
for do, why in (({"kind": "state", "state": "done", "task_id": TX}, "a step naming another task"),
                ({"kind": "section", "section_id": SX}, "a column of another project"),
                ({"kind": "delete"}, "an unknown kind"), ({"kind": "wont"}, "wont without a reason"),
                ({"kind": "wait", "until": "morgen"}, "wait without a day"), ({"kind": "state", "state": "done", "path": "/tasks/1"}, "a path"),
                ({}, "an empty step (reader F3)"), ([], "an empty list as step (reader F3)")):
    r = ask(T, [{"id": "a", "label": "A", "do": do}, {"id": "b", "label": "B"}])
    check(r.status_code == 400, f"posting: {why} -> 400 ({r.status_code} {r.text[:160]})")
r = ask(T, [{"id": "a", "label": "A", "do": {"kind": "state", "state": "done"}}, {"id": "b", "label": "B"}], multi=True)
check(r.status_code == 400, f"posting: multi with a step -> 400 ({r.status_code})")
r = requests.post(V + f"/agent/chats/{FID}", headers=H, json={"body": "Fertig?", "choices": [{"id": "a", "label": "Ja", "do": {"kind": "state", "state": "done"}}]})
check(r.status_code == 400, f"the chat: a step without the message's task -> 400 ({r.status_code} {r.text[:160]})")

r = ask(T, [{"id": "col", "label": "Anfangen", "do": {"kind": "section", "section_id": S1}},
            {"id": "keep", "label": "So lassen", "do": {"kind": "wont", "reason": "erledigt sich von selbst"}}, {"id": "talk", "label": "Später reden"}])
check(r.status_code == 201, f"a question with steps {r.status_code} {r.text[:200]}")
Q = r.json().get("id", 0)
ch = (r.json().get("choices") or {}).get("choices") or []
check(ch and ch[0].get("do") == {"kind": "section", "section_id": S1, "name": "In Arbeit"} and "do" not in ch[2],
      f"the stored options keep their step (the column's name for the label), 'answer only' has none {ch}")
# ---------------------------------------------------------------- rights: a viewer gets 403, nothing stored
r = click(OT, Q, ["col"])
check(r.status_code == 403 and row(T)[1] is None, f"a person who may not change the task: 403, nothing changed ({r.status_code})")
check(kt.dbx("SELECT extra->'choice' FROM obj_comments WHERE id=?", (Q,))[0][0] is None, "nothing stored")
# ---------------------------------------------------------------- the click: the step runs once, as the person
cur = cursor()
r = click(F, Q, ["col"])
check(r.ok and row(T)[1] == S1, f"the column step ran {r.status_code} {r.text[:200]} {row(T)}")
st = (r.json().get("choice") or {}).get("step") or {}
check(st.get("kind") == "section" and st.get("state") == "done", f"the answer names the step {st}")
ev = events(cur, {"comment"})
ans = (ev[0]["data"].get("answer") or {}) if ev else {}
check((ans.get("step") or {}).get("state") == "done" and ans.get("choice_ids") == ["col"], f"the agent hears the answer with its step {ans}")
r2 = click(F, Q, ["keep"])
check(r2.status_code == 409 and row(T)[0] == 0, f"a second click: 409, its step never runs ({r2.status_code} {row(T)})")
acts = kt.dbx("SELECT data FROM activity WHERE task_id=? AND kind='choice'", (T,))
check(len(acts) == 1 and '"step"' in str(acts[0][0]), f"the history: one answer with its step {acts}")

# ---------------------------------------------------------------- every step kind
for do, check_row, why in (({"kind": "state", "state": "done"}, lambda x: x[0] == 2, "done"),
                           ({"kind": "state", "state": "in_progress"}, lambda x: x[2] == "in_progress", "in progress"),
                           ({"kind": "wont", "reason": "zu teuer"}, lambda x: x[0] == -1, "will not be done"),
                           ({"kind": "park", "reason": "nach dem Urlaub"}, lambda x: x[2] == "parked" and x[3] == "nach dem Urlaub", "parked"),
                           ({"kind": "wait", "until": "2030-01-15", "note": "Vermieter"}, lambda x: str(x[4]) == "2030-01-15", "waiting until a day")):
    t = task("Schritt " + why)
    q = ask(t, [{"id": "go", "label": "Los", "do": do}, {"id": "no", "label": "Nein"}]).json().get("id")
    r = click(F, q, ["go"])
    check(r.ok and check_row(row(t)), f"step {why}: ran ({r.status_code} {r.text[:160]} {row(t)})")
t = task("Schritt Markierung")
# reader F14: only a tag the project has - an unknown name is refused when posted, a click never makes a new project tag
r = ask(t, [{"id": "go", "label": "Markieren", "do": {"kind": "tag", "tag": "Kunde"}}])
check(r.status_code == 400 and "Kunde" in r.text, f"F14: a tag the project does not have: 400 ({r.status_code} {r.text[:160]})")
assert F.patch(B + f"/api/tasks/{task('Mit Markierung')}", json={"ltags": ["Kunde"]}).ok  # the project's tag, made by its owner
q = ask(t, [{"id": "go", "label": "Markieren", "do": {"kind": "tag", "tag": "Kunde"}}]).json().get("id")
r = click(F, q, ["go"])
check(r.ok and "Kunde" in (F.get(B + f"/api/tasks/{t}").json().get("ltags") or []), f"step tag: the project's tag is on the task ({r.status_code})")
t = task("Nur Antwort")
q = ask(t, [{"id": "go", "label": "Los", "do": {"kind": "state", "state": "done"}}, {"id": "no", "label": "Nein"}]).json().get("id")
r = click(F, q, ["no"])
check(r.ok and row(t)[0] == 0 and "step" not in (r.json().get("choice") or {}), "an option without a step: answer only, the task stays")

# ---------------------------------------------------------------- the task moved on: the answer goes, the state stays
t = task("Schon weiter")
q = ask(t, [{"id": "go", "label": "Erledigt", "do": {"kind": "state", "state": "done"}}]).json().get("id")
kt.dbx("UPDATE tasks SET delivery='in_progress' WHERE id=?", (t,))
cur = cursor()
r = click(F, q, ["go"])
st = (r.json().get("choice") or {}).get("step") or {} if r.ok else {}
check(r.ok and row(t)[0] == 0 and st.get("state") == "skipped" and st.get("why") == "in_progress", f"in progress already: skipped, state stays {st} {row(t)}")
ev = events(cur, {"comment"})
check(ev and ((ev[0]["data"].get("answer") or {}).get("step") or {}).get("state") == "skipped", "the agent hears the answer (step skipped)")
t = task("Schon fertig")
q = ask(t, [{"id": "go", "label": "Parken", "do": {"kind": "park", "reason": "x"}}]).json().get("id")
assert F.post(B + f"/api/tasks/{t}/complete", json={}).ok
r = click(F, q, ["go"])
check(r.ok and row(t)[2] == "" and ((r.json().get("choice") or {}).get("step") or {}).get("why") == "done", f"done already: skipped ({r.status_code} {row(t)})")

# ---------------------------------------------------------------- an answer in words: out of "Waiting for me", buttons stay
t = task("Worte statt Klick")
q = ask(t, [{"id": "go", "label": "Anfangen", "do": {"kind": "section", "section_id": S1}}, {"id": "no", "label": "Nein"}]).json().get("id")
w = F.get(B + "/api/inbox").json()
check(any(x["kind"] == "question" and x["id"] == q for x in w.get("items", [])), f"the question waits for me {[(x['kind'], x['id']) for x in w.get('items', [])]}")
ask(t, [{"id": "x", "label": "X"}])  # the agent's next question does not make it expire
F.post(B + f"/api/tasks/{t}/comments", json={"body": "Erst nächste Woche", "reply_to": q})
w = F.get(B + "/api/inbox").json()
check(not any(x["kind"] == "question" and x["id"] == q for x in w.get("items", [])), "answered in words: no longer waiting for me")
c0 = next((x for x in F.get(B + f"/api/tasks/{t}/timeline").json().get("comments", []) if x["id"] == q), {})
check(c0.get("choice_state") == "open", f"its buttons stay answerable {c0.get('choice_state')}")
r = click(F, q, ["go"])
check(r.ok and row(t)[1] == S1, f"and a later click still runs the step ({r.status_code} {r.text[:160]})")

# ---------------------------------------------------------------- the chat: a step on the message's task
t = task("Im Chat")
r = requests.post(V + f"/agent/chats/{FID}", headers=H, json={"body": "Parken?", "task_id": t,
                                                               "choices": [{"id": "p", "label": "Parken", "do": {"kind": "park", "reason": "später"}}, {"id": "n", "label": "Nein"}]})
check(r.status_code == 201, f"a chat question with a step on its task {r.status_code} {r.text[:200]}")
MID = r.json().get("id", 0)
r = requests.post(V + f"/agent/chats/{FID}", headers=H, json={"body": "Fremd?", "task_id": t,
                                                               "choices": [{"id": "p", "label": "Los", "do": {"kind": "section", "section_id": SX}}]})
check(r.status_code == 400, f"the chat: a column of another project 400 ({r.status_code})")
w = F.get(B + "/api/inbox").json()
check(any(x["kind"] == "question" and x.get("source") == "chat" and x["id"] == MID for x in w.get("items", [])), "the chat question waits for me")
cur = cursor()
r = F.post(B + f"/api/agents/{AID}/chat/{MID}/choice", json={"choice_ids": ["p"]})
check(r.ok and row(t)[2] == "parked" and ((r.json().get("choice") or {}).get("step") or {}).get("state") == "done", f"the chat click parked the task ({r.status_code} {row(t)})")
ev = events(cur, {"chat_choice"})
check(ev and (ev[0]["data"].get("step") or {}).get("kind") == "park", "the agent hears the chat answer with its step")
r = F.post(B + f"/api/agents/{AID}/chat/{MID}/choice", json={"choice_ids": ["n"]})
check(r.status_code == 409, f"the chat: a second click 409 ({r.status_code})")

# ---------------------------------------------------------------- reader F11: the task moved to another project meanwhile
t = task("Umgezogen")
q = ask(t, [{"id": "go", "label": "Anfangen", "do": {"kind": "section", "section_id": S1}}]).json().get("id")
assert F.patch(B + f"/api/tasks/{t}", json={"list_id": L2}).ok
r = click(F, q, ["go"])
st = (r.json().get("choice") or {}).get("step") or {} if r.ok else {}
check(r.ok and st.get("state") == "skipped" and st.get("why") == "moved" and row(t)[1] != S1, f"F11: the column does not fit any more: skipped, moved {st} {row(t)}")

# ---------------------------------------------------------------- the tag gone at the click (reader F15): skipped
t = task("Tag gelöscht")
assert F.patch(B + f"/api/tasks/{task('Mit Selten')}", json={"ltags": ["Selten"]}).ok
q = ask(t, [{"id": "go", "label": "Markieren", "do": {"kind": "tag", "tag": "Selten"}}]).json().get("id")
TGS = kt.dbx("SELECT id FROM obj_tags WHERE scope_kind='list' AND scope_id=? AND name='Selten'", (str(L),))
assert TGS and F.delete(B + f"/api/list-tags/{TGS[0][0]}").ok, "setup: the project's tag deleted after the question"
r = click(F, q, ["go"])
st = (r.json().get("choice") or {}).get("step") or {} if r.ok else {}
left = kt.dbx("SELECT COUNT(*) FROM obj_tags WHERE scope_kind='list' AND scope_id=? AND name='Selten'", (str(L),))[0][0]
check(r.ok and st.get("state") == "skipped" and st.get("why") == "moved" and left == 0, f"tag deleted since the question: skipped, no new tag ({st} {left})")
t = task("Tag umgezogen")
q = ask(t, [{"id": "go", "label": "Markieren", "do": {"kind": "tag", "tag": "Kunde"}}]).json().get("id")
assert F.patch(B + f"/api/tasks/{t}", json={"list_id": L2}).ok
r = click(F, q, ["go"])
st = (r.json().get("choice") or {}).get("step") or {} if r.ok else {}
made = kt.dbx("SELECT COUNT(*) FROM obj_tags WHERE scope_kind='list' AND scope_id=? AND name='Kunde'", (str(L2),))[0][0]
check(r.ok and st.get("state") == "skipped" and st.get("why") == "moved" and made == 0, f"task moved to a project without the tag: skipped, no new tag ({st} {made})")

# ---------------------------------------------------------------- reader F8: a token with comments only runs no step
tk = F.post(B + "/api/me/tokens", json={"name": "nur Kommentare", "scopes": ["read", "comments"]}).json().get("token")
t = task("Token ohne Schreibrecht")
q = ask(t, [{"id": "go", "label": "Erledigt", "do": {"kind": "state", "state": "done"}}, {"id": "no", "label": "Nein"}]).json().get("id")
r = requests.post(V + f"/comments/{q}/choice", headers={"Authorization": "Bearer " + tk}, json={"choice_ids": ["go"]})
c0 = next((x for x in F.get(B + f"/api/tasks/{t}/timeline").json().get("comments", []) if x["id"] == q), {})
check(r.status_code == 403 and row(t)[0] == 0 and c0.get("choice_state") == "open", f"F8: comments-only token: 403, nothing stored ({r.status_code} {row(t)} {c0.get('choice_state')})")
r = requests.post(V + f"/comments/{q}/choice", headers={"Authorization": "Bearer " + tk}, json={"choice_ids": ["no"]})
check(r.ok and row(t)[0] == 0, f"F8: the option without a step still answers with that token ({r.status_code} {r.text[:160]})")

sys.exit(done("p7530_choicestep"))
