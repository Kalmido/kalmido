#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1325.0 (#6502, decision of 16.11.2026): what a support session reads, how its changes stand in the history, the log of a
grant loses nothing silently, and the client / the organisation's admins hear of it. Own container (hosted, a server key).
Invented accounts only (example.com).
freelancer-matrix: own
tenant-matrix: support
 - (a) cara (member of the organisation Client Studio, no grant of its admins) opens support access to her account: the support
   session reads her private project, not the organisation's project and task; her own session reads both, before and after
   the support session in the same process (the account's cached context is never the narrowed one, nor the other way
   round); once an admin of Client Studio opens support access for it, the support session reads it, and no longer after
   the admin ended it
 - (b) a project setting changed in the support session stands in the project's history marked as support (not merged with
   her own change of a minute before); a task's title changed there carries via 'support' in its activity
 - (b) the log: 300 writes on a grant do not push a new write out (was: the oldest change went); readings beyond 300 go and
   are counted (dropped); an entry that meets a held lock goes to the background queue and lands once the lock is gone
 - (c) a support sign-in is no known device of cara (sec_devices unchanged); her own grant brings a security mail; the first
   use is in her bell (News "support", stage start); an organisation's grant is in the other admin's bell (stage grant), its
   first use in every admin's bell, an early end in the other admins' bell (stage end); switched off in the notification
   settings (row "support"), no News
