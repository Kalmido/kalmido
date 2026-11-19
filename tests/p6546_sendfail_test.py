#!/usr/bin/env python3
# kalmido-suite: fresh
"""(#6546): sending through the own SMTP of a workspace mailbox fails. Own container (start.sh through kt.fresh) with the stub
mail server inside (stub_mail.py: IMAP 127.0.0.1:1143, login kalmido / secret; SMTP 127.0.0.1:1025, password "secret", a
sender "refuse@..." refused with 553, a recipient "refuse@..." with 550). Invented companies, people and addresses only.
freelancer-matrix: hubmail
 - migration 6546: send_fails / send_error / send_error_at / send_told_at
 - a mailbox that only sends (no IMAP, never fetched) counts its failed sends: wrong password = "auth", 502 with the reason in
   plain words and Settings > Company & office > E-mail; failing since = the first failure of the outage
 - 2 failures tell nobody; the 3rd tells the organisation's admins (News, and a mail to a proved address), not a member;
   a 4th does not tell again
 - a successful fetch (IMAP added to the same mailbox) does not set the send count back; only a send that went out does
 - the settings and the list of workspaces show the send outage beside the fetch state
 - new access data for sending starts the count anew; a refused sender address = "sender" with its own words; a refused
   recipient is no failure of the mailbox (count and error unchanged, no hint to the settings)
 - a person without an organisation: her private mailbox counts the same and she hears it herself
usage: p6546_sendfail_test.py <datadir>      (P6546_NOSTART=1: the container runs already, only the stub is started)"""
import os
import subprocess
import sys
import time

import dbx as dbxm
import kt
from kt import B, CT, DATA, check, done, sess, until
from freelancer_fixture import freelancer

N = os.path.dirname(os.path.abspath(__file__))
KEY = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="
FEAT = "cal,collab,comments,events,contacts,clients"
HINT = "Settings > Company & office > E-mail"

kt.fresh(env={"KALMIDO_SMTP_HOST": "127.0.0.1", "KALMIDO_SMTP_PORT": "1025", "KALMIDO_SMTP_TLS": "none", "KALMIDO_MAIL_FROM": "kalmido@example.test",
              "KALMIDO_IMAP_INTERVAL": "5", "KALMIDO_CALENDAR_ALLOW_HOSTS": "127.0.0.1:1143,127.0.0.1:1025", "KALMIDO_SECRET_KEY": KEY},
         prefix="P6546")
os.makedirs(os.path.join(DATA, "mail", "in"), exist_ok=True)
open(os.path.join(DATA, "stub_mail.py"), "w").write(open(os.path.join(N, "stub_mail.py")).read())
subprocess.run(["docker", "exec", "-d", CT, "python", "/data/stub_mail.py"])
time.sleep(1.2)


def dbx(sql, args=()):
    c = dbxm.connect(os.path.join(DATA, "tasks.db"), timeout=10)
    try:
        r = c.execute(sql, args).fetchall()
        c.commit()
        return r
    finally:
        c.close()


def box(ws):
    r = dbx("SELECT send_fails, send_error, send_error_at, send_told_at, ok_at FROM hub_mailboxes WHERE ws=?", (ws,))
    return dict(zip(("send_fails", "send_error", "send_error_at", "send_told_at", "ok_at"), r[0])) if r else {}


def news(s):
    return [x for x in s.get(B + "/api/news").json()["items"] if x["kind"] == "integfail" and x["data"].get("what") == "mailbox_send"]


def queued(uid):
    """The integration mails queued for uid (bg_jobs, added in the same step as the News item: no waiting)."""
    return dbx("SELECT count(*) FROM bg_jobs WHERE kind='mail:security' AND user_id=?", (uid,))[0][0]


NR = [0]


def send(s, cid, to=None):
    """A new mail from client cid's filing (each to another address: the day's limit per recipient stays far)."""
    NR[0] += 1
    return s.post(B + "/api/hubmail/send", json={"client_id": cid, "to": to or f"kunde{NR[0]}@example.com", "subject": f"Hallo {NR[0]}", "text": "Text."})


A = kt.setup()
U = {}
for u in ("bob", "carol", "dave"):
    r = A.post(B + "/api/users", json={"username": u, "display_name": u.title(), "password": "password123", "email": f"{u}@example.test"})
    assert r.ok, r.text
    U[u] = r.json()["id"]
