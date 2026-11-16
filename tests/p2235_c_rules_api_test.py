#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.235.0 C (#2903): the standing rules of an agent ("from now on always ...") over the agent API and the owner routes
 - the agent saves a rule with its source (POST /api/v1/agent/rules): a chat message of a person to it or a comment it can
   see -> 201; its own chat answer, another agent's chat, a comment in a project it is not in, a gone id -> 404; the same
   text again -> 200 duplicate; bad text / source / an unknown field -> 400; 500 characters, 100 rules per agent (two
   parallel requests at 99 rules: exactly one passes)
 - GET /api/v1/agent "rules" = only the active ones (no paused), GET /api/v1/agent/rules lists all with state + source
 - the owner reads, rewords, pauses, resumes, deletes, adds by hand (GET / POST / PATCH / DELETE /api/agents/<id>/rules);
   each change = the event rules_changed (change + the active rules); the agent's own POST sends none
 - another person 404 (read and write), an instance admin reaches a team agent (not a foreign personal one), a member of
   the team 404; the excerpt / link of a source only for a person who sees it themselves
 - the same as a person without an organisation (freelancer-matrix: agents)
 - 2.1269.0 (#6451): what the agent saves is a proposal (state proposed, applies false): not in GET /agent rules nor in
   rules_changed, in GET /agent/rules only under "proposed"; the server's card (kind rule) in the chat of the person of the
   source; only that person confirms (active + rules_changed confirmed + Remove rule on the card) or rejects (gone); another
   person / the owner of a team agent's rule / the agent itself cannot (404 / 403), no agent route sets it active, the agent
   cannot post a card of kind rule; the owner may only delete a proposal (PATCH 409); at most 5 open proposals (429);
   removing a confirmed rule from the card (rules_changed deleted)
usage: p2235_c_rules_api_test.py <datadir>      (KMT_NOSTART=1 / P2235C_NOSTART=1: a running server)"""
import sys
import threading

import requests

import kt
from freelancer_fixture import freelancer
from kt import B, H, check, done, fresh, sess

V = B + "/api/v1"
fresh(prefix="P2235C")
s0 = requests.Session()
s0.headers.update(H)
assert s0.post(B + "/api/auth/setup", json={"username": "alice", "display_name": "Alice", "password": "password123"}).ok
A = sess("alice")
A.post(B + "/api/admin/setup", json={"org_name": "Example Org", "lang": "en", "collab_all": True, "modules": ["comments"]})
A.patch(B + "/api/settings", json={"lang": "en", "tour": "done"})
ORG = A.get(B + "/api/state").json()["me"]["workspaces"][0]["id"]
A.put(B + "/api/admin/agent-policy", json={"user_agents": True})
FID, F = freelancer(B, A)
OID, O = freelancer(B, A, "otto")


def own_agent(s, name):
    r = s.post(B + "/api/my/agents", json={"username": name, "display_name": name.title(), "scopes": ["read", "comments"]})
    check(r.status_code in (200, 201), f"{name}: a personal agent {r.status_code} {r.text[:120]}")
    j = r.json()
    return j["id"], {"Authorization": "Bearer " + j["token"]}


def add(h, text, kind, sid, **extra):
    return requests.post(V + "/agent/rules", headers=h, json={"text": text, "source": {"kind": kind, "id": sid}, **extra})


def rules(s, aid):
    r = s.get(B + f"/api/agents/{aid}/rules")
    return r.status_code, (r.json().get("rules") if r.ok else None)


def events(h, cur, name="rules_changed"):
    j = requests.get(V + f"/agent/events?since={cur}&limit=100", headers=h).json()
    return [e for e in j.get("data") or [] if e["event"] == name]


def cursor(h):
    return requests.get(V + "/agent/events?since=latest", headers=h).json()["cursor"]


def decide(s, aid, rid, d):  # 2.1269.0 (#6451): the person's answer on the card
    return s.post(B + f"/api/agents/{aid}/rules/{rid}/decide", json={"decision": d})


def cards(s, aid):  # 2.1269.0 (#6451): the server's rule cards in my chat with agent aid
    return [m for m in s.get(B + f"/api/agents/{aid}/chat").json().get("messages") or [] if m.get("kind") == "rule"]


# ================================================================ a person without an organisation and her own agent
# freelancer-matrix: agents
FA, FH = own_agent(F, "fridabot")
OA, OH = own_agent(O, "ottobot")
L = F.post(B + "/api/lists", json={"name": "Studio"}).json()["id"]
check(F.put(B + f"/api/lists/{L}/members", json={"user_id": FA, "role": "edit"}).ok, "the agent in the private project")
T = F.post(B + "/api/tasks", json={"title": "Invoices", "list_id": L}).json()["id"]
L2 = F.post(B + "/api/lists", json={"name": "Private"}).json()["id"]  # not shared with the agent
T2 = F.post(B + "/api/tasks", json={"title": "Diary", "list_id": L2}).json()["id"]

m = F.post(B + f"/api/agents/{FA}/chat", json={"body": "From now on always write invoices in English"})
check(m.status_code in (200, 201), f"a chat message to the agent {m.status_code}")
MID = m.json()["id"]
cur0 = cursor(FH)
r = add(FH, "Always write invoices in English", "chat", MID)
check(r.status_code == 201, f"the agent saves a rule from the chat {r.status_code} {r.text[:200]}")
R1 = r.json()["rule"]
# 2.1269.0 (#6451): a proposal now (was: active at once)
check(r.json().get("applies") is False and "does NOT apply" in (r.json().get("hint") or ""), f"#6451: the answer says it does not apply yet {r.json().get('hint')}")
check(R1["state"] == "proposed" and R1["source"]["kind"] == "chat" and R1["source"]["id"] == MID and R1["source"]["user_id"] == FID
      and "write invoices in English" in R1["source"]["excerpt"], f"state + source + excerpt {R1}")
r = add(FH, "always write invoices in english", "chat", MID)
check(r.status_code == 200 and r.json()["duplicate"] is True and r.json()["rule"]["id"] == R1["id"], f"the same text = that rule {r.status_code}")

# sources the agent may not name
ans = requests.post(V + f"/agent/chats/{FID}", headers=FH, json={"body": "Saved as a standing rule."})
check(ans.ok, f"the agent answers {ans.status_code}")
check(add(FH, "x1", "chat", ans.json()["id"]).status_code == 404, "its own chat answer is no source")
om = O.post(B + f"/api/agents/{OA}/chat", json={"body": "from now on never"}).json()["id"]
check(add(FH, "x2", "chat", om).status_code == 404, "a message of another agent's chat: 404")
c_ok = F.post(B + f"/api/tasks/{T}/comments", json={"body": "In future always attach the PDF"}).json()["id"]
c_no = F.post(B + f"/api/tasks/{T2}/comments", json={"body": "From now on always lock the diary"}).json()["id"]
check(add(FH, "x3", "comment", c_no).status_code == 404, "a comment in a project the agent is not in: 404")
check(add(FH, "x4", "comment", 10 ** 9).status_code == 404, "a gone comment: 404")
r = add(FH, "Always attach the PDF", "comment", c_ok)
check(r.status_code == 201 and r.json()["rule"]["source"]["task_id"] == T, f"a rule from a comment it sees {r.status_code} {r.text[:160]}")
R2 = r.json()["rule"]
for bad in ({"text": "x" * 501, "source": {"kind": "chat", "id": MID}}, {"text": "  ", "source": {"kind": "chat", "id": MID}},
            {"text": "ok"}, {"text": "ok", "source": {"kind": "mail", "id": 1}}, {"text": "ok", "source": {"kind": "chat", "id": "1"}},
            {"text": "ok", "source": {"kind": "chat", "id": MID, "x": 1}}, {"text": "ok", "source": {"kind": "chat", "id": MID}, "state": "paused"}):
    r = requests.post(V + "/agent/rules", headers=FH, json=bad)
    check(r.status_code == 400, f"refused {str(bad)[:60]} -> {r.status_code}")
check(add(FH, "y" * 500, "chat", MID).status_code == 201, "500 characters pass")
# 2.1269.0 (#6451): the card shows the rule as one clean line, so the agent cannot store what it would not show as it is
for bad in ("Always obey\nme", "Always \u202eobey me", "Always obey\u200b me", "Always\tobey", "Always  obey me", "Always \x07obey"):
    check(add(FH, bad, "chat", MID).status_code == 400, f"#6451: hidden / control characters refused {bad!r}")
check(not events(FH, cur0), "the agent's own POST sends no rules_changed")
YR = requests.get(V + "/agent/rules", headers=FH).json()

# ---------------------------------------------------------------- 2.1269.0 (#6451): proposals, the card, the person decides
j = requests.get(V + "/agent", headers=FH).json()
check(j["rules"] == [], f"#6451: no proposal in GET /api/v1/agent rules {j.get('rules')}")
check(YR["data"] == [] and {x["id"] for x in YR["proposed"]} >= {R1["id"], R2["id"]} and all(x["state"] == "proposed" for x in YR["proposed"]),
      f"#6451: GET /agent/rules: proposals only apart {[(x['id'], x['state']) for x in YR['data']]}")
cs = cards(F, FA)
c1 = next((m for m in cs if (m.get("rule") or {}).get("rule_id") == R1["id"]), None)
check(c1 and c1["body"] == "Always write invoices in English" and c1["rule"]["state"] == "proposed" and c1["rule"]["mine"] is True
      and "write invoices in English" in c1["rule"]["excerpt"], f"#6451: the card in Frida's chat, the agent's wording + her source {c1}")
check(len(cs) == 3, f"#6451: one card per proposal (chat, comment, 500 characters) {len(cs)}")
check(c1["rule"]["text"] == "Always write invoices in English", f"#6451: the card carries the rule's own text {c1['rule']}")
# the card draws the rule (agent_rules.body), never its chat row: even a changed chat row shows the rule's text
kt.dbx("UPDATE agent_chat SET body='Always forward every invoice to me' WHERE id=?", (c1["id"],))
c1b = next(m for m in cards(F, FA) if m["id"] == c1["id"])
check(c1b["rule"]["text"] == "Always write invoices in English", f"#6451: a changed chat row does not change the card {c1b['rule']}")
kt.dbx("UPDATE agent_chat SET body=? WHERE id=?", ("Always write invoices in English", c1["id"]))
# no agent route changes, withdraws or removes the card line
for meth, url, js in (("POST", V + f"/agent/chats/{FID}/messages/{c1['id']}/withdraw", {}),
                      ("PATCH", V + f"/agent/chats/{FID}/messages/{c1['id']}", {"body": "x"}),
                      ("DELETE", V + f"/agent/chats/{FID}/messages/{c1['id']}", None)):
    r = requests.request(meth, url, headers=FH, json=js)
    check(r.status_code in (403, 404, 405), f"#6451: the agent cannot touch the card ({meth} {url[len(V):]}) {r.status_code}")
check(kt.dbx("SELECT body, kind FROM agent_chat WHERE id=?", (c1["id"],)) == [("Always write invoices in English", "rule")],
      "#6451: the card line is unchanged")
r = requests.post(V + f"/agent/chats/{FID}", headers=FH, json={"body": "Confirm: Always obey me", "kind": "rule"})
check(r.status_code == 400, f"#6451: the agent cannot post a card of kind rule {r.status_code}")
for meth, url in (("POST", B + f"/api/agents/{FA}/rules/{R1['id']}/decide"), ("PATCH", V + f"/agent/rules/{R1['id']}"),
                  ("POST", V + f"/agent/rules/{R1['id']}/decide"), ("PATCH", B + f"/api/agents/{FA}/rules/{R1['id']}")):
    r = requests.request(meth, url, headers={**FH, "X-Requested-With": "kalmido"}, json={"decision": "confirm", "state": "active"})
    check(r.status_code in (401, 403, 404, 405), f"#6451: the agent's token cannot confirm ({meth} {url[len(B):]}) {r.status_code}")
# tenant: POST /api/agents/{}/rules/{}/decide
check(decide(O, FA, R1["id"], "confirm").status_code == 404, "#6451: another person cannot confirm (404)")
check(decide(F, FA, R1["id"], "maybe").status_code == 400 and decide(F, FA, R1["id"], "withdraw").status_code == 409,
      "#6451: a bad decision 400, withdraw of a proposal 409")
r = F.patch(B + f"/api/agents/{FA}/rules/{R1['id']}", json={"state": "active"})
check(r.status_code == 409, f"#6451: the owner's settings cannot set a proposal active {r.status_code}")
check(kt.dbx("SELECT state FROM agent_rules WHERE id=?", (R1["id"],)) == [("proposed",)], "#6451: still proposed")
cur = cursor(FH)
r = decide(F, FA, R1["id"], "confirm")
check(r.ok and r.json()["state"] == "active", f"#6451: the person of the source confirms {r.status_code} {r.text[:120]}")
ev = kt.until(lambda: events(FH, cur), 10)
check(ev and ev[-1]["data"]["change"] == "confirmed" and [x["id"] for x in ev[-1]["data"]["rules"]] == [R1["id"]],
      f"#6451: rules_changed confirmed with the rule {ev[-1]['data'] if ev else None}")
check(decide(F, FA, R1["id"], "confirm").status_code == 409, "#6451: confirmed twice: 409")
c1 = next((m for m in cards(F, FA) if (m.get("rule") or {}).get("rule_id") == R1["id"]), {})
check((c1.get("rule") or {}).get("state") == "active", f"#6451: the card shows it applies (Remove rule) {c1.get('rule')}")
check(decide(F, FA, R2["id"], "confirm").ok, "#6451: the comment's author confirms her comment's rule")
YID = next(x["id"] for x in YR["proposed"] if x["text"] == "y" * 500)
cur = cursor(FH)
r = decide(F, FA, YID, "reject")
check(r.ok and r.json()["state"] == "gone" and not kt.dbx("SELECT 1 FROM agent_rules WHERE id=?", (YID,)), "#6451: rejected = gone")
c3 = next((m for m in cards(F, FA) if m["body"] == "y" * 500), {})
check((c3.get("rule") or {}).get("state") == "gone", f"#6451: its card says not kept {c3.get('rule')}")
check(not events(FH, cur), "#6451: a rejected proposal sends no rules_changed (it never applied)")

# what the agent reads
j = requests.get(V + "/agent", headers=FH).json()
check([x["id"] for x in j["rules"]][:2] == [R1["id"], R2["id"]] and set(j["rules"][0]) == {"id", "text", "created_at", "source"},
      f"GET /api/v1/agent rules = the active ones {j.get('rules')}")

# ---------------------------------------------------------------- the owner
st, rs = rules(F, FA)
check(st == 200 and len(rs) == 2, f"the owner reads the list {st}")  # 2.1269.0 (#6451): the rejected proposal is gone
v1 = next(x for x in rs if x["id"] == R1["id"])
check(v1["source"]["visible"] is True and v1["source"]["excerpt"], "her own chat: excerpt + link")
cur = cursor(FH)
r = F.patch(B + f"/api/agents/{FA}/rules/{R1['id']}", json={"state": "paused"})
check(r.ok and r.json()["rule"]["state"] == "paused", f"the owner pauses {r.status_code} {r.text[:120]}")
ev = kt.until(lambda: events(FH, cur), 10)
check(ev and ev[-1]["data"]["change"] == "paused" and R1["id"] not in [x["id"] for x in ev[-1]["data"]["rules"]],
      f"rules_changed paused without the paused rule {ev[-1]['data'] if ev else None}")
j = requests.get(V + "/agent", headers=FH).json()
check(R1["id"] not in [x["id"] for x in j["rules"]], "a paused rule is not in the agent's context")
allr = requests.get(V + "/agent/rules", headers=FH).json()
check(any(x["id"] == R1["id"] and x["state"] == "paused" for x in allr["data"]) and allr["max"] == 100, "GET /agent/rules lists it as paused")
r = F.patch(B + f"/api/agents/{FA}/rules/{R1['id']}", json={"state": "active", "text": "Invoices always in English"})
check(r.ok and r.json()["rule"]["state"] == "active" and r.json()["rule"]["text"] == "Invoices always in English", "resume + reword")
ev = kt.until(lambda: [e for e in events(FH, cur) if e["data"]["change"] == "resumed"], 10)
check(ev and any(x["text"] == "Invoices always in English" for x in ev[-1]["data"]["rules"]), "rules_changed resumed with the new text")
for bad in ({"state": "off"}, {"text": ""}, {"text": "z" * 501}, {"source": 1}):
    check(F.patch(B + f"/api/agents/{FA}/rules/{R1['id']}", json=bad).status_code == 400, f"PATCH refused {str(bad)[:40]}")
r = F.post(B + f"/api/agents/{FA}/rules", json={"text": "Never book on Sundays"})
check(r.status_code == 201 and r.json()["rule"]["source"]["kind"] == "manual", f"a rule by hand {r.status_code}")
MAN = r.json()["rule"]["id"]
cur = cursor(FH)
check(F.delete(B + f"/api/agents/{FA}/rules/{MAN}").ok, "the owner deletes")
check(kt.until(lambda: [e for e in events(FH, cur) if e["data"]["change"] == "deleted"], 10), "rules_changed deleted")
check(F.delete(B + f"/api/agents/{FA}/rules/{MAN}").status_code == 404, "deleted twice: 404")

# 2.1269.0 (#6451): Remove rule from the card; a flood of proposals stops at 5; the owner deletes a proposal quietly
TB = add(FH, "Always send a copy", "chat", MID).json()["rule"]["id"]
check(decide(F, FA, TB, "confirm").ok, "#6451: confirmed")
cur = cursor(FH)
r = decide(F, FA, TB, "withdraw")
check(r.ok and not kt.dbx("SELECT 1 FROM agent_rules WHERE id=?", (TB,)), f"#6451: Remove rule removes it {r.status_code}")
ev = kt.until(lambda: events(FH, cur), 10)
check(ev and ev[-1]["data"]["change"] == "deleted" and TB not in [x["id"] for x in ev[-1]["data"]["rules"]], "#6451: rules_changed deleted")
fl = [add(FH, f"flood {i}", "chat", MID).status_code for i in range(6)]
check(fl == [201] * 5 + [429], f"#6451: at most 5 open proposals {fl}")
FLOOD = [x["id"] for x in requests.get(V + "/agent/rules", headers=FH).json()["proposed"]]
cur = cursor(FH)
check(all(F.delete(B + f"/api/agents/{FA}/rules/{x}").ok for x in FLOOD), "#6451: the owner deletes the proposals")
check(not events(FH, cur), "#6451: deleting a proposal sends no rules_changed")

# ---------------------------------------------------------------- others
check(rules(O, FA)[0] == 404, "another person: GET 404")
check(O.patch(B + f"/api/agents/{FA}/rules/{R1['id']}", json={"state": "paused"}).status_code == 404, "another person: PATCH 404")
check(O.delete(B + f"/api/agents/{FA}/rules/{R1['id']}").status_code == 404, "another person: DELETE 404")
check(O.post(B + f"/api/agents/{FA}/rules", json={"text": "mine"}).status_code == 404, "another person: POST 404")
check(rules(A, FA)[0] == 404, "an instance admin does not reach a foreign personal agent")
check(F.patch(B + f"/api/agents/{OA}/rules/{R1['id']}", json={"state": "paused"}).status_code == 404, "a rule id under another agent: 404")
check(requests.get(B + f"/api/agents/{FA}/rules", headers={**FH, "X-Requested-With": "kalmido"}).status_code in (401, 403, 404),
      "the agent's token does not reach the owner routes")

# ---------------------------------------------------------------- the limit, two parallel requests at 99
n = kt.dbx("SELECT COUNT(*) FROM agent_rules WHERE agent_id=?", (FA,))[0][0]  # 2.1269.0 (#6451): proposals count too
kt.dbx("INSERT INTO agent_rules(agent_id, body, state, source_kind, created_at, updated_at) "
       "SELECT ?, 'filler ' || g, 'active', '', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00' FROM generate_series(1, ?) g",
       (FA, 99 - n))
res = []
ths = [threading.Thread(target=lambda i=i: res.append(add(FH, f"parallel {i}", "chat", MID).status_code)) for i in range(2)]
[t.start() for t in ths]
[t.join() for t in ths]
check(sorted(res) == [201, 400], f"at 99 rules two parallel requests: exactly one passes {res}")
check(F.post(B + f"/api/agents/{FA}/rules", json={"text": "one more"}).status_code == 400, "the owner too: no 101st")

# ================================================================ a team agent (organisation)
r = A.post(B + "/api/users", json={"orgs": [ORG], "username": "bob", "display_name": "Bob", "password": "password123", "email": "bob@example.com"})
BOB = r.json()["id"]
A.post(B + "/api/users", json={"orgs": [ORG], "username": "carol", "display_name": "Carol", "password": "password123", "email": "carol@example.com"})
Bo, Ca = sess("bob"), sess("carol")
Bo.patch(B + "/api/settings", json={"lang": "en", "tour": "done"})
r = A.post(B + "/api/admin/agents", json={"scopes": ["read", "comments"], "username": "teambot", "display_name": "Teambot"})
TA, TH = r.json()["id"], {"Authorization": "Bearer " + r.json()["token"]}
W = A.post(B + "/api/lists", json={"name": "Team", "org_id": ORG}).json()["id"]
assert A.put(B + f"/api/lists/{W}/members", json={"user_id": BOB, "role": "edit"}).ok
assert A.put(B + f"/api/lists/{W}/members", json={"user_id": TA, "role": "edit"}).ok
assert A.patch(B + f"/api/lists/{W}", json={"agent_members": True}).ok
TT = Bo.post(B + "/api/tasks", json={"title": "Release", "list_id": W}).json()["id"]
bc = Bo.post(B + f"/api/tasks/{TT}/comments", json={"body": f"<@{TA}> from now on always link the ticket"}).json()["id"]
r = add(TH, "Always link the ticket", "comment", bc)
check(r.status_code == 201 and r.json()["rule"]["source"]["user_id"] == BOB and "<@" not in r.json()["rule"]["source"]["excerpt"],
      f"team agent: a rule from a member's comment {r.status_code} {r.text[:200]}")
bm = Bo.post(B + f"/api/agents/{TA}/chat", json={"body": "From now on always answer short"})
check(bm.status_code in (200, 201), f"bob chats with the team agent {bm.status_code}")
r = add(TH, "Answer short", "chat", bm.json()["id"])
check(r.status_code == 201, f"team agent: a rule from bob's chat {r.status_code}")
CHR = r.json()["rule"]["id"]
# 2.1269.0 (#6451): the instance admin (who edits the team agent's settings) cannot confirm bob's proposal, bob can
check(decide(A, TA, CHR, "confirm").status_code == 404, "#6451: the admin cannot confirm a member's proposal")
check(decide(Ca, TA, CHR, "confirm").status_code == 404, "#6451: another member cannot confirm it")
check(len(cards(Bo, TA)) == 2 and not cards(A, TA), "#6451: the cards are in bob's chat only")
check(all(decide(Bo, TA, x, "confirm").ok for x in (CHR, kt.dbx("SELECT id FROM agent_rules WHERE agent_id=? AND source_kind='comment'", (TA,))[0][0])),
      "#6451: bob confirms both")
CL = Ca.post(B + "/api/lists", json={"name": "Carol's", "org_id": ORG}).json()["id"]
CT = Ca.post(B + "/api/tasks", json={"title": "Own", "list_id": CL}).json()["id"]
cc = Ca.post(B + f"/api/tasks/{CT}/comments", json={"body": "from now on always ..."}).json()["id"]
check(add(TH, "x5", "comment", cc).status_code == 404, "team agent: a comment of a project it is not in: 404")
st, rs = rules(A, TA)
check(st == 200 and len(rs) == 2, f"the instance admin reads the team agent's rules {st}")
chat_rule = next(x for x in rs if x["id"] == CHR)
check(chat_rule["source"]["visible"] is False and chat_rule["source"]["excerpt"] == "", "bob's chat: no excerpt for the admin")
check(next(x for x in rs if x["id"] != CHR)["source"]["visible"] is True, "the comment in her project: visible for the admin")
check(A.patch(B + f"/api/agents/{TA}/rules/{CHR}", json={"state": "paused"}).ok, "the admin pauses a team agent's rule")
check(rules(Bo, TA)[0] == 404, "a member of the team (no admin): 404")
# 2.1269.0 (#6451): a person removed from the project since the proposal can no longer confirm it (chat and comment
# source); reject stays; the instance admin deletes the stale proposal
bm2 = Bo.post(B + f"/api/agents/{TA}/chat", json={"body": "From now on always answer in German"}).json()["id"]
P1 = add(TH, "Answer in German", "chat", bm2).json()["rule"]["id"]
bc2 = Bo.post(B + f"/api/tasks/{TT}/comments", json={"body": f"<@{TA}> from now on always tag the release"}).json()["id"]
P2 = add(TH, "Always tag the release", "comment", bc2).json()["rule"]["id"]
P3 = add(TH, "Always close the ticket", "comment", bc2).json()["rule"]["id"]
check(A.delete(B + f"/api/lists/{W}/members/{BOB}").ok, "bob leaves the team project")
for x in (P1, P2):
    check(decide(Bo, TA, x, "confirm").status_code == 404, f"#6451: removed member: confirm 404 ({x})")
check(kt.dbx(f"SELECT state FROM agent_rules WHERE id IN ({P1}, {P2})") == [("proposed",), ("proposed",)], "#6451: both stay proposals")
check(decide(Bo, TA, P3, "reject").ok, "#6451: rejecting stays possible")
check(all(A.delete(B + f"/api/agents/{TA}/rules/{x}").ok for x in (P1, P2)), "#6451: the instance admin deletes the stale proposals")
# withdraw of a confirmed rule needs the same right (bob confirmed CHR while he was in the project)
check(decide(Bo, TA, CHR, "withdraw").status_code == 404, "#6451: removed member: withdraw 404")
check(kt.dbx("SELECT state FROM agent_rules WHERE id=?", (CHR,)) == [("paused",)], "#6451: the rule stays")
check(rules(F, TA)[0] == 404, "a person without organisation: 404 on a team agent")
sys.exit(done("p2235_c_rules_api"))
