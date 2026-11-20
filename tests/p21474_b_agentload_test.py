#!/usr/bin/env python3
# kalmido-suite: fresh
"""(#6408) agents' load on the server.
(1) ONE budget of web threads for long requests - an agent's long-poll, a hosted MCP call and an assistant
call share it (core/longslots.py), so the rest of the threads stays free for people (waitress queue live 17.-19.11.).
Before, the three had caps of their own that together passed the threads. The server runs with KALMIDO_AGENT_WAITERS=2:
 - Administration's health view shows the budget and the places taken per kind (threads.long)
 - two agents waiting for events take both places: a third agent's wait answers busy at once, and an assistant call answers
   503 at once (was: it ran); a person's normal request still answers
 - when the waits end the places come back: the assistant answers again
 - two assistant calls that hang at the model take both places: an agent's wait answers busy (the budget is shared both ways)
The model is tests/fake_ai.py (FAKE_TIMEOUT sleeps; KALMIDO_AI_TIMEOUT_S=6 ends the call).
(2) the month's usage of an agent is one counter row (agent_usage_month), written with every report: the month limit counts
   from it (used, reached -> 429); the first report of a month starts the row from the reports already there (a row deleted =
   a month begun before the row existed)
(3) GET /api/agents/usage sums in SQL: the same numbers and the same form (keys of the answer, the agent, the totals)
(4) the partial indexes are usable by the queries they are for (EXPLAIN with sequential scans off): the unread agent answers
   of a person, the waiting jobs newest first
usage: p21474_b_agentload_test.py <datadir>"""
import os
import shutil
import subprocess
import sys
import threading
import time

import dbx as _dbx
import requests
from kt import B, CT, DATA, N, check, dbx, done, fresh, setup, until

fresh(env={"KALMIDO_AGENT_WAITERS": "2", "KALMIDO_AI_BASE_URL": "http://127.0.0.1:8089/v1", "KALMIDO_AI_MODEL": "fake-1",
           "KALMIDO_AI_KEY": "test-key", "KALMIDO_AI_NAME": "Fake-AI", "KALMIDO_AI_TIMEOUT_S": "6"}, prefix="P21474B")
A = setup()
A.patch(B + "/api/settings", json={"lang": "en", "assistant_on": "1"})
shutil.copy(os.path.join(N, "fake_ai.py"), DATA)
subprocess.run(["docker", "exec", "-d", CT, "python", "/data/fake_ai.py"], check=True)
check(until(lambda: subprocess.run(["docker", "exec", CT, "python", "-c", "import socket; socket.create_connection(('127.0.0.1', 8089), 1)"],
                                   capture_output=True).returncode == 0, 15), "the fake model answers")

L = A.post(B + "/api/lists", json={"name": "Work"}).json()["id"]
T = A.post(B + "/api/tasks", json={"title": "Plan the launch", "list_id": L, "content": "Budget note"}).json()["id"]
TH = A.post(B + "/api/tasks", json={"title": "FAKE_TIMEOUT hangs", "list_id": L}).json()["id"]
check(A.put(B + "/api/assistant/lists", json={"list_ids": [L]}).ok, "the list is shared with the assistant")
r = A.post(B + "/api/assistant/run", json={"kind": "summary", "task_id": T})
check(r.ok, f"(sanity) the assistant answers ({r.status_code} {r.text[:120]})")

TOK = []
for i in range(3):
    r = A.post(B + "/api/admin/agents", json={"scopes": ["read"], "username": f"bot{i}", "display_name": f"Bot {i}"})
    assert r.ok, r.text
    TOK.append({"Authorization": "Bearer " + r.json()["token"]})


def poll(h, wait):
    cur = requests.get(B + "/api/v1/agent/events", headers=h, params={"since": "latest"}, timeout=10).json()["cursor"]
    return requests.get(B + "/api/v1/agent/events", headers=h, params={"since": cur, "wait": wait}, timeout=wait + 30).json()


# ---- two waiting agents take both places
res = {}
ths = [threading.Thread(target=lambda i=i: res.__setitem__(i, poll(TOK[i], 12)), daemon=True) for i in (0, 1)]
for t in ths:
    t.start()
def taken():
    return A.get(B + "/api/admin/health").json()["threads"]["long"]


check(until(lambda: taken()["taken"] == {"poll": 2}, 8) and taken()["budget"] == 2, f"two agents wait: both places taken ({taken()})")
check(poll(TOK[2], 1).get("busy") is True, "a third agent's wait answers busy")
t0 = time.time()
r = A.post(B + "/api/assistant/run", json={"kind": "summary", "task_id": T})
check(r.status_code == 503 and time.time() - t0 < 3, f"the places are taken: the assistant answers 503 at once ({r.status_code} {r.text[:120]})")
check(A.get(B + "/api/state").ok, "a person's normal request still answers")
for t in ths:
    t.join(40)
check(res.get(0, {}).get("busy") is False and res.get(1, {}).get("busy") is False, f"the two waits were not refused ({res})")
r = A.post(B + "/api/assistant/run", json={"kind": "summary", "task_id": T})
check(r.ok, f"the waits ended: the assistant answers again ({r.status_code})")