r = A.post(B + "/api/admin/orgs", json={"name": "Alpha", "admin_id": U["bob"]})
assert r.status_code == 201, r.text
ORG = r.json()["id"]
A.patch(B + f"/api/admin/orgs/{ORG}", json={"members": [U["bob"], U["carol"], U["dave"]], "admins": [U["bob"], U["dave"]]})
dbx("UPDATE users SET email_proved=lower(email) WHERE id=?", (U["bob"],))  # dave's address stays unproved: News only
ERIN, Er = freelancer(B, A, "erin")
dbx("UPDATE users SET email_proved=lower(email) WHERE id=?", (ERIN,))
Bo, Ca, Da = sess("bob"), sess("carol"), sess("dave")
for s in (Bo, Ca, Da, Er):
    s.patch(B + "/api/settings", json={"lang": "en", "tour": "done", "features": FEAT, "workspace": "all"})
ACME = Bo.post(B + "/api/clients", json={"name": "Acme", "org_id": ORG, "email": "acme@example.com"}).json()["id"]
SOLO = Er.post(B + "/api/clients", json={"name": "Solo", "email": "solo@example.com"}).json()["id"]
SMTP = {"smtp_host": "127.0.0.1", "smtp_port": 1025, "smtp_tls": "none", "smtp_user": "kalmido", "smtp_password": "secret",
        "from_addr": "office@example.test", "from_name": "Alpha Office"}

cols = {x[0] for x in dbx("SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='hub_mailboxes'")}
check({"send_fails", "send_error", "send_error_at", "send_told_at"} <= cols, f"migration 6546: the new columns ({sorted(cols)})")

# ---- a mailbox that only sends: a send that works leaves nothing
r = Bo.put(B + "/api/hubmail/mailbox", json={**SMTP, "ws": f"org:{ORG}"})
check(r.ok, f"setup: Alpha's mailbox only for sending {r.text[:200]}")
WS = dbx("SELECT ws FROM hub_mailboxes WHERE org_id=?", (ORG,))[0][0]
r = send(Bo, ACME)
check(r.status_code == 201 and r.json().get("via") == "workspace", f"setup: a send through the mailbox works ({r.status_code} {r.text[:200]})")
check(box(WS)["send_fails"] == 0 and not box(WS)["send_error"], f"#6546: a send that went out leaves no error ({box(WS)})")

# ---- a wrong password: counted, the reason in plain words, where to repair it
check(Bo.put(B + "/api/hubmail/mailbox", json={"ws": f"org:{ORG}", "smtp_password": "wrong"}).ok, "setup: a wrong password for sending")
r = send(Bo, ACME)
e = r.json().get("error", "")
check(r.status_code == 502 and "user name or the password" in e and HINT in e, f"#6546: the answer names the reason and the settings ({r.status_code} {e})")
b1 = box(WS)
check(b1["send_fails"] == 1 and b1["send_error"] == "auth" and b1["send_error_at"], f"#6546: a mailbox that only sends counts the failure ({b1})")
r = send(Bo, ACME)
b2 = box(WS)
check(r.status_code == 502 and b2["send_fails"] == 2 and b2["send_error_at"] == b1["send_error_at"], f"#6546: failing since = the first failure ({b2})")
check(not news(Bo) and not news(Da), "#6546: 2 failures in a row tell nobody yet")

# ---- the 3rd: the admins hear it (News; the mail only to a proved address), a member does not
mb = queued(U["bob"])
r = send(Bo, ACME)
check(r.status_code == 502 and box(WS)["send_fails"] == 3 and box(WS)["send_told_at"], f"#6546: the 3rd failure ({box(WS)})")
it = news(Bo)
check(len(it) == 1 and "office@example.test" in it[0]["data"]["text"] and "user name or the password" in it[0]["data"]["text"] and it[0]["data"].get("ws") == WS,
      f"#6546: the admin hears it, with the mailbox and the reason ({it})")
check(len(news(Da)) == 1 and not news(Ca), "#6546: the second admin too, the member not")
check(queued(U["bob"]) == mb + 1 and not queued(U["dave"]), f"#6546: a mail to the admin with a proved address only ({queued(U['bob'])} vs {mb})")
r = send(Bo, ACME)
check(r.status_code == 502 and box(WS)["send_fails"] == 4 and len(news(Bo)) == 1, "#6546: the 4th failure tells nobody again (3 days)")

