#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1408.0 (#6388): the queue bg_jobs - failed and lost rows are seen, a raising function is tried again, waiting rows have a
highest age; a server agent's run that a restart cut off tells its person. Own container (start.sh). Invented accounts only.
 1. a function that raises: the row waits again with a growing gap (30 s, then 60 s), the payload kept, the error named; after
    its runs (retry=3) it fails; a kind with tries=1 and no retry fails at once (the old way). mail:* / push:* retry 3, highest
    age 24 h / 1 h; other kinds keep their tries and have no highest age
 2. the housekeeping: a push waiting over an hour and a mail over 24 h fail 'expired' (payload gone), younger ones and kinds
    without a highest age wait on; a row of a kind no process knows fails 'unknown kind' after 24 h, not before
 3. the watchdog (notify/alerts.py aa_bgjobs): more than KALMIDO_BG_ALARM_FAILED rows failed in the last hour and a due row waiting > 15 min
    -> two admin alerts (kind storage, numbers and kind names only); GET /api/admin/health shows failed_1h / oldest_wait_s
 4. the server agent: a run taken for lost (_claim) and the runs of a stopping process (srv_on_stop, a hook of
    bgjobs BGJ_ON_STOP) end 'interrupted' and their person hears "please send it again" once; the run's own end then says
    nothing more
freelancer-matrix: n/a (no new route; alice has no organisation)
usage: p21408_6388_bgjobs_test.py <datadir>"""
import json
import os
import subprocess
import sys
import time

import kt
import requests
from kt import check, sess

N = os.path.dirname(os.path.abspath(__file__))
DATA = sys.argv[1] if len(sys.argv) > 1 else os.path.join(N, ".data")
B = "http://127.0.0.1:" + os.environ.get("KALMIDO_TEST_PORT", "3048")
H = {"X-Requested-With": "kalmido"}
CONT = os.environ.get("KALMIDO_TEST_CONTAINER", "kalmido-test")


def start():
    r = subprocess.run(["bash", os.path.join(N, "start.sh"), DATA], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    for _ in range(60):
        try:
            if requests.get(B + "/api/health", timeout=2).ok:
                break
        except requests.RequestException:
            pass
        time.sleep(0.5)


def py(code):
    """Runs code in a second process of the container (no loops: TASKS_WATCHDOG=0, role web); the last line = JSON."""
    for _try in range(3):  # the import may meet the running server's start-up DDL (deadlock): try again
        r = subprocess.run(["docker", "exec", "-w", "/app", "-e", "TASKS_WATCHDOG=0", "-e", "KALMIDO_ROLE=web", CONT,
                            "python", "-c", "import app\n" + code], capture_output=True, text=True)
        if "DeadlockDetected" not in r.stdout + r.stderr:
            break
        time.sleep(2)
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        print((r.stdout + r.stderr)[-2000:], flush=True)
        return {}


start()
s0 = requests.Session()
s0.headers.update(H)
assert s0.post(B + "/api/auth/setup", json={"username": "alice", "display_name": "Alice Admin", "password": "password123"}).ok
A = sess("alice")
A.post(B + "/api/admin/setup", json={"lang": "en"})

# ---------------------------------------------------------------- 1. a raising function is tried again, a while later
r1 = py("""
import json
from datetime import timedelta
from kalmido.accounts import bgjobs as q
from kalmido.core.db import connect
from kalmido.core.pg import system_ctx
from kalmido.core.db import parse_iso

@q.bgj_fn("p6388:boom", tries=1, retry=3)
def boom(x):
    raise RuntimeError("no")

@q.bgj_fn("p6388:once", tries=1)
def once(x):
    raise RuntimeError("no")

out = {"steps": []}
c = connect()
def run(kind):
    with system_ctx(c):
        c.execute("UPDATE bg_jobs SET run_after=? WHERE kind=? AND state='wait'", (q.iso(q._now() - timedelta(seconds=1)), kind))
    c.commit()
    r = q.bgj_claim(c, [kind])
    c.commit()
    t0 = q._now()
    q._run_row(r["id"], kind, q._unseal(c, kind, r["payload"]), r["attempts"])
    with system_ctx(c):
        x = c.execute("SELECT state, attempts, error, payload<>'' AS kept, run_after FROM bg_jobs WHERE id=?", (r["id"],)).fetchone()
    c.commit()
    return {"state": x["state"], "attempts": x["attempts"], "error": x["error"], "kept": bool(x["kept"]),
            "gap": round((parse_iso(x["run_after"]) - t0).total_seconds())}
q.bgj_add("p6388:boom", 1)
for _ in range(3):
    out["steps"].append(run("p6388:boom"))
