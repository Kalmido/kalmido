#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1302.0 (#6545): fetching a workspace mailbox that fails. Own container (start.sh) with the stub mail server inside
(stub_mail.py: IMAP 127.0.0.1:1143, login kalmido / secret; SMTP sink 127.0.0.1:1025 = the server's outgoing mail).
The clock is set through the rows (polled_at, told_at), never by waiting; "a round went by" = the freelancer's healthy
mailbox was fetched twice more.
 - a mail over KALMIDO_MAILBOX_MAIL_MAX stays in the mailbox and is counted there (skipped), the small one is filed;
   ok_at = the last success
 - the same mailbox in a second workspace: both see the warning (never which workspace), another folder ends it
 - after failures the mailbox waits longer each time (no login while it waits), and is fetched once the wait is over
 - 5 refused logins in a row: fetching stops (no more logins, "Fetch now" 409), its admins hear it by News AND mail (a member
   does not), again after 3 days, not before; the event "Integrations" switched off stops the mail; a changed sender name
   does not end the stop, the access data saved again does
 - review F1: the mail only to a proved address (an admin with an unproved one gets the News only); saving again + 5 failures
   within 3 days: News again, no second mail (mailed_at); "Fetch now" is limited (429)
 - review F2: the warning "fetched twice" only among the workspaces the person manages (their private one + the
   organisations they are admin of), never about another customer's mailbox; ok_at goes with a changed server
 - an organisation mailbox nobody can receive for (no admin) is not fetched: error norecipient, its mail stays unseen
usage: p6545_mailbox_test.py <datadir>      (P6545_NOSTART=1: the container runs already, only the stub is started)"""
import email
import email.message
import email.policy
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

import requests

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
import dbx as dbxm  # noqa: E402
from freelancer_fixture import freelancer  # noqa: E402
from kt import FAILS, OKS, check, sess, until  # noqa: E402

DATA = sys.argv[1] if len(sys.argv) > 1 else os.path.join(N, ".data")
B = "http://127.0.0.1:" + os.environ.get("KALMIDO_TEST_PORT", "3048")
CT = os.environ.get("KALMIDO_TEST_CONTAINER", "kalmido-test")
H = {"X-Requested-With": "kalmido"}
BIG = 4000  # KALMIDO_MAILBOX_MAIL_MAX below
ENV = ["-e", "KALMIDO_SMTP_HOST=127.0.0.1", "-e", "KALMIDO_SMTP_PORT=1025", "-e", "KALMIDO_SMTP_TLS=none",
       "-e", "KALMIDO_MAIL_FROM=kalmido@example.test", "-e", "KALMIDO_IMAP_INTERVAL=10", "-e", f"KALMIDO_MAILBOX_MAIL_MAX={BIG}",
       "-e", "KALMIDO_CALENDAR_ALLOW_HOSTS=127.0.0.1:1143,127.0.0.1:1025", "-e", "TASKS_WATCHDOG_INTERVAL=1",
       "-e", "KALMIDO_SECRET_KEY=AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="]


def dbx(sql, args=()):
    c = dbxm.connect(os.path.join(DATA, "tasks.db"), timeout=10)
    try:
        r = c.execute(sql, args).fetchall()
        c.commit()
        return r
    finally:
        c.close()


def ago(**kw):
    return (datetime.now(timezone.utc) - timedelta(**kw)).isoformat()


NEXT = [0]


def drop(subject, size=0):
    """One mail into the stub's INBOX; size = pad its text to about that many bytes. Returns its UID."""
    NEXT[0] += 1
    m = email.message.EmailMessage()
    m["From"], m["To"], m["Subject"] = "lisa@example.com", "office@example.test", subject
    m["Message-ID"] = f"<p6545-{NEXT[0]}@example.org>"
    m["Date"] = "Mon, 16 Nov 2026 10:00:00 +0100"
    m.set_content("Hello\n" + "x" * size)
    open(os.path.join(DATA, "mail", "in", f"{NEXT[0]}.eml"), "wb").write(bytes(m))
    return NEXT[0]


def seen_uids():
    try:
        return {int(x) for x in open(os.path.join(DATA, "mail", "seen")).read().split()}
    except FileNotFoundError:
        return set()


def logins(pw):
    try:
        return sum(1 for x in open(os.path.join(DATA, "mail", "imap.log")) if x.split() == ["LOGIN", "kalmido", pw])
    except FileNotFoundError:
        return 0


def mails(to):
    try:
        return [json.loads(x) for x in open(os.path.join(DATA, "mail", "out.jsonl"), encoding="utf-8") if x.strip() and to in json.loads(x)["to"]]
    except FileNotFoundError:
        return []


def queued(uid):
    """review F1: the integration mails queued for uid (bg_jobs, added in the same step as the News item: no waiting)."""
    return dbx("SELECT count(*) FROM bg_jobs WHERE kind='mail:security' AND user_id=?", (uid,))[0][0]


def news(s, what):
    return [x for x in s.get(B + "/api/news").json()["items"] if x["kind"] == "integfail" and x["data"].get("what") == what]


def box(ws):
    r = dbx("SELECT fails, error, polled_at, told_at, ok_at, skipped FROM hub_mailboxes WHERE ws=?", (ws,))
    return dict(zip(("fails", "error", "polled_at", "told_at", "ok_at", "skipped"), r[0])) if r else {}


def rounds(k=2):
    """k more rounds of the mailbox loop went by: the freelancer's healthy mailbox (fetched every round) was fetched k times."""
    for _ in range(k):
        dbx("UPDATE hub_mailboxes SET polled_at=NULL WHERE ws=?", (EWS,))
        check(until(lambda: box(EWS)["polled_at"], 40), "setup: a round of the mailbox loop went by")


if not os.environ.get("P6545_NOSTART"):
    subprocess.run(["docker", "rm", "-f", CT], capture_output=True)
    subprocess.run(["rm", "-rf", DATA])
os.makedirs(os.path.join(DATA, "mail", "in"), exist_ok=True)
subprocess.run(["cp", os.path.join(N, "stub_mail.py"), DATA])
if not os.environ.get("P6545_NOSTART"):
    r = subprocess.run(["bash", os.path.join(N, "start.sh"), DATA], env=dict(os.environ, KEEP="1", EXTRA=os.environ.get("EXTRA", "") + " " + " ".join(ENV)),
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
subprocess.run(["docker", "exec", "-d", CT, "python", "/data/stub_mail.py"])
time.sleep(1.0)
s0 = requests.Session()
s0.headers.update(H)
assert s0.post(B + "/api/auth/setup", json={"username": "alice", "display_name": "Alice", "password": "password123"}).ok
A = sess("alice")
A.post(B + "/api/admin/setup", json={"lang": "en", "collab_all": True})
U = {}
for u in ("bob", "carol", "dave"):
    r = A.post(B + "/api/users", json={"username": u, "display_name": u.title(), "password": "password123", "email": f"{u}@example.test"})
    assert r.ok, r.text
    U[u] = r.json()["id"]
r = A.post(B + "/api/admin/orgs", json={"name": "Alpha", "admin_id": U["bob"]})
assert r.status_code == 201, r.text
ORG = r.json()["id"]
# 2.1302.0 (#6545 review F1): dave is a second admin whose address is not proved; bob's is
A.patch(B + f"/api/admin/orgs/{ORG}", json={"members": [U["bob"], U["carol"], U["dave"]], "admins": [U["bob"], U["dave"]]})
dbx("UPDATE users SET email_proved=lower(email) WHERE id=?", (U["bob"],))
ERIN, Er = freelancer(B, A, "erin")
Bo, Ca, Da = sess("bob"), sess("carol"), sess("dave")
for s in (Bo, Ca, Da, Er):
    s.patch(B + "/api/settings", json={"lang": "en", "tour": "done", "features": "cal,collab,comments,events,contacts,clients", "workspace": "all"})
WS, EWS = f"o{ORG}", f"u{ERIN}"
BOX = {"ws": f"org:{ORG}", "imap_host": "127.0.0.1", "imap_port": 1143, "imap_ssl": False, "imap_user": "kalmido", "imap_password": "secret"}

cols = {x[0] for x in dbx("SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='hub_mailboxes'")}
check({"ok_at", "told_at", "mailed_at", "skipped", "skipped_at"} <= cols, f"migration 6545: the new columns ({sorted(cols)})")

# ---- a mail too large: counted at the mailbox, the small one filed, ok_at = the last success
small, big = drop("Small one"), drop("Big one", BIG + 500)
r = Bo.put(B + "/api/hubmail/mailbox", json=BOX)
check(r.ok, f"setup: Alpha's mailbox {r.text[:200]}")
WS = dbx("SELECT ws FROM hub_mailboxes WHERE org_id=?", (ORG,))[0][0]
check(until(lambda: box(WS)["skipped"] == 1 and box(WS)["ok_at"], 40), f"#6545: the mail over the limit is counted at the mailbox ({box(WS)})")
filed = {x[0] for x in dbx("SELECT message_id FROM hub_mails WHERE ws=?", (WS,))}  # (the subject is sealed in the row)
check(filed == {f"<p6545-{small}@example.org>"}, f"#6545: the small mail is filed, the big one is not ({filed}, big {big})")
b = Bo.get(B + f"/api/hubmail/mailbox?ws=org:{ORG}").json()["box"]
check(b["skipped"] == 1 and b["skipped_at"] and b["ok_at"] and not b["halted"] and not b["twice"], f"#6545: the settings show the count and the last success ({b})")
sp = {x["ws"]: x for x in Bo.get(B + "/api/hubmail/mailboxes").json()["spaces"]}
check(sp[f"org:{ORG}"].get("skipped") == 1 and sp[f"org:{ORG}"].get("ok_at"), f"#6545: the list of workspaces too ({sp})")
check(not [x for x in Ca.get(B + "/api/hubmail/mailboxes").json()["spaces"] if "skipped" in x], "a member who does not manage it sees no details")

# ---- the same mailbox in a second workspace of the same person: both are warned
# 2.1302.0 (#6545 review F2): was erin's private space (another customer) -- the warning must not tell about other customers
r = Bo.put(B + "/api/hubmail/mailbox", json={**BOX, "ws": "private"})
check(r.ok and "another workspace" in (r.json()["box"].get("twice") or ""), f"#6545: saving the same mailbox in bob's private space warns ({r.text[:300]})")
tw = Bo.get(B + f"/api/hubmail/mailbox?ws=org:{ORG}").json()["box"]["twice"]
check("another workspace" in tw, f"#6545: the organisation's mailbox is warned too ({tw})")
r = Bo.put(B + "/api/hubmail/mailbox", json={"ws": "private", "imap_folder": "Archive"})
check(r.ok and not r.json()["box"]["twice"], f"#6545: another folder is another mailbox ({r.text[:300]})")
check(not Bo.get(B + f"/api/hubmail/mailbox?ws=org:{ORG}").json()["box"]["twice"], "#6545: and the warning is gone for Alpha")
check(Bo.delete(B + "/api/hubmail/mailbox?ws=private").ok, "setup: bob's private mailbox goes again")
# review F2: another customer (erin, not in Alpha) saves the same mailbox: neither side learns of the other
r = Er.put(B + "/api/hubmail/mailbox", json={**BOX, "ws": "private"})
check(r.ok and not r.json()["box"]["twice"], f"#6545 F2: the same mailbox of another organisation is not told ({r.text[:300]})")
check(not Bo.get(B + f"/api/hubmail/mailbox?ws=org:{ORG}").json()["box"]["twice"], "#6545 F2: nor to Alpha about erin's")
r = Er.put(B + "/api/hubmail/mailbox", json={"ws": "private", "imap_folder": "Archive"})
check(r.ok, f"setup: erin's mailbox on another folder ({r.text[:300]})")
check(until(lambda: box(EWS).get("ok_at"), 40), "setup: erin's mailbox (the round marker) works")

# ---- failures: a longer wait each time
r = Bo.put(B + "/api/hubmail/mailbox", json={"ws": f"org:{ORG}", "imap_password": "wrong"})
check(r.ok, f"setup: a wrong password {r.text[:200]}")
check(until(lambda: box(WS)["fails"] >= 1 and box(WS)["error"] == "auth", 40), f"setup: the login is refused ({box(WS)})")
dbx("UPDATE hub_mailboxes SET fails=3, polled_at=? WHERE ws=?", (ago(seconds=5), WS))  # 3 in a row: 10 s x 8 = 80 s of waiting
n0 = logins("wrong")
rounds()
check(logins("wrong") == n0 and box(WS)["fails"] == 3, f"#6545: while it waits, no login is tried ({logins('wrong')} vs {n0}, {box(WS)})")
dbx("UPDATE hub_mailboxes SET polled_at=? WHERE ws=?", (ago(seconds=90), WS))
check(until(lambda: box(WS)["fails"] == 4, 40), f"#6545: once the wait is over it is fetched again ({box(WS)})")
check(not news(Bo, "mailbox_auth") and not news(Bo, "mailbox"), "#6545: 4 failures tell nobody yet")

# ---- the 5th refused login: fetching stops, News AND mail to the admins
dbx("UPDATE hub_mailboxes SET polled_at=? WHERE ws=?", (ago(hours=1), WS))
check(until(lambda: news(Bo, "mailbox_auth"), 40), f"#6545: the 5th refused login: the admin hears it ({box(WS)})")
it = news(Bo, "mailbox_auth")
check(len(it) == 1 and "kalmido" in it[0]["data"]["text"] and it[0]["data"]["ws"] == WS, f"#6545: the notice names the mailbox ({it})")
m = until(lambda: mails("bob@example.test"), 30)
body = email.message_from_string(m[0]["raw"], policy=email.policy.default).get_body(("plain",)).get_content() if m else ""
check(len(m) == 1 and "fetching stopped" in body and "Settings > Notifications" in body, f"#6545: and a mail to the admin ({body[:300]})")
check(not news(Ca, "mailbox_auth") and not mails("carol@example.test"), "#6545: a member who is no admin hears nothing")
check(until(lambda: news(Da, "mailbox_auth"), 20), "#6545: the second admin hears it in the News")
check(not queued(U["dave"]) and not mails("dave@example.test"), "#6545 F1: but gets no mail: the address is not proved")
b = Bo.get(B + f"/api/hubmail/mailbox?ws=org:{ORG}").json()["box"]
check(b["halted"] and "Save the access data again" in b["halted_text"] and b["error_at"] and b["ok_at"], f"#6545: the settings show the stop, failing since, the last success ({b})")
r = Bo.post(B + "/api/hubmail/mailbox/poll", json={"ws": f"org:{ORG}"})
check(r.status_code == 409, f"#6545: 'Fetch now' on a stopped mailbox: 409 ({r.status_code})")
dbx("UPDATE hub_mailboxes SET polled_at=? WHERE ws=?", (ago(days=1), WS))
n0 = logins("wrong")
rounds()
check(logins("wrong") == n0 and box(WS)["fails"] == 5, f"#6545: stopped means no login at all ({logins('wrong')} vs {n0}, {box(WS)})")
check(len(news(Bo, "mailbox_auth")) == 1 and len(mails("bob@example.test")) == 1, "#6545: and no second notice before 3 days")
r = Bo.put(B + "/api/hubmail/mailbox", json={"ws": f"org:{ORG}", "from_name": "Alpha Office"})
check(r.ok and r.json()["box"]["halted"] and box(WS)["fails"] == 5, f"#6545: a changed sender name does not end the stop ({r.text[:200]})")

# ---- again after 3 days while it lasts; the event switched off stops the mail
dbx("UPDATE hub_mailboxes SET told_at=?, mailed_at=? WHERE ws=?", (ago(days=3, minutes=5), ago(days=3, minutes=5), WS))
check(until(lambda: len(news(Bo, "mailbox_auth")) == 2, 40), "#6545: after 3 days the admin hears it again")
check(until(lambda: len(mails("bob@example.test")) == 2, 30), "#6545: by mail too")
check(Bo.patch(B + "/api/settings", json={"notify": {"integration": {"news": False, "push": False}}}).ok, "bob switches the event 'Integrations' off")
dbx("UPDATE hub_mailboxes SET told_at=?, mailed_at=? WHERE ws=?", (ago(days=4), ago(days=4), WS))
check(until(lambda: str(box(WS)["told_at"] or "")[:10] == datetime.now(timezone.utc).date().isoformat(), 40), "setup: the next notice is due and went out")
rounds(1)
check(len(mails("bob@example.test")) == 2 and len(news(Bo, "mailbox_auth")) == 2, f"#6545: the switched-off event stops News and mail ({len(mails('bob@example.test'))})")
check(Bo.patch(B + "/api/settings", json={"notify": {"integration": {"news": True, "push": True}}}).ok, "setup: on again")

# ---- review F1: saving again + 5 failures within 3 days: the News again, no second mail (mailed_at is not reset)
dbx("UPDATE hub_mailboxes SET mailed_at=? WHERE ws=?", (ago(days=1), WS))  # the last mail went out yesterday
nb, mb = len(news(Bo, "mailbox_auth")), queued(U["bob"])
r = Bo.put(B + "/api/hubmail/mailbox", json={"ws": f"org:{ORG}", "imap_password": "wrong"})
check(r.ok and not box(WS)["told_at"], f"setup: saved again, the outage starts anew ({box(WS)})")
check(until(lambda: box(WS)["fails"] >= 1, 40), f"setup: refused again ({box(WS)})")
dbx("UPDATE hub_mailboxes SET fails=4, polled_at=? WHERE ws=?", (ago(hours=1), WS))
check(until(lambda: len(news(Bo, "mailbox_auth")) == nb + 1, 40), f"#6545 F1: the admin hears the new outage in the News ({box(WS)})")
check(queued(U["bob"]) == mb, f"#6545 F1: but no second mail within 3 days ({queued(U['bob'])} vs {mb})")

# ---- the access data saved again: fetching goes on
check(Er.put(B + "/api/hubmail/mailbox", json={"ws": "private", "active": False}).ok, "setup: erin's mailbox paused (nothing else takes the mails)")
r = Bo.put(B + "/api/hubmail/mailbox", json={"ws": f"org:{ORG}", "imap_password": "secret"})
check(r.ok and not r.json()["box"]["halted"] and box(WS)["fails"] == 0 and not box(WS)["told_at"], f"#6545: new access data ends the stop ({r.text[:200]}, {box(WS)})")
after = drop("After the stop")
check(until(lambda: dbx("SELECT 1 FROM hub_mails WHERE ws=? AND message_id=?", (WS, f"<p6545-{after}@example.org>")), 40), "#6545: and the mailbox is fetched again")

# ---- nobody to receive: not fetched at all
dbx("UPDATE org_members SET role='member' WHERE org_id=? AND user_id IN (?,?)", (ORG, U["bob"], U["dave"]))
lost = drop("Nobody here")
dbx("UPDATE hub_mailboxes SET polled_at=? WHERE ws=?", (ago(hours=1), WS))
check(until(lambda: box(WS)["error"] == "norecipient", 40), f"#6545: no admin in the organisation: error 'no recipient' ({box(WS)})")
check(lost not in seen_uids() and not dbx("SELECT 1 FROM hub_mails WHERE message_id=?", (f"<p6545-{lost}@example.org>",)),
      "#6545: its mail stays unseen in the mailbox (was marked seen and filed nowhere)")
dbx("UPDATE org_members SET role='admin' WHERE org_id=? AND user_id=?", (ORG, U["bob"]))

# ---- review F1: "Fetch now" is limited per person
codes = [Er.post(B + "/api/hubmail/mailbox/poll", json={"ws": "private"}).status_code for _ in range(11)]
check(codes[:10] == [200] * 10 and codes[10] == 429, f"#6545 F1: 'Fetch now' after the limit: 429 ({codes})")

# ---- review F2 / N1: the last success belongs to the mailbox it came from: another server clears it
check(box(WS)["ok_at"], "setup: Alpha's mailbox had a successful fetch")
r = Bo.put(B + "/api/hubmail/mailbox", json={"ws": f"org:{ORG}", "imap_host": "localhost", "imap_password": "secret"})
check(r.ok and not r.json()["box"]["ok_at"] and not box(WS)["ok_at"], f"#6545 F2: ok_at is empty after a change of the server ({r.text[:300]})")

print(f"\n{OKS[0]} ok, {len(FAILS)} failed")
sys.exit(1 if FAILS else 0)
