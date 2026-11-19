#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1292.0 (#6569): the places of the server agents are shared fairly (agents/srvagent_run.py _turn, _wait_note).
freelancer-matrix: agents (the person without an organisation is a holder of her own: her agent gets a place next to an organisation's)
 - an organisation X with three agents and a steady inflow, a person Y without an organisation with one agent: while Y waits,
   X holds at most one place and Y gets the next free one; once Y runs, X may use the rest again
 - only X waits: X uses both places
 - order: of two waiting holders with no place, the one waiting longest (the oldest event) goes first
 - an agent with work but no queued row never holds a place back (nothing would come to take it)
 - the person who asked hears once per wait that the agent waits for a free place (never who holds them); a new wait after a
   run is told again
The checks call the place step (_claim) in the container; the queue rows wait for a day, so the worker never takes them.
usage: p21292_b_srvagent_fair_test.py <datadir>      (KMT_NOSTART=1 / P21292B_NOSTART=1: a running server)"""
import json
import sys
import subprocess
import uuid

from freelancer_fixture import freelancer
from kt import B, CT, check, dbx, done, fresh, sess

fresh(prefix="P21292B")
assert sess().post(B + "/api/auth/setup", json={"username": "alice", "display_name": "Alice", "password": "password123"}).ok
A = sess("alice")
A.post(B + "/api/admin/setup", json={"org_name": "Example Studio", "lang": "en", "collab_all": True, "modules": ["comments", "collab"]})
A.patch(B + "/api/settings", json={"tour": "done", "lang": "en"})
ORG = A.get(B + "/api/state").json()["me"]["workspaces"][0]["id"]
check(A.put(B + "/api/admin/agent-policy", json={"user_agents": True}).ok, "personal agents allowed")
FID, Fr = freelancer(B, A)            # Y: a person without an organisation
GID, Gi = freelancer(B, A, "gina")    # Z: another one


def team(name):
    r = A.post(B + "/api/admin/agents", json={"username": name, "display_name": name.title(), "org_id": ORG})
    check(r.status_code in (200, 201), f"setup: team agent {name} {r.status_code} {r.text[:160]}")
    return r.json()["id"]


def own(s, name):
    r = s.post(B + "/api/my/agents", json={"username": name, "display_name": name.title()})
    check(r.status_code == 201, f"setup: personal agent {name} {r.status_code} {r.text[:160]}")
    return r.json()["id"]


X1, X2, X3 = team("xone"), team("xtwo"), team("xthree")
Y1, Z1 = own(Fr, "yone"), own(Gi, "zone")
ALL = (X1, X2, X3, Y1, Z1)
check(all(dbx("SELECT org_id FROM agents WHERE user_id=?", (x,)) == [(ORG,)] for x in (X1, X2, X3)), "setup: X's agents in the organisation")
check(dbx("SELECT org_id, owner_id FROM agents WHERE user_id=?", (Y1,)) == [(None, FID)], "setup: Y's agent is hers, no organisation")
dbx("UPDATE orgs SET srv_agents=1")  # (#6363): the Kalmido AI is off in a new organisation
for x in ALL:  # server agents with a key (never opened here: no run reaches a model)
    dbx("UPDATE agents SET provider='kalmido-server', ai=1 WHERE user_id=?", (x,))
    dbx("INSERT INTO agent_server(agent_id, key_sealed, key_hint) VALUES(?, 'sealed-test', 'test')", (x,))


def reset():
    dbx("DELETE FROM agent_runs")
    dbx("DELETE FROM bg_jobs WHERE kind='srvagent:run'")
    dbx("UPDATE agent_server SET cursor=(SELECT COALESCE(MAX(id), 0) FROM agent_events), wait_note=0")


def ev(aid, event="ping", age=0, data=None, actor=None):
    """An event that asks for work (age = seconds ago) -> its id."""
    env = {"event": event, "actor": actor, "data": data or {}}
    return dbx(f"""INSERT INTO agent_events(agent_id, uuid, event, payload, created_at) VALUES(?,?,?,?, now() - interval '{int(age)} seconds')
                   RETURNING id""", (aid, str(uuid.uuid4()), event, json.dumps(env)))[0][0]


def queued(aid):
    """A queue row of the agent that the worker never takes (a day later): the proof that it waits."""
    dbx("""INSERT INTO bg_jobs(kind, user_id, payload, state, attempts, run_after, created_at)
           VALUES('srvagent:run', ?, '', 'wait', 0, to_char((now() + interval '1 day') AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'), now())""", (aid,))


def running(aid):
    dbx("INSERT INTO agent_runs(agent_id, cause, state, started, beat_at) VALUES(?, 'ping', 'run', to_char(now(), 'YYYY-MM-DD\"T\"HH24:MI:SS'), now())", (aid,))


def wait(aid, age=0, **kw):
    ev(aid, age=age, **kw)
    queued(aid)


def py(code):
    out = subprocess.run(["docker", "exec", CT, "python", "-c", "import app\nfrom kalmido.core.db import connect\n"
                          "from kalmido.agents import srvagent_run as R\n" + code], capture_output=True, text=True)
    check(out.returncode == 0, f"the step in the container works {out.stderr[-800:]}")
    return out.stdout.strip().splitlines()[-1] if out.stdout.strip() else ""


def claim(aid):
    """'run' / 'busy' / 'None' of the place step for agent aid (a run row when it got a place)."""
    return py(f"c = connect()\nr = R._claim(c, {aid})\nc.close()\nprint('run' if isinstance(r, tuple) else r)")


check(py("print(R.SRV_PARALLEL)") == "2", "the instance has its default of two places (unchanged)")

# ---------------------------------------------------------------- (1) X holds one place while Y waits
reset()
running(X1)
wait(X2)              # X's inflow: X2 and X3 wait longer than Y
wait(X3)
wait(Y1)
check(claim(X2) == "busy", "(1) X runs one, Y waits: X2 gets no second place for X")  # without the fix: run (1 of 2 places used)
check(claim(X3) == "busy", "(1) nor X3")
check(claim(Y1) == "run", "(1) Y gets the free place")
check(claim(X2) == "busy", "(1) both places taken: X2 waits")
dbx("UPDATE agent_runs SET state='done' WHERE agent_id=?", (X1,))
wait(X1)              # its inflow goes on: X1 has new work at once
check(claim(X2) == "run", "(1) X1 ended, nobody else waits: X2 (waiting longest of X) takes the place")
check(claim(X1) == "busy", "(1) X1 waits for the next one")

# ---------------------------------------------------------------- (2) only X waits: both places
reset()
wait(X1)
wait(X2)
wait(X3)
check(claim(X1) == "run", "(2) only X waits: X1 runs")
check(claim(X2) == "run", "(2) only X waits: X2 takes the second place")
check(claim(X3) == "busy", "(2) no third place")

# ---------------------------------------------------------------- (3) the longest wait first
reset()
running(X1)
wait(Z1, age=30)
wait(Y1, age=5)
check(claim(Y1) == "busy", "(3) Y waits less long than Z: Y does not take the one free place")
check(claim(Z1) == "run", "(3) Z, waiting longest, takes it")
reset()
running(X1)
wait(X2, age=60)      # X waits longest but holds a place already: Y (no place) first
wait(Y1, age=5)
check(claim(X2) == "busy", "(3) a holder without a place goes before one with a place, however long that waits")
check(claim(Y1) == "run", "(3) Y gets it")

# ---------------------------------------------------------------- an agent without a queued row holds nothing back
reset()
running(X1)
ev(Y1, age=120)       # old work, but no row will come for it
wait(X2)
check(claim(X2) == "run", "Y has work but no queued row: X2 takes the free place")

# ---------------------------------------------------------------- (4) the wait note, once per wait
reset()
running(X1)
running(X2)
ask = {"chat_with": FID, "user": {"id": FID, "name": "Frida"}, "message": {"body": "hello"}}
first = ev(Y1, "chat", age=60, data=ask, actor={"kind": "person", "id": FID})
queued(Y1)


def notes():
    ms = Fr.get(B + f"/api/agents/{Y1}/chat").json().get("messages") or []
    return [m for m in ms if m.get("from") == "agent" and "places for server agents are busy" in (m.get("body") or "")]


py(f"R.srv_run_job({Y1})")
n1 = notes()
check(len(n1) == 1, f"(4) the person who asked hears once that the agent waits for a free place ({len(n1)})")
check(n1 and "xone" not in n1[0]["body"].lower() and "example studio" not in n1[0]["body"].lower(), "(4) the note never names who holds the places")
py(f"R.srv_run_job({Y1})")
ev(Y1, "chat", age=50, data=ask, actor={"kind": "person", "id": FID})  # she writes again while it waits: the same wait
py(f"R.srv_run_job({Y1})")
check(len(notes()) == 1, "(4) more tries and a second message of the same wait: no second note")
check(dbx("SELECT state FROM agent_runs WHERE agent_id=?", (Y1,)) == [], "(4) no run while the places are full")
dbx("UPDATE agent_runs SET state='done' WHERE agent_id=?", (X1,))
check(claim(Y1) == "run", "(4) a place is free: Y runs")
dbx("UPDATE agent_server SET cursor=(SELECT MAX(id) FROM agent_events WHERE agent_id=?) WHERE agent_id=?", (Y1, Y1))  # the run took them
dbx("UPDATE agent_runs SET state='done' WHERE agent_id=?", (Y1,))
running(X1)
check(len(notes()) == 1, "(4) the run started: nothing more said")
ev(Y1, "chat", age=40, data=ask, actor={"kind": "person", "id": FID})
py(f"R.srv_run_job({Y1})")
check(len(notes()) == 2, "(4) a new wait after the run is told again (once)")
check(dbx("SELECT wait_note FROM agent_server WHERE agent_id=?", (Y1,))[0][0] > first, "(4) the note marks the newest event of its wait")

sys.exit(done("p21292_b_srvagent_fair"))
