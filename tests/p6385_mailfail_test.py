#!/usr/bin/env python3
# kalmido-suite: fresh
"""(#6385): a failing mail server is seen - the admins are alerted, a queued mail is tried again, an invitation counts as
sent only once its mail went. Own container (start.sh, mode workspaces); the SMTP of the instance points at the stub's port
(stub_mail.py), which runs only from part 5 on: before that every mail meets a refused connection. Invented names only.
 1. smtp_temp / smtp_down (accounts/mailfail.py): no connection and 4xx are passing failures, 5xx and a refused recipient are not; a refused
    recipient is no failure of the server
 2. every mail through the instance's SMTP counts (mail_deliver): AA_FAIL_ROW - 1 failures in a row no alert, AA_FAIL_ROW an
    admin alert of kind integration with the key smtp:<error>; a mail that goes ends the streak; the mail import's fetch
    ("mail") alerts the same way
 3. a queued mail (mail:forms) whose server fails raises SmtpTemporary: the row waits again (error named) while it has runs
    left and fails after its last; a lasting refusal (550) ends the row without another run; a list of mails (mail:evinvite)
    whose server fails after the first mail went: the rest goes into a new row, the first is never sent twice
 4. the person who started it hears a mail that failed for good: the booking page's person (mail_booking), an inviting
    instance admin (mail_invite); an inviting organisation admin hears nothing per invitation (#3570)
 5. an organisation admin invites a new address: the answer names no mail result, the invitation has no sent_at while its
    queued mail fails; the next invitation (new address or an existing account) and a resend carry the same general notice;
    the instance admin's list of people shows "e-mail not sent"; once the server works, the queued mail goes and sets sent_at
freelancer-matrix: own (frida has no organisation of an instance admin; her companies are her own)
usage: p6385_mailfail_test.py <datadir>"""
import json
import os
import shutil
import subprocess
import sys
import time

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
import kt  # noqa: E402
from freelancer_fixture import freelancer  # noqa: E402
from kt import B, CT, DATA, check  # noqa: E402

SMTP = {"KALMIDO_SMTP_HOST": "127.0.0.1", "KALMIDO_SMTP_PORT": "1025", "KALMIDO_SMTP_TLS": "none",
        "KALMIDO_MAIL_FROM": "kalmido@example.test", "KALMIDO_INSTANCE_MODE": "workspaces"}


def py(code):
    """Runs code in a second process of the container (no loops: TASKS_WATCHDOG=0, role web); the last line = JSON."""
    r = None
    for _try in range(3):  # the import may meet the running server's start-up DDL (deadlock): try again
        r = subprocess.run(["docker", "exec", "-w", "/app", "-e", "TASKS_WATCHDOG=0", "-e", "KALMIDO_ROLE=web", CT,
                            "python", "-c", "import app\n" + code], capture_output=True, text=True)
        if "DeadlockDetected" not in r.stdout + r.stderr:
            break
        time.sleep(2)
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        print((r.stdout + r.stderr)[-2000:], flush=True)
        return {}


def one(sql, args=()):
    r = kt.dbx(sql, args)
    return r[0][0] if r else None


def mails():
    try:
        return [json.loads(x) for x in open(os.path.join(DATA, "mail", "out.jsonl"), encoding="utf-8")]
    except OSError:
        return []


kt.fresh(env=SMTP, prefix="P6385")
A = kt.setup()
AID = kt.me_id(A)
FID, Fr = freelancer(B, A)
PID, _Pa = freelancer(B, A, "paula")
O1 = Fr.post(B + "/api/orgs", json={"name": "Frida Studio"}).json().get("id")
check(O1, f"setup: frida's company {O1}")
kt.proved()

# ---------------------------------------------------------------- 1. which failure is passing, which counts for the alert
r1 = py("""
import json, smtplib
from kalmido.accounts import mailfail as M
E = {"refused": ConnectionRefusedError(111, "x"), "timeout": TimeoutError(), "gone": smtplib.SMTPServerDisconnected("x"),
     "451": smtplib.SMTPDataError(451, b"later"), "550": smtplib.SMTPDataError(550, b"no"),
     "auth": smtplib.SMTPAuthenticationError(535, b"no"), "rcpt550": smtplib.SMTPRecipientsRefused({"a@example.com": (550, b"no")}),
     "rcpt450": smtplib.SMTPRecipientsRefused({"a@example.com": (450, b"later")}), "value": ValueError("x")}
print(json.dumps({"temp": {k: M.smtp_temp(e) for k, e in E.items()}, "down": {k: M.smtp_down(e) for k, e in E.items()}}))
""")
check(r1.get("temp") == {"refused": True, "timeout": True, "gone": True, "451": True, "550": False, "auth": False,
                         "rcpt550": False, "rcpt450": True, "value": False}, f"passing failures: no connection, 4xx {r1.get('temp')}")