q.bgj_add("p6388:once", 1)
out["once"] = run("p6388:once")
out["retry"] = {k: q.BGJ_RETRY_OF.get(k) for k in ("mail:pwreset", "mail:polls", "push:send", "backup", "umz:import")}
out["age"] = {k: q.BGJ_AGE_OF.get(k) for k in ("mail:pwreset", "mail:portal", "push:send", "backup", "umz:import")}
print(json.dumps(out))
""")
st = r1.get("steps") or [{}] * 3
check(st[0].get("state") == "wait" and st[0].get("attempts") == 1 and st[0].get("error") == "RuntimeError" and st[0].get("kept")
      and 25 <= st[0].get("gap", 0) <= 35, f"a raising function: the row waits again about 30 s later, payload kept, error named {st[0]}")
check(st[1].get("state") == "wait" and st[1].get("attempts") == 2 and 55 <= st[1].get("gap", 0) <= 65, f"the second run: 60 s (the gap grows) {st[1]}")
check(st[2].get("state") == "failed" and st[2].get("attempts") == 3 and not st[2].get("kept"), f"after its 3 runs the row fails, payload gone {st[2]}")
check((r1.get("once") or {}).get("state") == "failed" and (r1.get("once") or {}).get("attempts") == 1,
      f"a kind with tries=1 and no retry fails at its first error (as before) {r1.get('once')}")
check(r1.get("retry") == {"mail:pwreset": 3, "mail:polls": 3, "push:send": 3, "backup": 3, "umz:import": 1},
      f"retry: mail / push 3, the others their tries {r1.get('retry')}")
check(r1.get("age") == {"mail:pwreset": 86400, "mail:portal": 86400, "push:send": 3600, "backup": None, "umz:import": None},
      f"highest age: mail 24 h, push 1 h, the others none {r1.get('age')}")

# ---------------------------------------------------------------- 2. too old: expired; a kind nobody knows: not for ever
r2 = py("""
import json
from datetime import timedelta
from kalmido.accounts import bgjobs as q
from kalmido.core.db import connect
from kalmido.core.pg import system_ctx
c = connect()
now = q._now()
ids = {}
with system_ctx(c):
    for name, kind, h in (("push_old", "push:send", 2), ("push_new", "push:send", 0.5), ("mail_old", "mail:forms", 25),
                          ("mail_new", "mail:forms", 23), ("backup_old", "backup", 72), ("nokind_old", "p6388:nokind", 25),
                          ("nokind_new", "p6388:nokind", 2)):
        ids[name] = c.execute("INSERT INTO bg_jobs(kind, payload, state, attempts, run_after, created_at) VALUES(?, 'v2.x', 'wait', 0, "
                              "'2999-01-01T00:00:00+00:00', ?) RETURNING id", (kind, q.iso(now - timedelta(hours=h)))).fetchone()[0]
c.commit()
h = q.bgj_house(c, force=True)
with system_ctx(c):
    got = {n: dict(c.execute("SELECT state, error, payload FROM bg_jobs WHERE id=?", (i,)).fetchone()) for n, i in ids.items()}
    c.execute("DELETE FROM bg_jobs WHERE id IN (" + ",".join(str(i) for i in ids.values()) + ")")
c.commit()
print(json.dumps({"got": got, "house": h}))
""")
g = r2.get("got") or {}
st2 = {k: (v.get("state"), v.get("error")) for k, v in g.items()}
check(st2.get("push_old") == ("failed", "expired") and st2.get("mail_old") == ("failed", "expired")
      and g["push_old"]["payload"] == "" and g["mail_old"]["payload"] == "", f"a push over 1 h and a mail over 24 h: expired, payload gone {st2}")
check(st2.get("push_new", ("",))[0] == "wait" and st2.get("mail_new", ("",))[0] == "wait" and st2.get("backup_old", ("",))[0] == "wait",
      f"younger ones and a kind without a highest age wait on {st2}")
check(st2.get("nokind_old") == ("failed", "unknown kind") and st2.get("nokind_new", ("",))[0] == "wait",
      f"a kind no process knows: failed after 24 h, not before {st2}")
check((r2.get("house") or {}).get("expired", 0) >= 3, f"the housekeeping counts them {r2.get('house')}")

# ---------------------------------------------------------------- 3. the watchdog alerts the admins
r3 = py("""
import json
from datetime import timedelta
from kalmido.accounts import bgjobs as q
from kalmido.notify import alerts
from kalmido.core.db import connect
from kalmido.core.pg import system_ctx
c = connect()
now = q._now()
quiet = alerts.aa_bgjobs(c, force=True)
keys0 = [x[1] for x in alerts._AA["q"]]
with system_ctx(c):
    for i in range(alerts.AA_BG_FAILED + 1):
        c.execute("INSERT INTO bg_jobs(kind, payload, state, attempts, run_after, created_at, finished_at, error) "
                  "VALUES('p6388:gone', '', 'failed', 1, ?, ?, ?, 'RuntimeError')", (q.iso(now), q.iso(now), q.iso(now)))
    c.execute("INSERT INTO bg_jobs(kind, payload, state, attempts, run_after, created_at) VALUES('p6388:late', 'v2.x', 'wait', 0, ?, ?)",
              (q.iso(now - timedelta(minutes=20)), q.iso(now - timedelta(minutes=20))))
