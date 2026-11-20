#!/usr/bin/env python3
# kalmido-suite: fresh
"""(#6626): the status link of a customer report /p/<token> ends. Own container with the e-mail stub (stub_mail.py), organisations
(mode workspaces) and a fast watchdog. Invented names and example.com addresses only.
freelancer-matrix: portal
 - a live ticket: the page works, the timeline's ticket says link live (no end while the task is open), its url
 - done: the link stays valid, the ticket names its end (done + 90 days); done more than 90 days ago: the page is the one 404
   (like an unknown token), the ticket says expired without url, a new link = 409, no answer mail with the dead link;
   reopened: the same link works again
 - "End the status link" (PATCH {link: end}): the page is the 404 at once, the ticket says ended; undo ({link: on}) = the same
   link works again
 - "Send a new status link" ({link: new}): the old link is the 404 at once, the new one works and goes by mail to the stored
   address (mailed true); without an address: mailed false, the url to copy
 - a viewer may not end or renew the link (403); a bad value = 400
 - /portal (the reporter signed in by mail): an ended report is listed without a link, a live one with its link
 - the same for a person without an organisation (her own private project)
usage: p6626_portal_link_test.py <datadir>"""
import email
import json
import os
import re
import subprocess
import sys
import time

import requests

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
import dbx  # noqa: E402
from freelancer_fixture import freelancer  # noqa: E402

from kt import FAILS, OKS, check, sess, until, B, DATA  # noqa: E402
CT = os.environ.get("KALMIDO_TEST_CONTAINER", "kalmido-test")

MAILENV = ["-e", "KALMIDO_SMTP_HOST=127.0.0.1", "-e", "KALMIDO_SMTP_PORT=1025", "-e", "KALMIDO_SMTP_TLS=none",
           "-e", "KALMIDO_MAIL_FROM=kalmido@example.test", "-e", "KALMIDO_INSTANCE_MODE=workspaces", "-e", "TASKS_WATCHDOG_INTERVAL=2"]
subprocess.run(["docker", "rm", "-f", CT], capture_output=True)
subprocess.run(["rm", "-rf", DATA])
os.makedirs(os.path.join(DATA, "mail", "in"), exist_ok=True)
subprocess.run(["cp", os.path.join(N, "stub_mail.py"), DATA])
r = subprocess.run(["bash", os.path.join(N, "start.sh"), DATA], env=dict(os.environ, KEEP="1", EXTRA=os.environ.get("EXTRA", "") + " " + " ".join(MAILENV)),
                   capture_output=True, text=True)
assert r.returncode == 0, r.stdout + r.stderr
subprocess.run(["docker", "exec", "-d", CT, "python", "/data/stub_mail.py"])
time.sleep(0.8)
OUT = os.path.join(DATA, "mail", "out.jsonl")


def dbq(q, a=()):
    c = dbx.connect(os.path.join(DATA, "tasks.db"))
    try:
        return c.execute(q, a).fetchall()
    finally:
        c.close()


def mails(to):
    """The mails the stub got for address to: [(subject, plain text)]."""
    out = []
    try:
        lines = open(OUT, encoding="utf-8").read().splitlines()
    except FileNotFoundError:
        return out
    for ln in lines:
        j = json.loads(ln)
        m = email.message_from_string(j["raw"])
        txt = "".join(p.get_payload(decode=True).decode("utf-8", "replace") for p in m.walk() if p.get_content_type() == "text/plain")
        if any(to in x for x in j["to"]):
            out.append((str(email.header.make_header(email.header.decode_header(m["Subject"] or ""))), txt))
    return out