check(r1.get("down") == {"refused": True, "timeout": True, "gone": True, "451": True, "550": True, "auth": True,
                         "rcpt550": False, "rcpt450": False, "value": False}, f"failures of the server: all but a refused recipient {r1.get('down')}")

# reader F1 of job/5710: a passing refusal of the recipient is tried again under its own name, which mail_disturbed (the
# organisation admin's notice) does not count - an address anyone can name never switches the notice on
r1b = py("""
import json, smtplib
from kalmido.accounts import mailfail as M
from kalmido.accounts import bgjobs as Q
from kalmido.core.db import connect
out = {}
for k, e in (("rcpt450", smtplib.SMTPRecipientsRefused({"a@example.com": (450, b"later")})), ("refused", ConnectionRefusedError(111, "x"))):
    Q._CUR.rid, Q._CUR.run, Q._CUR.kind = 1, 1, "mail:forms"
    try:
        M.mail_bg_failed("test", e)
    except M.SmtpTemporary as x:
        out[k] = type(x).__name__
    finally:
        Q._CUR.rid = Q._CUR.run = Q._CUR.kind = None
c = connect()
from kalmido.core.pg import system_ctx
with system_ctx(c):
    c.execute("DELETE FROM bg_jobs WHERE kind='mail:p6385f1'")
    c.execute("INSERT INTO bg_jobs (kind, payload, state, error, run_after, created_at) VALUES ('mail:p6385f1', '[]', 'wait', 'SmtpRcptTemporary', '2999-01-01T00:00:00Z', '2026-01-01T00:00:00Z')")
c.commit()
out["disturbed_rcpt"] = M.mail_disturbed(c)
with system_ctx(c):
    c.execute("DELETE FROM bg_jobs WHERE kind='mail:p6385f1'")
c.commit()
c.close()
print(json.dumps(out))
""")
check(r1b.get("rcpt450") == "SmtpRcptTemporary" and r1b.get("refused") == "SmtpTemporary" and r1b.get("disturbed_rcpt") is False,
      f"reader F1: a recipient's 4xx is tried again as SmtpRcptTemporary and does not count for the notice {r1b}")

# ---------------------------------------------------------------- 2. the admin alert after AA_FAIL_ROW failures in a row
r2 = py("""
import json, smtplib, time
from kalmido.integrations import mail as M
from kalmido.notify import alerts
from kalmido.core.db import connect
c = connect()
streak = lambda: int((alerts._AA["int"].get("smtp") or {}).get("n") or 0)
cfg = {**alerts.aa_cfg(c), "on": True, "kinds": ["integration"], "mode": "instant", "cooldown_h": 0}
def tick():
    ints = {k: dict(v) for k, v in alerts._AA["int"].items()}
    alerts._aa_integrations(c, cfg, ints, time.time())
    return [r[0] for r in c.execute("SELECT key FROM admin_alerts WHERE kind='integration' ORDER BY id")]
def send():
    try:
        M.mail_send("someone@example.com", "s", "t")
        return "sent"
    except Exception as e:
        return type(e).__name__
out = {"first": [send() for _ in range(alerts.AA_FAIL_ROW - 1)]}
out["streak_before"] = streak()
out["keys_before"] = tick()
out["last"] = send()
out["streak"] = streak()
out["keys"] = tick()
real = M._deliver
def refused(m, smtp, timeout):
    raise smtplib.SMTPRecipientsRefused({"someone@example.com": (550, b"no")})
M._deliver = refused
out["refused"] = send()
out["streak_refused"] = streak()
M._deliver = lambda m, smtp, timeout: None
out["ok"] = send()
out["streak_ok"] = streak()
M._deliver = real
for _ in range(alerts.AA_FAIL_ROW):
    alerts.aa_fail("mail", "OSError")
out["keys_mail"] = tick()
c.execute("DELETE FROM admin_alerts")
c.commit()
print(json.dumps(out))
""")
check(r2.get("first") and set(r2["first"]) == {"ConnectionRefusedError"} and r2.get("streak_before") == len(r2["first"])
      and not [k for k in r2.get("keys_before") or [] if k.startswith("smtp:")],
      f"AA_FAIL_ROW - 1 failed mails: counted, no alert yet {r2.get('first')} {r2.get('streak_before')} {r2.get('keys_before')}")
