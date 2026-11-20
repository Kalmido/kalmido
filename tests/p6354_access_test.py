#!/usr/bin/env python3
# kalmido-suite: fresh
"""(#6354, audit #4773 F6): every new way into an account is told by a security mail; a new password ends the ways a
session could have left behind.
 - security mails (queued as bg_jobs kind mail:security, counted - the payload is sealed; no SMTP server needed): a new API token, a new app password,
   app codes switched on, a new passkey, a new personal agent and a new token of it (to the owner)
 - the own password change with the tick (revoke_tokens true, and without the field): app passwords, API tokens, the task
   feed link (users.ical_token_hash), the event calendar and absences feed links (ev_cal_feeds, abs_cal_feeds) and the
   upload token (users.drop_token_hash) end; without the tick they stay (the scan keys end as before, #2865)
 - the admin's reset and the reset link end them too (sessions.py ses_access_end, one place)
 - passkeys and own agents stay (the dialog points to their lists) - the agent's token is the agent's
freelancer-matrix: own
alice (instance admin), frida (a person WITHOUT an organisation), gus (made by the admin). Invented values only.
Red without the fix: no mail for the new token / app password / passkey / app codes / agent token; the feed links and the
upload token survive the password change and the resets.
usage: p6354_access_test.py <datadir>   (P6354_NOSTART=1: the container runs already)"""
import base64
import hashlib
import hmac
import json
import os
import struct
import time

import requests
from cryptography.hazmat.primitives.asymmetric import ec

import dbx as dbxm
import kt
from kt import B, DATA, H, check
from freelancer_fixture import freelancer

ORIGIN, RP = "https://kalmido.example", "kalmido.example"  # PUBLIC_URL of the test container
# outgoing mail switched on (the security mail kind is registered with it); nobody listens at the port: the rows stay
kt.fresh(env={"KALMIDO_SMTP_HOST": "127.0.0.1", "KALMIDO_SMTP_PORT": "1025", "KALMIDO_SMTP_TLS": "none",
              "KALMIDO_MAIL_FROM": "kalmido@example.test"}, prefix="P6354")
A = kt.setup()
FID, F = freelancer(B, A)


def dbx(q, args=()):
    c = dbxm.connect(os.path.join(DATA, "tasks.db"), timeout=10)
    try:
        r = c.execute(q, args).fetchall() if q.lstrip().upper().startswith(("SELECT", "WITH")) else c.execute(q, args)
        c.commit()
        return r
    finally:
        c.close()


def mails(uid):
    """The security mails queued for uid (bg_jobs, its payload is sealed: counted, the subject is checked in p2266_api's way)."""
    return dbx("SELECT count(*) FROM bg_jobs WHERE kind='mail:security' AND user_id=?", (uid,))[0][0]


