#!/usr/bin/env python3
# kalmido-suite: fresh
"""#6486: notify() itself turns a disabled account away (the second line behind every caller): no push, no channel message.
Invented names only. The person is one without an organisation (the main case); each step first shows the push reaches her
while the account is on, so a green result is not an empty one.
 (1) notify() directly: on = sent, disabled = False and nothing sent (web push, ntfy, channels)
 (2) the three callers not followed one by one in #6351, each run with the disabled person forced into the watchdog's users:
     the weekly rotation (family/v1.py _wd_rotations), the contact care push (life/model.py _wd_care), the fixed-time
     reminder (tasks/remindat.py rat_tick)
usage: p6486_notify_disabled_test.py <datadir>"""
import json
import os
import subprocess
import sys

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
from freelancer_fixture import freelancer  # noqa: E402
from kt import B, check, done, fresh, setup  # noqa: E402

CT = os.environ.get("KALMIDO_TEST_CONTAINER", "kalmido-test")
fresh()
A = setup()
DU, Do = freelancer(B, A, "dora")
check(Do.patch(B + "/api/settings", json={"lang": "en"}).ok, "setup: language")
L = Do.post(B + "/api/lists", json={"name": "Home"}).json()["id"]
BK = Do.post(B + "/api/books", json={"name": "Friends"}).json()["id"]
CID = Do.post(B + "/api/contacts", json={"book_id": BK, "fn": "Paula Example", "given": "Paula", "family": "Example"}).json()["id"]
check(Do.put(B + f"/api/contacts/{CID}/care", json={"every_days": 7, "last": "2020-01-01"}).ok, "setup: stay in touch with a contact")


def task(title):
    r = Do.post(B + "/api/tasks", json={"list_id": L, "title": title})
    assert r.ok, r.text
    return r.json()["id"]


T_ROT, T_ROT2, T_REM, T_REM2 = task("Bins out"), task("Water plants"), task("Call the bank"), task("Pay the rent")

HEAD = f"""import json
from datetime import datetime, timedelta, timezone
import app
from kalmido.core.db import connect, usettings
from kalmido.core.pg import system_ctx
from kalmido.core.usertz import tz_of_s
import kalmido.notify.push as P
import kalmido.notify.channels as CH
c = connect()
GOT = []
def _wp(uid, payload, *a, **k):
    GOT.append(("webpush", uid))
    return 1  # one device took it
def _nt(*a, **k):
    GOT.append(("ntfy", a[0]))
    return 1  # the ntfy server took it
def _ch(uid, *a, **k):
    GOT.append(("channel", uid))
    return 0  # nothing queued on a channel
P.webpush_user, P.ntfy, CH.chn_push = _wp, _nt, _ch
DU = {DU}
now = datetime.now(timezone.utc)

def world():
    with system_ctx(c):
        users = {{r["id"]: r for r in c.execute("SELECT * FROM users WHERE id=?", (DU,))}}  # forced in, also when disabled
        s = dict(usettings(c, DU))
    s.update(push_channel="both", ntfy_topic="t-dora", allday_time="00:00", care_sent="", features=",".join(sorted(set((s.get("features") or "").split(",")) | {{"care", "contacts"}} - {{""}})))
    return users, {{DU: s}}, {{DU: "en"}}

def disable(on):
    with system_ctx(c):
        c.execute("UPDATE users SET disabled=? WHERE id=?", (on, DU))
        c.commit()

def rotate(tid):
    with system_ctx(c):
        c.execute("UPDATE tasks SET assignee_id=NULL, rotation=? WHERE id=?", (json.dumps({{"mode": "week", "who": [DU], "i": 0, "wk": "2000-W01"}}), tid))
        c.commit()
    from kalmido.family.v1 import _wd_rotations
    with system_ctx(c):
        _wd_rotations(c, *world(), now)

def care():
    from kalmido.life.model import _wd_care
    with system_ctx(c):
        _wd_care(c, *world(), now)  # world() clears care_sent: the day's push may come again

def remind(tid):
    at = (now - timedelta(minutes=5)).astimezone(tz_of_s(world()[1][DU])).strftime("%Y-%m-%dT%H:%M")
    with system_ctx(c):
        c.execute("UPDATE tasks SET remind_at=?, reminded='[]' WHERE id=?", (at, tid))
        c.commit()
    from kalmido.tasks.remindat import rat_tick
    with system_ctx(c):
        rat_tick(c, *world(), now)

def mine():
    return [g for g in GOT if g[1] in (DU, "t-dora") or g[0] == "ntfy"]
"""


def in_app(code):
    """Lines of Python inside the container; prints the JSON of `out`."""
    r = subprocess.run(["docker", "exec", "-w", "/app", "-e", "TASKS_WATCHDOG=0", CT, "python", "-c",
                        HEAD + code + "\nprint('OUT' + json.dumps(out))"], capture_output=True, text=True, timeout=200)
    for line in r.stdout.splitlines():
        if line.startswith("OUT"):
            return json.loads(line[3:])
    raise AssertionError(r.stdout[-800:] + r.stderr[-1500:])


out = in_app(f"""
out = {{}}
disable(False)
s = world()[1][DU]
out["on"] = P.notify(DU, "Hello", "while on", s=s, kind="other", quiet=False)
out["on_got"] = len(mine())
GOT.clear()
disable(True)
out["off"] = P.notify(DU, "Hello", "while disabled", s=s, kind="other", quiet=False)
out["off_s_none"] = P.notify(DU, "Hello", "settings read by notify", kind="other", quiet=False)
out["off_got"] = mine()
GOT.clear()
# (2) the three callers: first on (the push comes), then disabled (nothing)
disable(False)
rotate({T_ROT}); out["rot_on"] = len(mine()); GOT.clear()
care(); out["care_on"] = len(mine()); GOT.clear()
remind({T_REM}); out["rem_on"] = len(mine()); GOT.clear()
disable(True)
rotate({T_ROT2}); out["rot_off"] = mine(); GOT.clear()
care(); out["care_off"] = mine(); GOT.clear()
remind({T_REM2}); out["rem_off"] = mine(); GOT.clear()
disable(False)
""")
check(bool(out["on"]) and out["on_got"] >= 1, f"(1) an account that is on gets the push {out}")
check(out["off"] is False and out["off_s_none"] is False and out["off_got"] == [],
      f"(1) a disabled account: notify() gives False, nothing goes out (also with the settings passed in) {out}")
for k, what in (("rot", "the weekly rotation"), ("care", "the contact care push"), ("rem", "the fixed-time reminder")):
    check(out[k + "_on"] >= 1, f"(2) {what}: reaches the person while the account is on {out}")
    check(out[k + "_off"] == [], f"(2) {what}: nothing for the disabled account, even when the caller passes her on {out}")

sys.exit(done("p6486_notify_disabled"))