check(r2.get("streak") == len(r2.get("first") or []) + 1 and "smtp:ConnectionRefusedError" in (r2.get("keys") or []),
      f"the AA_FAIL_ROW-th failure in a row: an admin alert smtp:<error> {r2.get('streak')} {r2.get('keys')}")
check(r2.get("refused") == "SMTPRecipientsRefused" and r2.get("streak_refused") == r2.get("streak"),
      f"a refused recipient is no failure of the server (the streak stays) {r2.get('streak_refused')}")
check(r2.get("ok") == "sent" and r2.get("streak_ok") == 0, f"a mail that goes ends the streak {r2.get('streak_ok')}")
check("mail:OSError" in (r2.get("keys_mail") or []), f"the mail import's fetch alerts too {r2.get('keys_mail')}")

# ---------------------------------------------------------------- 3. a queued mail is tried again; a list never twice
r3 = py("""
import json, smtplib
from kalmido.accounts import bgjobs as q
from kalmido.integrations import mail as M
from kalmido.core.db import connect
from kalmido.core.pg import system_ctx
import kalmido.team.forms, kalmido.events.invite  # noqa: F401 -- their kinds
c = connect()
def row(kind, args, run):
    rid = q.bgj_add(kind, *args, delay=3600)  # never due: the server's own loop leaves it alone
    with system_ctx(c):
        c.execute("UPDATE bg_jobs SET state='run', attempts=? WHERE id=?", (run, rid))
    c.commit()
    q._run_row(rid, kind, args, run)
    with system_ctx(c):
        x = c.execute("SELECT state, attempts, error FROM bg_jobs WHERE id=?", (rid,)).fetchone()
    c.commit()
    return rid, {"state": x["state"], "error": x["error"]}
out = {"retry": q.BGJ_RETRY_OF.get("mail:forms")}
out["first"] = row("mail:forms", ["someone@example.com", "s", "t"], 1)[1]
out["last"] = row("mail:forms", ["someone@example.com", "s", "t"], out["retry"])[1]
real = M._deliver
def refused(m, smtp, timeout):
    raise smtplib.SMTPRecipientsRefused({"someone@example.com": (550, b"no")})
M._deliver = refused
out["refused"] = row("mail:forms", ["someone@example.com", "s", "t"], 1)[1]
sent = []
def half(m, smtp, timeout):
    if sent:
        raise ConnectionRefusedError(111, "x")
    sent.append(m["To"])
M._deliver = half
ms = [[f"g{i}@example.com", "s", "t", "", "", "X", []] for i in range(3)]
rid, out["list"] = row("mail:evinvite", [ms], 1)
M._deliver = real
with system_ctx(c):
    rest = c.execute("SELECT id FROM bg_jobs WHERE kind='mail:evinvite' AND state='wait' AND id<>?", (rid,)).fetchall()
    out["rest"] = [q._unseal(c, "mail:evinvite", c.execute("SELECT payload FROM bg_jobs WHERE id=?", (r[0],)).fetchone()[0]) for r in rest]
    c.execute("DELETE FROM bg_jobs WHERE kind IN ('mail:forms', 'mail:evinvite')")
c.commit()
out["sent"] = sent
print(json.dumps(out, default=str))
""")
check(r3.get("retry") == 3, f"the mail kinds of #6385 have 3 runs (mailfail.MAIL_RETRY at their bgj_fn, #7181 keeps the others at one) {r3.get('retry')}")
check((r3.get("first") or {}).get("state") == "wait" and (r3.get("first") or {}).get("error") == "SmtpTemporary",
      f"a form mail whose server fails: the row waits for its next run, SmtpTemporary named {r3.get('first')}")
check((r3.get("last") or {}).get("state") == "failed" and (r3.get("last") or {}).get("error") == "SmtpTemporary",
      f"after its last run the row fails {r3.get('last')}")
check((r3.get("refused") or {}).get("state") == "done", f"a lasting refusal (550) is not tried again {r3.get('refused')}")
rest = r3.get("rest") or []
check(r3.get("sent") == ["g0@example.com"] and (r3.get("list") or {}).get("state") == "done" and len(rest) == 1
      and [m[0] for m in rest[0][0]] == ["g1@example.com", "g2@example.com"],
      f"a list whose server fails after the first mail: the rest waits in a new row, the first never twice {r3.get('sent')} {r3.get('list')} {rest}")