def ticket(task_id, list_id, name, mail):
    """A ticket as the form creates it (team/portal.py pt_create in the container) -> the status-link token."""
    code = ("import sys, app\nfrom kalmido.core.pg import system_ctx\nfrom kalmido.team.portal import pt_create\nc = app.connect()\n"
            "with system_ctx(c):\n    l = c.execute('SELECT id, org_id, owner_id FROM lists WHERE id=?', (int(sys.argv[2]),)).fetchone()\n"
            "    t = pt_create(c, int(sys.argv[1]), l, None, sys.argv[3], sys.argv[4])\nc.commit()\nprint(t[1])")
    out = subprocess.run(["docker", "exec", CT, "python", "-c", code, str(task_id), str(list_id), name, mail], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr[-600:]
    return out.stdout.strip().splitlines()[-1]


P = requests.Session()  # the reporter: no account


def page(tok):
    return P.get(B + f"/p/{tok}").status_code


def tk(s, tid):
    return s.get(B + f"/api/tasks/{tid}/timeline").json().get("ticket") or {}


def link(s, tid, v):
    return s.patch(B + f"/api/tasks/{tid}/ticket", json={"link": v})


def flow(s, who, lid, addr):
    def ok(cond, what):
        return check(cond, f"{who}: {what}")

    T = s.post(B + "/api/tasks", json={"list_id": lid, "title": f"{who}: export breaks", "content": "It breaks."}).json()["id"]
    TOK = ticket(T, lid, "Jane Example", addr)
    ok(page(TOK) == 200, "a live ticket: the page works")
    k = tk(s, T)
    ok(k.get("link") == "live" and not k.get("link_until") and TOK in (k.get("url") or "") and k.get("link_days") == 90,
       f"the ticket: link live, no end while open, its url {k}")
    # done: valid until done + 90 days; done long ago: expired
    ok(s.post(B + f"/api/tasks/{T}/complete", json={}).ok, "the task is done")
    k = tk(s, T)
    ok(page(TOK) == 200 and k.get("link") == "live" and (k.get("link_until") or "")[:4].isdigit(), f"done: still valid, with its end {k.get('link_until')}")
    dbq("UPDATE tasks SET completed_at=CURRENT_TIMESTAMP - INTERVAL '91 days' WHERE id=?", (T,))
    ok(page(TOK) == 404 and page("x" * 32) == 404, "done 91 days ago: the page is the one 404 (like an unknown token)")
    k = tk(s, T)
    ok(k.get("link") == "expired" and "url" not in k, f"the ticket: expired, no url {k}")
    r = link(s, T, "new")
    ok(r.status_code == 409, f"a new link of an expired one: 409 (reopen first) {r.status_code}")
    n = len(mails(addr))
    s.post(B + f"/api/tasks/{T}/comments", json={"body": "A late public answer.", "portal": True})
    dbq("UPDATE portal_tickets SET last_mail_at='2020-01-01T00:00:00+00:00' WHERE task_id=?", (T,))
    time.sleep(6)
    ok(len(mails(addr)) == n, "no answer mail with a dead link")
    ok(s.post(B + f"/api/tasks/{T}/reopen", json={}).ok, "reopened")
    ok(page(TOK) == 200 and tk(s, T).get("link") == "live", "reopened: the same link works again")
    # end + undo
    r = link(s, T, "end")
    ok(r.ok and r.json().get("link") == "ended" and "url" not in r.json(), f"end the link {r.status_code} {r.text[:160]}")
    ok(page(TOK) == 404, "ended: the page is the 404 at once")
    r = link(s, T, "on")
    ok(r.ok and r.json().get("link") == "live" and page(TOK) == 200, "undo: the same link works again")
    # new link: mailed to the address, the old one dead
    n = len(mails(addr))
    r = link(s, T, "new")
    j = r.json() if r.ok else {}
    new = (j.get("url") or "").rsplit("/", 1)[-1]
    ok(r.ok and j.get("mailed") is True and new and new != TOK, f"a new link, mailed {r.status_code} {j.get('mailed')}")
    ok(page(TOK) == 404 and page(new) == 200, "the old link is the 404 at once, the new one works")
    m = until(lambda: mails(addr)[n:], 25) or []
    ok(m and m[-1][0].startswith("New link to your report") and f"/p/{new}" in m[-1][1] and TOK not in m[-1][1],
       f"the mail with the new link to {addr} {[x[0] for x in m]}")
    # without an address
    T2 = s.post(B + "/api/tasks", json={"list_id": lid, "title": f"{who}: no address", "content": "x"}).json()["id"]
    TOK2 = ticket(T2, lid, "Anonymous", "")
    r = link(s, T2, "new")
    j = r.json() if r.ok else {}
    ok(r.ok and j.get("mailed") is False and j.get("url") and TOK2 not in j["url"] and page(TOK2) == 404, f"no address: a new link to copy {j}")
    ok(link(s, T2, "wipe").status_code == 400, "a bad value: 400")
    return T, new


# ---------------------------------------------------------------- organisation Alpha (alice admin, eve views)
assert sess().post(B + "/api/auth/setup", json={"username": "alice", "display_name": "Alice Admin", "password": "password123"}).ok
A = sess("alice")
A.post(B + "/api/admin/setup", json={"lang": "en", "collab_all": True, "modules": ["comments", "clients"]})
assert A.post(B + "/api/users", json={"username": "eve", "display_name": "Eve Viewer", "password": "password123", "email": "eve@example.com"}).ok
Ev = sess("eve")
for s in (A, Ev):
    s.patch(B + "/api/settings", json={"lang": "en", "features": "comments,collab,clients", "tour": "done"})
ALICE = A.get(B + "/api/state").json()["me"]["id"]
EVE = Ev.get(B + "/api/state").json()["me"]["id"]
ORG = A.post(B + "/api/admin/orgs", json={"name": "Alpha", "admin_id": ALICE}).json()["id"]
assert A.put(B + f"/api/orgs/{ORG}/members", json={"email": "eve@example.com", "role": "member"}).ok
for s in (A, Ev):
    s.patch(B + "/api/settings", json={"workspace": f"org:{ORG}"})
L = A.post(B + "/api/lists", json={"name": "Support", "org_id": ORG}).json()["id"]
assert A.put(B + f"/api/lists/{L}/members", json={"user_id": EVE, "role": "view"}).ok
TA, NEWA = flow(A, "Alpha", L, "jane@example.com")
check(link(Ev, TA, "end").status_code == 403 and page(NEWA) == 200, "Alpha: a viewer may not end the link (403)")

# ---------------------------------------------------------------- /portal: an ended report without a link
TB = A.post(B + "/api/tasks", json={"list_id": L, "title": "Second report of Jane", "content": "x"}).json()["id"]
TOKB = ticket(TB, L, "Jane Example", "jane@example.com")
dbq("UPDATE portal_tickets SET claimed=1 WHERE task_id IN (?, ?)", (TA, TB))
pg = P.get(B + f"/p/{NEWA}").text
m = re.search(r'action="' + re.escape(f"/p/{NEWA}/login") + r'"[^>]*>\s*<input type="hidden" name="f" value="([0-9a-f]{64})"', pg)
n = len(mails("jane@example.com"))
P.post(B + f"/p/{NEWA}/login", data={"email": "jane@example.com", "f": m.group(1) if m else ""})
sm = until(lambda: [x for x in mails("jane@example.com")[n:] if "sign-in link" in x[0]], 25) or []
lk = re.search(r"/portal/login/([A-Za-z0-9_-]+)", sm[-1][1]) if sm else None
check(bool(lk), "setup: the sign-in link by mail")
if lk:
    P.post(B + f"/portal/login/{lk.group(1)}")
    check(link(A, TB, "end").ok, "Alpha: the second report's link ended")
    pt = P.get(B + "/portal").text
    check(f'href="/p/{NEWA}"' in pt and f"/p/{TOKB}" not in pt and "Second report of Jane" in pt,
          "/portal: the ended report is listed without a link, the live one with its link")

# ---------------------------------------------------------------- a person without an organisation
FID, Fr = freelancer(B, A)
LF = Fr.post(B + "/api/lists", json={"name": "Frida support"}).json()["id"]
flow(Fr, "Frida", LF, "kim@example.com")

print(f"p6626_portal_link: {OKS[0]} ok, {len(FAILS)} failed", flush=True)
subprocess.run(["docker", "rm", "-f", CT], capture_output=True)
sys.exit(1 if FAILS else 0)