def b64u(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def totp(secret):
    key = base64.b32decode(secret + "=" * (-len(secret) % 8))
    mac = hmac.new(key, struct.pack(">Q", int(time.time() // 30)), hashlib.sha1).digest()
    o = mac[-1] & 15
    return str((struct.unpack(">I", mac[o:o + 4])[0] & 0x7FFFFFFF) % 10 ** 6).zfill(6)


def cbor(v):
    def head(major, n):
        if n < 24:
            return bytes([major << 5 | n])
        for ai, fmt in ((24, ">B"), (25, ">H"), (26, ">I")):
            if n < 1 << (8 * struct.calcsize(fmt)):
                return bytes([major << 5 | ai]) + struct.pack(fmt, n)
    if isinstance(v, int):
        return head(0, v) if v >= 0 else head(1, -1 - v)
    if isinstance(v, bytes):
        return head(2, len(v)) + v
    if isinstance(v, str):
        return head(3, len(v.encode())) + v.encode()
    return head(5, len(v)) + b"".join(cbor(k) + cbor(x) for k, x in v.items())


def passkey_cred(opts):
    """A software passkey (ES256, attestation none) for the registration options opts (as in twofa_test.py)."""
    n = ec.generate_private_key(ec.SECP256R1()).public_key().public_numbers()
    cid = os.urandom(32)
    cose = cbor({1: 2, 3: -7, -1: 1, -2: n.x.to_bytes(32, "big"), -3: n.y.to_bytes(32, "big")})
    cd = json.dumps({"type": "webauthn.create", "challenge": opts["challenge"], "origin": ORIGIN, "crossOrigin": False}).encode()
    auth = hashlib.sha256(RP.encode()).digest() + bytes([0x45]) + struct.pack(">I", 0) + b"\0" * 16 + struct.pack(">H", len(cid)) + cid + cose
    att = cbor({"fmt": "none", "attStmt": {}, "authData": auth})
    return {"id": b64u(cid), "rawId": b64u(cid), "type": "public-key",
            "response": {"clientDataJSON": b64u(cd), "attestationObject": b64u(att), "transports": ["internal"]}, "clientExtensionResults": {}}


def ways(uid):
    """What a session could have left behind: counts / marks of the access rows of uid."""
    r = dbx("SELECT ical_token_hash IS NOT NULL, drop_token_hash IS NOT NULL FROM users WHERE id=?", (uid,))[0]
    return {"apppw": dbx("SELECT count(*) FROM app_passwords WHERE user_id=?", (uid,))[0][0],
            "tokens": dbx("SELECT count(*) FROM api_tokens WHERE user_id=?", (uid,))[0][0],
            "evfeed": dbx("SELECT count(*) FROM ev_cal_feeds WHERE user_id=?", (uid,))[0][0],
            "absfeed": dbx("SELECT count(*) FROM abs_cal_feeds WHERE user_id=?", (uid,))[0][0],
            "ical": bool(r[0]), "drop": bool(r[1])}


def leave_ways(s, uid, tag):
    """A session leaves every kind of link behind: an app password, an API token, the task feed, an event calendar's feed,
    the absences feed (row: its route needs the team module) and the upload token."""
    check(s.post(B + "/api/me/app-passwords", json={"name": "Phone " + tag}).status_code == 201, f"{tag}: an app password")
    check(s.post(B + "/api/me/tokens", json={"name": "Script " + tag, "scopes": ["read"]}).status_code == 201, f"{tag}: an API token")
    check(s.post(B + "/api/ical", json={"action": "rotate"}).ok, f"{tag}: the task feed link")
    cal = s.post(B + "/api/evcals", json={"name": "Termine " + tag, "org_id": None})
    check(cal.ok, f"{tag}: an own event calendar {cal.text[:120]}")
    check(s.post(B + f"/api/evcals/{cal.json()['id']}/feed", json={"action": "create"}).ok, f"{tag}: its feed link")
    dbx("INSERT INTO abs_cal_feeds(user_id, secret, secret_hash, created_at) VALUES(?, '', ?, now()) ON CONFLICT (user_id) DO NOTHING",
        (uid, hashlib.sha256(tag.encode()).hexdigest()))
    check(s.post(B + "/api/me/drop-token").ok, f"{tag}: the upload token")
    w = ways(uid)
    check(all(w.values()), f"{tag}: every way is there {w}")


# ================================================================ security mails for new ways in (frida, no organisation)
A.put(B + "/api/admin/agent-policy", json={"user_agents": True})  # personal agents on (the server's switch)
n0 = mails(FID)
check(F.post(B + "/api/me/tokens", json={"name": "Backup script", "scopes": ["read"]}).status_code == 201, "frida creates an API token")
check(mails(FID) == n0 + 1, "#6354: a mail about the new API token")
check(F.post(B + "/api/me/app-passwords", json={"name": "Thunderbird"}).status_code == 201, "frida creates an app password")
check(mails(FID) == n0 + 2, "#6354: a mail about the new app password")
r = F.post(B + "/api/me/2fa/totp", json={"password": "password123"})
check(r.ok, f"frida starts the authenticator app {r.text[:120]}")
r = F.post(B + "/api/me/2fa/totp/confirm", json={"code": totp(r.json()["secret"].replace(" ", ""))})
check(r.ok, f"frida switches the app codes on {r.text[:120]}")
check(mails(FID) == n0 + 3, "#6354: a mail about the app codes")
o = F.post(B + "/api/me/passkeys/options", json={"password": "password123"})
check(o.ok, f"passkey options {o.text[:120]}")
r = F.post(B + "/api/me/passkeys", json={"credential": passkey_cred(o.json()), "name": "Laptop"})
check(r.ok, f"frida adds a passkey {r.text[:160]}")
check(mails(FID) == n0 + 4, "#6354: a mail about the new passkey")
r = F.post(B + "/api/my/agents", json={"username": "frida-helper", "display_name": "Frida Helper"})
check(r.status_code == 201, f"frida makes a personal agent {r.text[:160]}")
AG = r.json()["id"]
check(mails(FID) == n0 + 5, "#6354: a mail about the agent's token (to frida)")
check(F.post(B + f"/api/my/agents/{AG}/token", json={}).ok, "frida makes a new token for the agent")
check(mails(FID) == n0 + 6, "#6354: and again for the new token")
check(not dbx("SELECT 1 FROM bg_jobs WHERE kind='mail:security' AND user_id=?", (AG,)), "#6354: the agent itself gets no mail")

# ================================================================ the own password change ends the links (tick set)
leave_ways(F, FID, "f1")
r = F.patch(B + "/api/me", json={"current_password": "password123", "password": "password456", "revoke_tokens": True})
check(r.ok, f"frida changes her password with the tick {r.text[:120]}")
w = ways(FID)
check(w == {"apppw": 0, "tokens": 0, "evfeed": 0, "absfeed": 0, "ical": False, "drop": False}, f"#6354: the tick ends every link {w}")
check(dbx("SELECT count(*) FROM webauthn_creds WHERE user_id=?", (FID,))[0][0] == 1, "passkeys stay (the dialog points to them)")
check(dbx("SELECT count(*) FROM api_tokens WHERE user_id=?", (AG,))[0][0] == 1, "the agent's token is the agent's: it stays")

# without the field (API): the safe default, the same
leave_ways(F, FID, "f2")
check(F.patch(B + "/api/me", json={"current_password": "password456", "password": "password789"}).ok, "frida changes it without the field")
w = ways(FID)
check(w == {"apppw": 0, "tokens": 0, "evfeed": 0, "absfeed": 0, "ical": False, "drop": False}, f"#6354: without the field too {w}")

# without the tick: they stay
leave_ways(F, FID, "f3")
check(F.patch(B + "/api/me", json={"current_password": "password789", "password": "password123", "revoke_tokens": False}).ok,
      "frida changes it without the tick")
w = ways(FID)
check(all(w.values()), f"#4375: without the tick every link stays {w}")

# ================================================================ the admin's reset and the reset link
r = A.post(B + "/api/users", json={"username": "gus", "display_name": "Gus", "password": "password123", "email": "gus@example.com"})
assert r.ok, r.text
GUS = r.json()["id"]
G = kt.sess("gus")
G.patch(B + "/api/settings", json={"lang": "en", "tour": "done"})
leave_ways(G, GUS, "g1")
check(A.patch(B + f"/api/users/{GUS}", json={"password": "password456"}).ok, "the admin resets gus's password")
w = ways(GUS)
check(w == {"apppw": 0, "tokens": 0, "evfeed": 0, "absfeed": 0, "ical": False, "drop": False}, f"#6354: the admin's reset ends every link {w}")

G = kt.sess("gus", pw="password456")
G.patch(B + "/api/settings", json={"lang": "en", "tour": "done"})
leave_ways(G, GUS, "g2")
r = A.post(B + f"/api/users/{GUS}/invite", json={"send": False})
link = (r.json().get("link") or "") if r.ok else ""
check("/#invite/" in link, f"a reset link for gus {r.text[:160]}")
tok = link.rsplit("/#invite/", 1)[-1]
s0 = requests.Session()
s0.headers.update(H)
r = s0.post(B + "/api/auth/invite/accept", json={"token": tok, "password": "password789"})
check(r.ok, f"gus sets a new password through the link {r.text[:160]}")
w = ways(GUS)
check(w == {"apppw": 0, "tokens": 0, "evfeed": 0, "absfeed": 0, "ical": False, "drop": False}, f"#6354: the reset link ends every link {w}")

raise SystemExit(kt.done("p6354_access_test"))
