#!/usr/bin/env python3
# kalmido-suite: fresh
"""#7633 (audit #6007 F1, decision 20.11.2026): a way out of the account (an own webhook, an own forwarding to Slack / Matrix /
Telegram / Signal, the private mailbox's server for sending) is a way in like a token:
 - made or pointed elsewhere from an old session (the open computer, a stolen cookie) it asks the password (403
   password_needed, nothing stored), with the password it works; a new name or switching it on again needs nothing
 - each one made is told by a security mail (SEC_EVENTS out_new)
 - a new password with the tick, the admin's reset, the reset link and the first second factor switch the person's own
   webhooks and forwardings off (enabled false, disabled_reason 'password', their queue empty) instead of deleting them;
   without the tick they stay; an organisation's webhook stays on
 - the API (/api/v1/me/webhooks, a token) asks no password, like a token made through the API, but the mail goes out
 - F1 (reader #6109, decision 21.11.2026): the webhook of a document flow in the private workspace is such a way: a new or
   changed address asks the password and is told by mail; a new password switches the webhook action off (hook_state
   'password', a waiting call goes 'off'), the flow stays on; saving it again switches it on, no password; an organisation's
   flow is not touched
 - F2: the private mailbox asks for every new target for sending (server, port, user) and for the first password of a
   server that came in without it (the account import); a new server for receiving asks nothing
 - F3: an instance admin who points an agent's webhook elsewhere confirms the password and gets the mail
 - #7446 F6: the enrolment of a second factor forced at sign-in (the admin policy) ends the older sessions, the token and
   switches the own webhook off like the first second factor (red before the fix: the old session answered)
 - F5 (reader #6117): the mail out_new closes with its way's row: a webhook, a forwarding, a flow's webhook "a new password
   switches ... off"; the mailbox's server for sending and an agent's webhook "stays after a new password too: check it under
   <the place>" (red before: every mail promised the switch-off)
 - F6: an own webhook, forwarding and flow webhook already off after failures get the reason 'password' too (red before:
   "off after failures" stayed)
freelancer-matrix: own (frida: a person WITHOUT an organisation does all of it)
alice (instance admin), frida and hal (no organisation), gus (with his organisation). Invented values only, no delivery is awaited.
Red without the fix: the webhook and the forwarding are made from an old session without the password and without a mail,
and they stay on after every password change; the same for the flow's webhook, the mailbox's new user / port / first
password, the agent's webhook address and the forced enrolment.
usage: p7633_ausleitung_test.py <datadir>   (P7633_NOSTART=1: the container runs already)"""
import base64
import hashlib
import hmac
import json
import struct
import subprocess
import time

import requests

import kt
from kt import B, H, check, dbx
from freelancer_fixture import freelancer

OLD = "2020-01-01T00:00:00+00:00"
PW = "password123"
HOOK = "http://127.0.0.1:8097/p7633"  # an allowed host; nothing listens there and nothing waits for a delivery
# outgoing mail switched on (the security mail kind is registered with it); nobody listens at the port: the rows stay
kt.fresh(env={"KALMIDO_SECRET_KEY": base64.b64encode(b"p7633-invented-key-32-bytes-long").decode(),  # a flow's webhook is sealed
              "KALMIDO_SMTP_HOST": "127.0.0.1", "KALMIDO_SMTP_PORT": "1025", "KALMIDO_SMTP_TLS": "none",
              "KALMIDO_MAIL_FROM": "kalmido@example.test", "KALMIDO_WEBHOOK_ALLOW_HOSTS": "127.0.0.1:8097"}, prefix="P7633")
A = kt.setup()
FID, F = freelancer(B, A)
AID = dbx("SELECT id FROM users WHERE username='alice'")[0][0]
dbx("UPDATE users SET email='alice@example.com' WHERE id=?", (AID,))  # the instance admin hears of an agent's new address (F3)
FWS = f"u{FID}"