# ---- the settings and the list of workspaces show it
b = Bo.get(B + f"/api/hubmail/mailbox?ws=org:{ORG}").json()["box"]
check(b["send_error"] == "auth" and "user name or the password" in b["send_error_text"] and b["send_error_at"] and b["send_fails"] == 4,
      f"#6546: the settings show the send outage ({b})")
sp = {x["ws"]: x for x in Bo.get(B + "/api/hubmail/mailboxes").json()["spaces"]}
check(sp[f"org:{ORG}"].get("send_error_text") and sp[f"org:{ORG}"].get("send_error_at"), f"#6546: the list of workspaces too ({sp[f'org:{ORG}']})")
check(not [x for x in Ca.get(B + "/api/hubmail/mailboxes").json()["spaces"] if "send_error" in x], "#6546: a member who does not manage it sees no details")

# ---- a successful fetch does not set the send count back (IMAP added to the same mailbox, the SMTP data unchanged)
r = Bo.put(B + "/api/hubmail/mailbox", json={"ws": f"org:{ORG}", "imap_host": "127.0.0.1", "imap_port": 1143, "imap_ssl": False, "imap_user": "kalmido",
                                             "imap_password": "secret"})
check(r.ok, f"setup: the mailbox receives too {r.text[:200]}")
check(until(lambda: box(WS)["ok_at"], 40), f"setup: a fetch worked ({box(WS)})")
check(box(WS)["send_fails"] == 4 and box(WS)["send_error"] == "auth", f"#6546: a successful fetch leaves the send outage ({box(WS)})")

# ---- new access data for sending: the count starts anew; a refused sender address has its own words
r = Bo.put(B + "/api/hubmail/mailbox", json={"ws": f"org:{ORG}", "smtp_password": "secret", "from_addr": "refuse@example.test"})
check(r.ok and box(WS)["send_fails"] == 0 and not box(WS)["send_told_at"], f"#6546: new access data for sending start the count anew ({box(WS)})")
r = send(Bo, ACME)
e = r.json().get("error", "")
check(r.status_code == 502 and "sender address" in e and HINT in e and box(WS)["send_error"] == "sender" and box(WS)["send_fails"] == 1,
      f"#6546: a refused sender: 'sender', its words ({r.status_code} {e} {box(WS)})")

# ---- a refused recipient is the address's problem, not the mailbox's
check(Bo.put(B + "/api/hubmail/mailbox", json={"ws": f"org:{ORG}", "from_addr": "office@example.test"}).ok, "setup: the right sender again")
before = box(WS)
r = send(Bo, ACME, to="refuse@example.com")
e = r.json().get("error", "")
check(r.status_code == 502 and "recipient address" in e and HINT not in e, f"#6546: a refused recipient: its words, no hint to the settings ({r.status_code} {e})")
check(box(WS)["send_fails"] == before["send_fails"] and box(WS)["send_error"] == before["send_error"], f"#6546: and the mailbox's count is unchanged ({box(WS)} vs {before})")

# ---- a send that goes out ends the outage
r = send(Bo, ACME)
b = box(WS)
check(r.status_code == 201 and b["send_fails"] == 0 and not b["send_error"] and not b["send_error_at"] and not b["send_told_at"], f"#6546: a send that went out ends it ({b})")
check(not Bo.get(B + f"/api/hubmail/mailbox?ws=org:{ORG}").json()["box"]["send_error_text"], "#6546: and the settings show no send outage")

# ---- a person without an organisation: the same with her private mailbox, she hears it herself
r = Er.put(B + "/api/hubmail/mailbox", json={**SMTP, "ws": "private", "from_addr": "erin@example.test", "from_name": "", "smtp_password": "wrong"})
check(r.ok, f"setup: erin's private mailbox only for sending {r.text[:200]}")
EWS = f"u{ERIN}"
nb = len(news(Bo))
codes = [send(Er, SOLO).status_code for _ in range(3)]
check(codes == [502] * 3 and box(EWS)["send_fails"] == 3 and box(EWS)["send_error"] == "auth", f"freelancer: her failed sends count ({codes} {box(EWS)})")
check(len(news(Er)) == 1, f"freelancer: she hears it herself ({news(Er)})")
check(len(news(Bo)) == nb, "freelancer: nobody else (Alpha's admin)")

sys.exit(done("p6546_sendfail"))