c.commit()
t = alerts.aa_bgjobs(c, force=True)
again = alerts.aa_bgjobs(c)
qq = [x for x in alerts._AA["q"]]
print(json.dumps({"quiet": quiet, "keys0": keys0, "t": t, "again": again, "alerts": [[x[0], x[1], x[3], x[4]] for x in qq]}))
""")
al = {a[1]: a for a in r3.get("alerts") or []}
check(not [k for k in r3.get("keys0") or [] if k.startswith("bgjobs:")], f"a quiet queue: no alert {r3.get('keys0')} {r3.get('quiet')}")
t = r3.get("t") or {}
check(t.get("failed_1h", 0) > 10 and "p6388:gone" in (t.get("failed_kinds") or []) and t.get("oldest_wait_s", 0) >= 1150,
      f"the numbers: failed in the last hour, their kinds, the oldest due row's wait {t}")
check("bgjobs:failed" in al and al["bgjobs:failed"][0] == "storage" and al["bgjobs:failed"][3] == t.get("failed_1h")
      and "p6388:gone" in str(al["bgjobs:failed"][2]), f"more than {10} failed in an hour: an admin alert (storage) with count and kinds {al.get('bgjobs:failed')}")
check("bgjobs:waiting" in al and al["bgjobs:waiting"][2][0] >= 19, f"the oldest due row waits over 15 min: an admin alert with the minutes {al.get('bgjobs:waiting')}")
check(r3.get("again") is None, "the watchdog looks again only after AA_BG_EVERY")
hq = (A.get(B + "/api/admin/health").json() or {}).get("queue") or {}
check(hq.get("failed_1h", 0) > 10 and hq.get("oldest_wait_s", 0) >= 1150 and "p6388:gone" in (hq.get("failed_kinds") or []),
      f"GET /api/admin/health: the queue shows failed_1h, failed_kinds, oldest_wait_s {hq}")
py("""
from kalmido.core.db import connect
from kalmido.core.pg import system_ctx
c = connect()
with system_ctx(c):
    c.execute("DELETE FROM bg_jobs WHERE kind LIKE 'p6388:%'")
c.commit()
print("{}")
""")

# ---------------------------------------------------------------- 4. the server agent tells the person of a cut-off run
r4 = py("""
import json
from datetime import timedelta
from kalmido.accounts import bgjobs as q
from kalmido.agents import srvagent_run as sr
from kalmido.core.db import connect, iso, now_utc
from kalmido.core.pg import system_ctx
said = []
sr._wait_say = lambda aid, who, text=sr.SRV_WAIT_TEXT: said.append([aid, list(who), text])
c = connect()
with system_ctx(c):
    uid = c.execute("SELECT id FROM users WHERE username='alice'").fetchone()[0]
    old = iso(now_utc() - timedelta(seconds=sr.SRV_LOST_S + 60))
    lost = c.execute("INSERT INTO agent_runs(agent_id, cause, state, started, beat_at, asked_by) VALUES(?, 'chat', 'run', ?, ?, ?) RETURNING id",
                     (uid, old, old, uid)).fetchone()[0]
    live = c.execute("INSERT INTO agent_runs(agent_id, cause, state, started, beat_at, asked_by) VALUES(?, 'chat', 'run', ?, ?, ?) RETURNING id",
                     (uid, iso(now_utc()), iso(now_utc()), uid)).fetchone()[0]
c.commit()
out = {}
sr._claim(c, uid, out=out)
c.close()
sr._lost_say(out.get("lost"))
claim_said = list(said)
said.clear()
sr._LIVE[live] = uid
sr.srv_on_stop()
c = connect()
with system_ctx(c):
    st = {i: list(c.execute("SELECT state, error FROM agent_runs WHERE id=?", (i,)).fetchone()) for i in (lost, live)}
    c.execute("DELETE FROM agent_runs WHERE id IN (?, ?)", (lost, live))
c.commit()
print(json.dumps({"uid": uid, "claim": claim_said, "stop": said, "st": {str(k): v for k, v in st.items()}, "told": live in sr._TOLD,
                  "hooked": sr.srv_on_stop in q.BGJ_ON_STOP, "lost": lost, "live": live, "text": sr.SRV_INTR_TEXT}))
""")
uid, txt = r4.get("uid"), r4.get("text")
st4 = r4.get("st") or {}
check(r4.get("claim") == [[uid, [uid], txt]], f"a run taken for lost: its person hears once 'please send it again' {r4.get('claim')}")
check(st4.get(str(r4.get("lost"))) == ["failed", "The server agent was interrupted"], f"... the run is interrupted {st4}")
check(r4.get("hooked") and r4.get("stop") == [[uid, [uid], txt]] and st4.get(str(r4.get("live"))) == ["failed", "The server agent was interrupted"],
      f"the stop of the process: the running run ends interrupted, its person is told at once {r4.get('stop')} {st4}")
check(r4.get("told"), "the run told at the stop says nothing more at its own end")
de = json.load(open(os.path.join(N, "..", "static", "i18n", "de.json"), encoding="utf-8"))
check(all(k in de for k in (txt or "-", "The oldest background job has been waiting for {0} minutes. Is the worker running?",
                            "{0} background job failed in the last hour ({1}).")), "the new texts are translated (de)")

sys.exit(kt.done("p21408_6388_bgjobs_test"))