def mails(uid):
    return dbx("SELECT count(*) FROM bg_jobs WHERE kind='mail:security' AND user_id=?", (uid,))[0][0]


def age(uid):  # the session was opened long ago
    dbx("UPDATE sessions SET created_at=?, stepup_for='' WHERE user_id=?", (OLD, uid))


def hooks(uid):
    return [tuple(r) for r in dbx("SELECT enabled, disabled_reason FROM webhooks WHERE user_id=? AND org_id IS NULL AND agent=0 ORDER BY id", (uid,))]


def chans(uid):
    return [tuple(r) for r in dbx("SELECT enabled, disabled_reason FROM notify_channels WHERE user_id=? AND org_id IS NULL ORDER BY id", (uid,))]


def queue(uid):  # a delivery waiting for each own webhook / forwarding (the delivery loop must not send it any more)
    for (wid,) in dbx("SELECT id FROM webhooks WHERE user_id=? AND org_id IS NULL AND enabled", (uid,)):
        dbx("INSERT INTO webhook_queue(webhook_id, delivery, event, payload, attempt, next_at, created_at) VALUES(?,?,?,?,0,?,?)",
            (wid, f"d{wid}-{time.time()}", "task.created", "{}", time.time() + 3600, OLD))
    for (cid,) in dbx("SELECT id FROM notify_channels WHERE user_id=? AND org_id IS NULL AND enabled", (uid,)):
        dbx("INSERT INTO notify_channel_queue(channel_id, text, created_at) VALUES(?,?,?)", (cid, "x", time.time()))


def queued(uid):
    return (dbx("SELECT count(*) FROM webhook_queue q JOIN webhooks w ON w.id=q.webhook_id WHERE w.user_id=? AND w.org_id IS NULL", (uid,))[0][0]
            + dbx("SELECT count(*) FROM notify_channel_queue q JOIN notify_channels c ON c.id=q.channel_id WHERE c.user_id=? AND c.org_id IS NULL", (uid,))[0][0])


def switch_on(s, uid):
    for (wid,) in dbx("SELECT id FROM webhooks WHERE user_id=? AND org_id IS NULL AND agent=0 AND NOT enabled", (uid,)):
        check(s.patch(B + f"/api/me/webhooks/{wid}", json={"enabled": True}).ok, "switching an own webhook on again needs no password")
    for (cid,) in dbx("SELECT id FROM notify_channels WHERE user_id=? AND org_id IS NULL AND NOT enabled", (uid,)):
        check(s.patch(B + f"/api/me/channels/{cid}", json={"enabled": True}).ok, "switching an own forwarding on again needs no password")


