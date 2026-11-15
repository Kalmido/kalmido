#!/usr/bin/env python3
# kalmido-suite: fresh
# freelancer-matrix: agents
"""2.1215.0 (#6100): agent texts in the bell and in the pop-up carry no Markdown marks (kalmido/agents/chatnews.py,
kalmido/agents/msgpop.py use md_brief like the team texts). Run as a person WITHOUT an organisation with her own agent.
 - an approval card with a **bold** `code` title: the News entry's title is plain
 - a question with Markdown: the entry's text is plain
 - the pop-up line of an agent answer (GET /api/msgpop): plain
usage: p21215_a_chat_phone_news_test.py <datadir>"""
import os
import sys

import requests

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
from kt import B, check, done, fresh, setup  # noqa: E402
from freelancer_fixture import freelancer  # noqa: E402

V = B + "/api/v1"
fresh()
A = setup("alice", "Alice")
assert A.put(B + "/api/admin/agent-policy", json={"user_agents": True, "max_per_user": 2}).ok
FID, Fr = freelancer(B, A)
ag = Fr.post(B + "/api/my/agents", json={"username": "helper", "display_name": "Helper", "scopes": ["read", "tasks:write", "comments"]}).json()
assert "id" in ag, ag
AG, AH = ag["id"], {"Authorization": "Bearer " + ag["token"]}


def say(**b):
    r = requests.post(V + f"/agent/chats/{FID}", headers=AH, json=b)
    assert r.status_code == 201, (r.status_code, r.text[:300])
    return r.json()


def feed(kind):
    return [x for x in Fr.get(B + "/api/news").json()["items"] if x["kind"] == kind]


Fr.get(B + "/api/msgpop")  # the window's start
say(approval={"title": "Deploy **version 1.2** with `fast` mode"})
t = [x["data"].get("title") for x in feed("approval")]
check(t == ["Deploy version 1.2 with fast mode"], f"#6100 approval title without Markdown marks: {t}")
m = say(body="Shall I **really** send `the cut`?", choices=["Yes", "No"])
x = [i["data"].get("text") for i in feed("agentask")]
check(x and "**" not in x[0] and "`" not in x[0] and "really" in x[0], f"#6100 question text without Markdown marks: {x}")
say(body="## Done\n**Rendered** the `final` cut")
j = Fr.get(B + "/api/msgpop?t=0&a=0").json()
txt = [i["text"] for i in j.get("items", []) if i["src"] == "agent"]
check(txt and all("**" not in s and "`" not in s and "#" not in s for s in txt), f"#6100 pop-up lines without Markdown marks: {txt}")
sys.exit(done("p21215_a_chat_phone_news"))