usage: p6502_support_ctx_test.py <datadir>"""
import email
import email.policy
import json
import os
import shutil
import subprocess
import sys
import threading

import kt
from kt import B, check, sess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from freelancer_fixture import login, org_join  # noqa: E402

KEY = "AQIDBAUGBwgJCgsMDQ4PEBESExQVFhcYGRobHB0eHyA="  # a test server key (32 bytes, base64)
SMTP = {"KALMIDO_SMTP_HOST": "127.0.0.1", "KALMIDO_SMTP_PORT": "1025", "KALMIDO_SMTP_TLS": "none", "KALMIDO_MAIL_FROM": "kalmido@example.test"}
N = os.path.dirname(os.path.abspath(__file__))


def dbw(q, a=()):
    c = kt._dbx.connect(os.path.join(kt.DATA, "tasks.db"))
    try:
        c.execute(q, a)
        c.commit()
    finally:
        c.close()


def mails(addr, part):
    """The mails the SMTP sink (stub_mail.py, as in p2266_api_test.py) got for addr with part in the subject."""
    out = []
    try:
        for x in open(os.path.join(kt.DATA, "mail", "out.jsonl"), encoding="utf-8"):
            m = json.loads(x)
            msg = email.message_from_string(m["raw"], policy=email.policy.default)
            if addr in [t.lower() for t in m["to"]] and part in str(msg["subject"] or ""):
                out.append(msg)
    except OSError:
        pass
    return out


kt.fresh(env={"KALMIDO_SECRET_KEY": KEY, "KALMIDO_HOSTED": "1", **SMTP})
os.makedirs(os.path.join(kt.DATA, "mail"), exist_ok=True)
shutil.copy(os.path.join(N, "stub_mail.py"), kt.DATA)
subprocess.run(["docker", "exec", "-d", kt.CT, "python", "/data/stub_mail.py"], check=True)
assert kt.until(lambda: subprocess.run(["docker", "exec", kt.CT, "python", "-c", "import socket; socket.create_connection(('127.0.0.1', 1025), 1)"],
                                       capture_output=True).returncode == 0, 15), "the SMTP sink listens"
assert kt.sess(None).post(B + "/api/auth/setup", json={"username": "alice", "display_name": "Alice", "password": "password123"}).ok
A = sess("alice")
A.post(B + "/api/admin/setup", json={"org_name": "Alpha", "lang": "en", "collab_all": True, "modules": ["comments"]})
A = sess("alice")
ALPHA = A.get(B + "/api/orgs").json()["orgs"][0]["id"]
IDS = {}
for name, orgs in (("carl", None), ("dave", None), ("cara", [{"id": ALPHA, "role": "member"}])):
    r = A.post(B + "/api/users", json={"username": name, "display_name": name.title(), "password": "password123",
                                       "email": f"{name}@example.com", **({"orgs": orgs} if orgs else {})})
    assert r.ok, r.text
    IDS[name] = r.json()["id"]
CARL, DAVE, CARA = IDS["carl"], IDS["dave"], IDS["cara"]
Ca, Dv, Cc = login(B, "carl"), login(B, "dave"), login(B, "cara")
for s in (Ca, Dv, Cc):
    assert s.patch(B + "/api/settings", json={"lang": "en", "tour": "done", "features": "comments,collab"}).ok
r = Ca.post(B + "/api/orgs", json={"name": "Client Studio"})
assert r.status_code == 201, r.text
CO = r.json()["id"]
for x in (CARA, DAVE):
    kt.dbx("INSERT INTO conn_links(a_id, b_id, created_at) VALUES(?, ?, '2026-01-01T00:00:00Z')", tuple(sorted((CARL, x))))
kt.proved()
for name in ("cara", "dave"):
    assert Ca.put(B + f"/api/orgs/{CO}/members", json={"email": f"{name}@example.com"}).ok
    assert org_join(B, name, CO)
dbw("UPDATE org_members SET role='admin' WHERE org_id=? AND user_id=?", (CO, DAVE))  # a second admin of the organisation
r = Cc.post(B + "/api/lists", json={"name": "Studio project", "org_id": CO})
assert r.status_code in (200, 201), r.text
OL = r.json()["id"]
r = Cc.post(B + "/api/tasks", json={"title": "Studio task", "list_id": OL})
assert r.status_code in (200, 201), r.text
OT = r.json()["id"]
r = Cc.post(B + "/api/lists", json={"name": "Cara private"})
PL = r.json()["id"]
r = Cc.post(B + "/api/tasks", json={"title": "Private task", "list_id": PL})
PT = r.json()["id"]


def lists_of(s):
    r = s.get(B + "/api/state")
    assert r.ok, r.text[:200]
    return {x["id"] for x in r.json().get("lists", [])}


def reads_org(s):
    """(the organisation's project in the state, its task readable)"""
    return OL in lists_of(s), s.get(B + f"/api/tasks/{OT}").ok


def news(s, stage=None):
    return [x for x in s.get(B + "/api/news").json()["items"] if x["kind"] == "support" and (stage is None or (x.get("data") or {}).get("stage") == stage)]


def devices():
    r = kt.dbx("SELECT value FROM user_settings WHERE user_id=? AND key='sec_devices'", (CARA,))
    return r[0][0] if r else None


# ---------------------------------------------------------------- (a) the narrowed reading context
check(reads_org(Cc) == (True, True), "cara's own session reads the organisation's project and task (fills the account's cached context)")
DEV0 = devices()
r = Cc.post(B + "/api/support-access", json={"hours": 1})
check(r.ok, "cara opens support access to her account " + r.text[:120])
G1 = r.json()["grant"]["id"]
m = kt.until(lambda: mails("cara@example.com", "Support access opened"), 15)
check(len(m) == 1 and "Settings > Account" in m[0].get_body(("plain",)).get_content(), "(c) her grant brings her a security mail (how to end it)")
r = A.post(B + f"/api/users/{CARA}/signin-link")
assert r.ok, r.text
Y = kt.sess(None)
r = Y.post(B + "/api/auth/link", json={"token": r.json()["link"].split("#signin/")[1]}, headers={"User-Agent": "OperatorBrowser/1.0 (X11; Linux)"})
check(r.ok, "the operator signs in with the support link " + r.text[:120])
check(devices() == DEV0, f"(c) the support sign-in is no known device of cara ({DEV0!r} -> {devices()!r})")
check(reads_org(Y) == (False, False), "support session: neither the organisation's project nor its task (no grant of its admins)")
check(PL in lists_of(Y) and Y.get(B + f"/api/tasks/{PT}").ok, "support session: her private project and task stay readable")
check(reads_org(Cc) == (True, True), "cara's own session right after: still the organisation's project and task (not the narrowed context)")
check(reads_org(Y) == (False, False), "support session again after her own request: still narrowed (not the account's cached context)")
st = [x for x in news(Cc, "start") if (x.get("data") or {}).get("grant_id") == G1]
check(len(st) == 1, f"(c) the first use is in cara's bell: support started in her account {news(Cc)}")
r = Ca.post(B + "/api/support-access", json={"hours": 1, "org_id": CO})
check(r.ok, "carl opens support access for Client Studio " + r.text[:120])
G2 = r.json()["grant"]["id"]
check(reads_org(Y) == (True, True), "with the organisation's own grant: the support session reads its project and task")
check(any((x.get("data") or {}).get("grant_id") == G2 for x in news(Dv, "grant")) and not news(Ca, "grant"),
      "(c) the other admin (dave) hears of carl's grant, carl himself not")
check(kt.until(lambda: kt.dbx("SELECT uses FROM support_grants WHERE id=?", (G2,))[0][0] not in (None, "", "[]"), 10),
      "the organisation's grant has its first entry")
check(all(any((x.get("data") or {}).get("grant_id") == G2 for x in news(s, "start")) for s in (Ca, Dv)),
      "(c) its first use is in the bell of every admin of the organisation")
check(Dv.delete(B + f"/api/support-access/{G2}").ok, "dave ends the organisation's grant early")
check(reads_org(Y) == (False, False), "after the end: the support session no longer reads the organisation")
check(any((x.get("data") or {}).get("grant_id") == G2 for x in news(Ca, "end")) and not news(Dv, "end"),
      "(c) carl hears that dave ended it, dave himself not")
check(reads_org(Cc) == (True, True), "cara's own session still reads everything")

# ---------------------------------------------------------------- (b) the history marks the support session's changes
check(Cc.patch(B + f"/api/lists/{PL}", json={"columns": ["due"]}).ok, "cara changes her project's columns")
check(Y.patch(B + f"/api/lists/{PL}", json={"columns": ["due", "prio"]}).ok, "the support session changes them a minute later")
h = Cc.get(B + f"/api/lists/{PL}/history").json()["history"]
check(len(h) == 2 and h[0]["support"] is True and h[0]["name"] == "Cara (support access)" and h[1]["support"] is False and h[1]["name"] == "Cara",
      f"two entries (not merged): the newer one marked as support access {[(e['name'], e['support']) for e in h]}")
check(kt.dbx("SELECT via FROM obj_history WHERE kind='list' AND ref_id=? ORDER BY id", (PL,)) == [(None,), ("support",)], "obj_history.via")
check(Y.patch(B + f"/api/tasks/{PT}", json={"title": "Private task, fixed"}).ok, "the support session renames her task")
acts = [json.loads(d) if isinstance(d, str) else d for (d,) in kt.dbx("SELECT data FROM activity WHERE task_id=? AND kind='title'", (PT,))]
check(acts and acts[-1].get("via") == "support", f"the task's activity carries via 'support' {acts}")

# ---------------------------------------------------------------- (b) the log keeps every change and drops nothing silently
OLD = "2026-01-01T00:00:00.000Z"
dbw("UPDATE support_grants SET uses=?, uses_dropped=0 WHERE id=?",
    (json.dumps([{"at": OLD, "by": CARA, "m": "PATCH", "r": f"/api/x/{i}", "s": 200, "sup": 1} for i in range(300)]), G1))
check(Y.patch(B + f"/api/tasks/{PT}", json={"title": "Private task, fixed 2"}).ok, "one more change in the support session")


def uses():
    return json.loads(kt.dbx("SELECT uses FROM support_grants WHERE id=?", (G1,))[0][0])


u = uses()
check(len(u) == 301 and u[0]["r"] == "/api/x/0" and u[-1]["m"] == "PATCH",
      f"300 changes on the log: the new one is added, the oldest change stays ({len(u)} entries, first {u[0]['r']})")
dbw("UPDATE support_grants SET uses=?, uses_dropped=0 WHERE id=?",
    (json.dumps([{"at": OLD, "by": CARA, "m": "GET", "r": f"/api/y/{i}", "s": 200, "sup": 1} for i in range(300)]), G1))
check(Y.get(B + f"/api/tasks/{PT}").ok, "one more reading in the support session")
u = uses()
check(len(u) == 300 and u[0]["r"] == "/api/y/1" and kt.dbx("SELECT uses_dropped FROM support_grants WHERE id=?", (G1,)) == [(1,)],
      "300 readings: the oldest reading goes and is counted (uses_dropped 1)")
g = Cc.get(B + "/api/support-access").json()["account"]
check(g and g["id"] == G1 and g["dropped"] == 1, f"the client sees the number of entries no longer listed {g and g.get('dropped')}")

# a held lock: the entry is not lost, it goes to the background queue and lands once the lock is gone
dbc, dbn = kt._dbx._target(kt.DATA)
holder = threading.Thread(target=lambda: kt._dbx._psql(dbc, dbn, f"BEGIN; SELECT id FROM support_grants WHERE id={int(G1)} FOR UPDATE; "
                                                                  "SELECT pg_sleep(8); COMMIT;", timeout=60))
holder.start()
check(kt.until(lambda: kt.dbx("SELECT COUNT(*) FROM pg_stat_activity WHERE query LIKE '%pg_sleep(8)%' AND state='active' AND pid<>pg_backend_pid()")[0][0] > 0, 10),
      "a database session holds the grant's row")
check(Y.patch(B + f"/api/tasks/{PT}", json={"title": "Fixed while the log was locked"}).ok, "a change while the log's row is held")
check(kt.until(lambda: kt.dbx("SELECT COUNT(*) FROM bg_jobs WHERE kind='sga:log'")[0][0] > 0, 15), "the entry went to the background queue")
holder.join()
n = len(uses())
check(kt.until(lambda: any(x.get("m") == "PATCH" and x.get("at", "") > OLD for x in uses()), 30),
      f"once the lock is gone the background run writes it on the log (was dropped silently; {n} entries before)")

# ---------------------------------------------------------------- (c) switched off: no News
assert Ca.patch(B + "/api/settings", json={"notify": json.dumps({"support": {"news": False, "push": False}})}).ok
n0 = len(news(Ca))
r = Dv.post(B + "/api/support-access", json={"hours": 1, "org_id": CO})
check(r.ok and len(news(Ca)) == n0, f"carl switched the row 'support' off: dave's grant brings him no News ({len(news(Ca))} vs {n0})")
check(Dv.delete(B + f"/api/support-access/{r.json()['grant']['id']}").ok and Cc.delete(B + f"/api/support-access/{G1}").ok, "the grants end")
check(Y.get(B + "/api/state").status_code == 401, "the support session ends with cara's grant")
sys.exit(kt.done("p6502_support_ctx"))