def totp(secret):
    key = base64.b32decode(secret + "=" * (-len(secret) % 8))
    mac = hmac.new(key, struct.pack(">Q", int(time.time() // 30)), hashlib.sha1).digest()
    o = mac[-1] & 15
    return str((struct.unpack(">I", mac[o:o + 4])[0] & 0x7FFFFFFF) % 10 ** 6).zfill(6)


ON, OFF = (True, ""), (False, "password")


def py(code):
    """Python in the app container (the app's own functions); prints one JSON line."""
    out = subprocess.run(["docker", "exec", kt.CT, "python", "-c", "import os; os.environ['TASKS_WATCHDOG']='0'\nimport app, json\n" + code],
                         capture_output=True, text=True)
    try:
        return json.loads(out.stdout.strip().splitlines()[-1]), out.stderr[-600:]
    except (ValueError, IndexError):
        return None, out.stdout[-300:] + out.stderr[-600:]


def flows(uid):  # the webhook state of the flows of uid's private workspace
    return [r[0] for r in dbx("SELECT hook_state FROM doc_rules WHERE ws=? ORDER BY id", (f"u{uid}",))]


def flow(s, name):
    rs = s.get(B + "/api/docs/settings?ws=private").json()["rules"]
    return next((x for x in rs if x.get("name") == name), None)


def flow_save(s, r, **kw):  # saved again as the list does it: the whole flow with its version
    b = {k: v for k, v in r.items() if k not in ("id", "updated_at")}
    b.update(expect_updated_at=r.get("updated_at"), **kw)
    return s.patch(B + f"/api/docs/rules/{r['id']}", json=b)

# ================================================================ a fresh sign-in: as before, plus the mail
n0 = mails(FID)
r = F.post(B + "/api/me/webhooks", json={"name": "Mine", "url": HOOK, "events": ["task.created"]})
check(r.status_code == 201, f"fresh: frida makes a webhook {r.status_code} {r.text[:160]}")
W1 = r.json().get("id")
check(mails(FID) == n0 + 1, "#7633: a security mail about the new webhook")
r = F.post(B + "/api/me/channels", json={"kind": "slack", "name": "Team", "url": HOOK + "/slack", "events": ["assign"]})
check(r.status_code == 201, f"fresh: frida makes a forwarding {r.status_code} {r.text[:160]}")
C1 = r.json().get("id")
check(mails(FID) == n0 + 2, "#7633: a security mail about the new forwarding")
r = F.post(B + "/api/docs/rules", json={"ws": "private", "name": "Flow out", "kind": "any", "match": "p7633", "tags": ["Out"], "webhook": HOOK + "/flow"})
check(r.status_code == 201 and r.json().get("hook_secret"), f"fresh: frida makes a flow with a webhook {r.status_code} {r.text[:160]}")
FL1 = r.json().get("id")
check(mails(FID) == n0 + 3, "F1: a security mail about the flow's webhook")

# ================================================================ an old session: the password once more
age(FID)
n1, nh = mails(FID), len(hooks(FID))
r = F.post(B + "/api/me/webhooks", json={"name": "Thief", "url": HOOK + "/x", "events": ["task.created"]})
check(r.status_code == 403 and r.json().get("password_needed"), f"#7633: old session, a new webhook asks the password {r.status_code} {r.text[:160]}")
r = F.post(B + "/api/me/webhooks", json={"name": "Thief", "url": HOOK + "/x", "events": ["task.created"], "password": "wrong-one"})
check(r.status_code == 403, f"#7633: a wrong password is refused {r.status_code}")
check(len(hooks(FID)) == nh and mails(FID) == n1, "#7633: nothing stored, no mail")
r = F.post(B + "/api/me/webhooks", json={"name": "Second", "url": HOOK + "/2", "events": ["task.created"], "password": PW})
check(r.status_code == 201, f"#7633: with the password it works {r.status_code} {r.text[:160]}")
check(mails(FID) == n1 + 1, "#7633: and the mail goes out")
r = F.patch(B + f"/api/me/webhooks/{W1}", json={"url": HOOK + "/elsewhere"})
check(r.status_code == 403 and r.json().get("password_needed"), f"#7633: pointing a webhook elsewhere asks the password {r.status_code}")
check(dbx("SELECT url FROM webhooks WHERE id=?", (W1,))[0][0] == HOOK, "#7633: the address stays")
check(F.patch(B + f"/api/me/webhooks/{W1}", json={"name": "Renamed", "url": HOOK}).ok, "a new name (the same address) needs nothing")
r = F.patch(B + f"/api/me/webhooks/{W1}", json={"url": HOOK + "/elsewhere", "password": PW})
check(r.ok and mails(FID) == n1 + 2, f"#7633: with the password the address changes and is told {r.status_code}")
r = F.post(B + "/api/me/channels", json={"kind": "slack", "name": "Thief", "url": HOOK + "/s2", "events": ["assign"]})
check(r.status_code == 403 and r.json().get("password_needed"), f"#7633: old session, a new forwarding asks the password {r.status_code}")
r = F.patch(B + f"/api/me/channels/{C1}", json={"url": HOOK + "/s3"})
check(r.status_code == 403, f"#7633: a new target of a forwarding asks the password {r.status_code}")
check(F.patch(B + f"/api/me/channels/{C1}", json={"name": "Team 2"}).ok, "a forwarding's new name needs nothing")
r = F.patch(B + f"/api/me/channels/{C1}", json={"url": HOOK + "/s3", "password": PW})
check(r.ok and mails(FID) == n1 + 3, f"#7633: with the password the target changes and is told {r.status_code} {r.text[:120]}")
# F1: the webhook of a private document flow
n3 = mails(FID)
r = F.post(B + "/api/docs/rules", json={"ws": "private", "name": "Thief flow", "kind": "any", "match": "x", "webhook": HOOK + "/fx"})
check(r.status_code == 403 and r.json().get("password_needed"), f"F1: old session, a flow with a webhook asks the password {r.status_code} {r.text[:160]}")
check(len(flows(FID)) == 1 and mails(FID) == n3, "F1: no flow stored, no mail")
r = F.post(B + "/api/docs/rules", json={"ws": "private", "name": "No hook", "kind": "any", "match": "y", "tags": ["Y"]})
check(r.status_code == 201 and mails(FID) == n3, f"F1: a flow without a webhook needs nothing {r.status_code} {r.text[:160]}")
r = flow_save(F, flow(F, "Flow out"), webhook=HOOK + "/flow-elsewhere")
check(r.status_code == 403 and r.json().get("password_needed"), f"F1: pointing the flow's webhook elsewhere asks the password {r.status_code}")
check(flow(F, "Flow out").get("webhook") == HOOK + "/flow", "F1: the address stays")
check(flow_save(F, flow(F, "Flow out"), name="Flow out", match="p7633b").ok and mails(FID) == n3, "F1: another change, the same address: nothing asked")
r = flow_save(F, flow(F, "Flow out"), webhook=HOOK + "/flow-elsewhere", password=PW)
check(r.ok and flow(F, "Flow out").get("webhook") == HOOK + "/flow-elsewhere" and mails(FID) == n3 + 1,
      f"F1: with the password the address changes and is told {r.status_code} {r.text[:120]}")
r = F.post(B + "/api/docs/rules", json={"ws": "private", "name": "Flow two", "kind": "any", "match": "z", "webhook": HOOK + "/f2", "password": PW})
check(r.status_code == 201 and mails(FID) == n3 + 2, f"F1: with the password a new flow with a webhook {r.status_code} {r.text[:120]}")

# the private mailbox's server for sending
r = F.put(B + "/api/hubmail/mailbox", json={"ws": "private", "smtp_host": "smtp.example.com", "smtp_port": 587, "smtp_tls": "starttls",
                                            "smtp_user": "frida", "smtp_password": "secret-1", "from_addr": "frida@example.com"})
check(r.status_code == 403 and r.json().get("password_needed"), f"#7633: old session, the mailbox's server for sending asks the password {r.status_code} {r.text[:160]}")
check(not dbx("SELECT 1 FROM hub_mailboxes WHERE owner_id=?", (FID,)), "#7633: no mailbox stored")
n4 = mails(FID)
r = F.put(B + "/api/hubmail/mailbox", json={"ws": "private", "smtp_host": "smtp.example.com", "smtp_port": 587, "smtp_tls": "starttls",
                                            "smtp_user": "frida", "smtp_password": "secret-1", "from_addr": "frida@example.com", "password": PW})
check(r.ok and mails(FID) == n4 + 1, f"#7633: with the password the mailbox sends through the server, told by mail {r.status_code} {r.text[:160]}")


def mbx():
    return tuple(dbx("SELECT smtp_host, smtp_port, smtp_user FROM hub_mailboxes WHERE owner_id=?", (FID,))[0])


r = F.put(B + "/api/hubmail/mailbox", json={"ws": "private", "smtp_user": "thief", "smtp_password": "secret-2"})
check(r.status_code == 403 and r.json().get("password_needed") and mbx()[2] == "frida", f"F2: another user for sending asks the password {r.status_code} {r.text[:120]}")
r = F.put(B + "/api/hubmail/mailbox", json={"ws": "private", "smtp_port": 465, "smtp_tls": "ssl", "smtp_password": "secret-1"})
check(r.status_code == 403 and mbx()[1] == 587, f"F2: another port for sending asks the password {r.status_code} {r.text[:120]}")
check(F.put(B + "/api/hubmail/mailbox", json={"ws": "private", "from_name": "Frida F"}).ok and mails(FID) == n4 + 1,
      "F2: the sender's name needs nothing")
r = F.put(B + "/api/hubmail/mailbox", json={"ws": "private", "smtp_user": "frida2", "smtp_password": "secret-2", "password": PW})
check(r.ok and mbx()[2] == "frida2" and mails(FID) == n4 + 2, f"F2: with the password the user changes and is told {r.status_code} {r.text[:120]}")
# the account import brings the server without its password (admin/acctimport.py, mbx_take_values): the first one asks
dbx("UPDATE hub_mailboxes SET secret='', error='password' WHERE owner_id=?", (FID,))
r = F.put(B + "/api/hubmail/mailbox", json={"ws": "private", "smtp_password": "secret-3"})
check(r.status_code == 403 and r.json().get("password_needed"), f"F2: the first password of an imported server asks the password {r.status_code} {r.text[:120]}")
r = F.put(B + "/api/hubmail/mailbox", json={"ws": "private", "smtp_password": "secret-3", "password": PW})
check(r.ok and mails(FID) == n4 + 3, f"F2: with the password it is stored and told {r.status_code} {r.text[:120]}")
r = F.put(B + "/api/hubmail/mailbox", json={"ws": "private", "imap_host": "imap.example.com", "imap_port": 993, "imap_user": "frida",
                                            "imap_password": "secret-4"})
check(r.ok and mails(FID) == n4 + 3, f"F2: a server for receiving asks nothing (it sends nothing out) {r.status_code} {r.text[:120]}")

# ================================================================ the API: no password (its token was confirmed), but the mail
r = F.post(B + "/api/me/tokens", json={"name": "cli", "scopes": ["read", "write", "integrations"], "password": PW})
check(r.status_code == 201, f"a token for the API {r.status_code} {r.text[:160]}")
T = requests.Session()
T.headers.update({"Authorization": "Bearer " + r.json().get("token", "")})
n2 = mails(FID)
r = T.post(B + "/api/v1/me/webhooks", json={"name": "Script", "url": HOOK + "/api", "events": ["task.created"]})
check(r.status_code == 201, f"the API makes a webhook without the password {r.status_code} {r.text[:160]}")
check(mails(FID) == n2 + 1, "#7633: the mail of the webhook made through the API")

# ================================================================ the own password change: the tick switches them off
F = kt.sess("frida")
queue(FID)
check(queued(FID) > 0, "deliveries are waiting")
NODE = dbx("INSERT INTO fs_nodes(kind, name, owner_id, created_at, updated_at) VALUES('folder', 'p7633', ?, ?, ?) RETURNING id", (FID, OLD, OLD))[0][0]
RUN = dbx("INSERT INTO doc_flow_runs(ws, node_id, rule_id, trig, state, hook, hook_next, created_at) VALUES(?, ?, ?, 'new', 'done', 'wait', ?, ?) RETURNING id",
          (FWS, NODE, FL1, time.time() + 3600, OLD))[0][0]  # a call of the flow's webhook waiting
r = F.patch(B + "/api/me", json={"current_password": PW, "password": "password456", "revoke_tokens": False})
check(r.ok, f"frida changes her password without the tick {r.text[:120]}")
check(all(h == ON for h in hooks(FID)) and all(ch == ON for ch in chans(FID)), f"#4375: without the tick they stay on {hooks(FID)} {chans(FID)}")
check(set(flows(FID)) == {""}, f"#4375: without the tick the flows' webhooks stay on {flows(FID)}")
# F6: one of each is off already after failures (a stranger's way the delivery loop gave up on)
dbx("UPDATE webhooks SET enabled=false, disabled_reason='failures' WHERE id=?", (W1,))
dbx("UPDATE notify_channels SET enabled=false, disabled_reason='failures' WHERE id=?", (C1,))
dbx("UPDATE doc_rules SET hook_state='failures' WHERE id=?", (FL1,))
r = F.patch(B + "/api/me", json={"current_password": "password456", "password": PW, "revoke_tokens": True})
check(r.ok, f"frida changes her password with the tick {r.text[:120]}")
check(hooks(FID) and all(h == OFF for h in hooks(FID)), f"#7633: the tick switches her webhooks off {hooks(FID)}")
check(chans(FID) and all(ch == OFF for ch in chans(FID)), f"#7633: and her forwardings {chans(FID)}")
check(queued(FID) == 0, "#7633: nothing waits to go out any more")
check(len(hooks(FID)) == 3 and len(chans(FID)) == 1, "#7633: switched off, not deleted")
check(dbx("SELECT disabled_reason FROM webhooks WHERE id=?", (W1,))[0][0] == "password",
      "F6: the webhook off after failures says 'switched off by the new password' now")
check(dbx("SELECT disabled_reason FROM notify_channels WHERE id=?", (C1,))[0][0] == "password",
      "F6: so does the forwarding off after failures")
check(dbx("SELECT hook_state FROM doc_rules WHERE id=?", (FL1,))[0][0] == "password", "F6: and the flow's webhook off after failed calls")
check(flows(FID) and set(flows(FID)) == {"password"}, f"F1: the tick switches the webhooks of her private flows off {flows(FID)}")
check(dbx("SELECT hook FROM doc_flow_runs WHERE id=?", (RUN,))[0][0] == "off", "F1: the waiting call of the flow does not go out")
f = flow(F, "Flow out")
check(f and f.get("hook_state") == "password" and not f.get("off") and f.get("webhook"), f"F1: the flow stays on with its other actions, the list says why {f}")
age(FID)
check(flow_save(F, f).ok and flow(F, "Flow out").get("hook_state") == "", "F1: saving the flow again switches its webhook on, no password")
lst = F.get(B + "/api/me/webhooks").json()["hooks"]
check(all(h["disabled_reason"] == "password" for h in lst), "the list says why (the settings show it)")
switch_on(F, FID)
check(all(h == ON for h in hooks(FID)), "switched on again")

# ================================================================ the first second factor
r = F.post(B + "/api/me/2fa/totp", json={"password": PW})
check(r.ok, f"frida starts the authenticator app {r.text[:120]}")
r = F.post(B + "/api/me/2fa/totp/confirm", json={"code": totp(r.json()["secret"].replace(" ", ""))})
check(r.ok, f"frida switches the app codes on {r.text[:120]}")
check(all(h == OFF for h in hooks(FID)) and all(ch == OFF for ch in chans(FID)), f"#7633: the first second factor switches them off {hooks(FID)}")
check(set(flows(FID)) == {"password"}, f"F1: and the webhooks of her private flows {flows(FID)}")

# ================================================================ an organisation's webhook stays (gus, with his organisation)
r = A.post(B + "/api/users", json={"username": "gus", "display_name": "Gus", "password": PW, "email": "gus@example.com"})
assert r.ok, r.text
GUS = r.json()["id"]
G = kt.sess("gus")
G.patch(B + "/api/settings", json={"lang": "en", "tour": "done"})
r = G.post(B + "/api/orgs", json={"name": "Gus Studio"})
check(r.ok, f"gus makes an organisation {r.text[:120]}")
OID = r.json().get("id")
r = G.post(B + f"/api/orgs/{OID}/webhooks", json={"name": "Studio", "url": HOOK + "/org", "events": ["task.created"]})
check(r.status_code == 201, f"an organisation webhook {r.status_code} {r.text[:160]}")
OW = r.json().get("id")
# an organisation's flow (made directly: its webhook state is all that counts here) is not touched by a person's new password
OFL = dbx("INSERT INTO doc_rules(org_id, ws, pos, data, created_by, created_at) VALUES(?, ?, 1, '{}', ?, ?) RETURNING id", (OID, f"o{OID}", GUS, OLD))[0][0]
check(G.post(B + "/api/me/webhooks", json={"url": HOOK + "/gus", "events": ["task.created"]}).status_code == 201, "gus's own webhook")
check(G.patch(B + "/api/me", json={"current_password": PW, "password": "password456", "revoke_tokens": True}).ok, "gus changes his password")
check(hooks(GUS) == [OFF], f"#7633: his own webhook is off {hooks(GUS)}")
check(dbx("SELECT enabled, disabled_reason FROM webhooks WHERE id=?", (OW,))[0] == (True, ""), "#7633: the organisation's webhook stays on")
check(dbx("SELECT hook_state FROM doc_rules WHERE id=?", (OFL,))[0][0] == "", "F1: the organisation's flow stays as it is")

# ================================================================ the admin's reset and the reset link (hal, no organisation)
HID, Hs = freelancer(B, A, name="hal")
check(Hs.post(B + "/api/me/webhooks", json={"url": HOOK + "/hal", "events": ["task.created"]}).status_code == 201, "hal's own webhook")
r = A.patch(B + f"/api/users/{HID}", json={"password": "password456"})
check(r.ok, f"the admin resets hal's password {r.status_code} {r.text[:160]}")
check(hooks(HID) == [OFF], f"#7633: the admin's reset switches his own webhook off {hooks(HID)}")
Hs = kt.sess("hal", pw="password456")
switch_on(Hs, HID)
r = A.post(B + f"/api/users/{HID}/invite", json={"send": False})
tok = ((r.json().get("link") or "") if r.ok else "").rsplit("/#invite/", 1)[-1]
check(bool(tok), f"a reset link for hal {r.status_code} {r.text[:160]}")
s0 = requests.Session()
s0.headers.update(H)
r = s0.post(B + "/api/auth/invite/accept", json={"token": tok, "password": "password789"})
check(r.ok, f"hal sets a new password through the link {r.text[:160]}")
check(hooks(HID) == [OFF], f"#7633: the reset link switches it off {hooks(HID)}")

# ================================================================ F3: an agent's webhook address (alice, instance admin)
A = kt.sess("alice")
r = A.post(B + "/api/admin/agents", json={"username": "p7633bot", "display_name": "Bot", "webhook_url": HOOK + "/agent"})
check(r.status_code == 201, f"alice makes an agent with a webhook {r.status_code} {r.text[:160]}")
BOT = r.json().get("id")


def bot_url():
    return dbx("SELECT w.url FROM agents a JOIN webhooks w ON w.id=a.webhook_id WHERE a.user_id=?", (BOT,))[0][0]


age(AID)
na = mails(AID)
r = A.patch(B + f"/api/admin/agents/{BOT}", json={"webhook_url": HOOK + "/agent-thief"})
check(r.status_code == 403 and r.json().get("password_needed") and bot_url() == HOOK + "/agent",
      f"F3: old session, the agent's webhook pointed elsewhere asks the password {r.status_code} {r.text[:160]}")
check(A.patch(B + f"/api/admin/agents/{BOT}", json={"display_name": "Bot 2", "webhook_url": HOOK + "/agent"}).ok and mails(AID) == na,
      "F3: the same address and a new name need nothing")
r = A.patch(B + f"/api/admin/agents/{BOT}", json={"webhook_url": HOOK + "/agent-2", "password": PW})
check(r.ok and bot_url() == HOOK + "/agent-2" and mails(AID) == na + 1, f"F3: with the password the address changes, the admin is told {r.status_code} {r.text[:160]}")
A = kt.sess("alice")

# ================================================================ #7446 F6: the enrolment forced at sign-in (ivy, no organisation)
IID, Iv = freelancer(B, A, name="ivy")
check(Iv.post(B + "/api/me/webhooks", json={"url": HOOK + "/ivy", "events": ["task.created"]}).status_code == 201, "ivy's own webhook")
check(Iv.post(B + "/api/me/tokens", json={"name": "ivy-cli", "scopes": ["read"], "password": PW}).status_code == 201, "ivy's token")
r = A.patch(B + "/api/admin/settings", json={"twofa_required": True, "password": PW})
check(r.ok and r.json().get("twofa_required") is True, f"the admin policy: a second factor for everybody {r.status_code} {r.text[:120]}")
try:
    s1 = requests.Session()
    s1.headers.update(H)
    r = s1.post(B + "/api/auth/login", json={"username": "ivy", "password": PW})
    check(r.ok and r.json().get("enrol") is True, f"ivy signs in again: she must set up a second factor {r.text[:120]}")
    sec = s1.post(B + "/api/auth/enrol/totp").json().get("secret", "").replace(" ", "")
    r = s1.post(B + "/api/auth/enrol/totp/confirm", json={"code": totp(sec)})
    check(r.ok and s1.get(B + "/api/state").ok, f"ivy set it up and is signed in {r.status_code} {r.text[:120]}")
    check(Iv.get(B + "/api/state").status_code == 401, "#7446 F6: the older session ends with the forced enrolment")
    check(dbx("SELECT count(*) FROM api_tokens WHERE user_id=?", (IID,))[0][0] == 0, "#7446 F6: her token is gone")
    check(hooks(IID) == [OFF], f"#7446 F6: her own webhook is switched off {hooks(IID)}")
finally:
    A.patch(B + "/api/admin/settings", json={"twofa_required": False, "password": PW})

# ================================================================ F5: the mail's closing sentence follows its way's row
j, er = py(f"from kalmido.accounts.secmail import sec_content\nc = app.connect()\n"
           f"print(json.dumps({{lg + ':' + w: sec_content(c, {FID}, 'out_new', ('Mine', '127.0.0.1'), lg, way=w)[1] "
           f"for lg in ('en', 'de') for w in ('webhooks', 'channels', 'flow_hooks', 'mailbox', 'agents')}}))")
check(j is not None, "F5: the mail texts are built " + er)
j = j or {}
OFFS, STAYS = "A new password switches your own webhooks and forwardings off.", "This stays after a new password too: check it under"
for w in ("webhooks", "channels", "flow_hooks"):
    t = j.get("en:" + w, "")
    check("sends data to “Mine” (127.0.0.1)" in t and OFFS in t and STAYS not in t, f"F5: {w} (off): a new password switches it off {t[:200]!r}")
    check("Ein neues Passwort schaltet deine eigenen Webhooks und Weiterleitungen aus." in j.get("de:" + w, ""), f"F5: {w} (off) in German")
for w, where, wo in (("mailbox", "E-mail filing > Mailbox", "E-Mail-Ablage > Postfach"), ("agents", "Settings > Agents", "Einstellungen > Agenten")):
    t = j.get("en:" + w, "")
    check(f"{STAYS} {where}." in t and OFFS not in t, f"F5: {w} (stays): no promise, the place to check it {t[:200]!r}")
    check(f"Das bleibt auch nach einem neuen Passwort: prüfe es unter {wo}." in j.get("de:" + w, ""), f"F5: {w} (stays) in German")
# the mailbox is not switched off by a new password (it stays, the mail says so)
check(dbx("SELECT count(*) FROM hub_mailboxes WHERE owner_id=? AND smtp_host<>''", (FID,))[0][0] == 1,
      "F5: the mailbox's server for sending stays after the new passwords")

raise SystemExit(kt.done("p7633_ausleitung_test"))