# ---- two hanging assistant calls take both places: an agent's wait answers busy
hang = [threading.Thread(target=lambda: A.post(B + "/api/assistant/run", json={"kind": "summary", "task_id": TH}, timeout=40), daemon=True)
        for _ in (0, 1)]
for t in hang:
    t.start()
check(until(lambda: taken()["taken"] == {"assistant": 2}, 4), f"two assistant calls at the model: both places taken ({taken()})")
check(poll(TOK[0], 1).get("busy") is True, "an agent's wait answers busy")
for t in hang:
    t.join(40)
check(taken()["taken"] == {} and poll(TOK[0], 1).get("busy") is False, "the assistant calls ended: the places are free, the agent waits again")

# ---- (2) the month counter
r = A.post(B + "/api/admin/agents", json={"scopes": ["write"], "username": "meter", "display_name": "Meter"})
MID, HM = r.json()["id"], {"Authorization": "Bearer " + r.json()["token"]}
check(A.patch(B + f"/api/admin/agents/{MID}", json={"limits": {"period": "month", "metric": "tokens", "hard": 1000}}).ok, "a month limit of 1000 tokens")


def report(i, o, cost=None):
    j = {"model": "m1", "input_tokens": i, "output_tokens": o, **({"cost_usd": cost} if cost is not None else {})}
    r = requests.post(B + "/api/v1/agent/usage", headers=HM, json=j)
    assert r.status_code == 201, r.text
    return r.json()["limit"]


def month_row():
    rows = dbx("SELECT input_tokens, output_tokens, cost_usd, calls FROM agent_usage_month WHERE agent_id=?", (MID,))
    return dict(rows[0]) if rows else None


lim = report(300, 100, 0.5)
check(lim["used"] == 400 and month_row() == {"input_tokens": 300, "output_tokens": 100, "cost_usd": 0.5, "calls": 1},
      f"the first report starts the month's row ({lim['used']}, {month_row()})")
dbx("DELETE FROM agent_usage_month WHERE agent_id=?", (MID,))


def limit_used():
    return [a for a in A.get(B + "/api/agents/usage").json()["agents"] if a["id"] == MID][0]["limit"]["used"]


check(month_row() is None and limit_used() == 400, "without a row the month is summed from the reports")
lim = report(200, 100)
check(lim["used"] == 700 and month_row() == {"input_tokens": 500, "output_tokens": 200, "cost_usd": 0.5, "calls": 2},
      f"a month begun before the row: started from all its reports ({lim['used']}, {month_row()})")
check(requests.get(B + "/api/v1/lists", headers=HM).ok, "under the limit: calls pass")
lim = report(300, 50)
check(lim["used"] == 1050 and lim["reached"] and month_row()["calls"] == 3, f"the counter adds up to the limit ({lim})")
check(requests.get(B + "/api/v1/lists", headers=HM).status_code == 429, "over the month limit: 429 (counted from the row)")

# ---- (3) the overview: the same numbers, the same form
u = A.get(B + "/api/agents/usage", params={"agent_id": MID}).json()
check(set(u) == {"agents", "admin", "days", "agent_id", "per_day", "tasks", "lists", "models", "flows", "cost"}, f"the answer's keys {sorted(u)}")
me_ = [a for a in u["agents"] if a["id"] == MID][0]
check(set(me_) == {"id", "name", "enabled", "avatar", "totals", "limit_reached", "limit"} and set(me_["totals"]) == {"today", "d7", "d30"},
      f"an agent's keys {sorted(me_)}")
t = me_["totals"]["today"]
check(t == {"tokens": 1050, "input": 800, "output": 250, "cache_read": 0, "cache_write": 0, "cost": 0.5, "calls": 3, "web_searches": 0, "web_fetches": 0}
      and me_["totals"]["d30"] == t and me_["limit_reached"] is True, f"totals summed in SQL {t}")
day = [d for d in u["per_day"] if d["tokens"]]
check(len(u["per_day"]) == 30 and len(day) == 1 and day[0]["calls"] == 3 and day[0]["tokens"] == 1050, f"one day with the three reports {day}")
check([m["model"] for m in u["models"]] == ["m1"] and u["models"][0]["calls"] == 3 and u["cost"] is True, f"models {u['models']}")
check(u["lists"] and u["lists"][0].get("none") is True and u["lists"][0]["calls"] == 3, f"the reports without a project in one row {u['lists']}")

# ---- (4) the partial indexes are usable
dbc, dbn = _dbx._target(os.path.join(DATA, "tasks.db"))


def plan(sql):
    return _dbx._psql(dbc, dbn, "SET enable_seqscan=off;\nEXPLAIN " + sql + ";\n")


p = plan("SELECT agent_id, COUNT(*) FROM agent_chat WHERE agent_id = ANY(ARRAY[1,2]::BIGINT[]) AND user_id=1 AND sender='agent' "
         "AND read_at IS NULL GROUP BY agent_id")
check("ix6408_agent_chat_unread" in p, f"the unread count uses the partial index: {p}")
p = plan("SELECT * FROM agent_jobs WHERE state='waiting' ORDER BY updated_at DESC, id DESC LIMIT 200")
check("ix6408_agent_jobs_waiting" in p, f"the waiting jobs use the partial index: {p}")
sys.exit(done("p21474_b_agentload"))
