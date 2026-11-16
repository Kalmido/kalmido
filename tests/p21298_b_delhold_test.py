#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1298.0 (#6395): an admin's lock holds the final own deletion (admin/selfdelete.py, accounts/delhold.py). Own container
with the SMTP stub (tests/stub_mail.py), the admin alerts on and the hoster's operator interface (a token file). People
without an organisation throughout (freelancer-matrix: team):
 - frida asks for her deletion, the admin locks her: the plan notes the lock, the user management shows delete_hold
   (until = lock + 30 days), the admins hear of it in the bell (News "delhold", stage "lock")
 - the sign-in with her password and her cancel link of before the lock both say: held, by <day> at the latest (the link 409);
   a wrong link stays 403 and says nothing
 - her day passes (delete_at in the past): the account is NOT deleted while it is held (the tick passed: its note is back)
 - 7 days and 1 day before the end of the hold the admins hear of it again (stages d7, d1)
 - a person who is no admin may not decide (403); an invalid decision 400
 - the admin releases it: deleted at the next tick, the last mail, the security log
 - greta: the admin rejects: the plan is gone, the account stays locked, the mail "admin has locked", the security log;
   deciding again: 409 no_hold
 - hanna: 30 days after the lock without a decision: deleted
 - ida: the hoster locks her (operator interface), sees delete_hold, rejects through its own route (409 / 400 as in the app)
