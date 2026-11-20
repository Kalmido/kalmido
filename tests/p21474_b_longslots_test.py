#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1474.0 (#6408): ONE budget of web threads for long requests - an agent's long-poll, a hosted MCP call and an assistant
call share it (core/longslots.py), so the rest of the threads stays free for people (waitress queue live 17.-19.11.).
Before, the three had caps of their own that together passed the threads. The server runs with KALMIDO_AGENT_WAITERS=2:
 - Administration's health view shows the budget and the places taken per kind (threads.long)
 - two agents waiting for events take both places: a third agent's wait answers busy at once, and an assistant call answers
   503 at once (was: it ran); a person's normal request still answers
 - when the waits end the places come back: the assistant answers again
 - two assistant calls that hang at the model take both places: an agent's wait answers busy (the budget is shared both ways)
The model is tests/fake_ai.py (FAKE_TIMEOUT sleeps; KALMIDO_AI_TIMEOUT_S=6 ends the call).
usage: p21474_b_longslots_test.py <datadir>"""
import os
import shutil
import subprocess
import sys
import threading
import time

import requests
from kt import B, CT, DATA, N, check, done, fresh, setup, until

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
sys.exit(done("p21474_b_longslots"))
