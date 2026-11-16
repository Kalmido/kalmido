#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1294.0 (#6568): on a hosted server (KALMIDO_HOSTED=1) a server agent never runs without a hard day limit, and runs nobody
asked for count against their own share of it (agents/srvteam.py srv_limits_check / srv_limit_fix / srv_nobody_block).
Against tests/fake_anthropic.py (a stand-in for the Anthropic Messages API inside the test container); invented names and keys.
freelancer-matrix: agents (the person without an organisation sets up her own server agent on a hosted server)
 - GET /api/agents/server/defaults and .../server: day_limit_required, day_limit_max = the operator's ceiling (default 10 million)
 - PUT with the first key: day_limit null 400 (never emptied), above the ceiling 400, missing = the default 2 million a day
 - PATCH /api/my/agents/<id> limits: null / a month limit / above the ceiling 400; another day limit within the ceiling is kept
 - the operator's ceiling (PUT /api/admin/agent-policy server_day_cap): an agent from before without a limit, or above a lowered
   ceiling, gets a hard day limit at its next run
 - a run nobody asked for (a public form in a project the agent listens in) runs within a quarter of the day limit and is marked
   no_person; over that share the next such run fails with a clear reason in the owner's chat, the owner's own requests still run
usage: p21294_b_srvhosted_test.py <datadir>      (KMT_NOSTART=1 / P21294B_NOSTART=1: a running server)"""
import json
import os
import re
import shutil
import subprocess
import time

import requests

from kt import B, CT, DATA, check, dbx, done, docker_logs_on_first_fail, fresh, until
from freelancer_fixture import freelancer

N = os.path.dirname(os.path.abspath(__file__))
SKEY = "AQIDBAUGBwgJCgsMDQ4PEBESExQVFhcYGRobHB0eHyA="  # a test server key (the provider key is sealed with it)
KEY1 = "sk-test-hosted-0123456789-hhhh"
fresh(env={"KALMIDO_SECRET_KEY": SKEY, "KALMIDO_HOSTED": "1", "KALMIDO_SRVAGENT_ANTHROPIC_URL": "http://127.0.0.1:8091",
           "KALMIDO_SRVAGENT_RUN_S": "60", "KALMIDO_SRVAGENT_STEPS": "6"}, prefix="P21294B")
docker_logs_on_first_fail()
import kt  # noqa: E402
A = kt.setup()
shutil.copy(os.path.join(N, "fake_anthropic.py"), DATA)
subprocess.run(["docker", "exec", "-d", CT, "python", "/data/fake_anthropic.py"], check=True)
until(lambda: subprocess.run(["docker", "exec", CT, "python", "-c", "import socket; socket.create_connection(('127.0.0.1', 8091), 1)"],
                             capture_output=True).returncode == 0, 20)
H = {"X-Requested-With": "kalmido"}
DAY = lambda hard, soft=None: {"period": "day", "metric": "tokens", "soft": soft, "hard": hard}  # noqa: E731

check(A.put(B + "/api/admin/agent-policy", json={"user_agents": True, "max_per_user": 5}).ok, "personal agents allowed")
FID, Fr = freelancer(B, A)


def limits(aid):
    x = dbx("SELECT usage_limits FROM agents WHERE user_id=?", (aid,))
    return json.loads(x[0][0]) if x and x[0][0] else None


def agent(name):
    r = Fr.post(B + "/api/my/agents", json={"username": name, "display_name": name.title()})
    check(r.status_code == 201, f"setup: her agent {name} ({r.status_code} {r.text[:160]})")
    return r.json().get("id")


def runs(aid):
    return dbx("SELECT id, state, error, no_person FROM agent_runs WHERE agent_id=? ORDER BY id", (aid,))


def ended(aid, n):
    """The runs of aid once n of them ended (a real state, no fixed wait)."""
    return until(lambda: (lambda rs: rs if len([x for x in rs if x[1] != "run"]) >= n else None)(runs(aid)), 40)


def agent_says(aid, after, needle, secs=40):
    def f():
        ms = Fr.get(B + f"/api/agents/{aid}/chat").json()["messages"]
        hit = [m for m in ms if m["from"] == "agent" and m["id"] > after and needle in (m["body"] or "")]
        return hit[-1] if hit else None
    return until(f, secs)


def max_mid(aid):
    return max([m["id"] for m in Fr.get(B + f"/api/agents/{aid}/chat").json()["messages"]] or [0])


# ---------------------------------------------------------------- what the dialogs learn
j = Fr.get(B + "/api/agents/server/defaults").json()
check(j.get("day_limit_required") is True and j.get("day_limit_max") == 10000000 and j.get("day_limit_default") == 2000000,
      f"the new-agent dialog: the day limit is required, at most the ceiling ({j.get('day_limit_required')}, {j.get('day_limit_max')})")
p = A.get(B + "/api/admin/agent-policy").json()
check(p.get("server_day_cap") == 10000000 and p.get("server_day_cap_applies") is True, f"the operator view: the ceiling {p.get('server_day_cap')}")

# ---------------------------------------------------------------- the first key: never without a day limit
A1 = agent("kki-host")
r = Fr.put(B + f"/api/agents/{A1}/server", json={"api_key": KEY1, "day_limit": None})
check(r.status_code == 400 and "daily limit" in r.text and KEY1 not in r.text, f"day_limit emptied: 400 ({r.status_code} {r.text[:160]})")
r = Fr.put(B + f"/api/agents/{A1}/server", json={"api_key": KEY1, "day_limit": 10000001})
check(r.status_code == 400 and "at most" in r.text, f"day_limit above the ceiling: 400 ({r.status_code} {r.text[:160]})")
check(limits(A1) is None and not dbx("SELECT 1 FROM agent_server WHERE agent_id=? AND key_sealed<>''", (A1,)), "a refused PUT stores nothing")
r = Fr.put(B + f"/api/agents/{A1}/server", json={"api_key": KEY1})
check(r.ok and r.json().get("limits") == DAY(2000000) and r.json().get("day_limit_required") is True,
      f"the first key without day_limit: the default hard day limit ({r.status_code} {r.text[:300]})")
check(limits(A1) == DAY(2000000), f"stored on the agent ({limits(A1)})")

# ---------------------------------------------------------------- changed, never removed
for bad, what in ((None, "removed"), ({"period": "month", "metric": "tokens", "hard": 500}, "a month limit"),
                  ({"period": "day", "metric": "tokens", "soft": 500}, "only a soft limit"), (DAY(10000001), "above the ceiling")):
    r = Fr.patch(B + f"/api/my/agents/{A1}", json={"limits": bad})
    check(r.status_code == 400 and limits(A1) == DAY(2000000), f"the owner's limits {what}: 400, the limit stays ({r.status_code} {limits(A1)})")
r = Fr.patch(B + f"/api/my/agents/{A1}", json={"limits": DAY(3000000, 1000000)})
check(r.ok and limits(A1) == DAY(3000000, 1000000), f"another day limit within the ceiling is kept ({r.status_code} {limits(A1)})")

# ---------------------------------------------------------------- an agent from before and a lowered ceiling: fixed at its next run
dbx("UPDATE agents SET usage_limits='' WHERE user_id=?", (A1,))  # as an agent set up before 2.1294.0 (no limit)
r = A.put(B + "/api/admin/agent-policy", json={"server_day_cap": 1000000})
check(r.ok and r.json().get("server_day_cap") == 1000000, f"the operator lowers the ceiling ({r.status_code} {r.text[:160]})")
after = max_mid(A1)
check(Fr.post(B + f"/api/agents/{A1}/chat", json={"body": "Hello"}).status_code == 201, "a chat message")
check(agent_says(A1, after, "FAKE answer"), "the run answers")
check(limits(A1) == DAY(1000000), f"its run gave it the hard day limit (the default, at most the ceiling) ({limits(A1)})")
check(Fr.patch(B + f"/api/my/agents/{A1}", json={"limits": DAY(1500000)}).status_code == 400, "above the lowered ceiling: 400")
check(A.put(B + "/api/admin/agent-policy", json={"server_day_cap": None}).json().get("server_day_cap") == 10000000, "the ceiling back to its default")

# ---------------------------------------------------------------- runs nobody asked for: their own share
check(Fr.patch(B + f"/api/my/agents/{A1}", json={"limits": DAY(400)}).ok, "setup: a small day limit (its share without a person: 100)")
dbx("DELETE FROM agent_usage WHERE agent_id=?", (A1,))  # today starts empty (the chat above used tokens)
A.patch(B + "/api/admin/settings", json={"public_links": True})
FL = Fr.post(B + "/api/lists", json={"name": "Requests", "org_id": None}).json()["id"]
check(Fr.put(B + f"/api/lists/{FL}/members", json={"user_id": A1, "role": "edit"}).ok, "setup: the project shared with her agent")
check(Fr.patch(B + f"/api/lists/{FL}", json={"listen_agent_ids": [A1]}).ok, "her agent listens in")
r = Fr.post(B + f"/api/lists/{FL}/forms", json={"title": "Contact", "access": "public", "questions": [{"kind": "short", "label": "Your wish", "required": True}]})
check(r.status_code == 201, f"setup: a public form ({r.status_code} {r.text[:160]})")
QID, TOK = r.json()["questions"][0]["id"], r.json()["url"].rsplit("/", 1)[1]


def send_form(text):
    anon = requests.Session()
    anon.headers.update(H)
    m = re.search(r'name="stamp" value="([^"]+)"', anon.get(B + "/f/" + TOK).text)
    st = m.group(1) if m else ""
    until(lambda: time.time() - int(st.split(".")[0] or 0) > 3.2, 10)  # the stamp's least age (FRM_MIN_S): a real state
    rr = anon.post(B + "/f/" + TOK, data={f"q_{QID}": text, "name": "Eve", "email": "eve@example.com", "stamp": st})
    check(rr.ok and "Your request has been sent." in rr.text, f"a stranger sends the form ({rr.status_code})")


n0 = len(runs(A1))
send_form("A first wish")
rs = ended(A1, n0 + 1)
last = rs[-1] if rs else None
check(last and last[1] == "done" and last[3] is True, f"the run nobody asked for runs and is marked no_person {last}")
u = dbx("SELECT COUNT(*), SUM(input_tokens + output_tokens + cache_write_tokens) FROM agent_usage WHERE agent_id=? AND no_person", (A1,))
check(u and u[0][0] == 1 and u[0][1] == 125, f"its usage counts as nobody's ({u})")
after = max_mid(A1)
send_form("A second wish")
rs = ended(A1, n0 + 2)
last = rs[-1] if rs else None
check(last and last[1] == "failed" and "nobody asked for" in (last[2] or "") and last[3] is True,
      f"over its share (125 of 100 used) the next run nobody asked for fails with the reason {last}")
m = agent_says(A1, after, "nobody asked for")
check(m and "could not finish" in m["body"], f"the owner reads why in the chat {(m or {}).get('body', '')[:200]}")
check(dbx("SELECT COUNT(*) FROM agent_usage WHERE agent_id=? AND no_person", (A1,))[0][0] == 1, "no model call for it")
after = max_mid(A1)
check(Fr.post(B + f"/api/agents/{A1}/chat", json={"body": "Still there?"}).status_code == 201, "the owner asks herself")
check(agent_says(A1, after, "FAKE answer"), "her own request still runs (125 + 125 of 400)")
rs = ended(A1, n0 + 3)
check(rs and rs[-1][1] == "done" and rs[-1][3] is False, f"her run is no run without a person {rs[-1] if rs else None}")
check(dbx("SELECT status FROM agents WHERE user_id=?", (A1,)) == [("idle",)], "the agent itself does not pause")

raise SystemExit(done("p21294_b_srvhosted"))