Time is moved in the database (delete_at, plan.admin), never waited for. Invented names only.
usage: p21298_b_delhold_test.py <datadir>"""
import email
import email.policy
import json
import os
import secrets
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dbx as dbxm  # noqa: E402
import kt  # noqa: E402
from freelancer_fixture import freelancer  # noqa: E402
from kt import B, CT, check, dbx, until  # noqa: E402

N = os.path.dirname(os.path.abspath(__file__))
DATA = sys.argv[1] if len(sys.argv) > 1 else kt.DATA
PW = "password123"
OPDIR = os.path.abspath(DATA.rstrip("/")) + "-op"
TOKEN = secrets.token_urlsafe(40)
EXTRA = (os.environ.get("EXTRA", "") + f" -v {OPDIR}:/run/kop:ro -e KALMIDO_OPERATOR_TOKEN_FILE=/run/kop/token"
         " -e KALMIDO_SMTP_HOST=127.0.0.1 -e KALMIDO_SMTP_PORT=1025 -e KALMIDO_SMTP_TLS=none"
         " -e KALMIDO_MAIL_FROM=kalmido@example.test -e KALMIDO_INSTANCE_MODE=workspaces -e KALMIDO_ADMIN_ALERTS=1").strip()


def write(q, args=()):
    c = dbxm.connect(os.path.join(DATA, "tasks.db"))
    c.execute(q, args)
    c.commit()
    c.close()


def mails():
    out = []
    try:
        for x in open(os.path.join(DATA, "mail", "out.jsonl"), encoding="utf-8"):
            m = json.loads(x)
            msg = email.message_from_string(m["raw"], policy=email.policy.default)
            body = msg.get_body(("plain",))
            out.append({"to": [t.lower() for t in m["to"]], "subject": str(msg["subject"] or ""), "text": body.get_content() if body else ""})
    except OSError:
        pass
    return out


def mail_to(addr, part, n=1, wait=15):
    return until(lambda: (lambda ms: ms if len(ms) >= n else None)([m for m in mails() if addr in m["to"] and part in m["subject"]]), wait)


def cancel_token(m):
    import re
    x = re.search(r"#delete-cancel=([\w.-]+)", m["text"])
    return x.group(1) if x else ""


def plan(uid):
    r = dbx("SELECT delete_plan FROM users WHERE id=?", (uid,))
    return json.loads(r[0][0] or "{}") if r else None


def set_plan(uid, **kw):
    p = plan(uid)
    p.update(kw)
    write("UPDATE users SET delete_plan=? WHERE id=?", (json.dumps(p), uid))


def ago(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")


def news(uid, stage=None):
    rows = [json.loads(r[0] or "{}") for r in dbx("SELECT data FROM notifications WHERE user_id=? AND kind='delhold' ORDER BY id", (AID,))]
    return [d for d in rows if d.get("user_id") == uid and (stage is None or d.get("stage") == stage)]


def alert(key):
    return dbx("SELECT message FROM admin_alerts WHERE kind='security' AND key LIKE ?", (key + "%",))


def op(method, path, **kw):
    return requests.request(method, B + "/api/operator/" + path, headers={"Authorization": "Bearer " + TOKEN}, timeout=60, **kw)


def ask(sess):
    r = sess.post(B + "/api/account/delete", json={"password": PW, "lists": {}})
    return r.ok and bool(r.json().get("delete_at"))


# ---------------------------------------------------------------- the container: SMTP stub, admin alerts, operator token
shutil.rmtree(OPDIR, ignore_errors=True)
os.makedirs(OPDIR)
with open(os.path.join(OPDIR, "token"), "w") as f:
    f.write(TOKEN + "\n")
os.chmod(OPDIR, 0o755)
os.chmod(os.path.join(OPDIR, "token"), 0o644)
r = subprocess.run(["bash", os.path.join(N, "start.sh"), DATA], capture_output=True, text=True, env=dict(os.environ, EXTRA=EXTRA))
assert r.returncode == 0, r.stdout + r.stderr
os.makedirs(os.path.join(DATA, "mail"), exist_ok=True)
shutil.copy(os.path.join(N, "stub_mail.py"), DATA)
subprocess.run(["docker", "exec", "-d", CT, "python", "/data/stub_mail.py"], check=True)
until(lambda: subprocess.run(["docker", "exec", CT, "python", "-c", "import socket; socket.create_connection(('127.0.0.1', 1025), 1)"],
                             capture_output=True).returncode == 0, 15)
A = kt.setup()
A.patch(B + "/api/settings", json={"tour": "done", "lang": "en"})
AID = A.get(B + "/api/state").json()["me"]["id"]
FID, Fr = freelancer(B, A, "frida")
BOB, Bo = freelancer(B, A, "bob")

# ---------------------------------------------------------------- frida asks, the admin locks her: the deletion is held
check(ask(Fr), "frida asks for her deletion")
m = mail_to("frida@example.com", "will be deleted")
TOK = cancel_token(m[0]) if m else ""
check(bool(TOK), "setup: the mail with her cancel link")
r = A.patch(B + f"/api/users/{FID}", json={"disabled": True})
check(r.ok and (r.json().get("delete_hold") or {}).get("release") is False, f"the admin locks her: the answer shows the held deletion {r.text[:300]}")
p = plan(FID)
check(bool(p.get("admin")) and not p.get("toks") and len(p.get("held_toks") or []) == 1, f"the plan notes the lock, the link is kept apart {p}")
row = [u for u in A.get(B + "/api/users?all=1").json()["users"] if u["id"] == FID]
h = (row[0].get("delete_hold") or {}) if row else {}
until_day = (datetime.fromisoformat(p["admin"]) + timedelta(days=30)).isoformat(timespec="seconds")
check(h.get("until") == until_day and h.get("at") and h.get("release") is False, f"the user management: held until the lock + 30 days {h} {until_day}")
check(bool(until(lambda: news(FID, "lock"), 15)), "the admin hears of it in the bell (stage lock)")
check(bool(until(lambda: "lock" in (plan(FID).get("told") or []), 10)), "the stage told is noted in the plan")

# ---------------------------------------------------------------- what the person sees
s = requests.Session()
s.headers.update({"X-Requested-With": "kalmido"})
r = s.post(B + "/api/auth/login", json={"username": "frida", "password": PW})
j = r.json()
check(r.status_code == 403 and j.get("deleting") is True and j.get("held") is True and j.get("delete_by") == until_day
      and "on hold for a review" in j.get("error", ""), f"the sign-in: held, by the end of the hold at the latest ({r.status_code} {r.text[:200]})")
r = s.post(B + "/api/auth/login", json={"username": "frida", "password": "wrong-pass"})
check(r.status_code == 401 and not r.json().get("held"), "a wrong password learns nothing")
r = s.post(B + "/api/auth/delete-cancel", json={"token": TOK})
check(r.status_code == 409 and r.json().get("held") is True and r.json().get("delete_by") == until_day,
      f"her cancel link of before the lock: held, with the day ({r.status_code} {r.text[:200]})")
r = s.post(B + "/api/auth/delete-cancel", json={"token": f"{FID}.nope"})
check(r.status_code == 403 and "held" not in r.json(), "a wrong link: 403, nothing of the account's state")
check(dbx("SELECT disabled, delete_at IS NOT NULL FROM users WHERE id=?", (FID,))[0] == (1, True), "the link cancelled nothing")

# ---------------------------------------------------------------- her day passes: nothing is deleted while it is held
write("UPDATE users SET delete_at='2000-01-01T00:00:00+00:00' WHERE id=?", (FID,))
set_plan(FID, told=[])  # a stage it has to tell again: its note shows that the tick saw the account with its day passed
check(bool(until(lambda: "lock" in (plan(FID) or {}).get("told", []), 15)), "the tick passed the account after its day")
check(dbx("SELECT 1 FROM users WHERE id=?", (FID,)) == [(1,)], "held: not deleted although its day passed")

# ---------------------------------------------------------------- 7 days and 1 day before the end of the hold
set_plan(FID, admin=ago(24))  # the hold ends in 6 days
check(bool(until(lambda: news(FID, "d7"), 15)), "7 days before the end: the admin hears of it again (d7)")
set_plan(FID, admin=ago(29.5))  # ends in half a day
check(bool(until(lambda: news(FID, "d1"), 15)), "1 day before the end: once more (d1)")
check(len(news(FID, "d7")) == 1 and dbx("SELECT 1 FROM users WHERE id=?", (FID,)) == [(1,)], "each stage once, still not deleted")
check(Bo.get(B + "/api/news").ok and not [x for x in (Bo.get(B + "/api/news").json().get("items") or []) if x.get("kind") == "delhold"],
      "bob (no admin) sees no such entry")

# ---------------------------------------------------------------- deciding: only an admin, a valid decision
r = Bo.post(B + f"/api/users/{FID}/deletion", json={"decision": "release"})
check(r.status_code == 403, f"bob (no admin) may not decide ({r.status_code})")
r = A.post(B + f"/api/users/{FID}/deletion", json={"decision": "maybe"})
check(r.status_code == 400, f"an invalid decision: 400 ({r.status_code})")
r = A.post(B + f"/api/users/{BOB}/deletion", json={"decision": "release"})
check(r.status_code == 409 and r.json().get("code") == "no_hold", f"bob's account waits for nothing: 409 ({r.status_code} {r.text[:150]})")
r = A.post(B + f"/api/users/{FID}/deletion", json={"decision": "release"})
check(r.ok and r.json().get("decision") == "release", f"the admin releases frida's deletion ({r.status_code} {r.text[:150]})")
check(bool(until(lambda: not dbx("SELECT 1 FROM users WHERE id=?", (FID,)), 30)), "released: the next tick deleted her account")
check(bool(mail_to("frida@example.com", "was deleted")), "the last mail confirms the deletion")
check(bool(until(lambda: alert("selfdel-release:"), 15)), "the security log names the release")

# ---------------------------------------------------------------- greta: the admin rejects
GID, Gr = freelancer(B, A, "greta")
ag = Gr.post(B + "/api/my/agents", json={"username": "gretabot", "display_name": "Greta's bot", "scopes": ["read"]})
GAG = ag.json().get("id") if ag.status_code in (200, 201) else None
check(bool(GAG), f"setup: greta's agent {ag.status_code} {ag.text[:150]}")
check(ask(Gr), "greta asks for her deletion")
n_c = len([x for x in mails() if "greta@example.com" in x["to"] and "was cancelled" in x["subject"]])
check(A.patch(B + f"/api/users/{GID}", json={"disabled": True}).ok, "the admin locks her")
r = A.post(B + f"/api/users/{GID}/deletion", json={"decision": "reject"})
check(r.ok and r.json().get("decision") == "reject", f"the admin rejects ({r.status_code} {r.text[:150]})")
check(dbx("SELECT disabled, delete_at, delete_plan FROM users WHERE id=?", (GID,))[0] == (1, None, ""), "the deletion is off, the account stays locked")
check(dbx("SELECT enabled FROM agents WHERE user_id=?", (GAG,))[0][0] == 0, "her agent stays paused")
mc = mail_to("greta@example.com", "was cancelled", n_c + 1)
check(bool(mc) and "admin has locked" in mc[-1]["text"], f"the mail says the deletion is off and the lock stays {mc[-1:]}")
check(bool(until(lambda: alert("selfdel-reject:"), 15)), "the security log names the rejection")
r = A.post(B + f"/api/users/{GID}/deletion", json={"decision": "reject"})
check(r.status_code == 409, f"deciding again: nothing waits (409, {r.status_code})")
r = s.post(B + "/api/auth/login", json={"username": "greta", "password": PW})
check(r.status_code in (401, 403) and not r.json().get("deleting"), "her sign-in stays refused like any locked account")
check(not news(GID) or not [x for x in (A.get(B + "/api/news").json().get("items") or []) if x.get("kind") == "delhold"
                            and (x.get("data") or {}).get("user_id") == GID], "the bell entry is gone with the decision")

# ---------------------------------------------------------------- hanna: 30 days without a decision
HID, Ha = freelancer(B, A, "hanna")
check(ask(Ha), "hanna asks for her deletion")
check(A.patch(B + f"/api/users/{HID}", json={"disabled": True}).ok, "the admin locks her")
write("UPDATE users SET delete_at='2000-01-01T00:00:00+00:00' WHERE id=?", (HID,))
set_plan(HID, told=[])
check(bool(until(lambda: "lock" in ((plan(HID) or {}).get("told") or []), 15)) and dbx("SELECT 1 FROM users WHERE id=?", (HID,)) == [(1,)],
      "held: the tick passed her, not deleted")
set_plan(HID, admin=ago(31))  # the hold ended a day ago, nobody decided
check(bool(until(lambda: not dbx("SELECT 1 FROM users WHERE id=?", (HID,)), 30)), "30 days after the lock without a decision: deleted")

# ---------------------------------------------------------------- ida: the hoster (operator interface)
IID, Ia = freelancer(B, A, "ida")
check(ask(Ia), "ida asks for her deletion")
r = op("POST", f"accounts/{IID}/deletion", json={"decision": "reject"})
check(r.status_code == 409 and r.json().get("code") == "no_hold", f"the hoster: nothing held yet (409, {r.status_code})")
r = op("PUT", f"accounts/{IID}", json={"disabled": True})
check(r.ok and (r.json()["account"].get("delete_hold") or {}).get("release") is False, f"the hoster locks her: the deletion is held {r.text[:300]}")
check(bool(plan(IID).get("admin")), "the plan notes the hoster's lock")
r = op("POST", f"accounts/{IID}/deletion", json={"decision": "later"})
check(r.status_code == 400, f"the hoster: an invalid decision 400 ({r.status_code})")
r = requests.post(B + f"/api/operator/accounts/{IID}/deletion", json={"decision": "reject"})
check(r.status_code == 401, f"without the token: 401 ({r.status_code})")
r = op("POST", f"accounts/{IID}/deletion", json={"decision": "reject"})
check(r.ok and r.json().get("decision") == "reject" and "delete_hold" not in r.json().get("account", {}) and "username" not in r.text,
      f"the hoster rejects: numbers only, nothing held any more ({r.status_code} {r.text[:200]})")
check(dbx("SELECT disabled, delete_at FROM users WHERE id=?", (IID,))[0] == (1, None), "ida stays locked, the deletion is off")
check(bool(until(lambda: [x for x in alert("selfdel-reject:") if "operator" in x[0]], 15)), "the security log names the hoster")
sys.exit(kt.done("p21298_b_delhold"))