# ---------------------------------------------------------------- 4. a mail that failed for good: who hears it
r4 = py(f"""
import json
from kalmido.calendars.apptbook import apb_mail_bg
from kalmido.integrations import mail as M
from kalmido.core.db import connect
out = {{}}
for name, fn in (("booking", lambda: apb_mail_bg("guest@example.com", "s", "t", "", "", "Frida", {FID})),
                 ("admin", lambda: M._sec_mail_send("neu9@example.com", "s", "t", "", None, [{PID}, "nohash", {AID}])),
                 ("orgadmin", lambda: M._sec_mail_send("neu8@example.com", "s", "t", "", None, [{PID}, "nohash", {FID}]))):
    try:
        fn()
        out[name] = "returned"
    except Exception as e:
        out[name] = type(e).__name__
c = connect()
out["news"] = [[r[0], json.loads(r[1]).get("what"), json.loads(r[1]).get("text")] for r in
               c.execute("SELECT user_id, data FROM notifications WHERE kind='integfail' ORDER BY id")]
print(json.dumps(out))
""")
news = r4.get("news") or []
check(r4.get("booking") == "SmtpTemporary" and r4.get("admin") == "SmtpTemporary",
      f"outside a queue row (no run left) the failure still raises {r4}")
check([n for n in news if n[0] == FID and n[1] == "mail_booking" and "guest@example.com" in n[2]],
      f"the booking page's person hears the booking mail that failed for good {news}")
check([n for n in news if n[0] == AID and n[1] == "mail_invite" and "neu9@example.com" in n[2]],
      f"an inviting instance admin hears the invitation that failed for good {news}")
check(not [n for n in news if n[0] == FID and n[1] == "mail_invite"],
      f"an inviting organisation admin hears nothing per invitation (#3570) {news}")

# ---------------------------------------------------------------- 5. the invitation of an organisation admin
r = Fr.post(B + f"/api/orgs/{O1}/invites", json={"email": "neu@example.com", "role": "member"})
check(r.ok and "invitation" not in r.json() and "notice" not in r.json(), f"frida invites neu@: no mail result in the answer {r.status_code} {r.text[:300]}")
NID = one("SELECT id FROM users WHERE lower(email)='neu@example.com'")
failed = kt.until(lambda: one("SELECT id FROM bg_jobs WHERE kind='mail:security' AND error LIKE 'SmtpTemporary%'"), 60)
check(failed, "the queued invitation mail meets the failing server and waits for its next run")
check(NID and one("SELECT sent_at FROM user_invites WHERE user_id=?", (NID,)) is None, "the invitation has no sent_at while its mail failed")
r = Fr.post(B + f"/api/orgs/{O1}/invites", json={"email": "neu2@example.com", "role": "member"})
r_acc = Fr.post(B + f"/api/orgs/{O1}/invites", json={"email": "paula@example.com", "role": "member"})
note = r.json().get("notice") if r.ok else None
check(note and "disturbed" in note and r_acc.ok and r_acc.json().get("notice") == note,
      f"the next invitations carry the general notice, the same for an address with an account {r.text[:300]} {r_acc.text[:300]}")
ref = [x for x in Fr.get(B + f"/api/orgs/{O1}/invites").json().get("invites", []) if x.get("email") == "neu@example.com"]
rs = Fr.post(B + f"/api/orgs/{O1}/invites/{ref[0]['ref']}/resend") if ref else None
check(rs is not None and rs.ok and rs.json().get("notice") == note, f"a resend carries it too {rs.text[:300] if rs is not None else ref}")
NID = one("SELECT id FROM users WHERE lower(email)='neu@example.com'")
us = {u["id"]: u for u in A.get(B + "/api/users?all=1").json().get("users", [])}
check(us.get(NID, {}).get("invite") == "invited" and us[NID].get("invite_unsent") is True and us.get(AID, {}).get("invite_unsent") is False,
      f"the instance admin's list: neu's invitation was not sent by e-mail {us.get(NID)}")
# the server works again: the waiting mail goes at its next run and sets sent_at
os.makedirs(os.path.join(DATA, "mail"), exist_ok=True)
shutil.copy(os.path.join(N, "stub_mail.py"), DATA)
subprocess.run(["docker", "exec", "-d", CT, "python", "/data/stub_mail.py"], check=True)
kt.until(lambda: subprocess.run(["docker", "exec", CT, "python", "-c", "import socket; socket.create_connection(('127.0.0.1', 1025), 1)"],
                                capture_output=True).returncode == 0, 20)
kt.dbx("UPDATE bg_jobs SET run_after='2000-01-01T00:00:00+00:00' WHERE kind='mail:security' AND state='wait'")
sent = kt.until(lambda: one("SELECT sent_at FROM user_invites WHERE user_id=?", (NID,)), 90)
check(sent and [m for m in mails() if "neu@example.com" in json.dumps(m)], "once the server works, the queued invitation goes and sets sent_at")

sys.exit(kt.done("p6385_mailfail"))
