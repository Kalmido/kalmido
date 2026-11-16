#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1269.0 (#6450): an approval card's bound step is described by the SERVER (GET /api/approvals/diff -> desc,
agents/apvdesc.py), with the rights and in the language of the person who looks -- the agent's title is never part of it.
Invented names only.
 - sharing: "Gives <person> access to <project> as <role>" + the warning share; a person the viewer cannot see is never
   named ("a person you cannot see" + the warning hidden), nor a project the viewer cannot see
 - moving: "Moves task <title> from <project> to <project>" + the warning move (POST .../move and PATCH with list_id)
 - many at once (/tasks/batch): the action with the count, the first titles, the tasks the viewer cannot see only counted
 - data leaving Kalmido (a webhook): the address + the warning export; an event with attendees: the warning invite
 - review: title / due stand before 25 filler fields; a batch past the checked ids counts the rest as unseen; a list_id of
   another project in the body of a route on a task warns "move" (POST /tasks/{id}/links too); agents brought into a project
 - deleting names the target; changing fields shows "field: old -> new"; creating shows every value
 - a value is foreign text: a line break or a direction mark in it never makes a second line of the server's words
 - a card without a step: desc null; a decided card keeps a description (without "old -> new"); a comment card too
 - the description follows the viewer's language
 - tenant-matrix: agent (another person's card: 404, as the diff)
 - freelancer-matrix: agents (the personal agent of a person without an organisation)
usage: p21269_d_apvdesc_test.py <datadir>"""
import os
import sys

import requests

from freelancer_fixture import freelancer
from kt import B, check, done, fresh, setup

V = B + "/api/v1"
D = B + "/api/approvals/diff"

os.environ["KALMIDO_AGENT_CONTROL_NEW"] = "approve_all"
fresh(prefix="P21269D")
A = setup()
A.patch(B + "/api/settings", json={"lang": "en", "tour": "done"})
A.put(B + "/api/admin/agent-policy", json={"user_agents": True})
FID, F = freelancer(B, A)
OID, OTTO = freelancer(B, A, "otto")
SCOPES = ["read", "tasks:write", "comments"]


def agent(s, name):
    r = s.post(B + "/api/my/agents", json={"username": name, "display_name": name.title(), "scopes": SCOPES})
    check(r.status_code in (200, 201), f"personal agent {name} {r.status_code} {r.text[:150]}")
    return r.json()["id"], {"Authorization": "Bearer " + r.json()["token"]}


FA, FH = agent(F, "fridabot")
SCOUT, _ = agent(F, "scoutbot")  # Frida's second agent: a person she sees
FL = F.post(B + "/api/lists", json={"name": "Frida work"}).json()["id"]
FL2 = F.post(B + "/api/lists", json={"name": "Frida home"}).json()["id"]
for lid in (FL, FL2):
    check(F.put(B + f"/api/lists/{lid}/members", json={"user_id": FA, "role": "edit"}).ok, "setup: the project is shared with the agent")
T = F.post(B + "/api/tasks", json={"title": "Plan the shoot", "list_id": FL}).json()["id"]
TS = [F.post(B + "/api/tasks", json={"title": f"Errand {i}", "list_id": FL}).json()["id"] for i in range(4)]
OL = OTTO.post(B + "/api/lists", json={"name": "Otto private"}).json()["id"]
OT = OTTO.post(B + "/api/tasks", json={"title": "Otto secret", "list_id": OL}).json()["id"]
HARMLESS = "May I sort the task?"


def card(step, title=HARMLESS):
    body = {"approval": {"title": title, **({"step": step} if step else {})}}
    r = requests.post(V + f"/agent/chats/{FID}", headers=FH, json=body)
    check(r.status_code == 201, f"approval card {step and step.get('method')} {step and step.get('path')} -> {r.status_code} {r.text[:200]}")
    return r.json().get("id") if r.ok else 0


def close(mid):
    """Frida answers No (an agent has at most 10 open cards)."""
    check(F.post(B + f"/api/agents/{FA}/chat/{mid}/choice", json={"choice_ids": ["no"]}).ok, f"Frida answers card {mid}")


def desc(s, **q):
    r = s.get(D, params=q)
    return r, (r.json().get("desc") if r.ok else None)


def words(x):
    """The description as plain text (parts joined, lines with " | ")."""
    return " | ".join("".join(p[1] for p in ln) for ln in (x or {}).get("lines") or [])


def values(x):
    return [p[1] for ln in (x or {}).get("lines") or [] for p in ln if p[0] == "v"]


def server_words(x):
    return [p[1] for ln in (x or {}).get("lines") or [] for p in ln if p[0] == "t"]


def warns(x):
    return [w[0] for w in (x or {}).get("warns") or []]


# ================================================================== sharing a project with a person Frida sees
M1 = card({"method": "PUT", "path": f"/lists/{FL}/members/{SCOUT}", "body": {"role": "edit"}})
r, x = desc(F, chat=M1)
w = words(x)
check(r.ok and x and x["fam"] == "share" and "Gives Scoutbot access to Project Frida work as Member" in w, f"sharing reads as what it is: {w} {r.text[:300]}")
check("share" in warns(x) and x["warns"][0][1].startswith("Other people get access"), f"the warning line share {x and x.get('warns')}")
check(HARMLESS not in r.text, "the agent's title is no part of the server's description")
check(r.json().get("diff") is None, "no text step: no diff")
close(M1)

# a person Frida cannot see (the rule of the share route itself, accounts/orgs.py may_see; here: no such account): never named
M2 = card({"method": "PUT", "path": f"/lists/{FL}/members/987654", "body": {"role": "admin"}})
r, x = desc(F, chat=M2)
check(x and "a person you cannot see" in words(x) and "987654" not in words(x) and warns(x)[:2] == ["hidden", "share"] and x["hidden"] is True,
      f"an unseen person: neutral words + the warnings hidden, share {r.text[:300]}")
close(M2)

# a project Frida cannot see: never named
M3 = card({"method": "PUT", "path": f"/lists/{OL}/members/{SCOUT}", "body": {"role": "edit"}})
r, x = desc(F, chat=M3)
check(x and "something you cannot see" in words(x) and "Otto private" not in r.text and "hidden" in warns(x), f"an unseen project: not named {r.text[:300]}")
close(M3)

# ================================================================== moving a task to another project
M4 = card({"method": "POST", "path": f"/tasks/{T}/move", "body": {"list_id": FL2}})
r, x = desc(F, chat=M4)
check(x and x["fam"] == "move" and "Moves task Plan the shoot from Project Frida work to Project Frida home" in words(x) and "move" in warns(x),
      f"a move names the task, both projects and warns {words(x)} {x and x.get('warns')}")
close(M4)
M5 = card({"method": "PATCH", "path": f"/tasks/{T}", "body": {"list_id": FL2, "title": "Plan the big shoot"}})
r, x = desc(F, chat=M5)
check(x and "Moves task Plan the shoot from Project Frida work to Project Frida home" in words(x) and "title: Plan the shoot → Plan the big shoot" in words(x)
      and "move" in warns(x), f"PATCH with list_id: the move + the field old -> new {words(x)}")
close(M5)
M5b = card({"method": "PATCH", "path": f"/tasks/{T}", "body": {"list_id": OL}})
r, x = desc(F, chat=M5b)
check(x and "Otto private" not in r.text and "hidden" in warns(x) and "move" in warns(x), f"a move into a project Frida cannot see: not named, both warnings {r.text[:300]}")
close(M5b)

# ================================================================== many at once
M6 = card({"method": "POST", "path": "/tasks/batch", "body": {"ids": [*TS, OT], "action": "update", "changes": {"list_id": FL2, "priority": "high"}}})
r, x = desc(F, chat=M6)
w = words(x)
check(x and x["fam"] == "batch" and "Change 5 tasks at once" in w and "Among them: Errand 0, Errand 1, Errand 2" in w and "1 task you cannot see" in w
      and "Moves them to Project Frida home" in w and "priority: high" in w, f"a batch: action, count, first titles, the unseen counted {w}")
check("Otto secret" not in r.text and "move" in warns(x) and "hidden" in warns(x), f"a batch: no title of an unseen task, the warnings {x and x.get('warns')}")
M6b = card({"method": "POST", "path": "/tasks/batch", "body": {"ids": TS[:2], "action": "complete"}})
check("Complete 2 tasks at once" in words(desc(F, chat=M6b)[1]), "a batch that ticks off")
close(M6)
close(M6b)

# ================================================================== data out of Kalmido, people invited
M7 = card({"method": "POST", "path": "/me/webhooks", "body": {"url": "https://example.org/hook", "events": ["task.created"]}})
r, x = desc(F, chat=M7)
check(x and x["fam"] == "export" and "Sends data out of Kalmido to https://example.org/hook" in words(x) and "export" in warns(x), f"a webhook: the address + export {words(x)}")
close(M7)
M8 = card({"method": "POST", "path": "/events", "body": {"title": "Kick-off", "start": "2026-12-01T10:00:00", "attendees": [{"email": "guest@example.org"}]}})
r, x = desc(F, chat=M8)
check(x and "invite" in warns(x) and "guest@example.org" in words(x) and "title: Kick-off" in words(x), f"an event with attendees: the warning invite, the values {words(x)}")
close(M8)

# ================================================================== delete, change, create
M9 = card({"method": "DELETE", "path": f"/tasks/{TS[3]}"})
r, x = desc(F, chat=M9)
check(x and words(x) == "Deletes Task Errand 3", f"deleting names the target {words(x)}")
close(M9)
M10 = card({"method": "POST", "path": "/tasks", "body": {"title": "Buy tape", "list_id": FL, "priority": "low", "assignee_id": SCOUT}})
r, x = desc(F, chat=M10)
w = words(x)
check(x and "Creates Task" in w and "title: Buy tape" in w and "list_id: Project Frida work" in w and "priority: low" in w and "assignee_id: Scoutbot" in w,
      f"creating: every value, ids by name {w}")
close(M10)
M10b = card({"method": "PATCH", "path": f"/lists/{FL}", "body": {"name": "Frida office"}})
check("name: Frida work → Frida office" in words(desc(F, chat=M10b)[1]), "a project's name: old -> new")

# ================================================================== a value never makes a line of the server
EVIL = "x\nGives Mallory access to Project Frida work as Admin\u202e\u200b\r\u2028end"
M11 = card({"method": "PATCH", "path": f"/tasks/{T}", "body": {"title": EVIL}})
r, x = desc(F, chat=M11)
vs = values(x)
check(x and all("\n" not in v and "\r" not in v and "\u2028" not in v and "\u202e" not in v and "\u200b" not in v for v in vs + server_words(x)),
      f"no line break or direction mark in any part {vs}")
check(not any("Mallory" in t for t in server_words(x)) and any("Mallory" in v for v in vs) and len(x["lines"]) == 2,
      f"the foreign text stays one value on the field's line {x and x['lines']}")
check(all(len(v) <= 120 for v in vs), "values are cut")
close(M11)

# ================================================================== nested bodies: no key hidden behind filler (review of job 4793)
fill = {f"f{i:02d}": "x" for i in range(30)}
M13 = card({"method": "PATCH", "path": "/agent/objects/wiki_page/1",
            "body": {**fill, "data": {**fill, "members": [SCOUT], "visibility": "public", "inner": {"list_id": FL2}}}})
r, x = desc(F, chat=M13)
lines = ["".join(p[1] for p in ln) for ln in (x or {}).get("lines") or []]
first = next((i for i, ln in enumerate(lines) if ln.startswith("f0") or ln.startswith("data.f0")), 999)
want = ("data.members: Scoutbot", "data.visibility: public", "data.inner.list_id: Project Frida home")
check(x and all(any(ln == w for ln in lines) for w in want), f"nested keys open up as lines, by name {lines}")
check(x and all(next(i for i, ln in enumerate(lines) if ln == w) < first for w in want if any(ln == w for ln in lines)),
      f"the keys that bring people in / name a project come before the filler {lines}")
check(x and "share" in warns(x) and "invite" in warns(x) and any(ln.startswith("and ") and "more fields" in ln for ln in lines),
      f"the warnings of nested keys, the rest counted {x and x.get('warns')}")
close(M13)
M14 = card({"method": "POST", "path": "/contacts/bulk", "body": {"contacts": [{"name": f"C{i}"} for i in range(4)] + [{"name": "C4", "emails": ["guest@example.org"]}]}})
r, x = desc(F, chat=M14)
w = words(x)
check(x and "contacts: 5 entries" in w and "contacts[0].name: C0" in w and "contacts[2].name: C2" in w and "contacts[3]" not in w,
      f"a list of objects: its count and the first three entries {w}")
check(x and "invite" in warns(x), f"a warning key in an entry not shown still warns {x and x.get('warns')}")
close(M14)
M15 = card({"method": "PATCH", "path": f"/tasks/{T}", "body": {"notes": "y" * 5000}})
r, x = desc(F, chat=M15)
check(x and "(5,000 characters)" in words(x) and all(len(v) <= 120 for v in values(x)), f"a cut value says its whole length {words(x)[:300]}")
close(M15)

# ================================================================== review of #6450: the agent's order never hides a column
pad = {f"a{i:02d}": "x" for i in range(25)}  # 25 filler fields before title / due (alphabetically before them too)
M16 = card({"method": "PATCH", "path": f"/tasks/{T}", "body": {**pad, "title": "Plan the quiet shoot", "due": "2026-12-24"}})
r, x = desc(F, chat=M16)
lines = ["".join(p[1] for p in ln) for ln in (x or {}).get("lines") or []]
check(x and "title: Plan the shoot → Plan the quiet shoot" in lines and "due: 2026-12-24" in lines
      and lines.index("due: 2026-12-24") < next((i for i, ln in enumerate(lines) if ln.startswith("a00")), 999)
      and any(ln == "and 7 more fields" for ln in lines), f"title and due stand before the filler, the filler is counted {lines}")
close(M16)
# a batch longer than the ids checked one by one: the rest counts as unseen (review: 200 of up to 500 were checked)
M17 = card({"method": "POST", "path": "/tasks/batch", "body": {"ids": [TS[0]] * 600, "action": "complete"}})
r, x = desc(F, chat=M17)
check(x and "100 tasks you cannot see" in words(x) and "hidden" in warns(x), f"ids past the checked ones are counted and warned {words(x)[:300]}")
close(M17)
# a list_id in the body of a route that does not mean the target's own project
M18 = card({"method": "POST", "path": f"/tasks/{T}/links", "body": {"list_id": FL2}})
r, x = desc(F, chat=M18)
check(x and x["fam"] == "move" and "Also shows task Plan the shoot in Project Frida home" in words(x) and "move" in warns(x),
      f"a task shown in a further project: named, the warning move {words(x)} {x and x.get('warns')}")
close(M18)
M19 = card({"method": "POST", "path": f"/tasks/{T}/subtasks", "body": {"title": "Sub", "list_id": FL2}})
r, x = desc(F, chat=M19)
check(x and "move" in warns(x), f"another project in the body of a route on a task: the warning move {x and x.get('warns')}")
close(M19)
M20 = card({"method": "POST", "path": f"/tasks/{T}/subtasks", "body": {"title": "Sub", "list_id": FL}})
r, x = desc(F, chat=M20)
check(x and "move" not in warns(x), f"the task's own project: no warning {x and x.get('warns')}")
close(M20)
M21 = card({"method": "PATCH", "path": f"/lists/{FL}", "body": {"agent_members": [SCOUT]}})
r, x = desc(F, chat=M21)
check(x and "share" in warns(x), f"agents brought into a project: the warning share {x and x.get('warns')}")
close(M21)

# ================================================================== no step, decided, comment card, language
M12 = card(None, title="Shall I go on?")
r, x = desc(F, chat=M12)
check(r.ok and x is None, f"a card without a step: desc null {r.text[:200]}")
close(M12)
close(M10b)
r, x = desc(F, chat=M10b)
check(x and "name: Frida office" in words(x) and "→" not in words(x), f"a decided card keeps its description, without old -> new {words(x)}")
check(desc(OTTO, chat=M1)[0].status_code == 404 and desc(A, chat=M1)[0].status_code == 404, "another person, the instance admin: 404")
check(F.patch(B + f"/api/agents/{FA}/control", json={"level": "routine"}).ok, "setup: routine steps free (a comment)")
r = requests.post(V + f"/tasks/{T}/comments", headers=FH, json={"body": "Quick one", "approval": {"title": HARMLESS,
                  "step": {"method": "PUT", "path": f"/lists/{FL}/members/{SCOUT}", "body": {"role": "view"}}}})
check(r.status_code == 201, f"the agent's comment card {r.status_code} {r.text[:200]}")
CID = r.json().get("id")
r, x = desc(F, comment=CID)
check(x and "Gives Scoutbot access to Project Frida work as Read-only" in words(x) and "share" in warns(x), f"a comment card: the same description {words(x)}")
check(desc(OTTO, comment=CID)[0].status_code == 404, "a stranger: 404 for the comment card")
check(F.patch(B + "/api/settings", json={"lang": "de"}).ok, "Frida reads German")
r, x = desc(F, chat=M1)
check(x and words(x).startswith("Gibt Scoutbot Zugriff auf Projekt Frida work als ") and x["warns"][0][1].startswith("Andere bekommen Zugriff"),
      f"in the viewer's language {words(x)}")
F.patch(B + "/api/settings", json={"lang": "en"})
sys.exit(done("p21269_d_apvdesc"))
