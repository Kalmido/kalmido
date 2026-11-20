#!/usr/bin/env python3
# kalmido-suite: fresh
"""#6337 the bell's number is the same on every device (decision of 12.11.2026). Invented names only, addresses
@example.com. Two people without an organisation (freelancer-matrix: team) who share a project and a group.
 F1 a new direct message: /api/team carries dm_unread (the browser's bell follows the poll's "t" without a full state); the read
    routes (main conversation, thread, mute) answer dm_unread too -- red before: only unread came back, the bell stayed on 1
 F2 "All read" with max_id (the highest id the device showed): an item that arrived after it stays unread and is not in
    `marked`; a wrong max_id is refused; without max_id all items (older clients)
 F6 "seen for today" of a deadline line moves the News marker of /api/version (the other device reloads) and answers it; an
    item dismissed on one device moves it too -- red before: the marker counted only unread items
 F7 the summary push after the quiet hours never names more than still waits: everything read meanwhile = no summary, else
    at most the bell's number (badge_count)
usage: p6337_bell_devices_test.py <datadir>"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kt  # noqa: E402
from kt import B, CT, check, sess, today, until  # noqa: E402
from freelancer_fixture import FEATURES, freelancer  # noqa: E402

kt.fresh(prefix="P6337")
kt.docker_logs_on_first_fail()
assert sess().post(B + "/api/auth/setup", json={"username": "alice", "display_name": "Alice", "password": "password123"}).ok
A = sess("alice")
A.post(B + "/api/admin/setup", json={"lang": "en", "collab_all": True, "modules": ["comments", "collab"]})
A.patch(B + "/api/settings", json={"lang": "en", "features": FEATURES, "tour": "done"})
ALICE = kt.me_id(A)
FID, Fr = freelancer(B, A)
FIO, Fi = freelancer(B, A, "fiona")
kt.dbx("INSERT INTO groups(name,oidc_group,created_at,created_by) VALUES(?,?,?,?)", ("Freelance pool", "", "2026-11-20T08:00:00", ALICE))
GID = kt.dbx("SELECT id FROM groups WHERE name=?", ("Freelance pool",))[0][0]
for x in (FID, FIO):
    kt.dbx("INSERT INTO group_members(group_id,user_id,added_at) VALUES(?,?,?)", (GID, x, "2026-11-20T08:00:00"))
for s in (Fr, Fi):  # no quiet hours (their default 22:00-07:00 would hold the pushes of F7 at night)
    s.patch(B + "/api/settings", json={"quiet_from": "", "quiet_to": ""})
FL = Fr.post(B + "/api/lists", json={"name": "Own studio"}).json()["id"]
check(Fr.put(B + f"/api/lists/{FL}/members", json={"user_id": FIO, "role": "edit"}).ok, "setup: frida's project shared with fiona")


def in_app(code):
    """Lines of Python inside the container; prints the JSON of `out`."""
    head = "import json\nimport app\n"
    r = subprocess.run(["docker", "exec", "-w", "/app", "-e", "TASKS_WATCHDOG=0", CT, "python", "-c", head + code + "\nprint('OUT' + json.dumps(out))"],
                       capture_output=True, text=True, timeout=200)
    for line in r.stdout.splitlines():
        if line.startswith("OUT"):
            return json.loads(line[3:])
    raise AssertionError(r.stdout[-800:] + r.stderr[-1500:])


def news(s):
    r = s.get(B + "/api/news")
    check(r.ok, f"GET /api/news {r.status_code}")
    return r.json() if r.ok else {"items": [], "unread_me": 0, "unread": 0, "sig": ""}


def ver_n(s):
    return s.get(B + "/api/version").json().get("n")


def say(s, rid, text, **kw):
    r = s.post(B + f"/api/team/rooms/{rid}/messages", json={"body": text, **kw})
    check(r.status_code == 201, f"message in room {rid}: {r.status_code} {r.text[:160]}")
    return r.json().get("id") if r.ok else None


# ================================================================ F1 direct messages count live
r = Fr.post(B + "/api/team/dm", json={"user_id": FIO})
check(r.ok, "setup: frida's direct conversation with fiona " + r.text[:200])
DM = r.json().get("id")
t0 = Fi.get(B + "/api/team").json()
check(t0.get("dm_unread") == 0, f"F1: /api/team carries dm_unread (0 before) {t0.get('dm_unread')!r}")
M1 = say(Fr, DM, "Can you check the draft?")
j = Fi.get(B + "/api/team").json()
check(j.get("dm_unread") == 1 and j.get("unread") == 1, f"F1: a new direct message: /api/team says dm_unread 1 (the bell follows) {j.get('dm_unread')!r}")
check(j["dm_unread"] == Fi.get(B + "/api/state").json()["team"]["dm_unread"], "F1: the same number as the full state")
r = Fi.post(B + f"/api/team/rooms/{DM}/read", json={"last_id": M1})
check(r.ok and r.json().get("dm_unread") == 0 and r.json().get("unread") == 0, f"F1: read: the answer carries dm_unread 0 (was only unread) {r.text[:200]}")
say(Fr, DM, "And the invoice")
r = Fi.post(B + f"/api/team/rooms/{DM}/read", json={"muted": True})
check(r.ok and r.json().get("dm_unread") == 0, f"F1: muted: the direct message leaves the bell, the answer says so {r.text[:200]}")
r = Fi.post(B + f"/api/team/rooms/{DM}/read", json={"muted": False})
check(r.ok and r.json().get("dm_unread") == 1, f"F1: unmuted: it counts again {r.text[:200]}")
ans = say(Fi, DM, "Thread start")
Fi.post(B + f"/api/team/rooms/{DM}/read", json={})
say(Fr, DM, "an answer", thread_of=ans)
check(Fi.get(B + "/api/team").json().get("dm_unread") == 1, "F1: an answer in a thread of the direct conversation counts")
r = Fi.post(B + f"/api/team/rooms/{DM}/read", json={"thread": ans})
check(r.ok and r.json().get("dm_unread") == 0, f"F1: read in the thread: the answer carries dm_unread 0 {r.text[:200]}")

# ================================================================ F2 "All read" with an upper bound
T1 = Fr.post(B + "/api/tasks", json={"title": "Sketch the logo", "list_id": FL, "assignee_id": FIO}).json()["id"]
T2 = Fr.post(B + "/api/tasks", json={"title": "Pick the colours", "list_id": FL, "assignee_id": FIO}).json()["id"]
shown = until(lambda: (lambda j: j if sum(1 for x in j["items"] if not x["read"]) >= 2 else None)(news(Fi)), 10)
check(shown, "F2 setup: two assignments wait for fiona")
top = max(i for x in (shown or {"items": []})["items"] for i in x["ids"])
T3 = Fr.post(B + "/api/tasks", json={"title": "Print the flyer", "list_id": FL, "assignee_id": FIO}).json()["id"]
late = until(lambda: next((x for x in news(Fi)["items"] if x.get("task_id") == T3 and not x["read"]), None), 10)
check(late and min(late["ids"]) > top, "F2 setup: a third one arrives after the list was drawn")
check(Fi.post(B + "/api/news/read", json={"all": True, "max_id": "x"}).status_code == 400, "F2: a wrong max_id is refused")
check(Fi.post(B + "/api/news/read", json={"all": True, "max_id": True}).status_code == 400, "F2: max_id true is refused")
r = Fi.post(B + "/api/news/read", json={"all": True, "max_id": top})
j = r.json() if r.ok else {}
check(r.ok and late and not set(late["ids"]) & set(j.get("marked") or []), f"F2: the late item is not marked {j.get('marked')}")
items = news(Fi)["items"]
check(any(x.get("task_id") == T3 and not x["read"] for x in items), "F2: the item never shown stays unread (red before: all read)")
check(all(x["read"] for x in items if x.get("task_id") in (T1, T2)), "F2: the shown ones are read")
check(j.get("unread_me", 0) >= 1, f"F2: the bell keeps the late one {j.get('unread_me')}")
r = Fi.post(B + "/api/news/read", json={"all": True})
check(r.ok and not any(not x["read"] for x in news(Fi)["items"]), "F2: without max_id (older clients) all are read")

# ================================================================ F6 seen / dismissed moves the marker
check(Fr.post(B + "/api/tasks", json={"title": "Call the printer", "list_id": FL, "assignee_id": FIO, "due": today().isoformat()}).ok,
      "F6 setup: a task due today for fiona")
d = news(Fi).get("due") or {}
check(d.get("today", 0) >= 1 and d.get("n", 0) >= 1, f"F6 setup: the line 'due today' counts {d}")
n0 = ver_n(Fi)
r = Fi.post(B + "/api/news/due-seen", json={"line": "today"})
check(r.ok, "F6: seen for today")
n1 = ver_n(Fi)
check(n1 != n0, f"F6: 'seen for today' moves the News marker of /api/version (the other device follows) {n0} -> {n1}")
check(r.json().get("sig") == n1, "F6: the answer carries the new marker (this device does not reload)")
Fi.post(B + "/api/news/due-seen", json={"line": "today"})
check(ver_n(Fi) == n1, "F6: the same mark again moves nothing")
rid = next((x["ids"] for x in news(Fi)["items"] if x["read"]), None)
check(rid, "F6 setup: a read item")
n2 = ver_n(Fi)
check(Fi.post(B + "/api/news/dismiss", json={"ids": rid or []}).ok, "F6: a read item dismissed")
check(ver_n(Fi) != n2, "F6: a dismissed item moves the marker (the other device's open list drops it)")

# ================================================================ F7 the quiet hours' summary
SUM = f"""
import kalmido.notify.push as P
from kalmido.core.db import connect, local_now, usettings
from kalmido.core.pg import system_ctx
sent = []
P.notify = lambda uid, title, msg, *a, **k: sent.append(msg)
c = connect()
with system_ctx(c):
    c.execute("INSERT INTO quiet_push_held(user_id,n,first_at,last_at) VALUES(?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET n=excluded.n",
              ({FIO}, 3, '2026-11-20T01:00:00', '2026-11-20T01:00:00'))
    c.commit()
    P.quiet_held_tick(c, {{{FIO}}}, {{{FIO}: usettings(c, {FIO})}}, {{{FIO}: 'en'}}, local_now())
    c.commit()
out = [sent, P.badge_count({FIO})]
"""
Fi.post(B + "/api/news/read", json={"all": True})
Fi.post(B + "/api/news/due-seen", json={"line": "overdue"})
for x in Fi.get(B + "/api/team").json().get("rooms") or []:
    Fi.post(B + f"/api/team/rooms/{x['id']}/read", json={})
sent, badge = in_app(SUM)
check(badge == 0 and sent == [], f"F7: everything read elsewhere meanwhile: no summary (was '3 notifications') {sent} badge={badge}")
say(Fr, DM, "One more thing")
sent, badge = in_app(SUM)
check(badge == 1 and sent == ["1 notification during the quiet hours"], f"F7: the summary names at most what still waits {sent} badge={badge}")

sys.exit(kt.done("p6337_bell_devices"))
