#!/usr/bin/env python3
# kalmido-suite: fresh
"""#6499 (audit #4800 F4, decision 16.11.2026): a new way into the account confirms the sign-in once more, the first second factor
ends the own API tokens and app passwords, a new personal token ends after 90 days unless "never" is chosen. Invented names only.
freelancer-matrix: tokens (a person without an organisation: the same confirmation for her token)
 - a fresh sign-in (a few minutes old) creates a token as before; without expires_days it ends after 90 days, null = never
 - an old session (the open computer): POST /api/me/tokens, wider rights for a token (a scope, all projects), an app password,
   a personal agent, its new token and a setup code answer 403 password_needed and store nothing; a wrong password 403; with the
   current password they work; a new name or fewer rights need nothing
 - an account without a password and an old session: 403 reauth_needed
 - switching on the authenticator app the first time: the own API tokens and app passwords end (an agent's token stays)
usage: p6499_creator_reauth_test.py <datadir>      (KMT_NOSTART=1 / P6499_NOSTART=1: a running server)"""
import sys
import base64
import hashlib
import hmac
import struct
import time
from datetime import datetime, timedelta, timezone

from kt import B, check, dbx, done, fresh, me_id, sess, setup
from freelancer_fixture import freelancer

OLD = "2020-01-01T00:00:00+00:00"
PW = "password123"

fresh(prefix="P6499")
A = setup()
A.put(B + "/api/admin/agent-policy", json={"user_agents": True, "max_per_user": 10})
ALICE = me_id(A)
FID, F = freelancer(B, A)


def age(uid):  # the session was opened long ago (the open computer, a stolen cookie)
    dbx("UPDATE sessions SET created_at=?, stepup_for='' WHERE user_id=?", (OLD, uid))


def toks(uid):
    return dbx("SELECT COUNT(*) FROM api_tokens WHERE user_id=?", (uid,))[0][0]


def days_left(j):
    return (datetime.fromisoformat(j["expires_at"].replace("Z", "+00:00")) - datetime.now(timezone.utc)) / timedelta(days=1)


# ---------------------------------------------------------------- a fresh sign-in: as before, the 90-day default
r = A.post(B + "/api/me/tokens", json={"name": "cli", "scopes": ["read"]})
check(r.status_code == 201 and r.json().get("expires_at") and 89 < days_left(r.json()) <= 90,
      f"fresh: a token without expires_days ends after 90 days {r.status_code} {r.text[:160]}")
r = A.post(B + "/api/me/tokens", json={"name": "forever", "scopes": ["read"], "expires_days": None})
check(r.status_code == 201 and r.json().get("expires_at") is None, f"fresh: expires_days null = never {r.text[:160]}")
T1 = r.json()["id"]
r = A.post(B + "/api/my/agents", json={"username": "alice-bot", "display_name": "Alice Bot"})
check(r.status_code == 201 and r.json().get("token"), f"fresh: a personal agent with its token {r.status_code} {r.text[:160]}")
AG = r.json()["id"]

# ---------------------------------------------------------------- an old session: the password once more
age(ALICE)
n0 = toks(ALICE)
r = A.post(B + "/api/me/tokens", json={"name": "late", "scopes": ["read", "tasks:write"]})
check(r.status_code == 403 and r.json().get("password_needed") is True and toks(ALICE) == n0,
      f"old session: a new token asks for the password, nothing stored {r.status_code} {r.text[:160]}")
r = A.post(B + "/api/me/tokens", json={"name": "late", "scopes": ["read"], "password": "wrong-password"})
check(r.status_code == 403 and toks(ALICE) == n0, f"old session: a wrong password 403 {r.status_code}")
r = A.post(B + "/api/me/tokens", json={"name": "late", "scopes": ["read"], "password": PW})
check(r.status_code == 201 and toks(ALICE) == n0 + 1, f"old session: with the password it works {r.status_code} {r.text[:160]}")
r = A.patch(B + f"/api/me/tokens/{T1}", json={"name": "renamed"})
check(r.ok, f"old session: a new name needs nothing {r.status_code}")
r = A.patch(B + f"/api/me/tokens/{T1}", json={"scopes": ["read", "tasks:write"]})
check(r.status_code == 403 and r.json().get("password_needed") is True, f"old session: a wider scope asks for the password {r.status_code}")
check(dbx("SELECT scopes FROM api_tokens WHERE id=?", (T1,)) == [("read",)], "old session: the scope stayed")
r = A.patch(B + f"/api/me/tokens/{T1}", json={"scopes": ["read", "tasks:write"], "password": PW})
check(r.ok and "tasks:write" in r.json().get("scopes", []), f"old session: with the password the scope is added {r.status_code}")
r = A.patch(B + f"/api/me/tokens/{T1}", json={"scopes": ["read"]})
check(r.ok, f"old session: fewer rights need nothing {r.status_code} {r.text[:120]}")
r = A.post(B + "/api/me/app-passwords", json={"name": "Telefon"})
check(r.status_code == 403 and r.json().get("password_needed") is True, f"old session: an app password asks for the password {r.status_code} {r.text[:120]}")
r = A.post(B + "/api/my/agents", json={"username": "late-bot", "display_name": "Late Bot"})
check(r.status_code == 403 and r.json().get("password_needed") is True and not dbx("SELECT 1 FROM users WHERE username='late-bot'"),
      f"old session: a personal agent asks for the password, none made {r.status_code}")
r = A.post(B + f"/api/my/agents/{AG}/token", json={})
check(r.status_code == 403 and r.json().get("password_needed") is True and toks(AG) == 1, f"old session: the agent's new token asks, the old one stays {r.status_code}")
r = A.post(B + f"/api/my/agents/{AG}/token", json={"password": PW})
check(r.ok and r.json().get("token"), f"old session: with the password the agent gets its new token {r.status_code}")
r = A.post(B + f"/api/my/agents/{AG}/setup-code", json={"os": "mac", "folder": "~/kalmido-agent"})
check(r.status_code == 403 and r.json().get("password_needed") is True, f"old session: a setup code asks for the password {r.status_code} {r.text[:120]}")
r = A.post(B + "/api/admin/agents", json={"username": "team-bot", "display_name": "Team Bot"})
check(r.status_code == 403 and r.json().get("password_needed") is True, f"old session: an admin's team agent asks for the password {r.status_code}")

# a person without an organisation: the same
age(FID)
r = F.post(B + "/api/me/tokens", json={"name": "frida", "scopes": ["read"]})
check(r.status_code == 403 and r.json().get("password_needed") is True, f"freelancer: old session, the password once more {r.status_code}")
r = F.post(B + "/api/me/tokens", json={"name": "frida", "scopes": ["read"], "password": PW})
check(r.status_code == 201, f"freelancer: with the password it works {r.status_code}")

# an account without a password: sign in again
dbx("UPDATE users SET password_hash=NULL WHERE id=?", (FID,))
r = F.post(B + "/api/me/tokens", json={"name": "frida2", "scopes": ["read"]})
check(r.status_code == 403 and r.json().get("reauth_needed") is True, f"no password: 403 reauth_needed {r.status_code} {r.text[:120]}")


# ---------------------------------------------------------------- the first second factor ends the own tokens and app passwords
def totp(secret, step):
    key = base64.b32decode(secret + "=" * (-len(secret) % 8))
    mac = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    o = mac[-1] & 15
    return str((struct.unpack(">I", mac[o:o + 4])[0] & 0x7FFFFFFF) % 10 ** 6).zfill(6)


A2 = sess("alice")  # a fresh sign-in
check(toks(ALICE) >= 3 and toks(AG) == 1, f"before: alice's tokens and her agent's ({toks(ALICE)}, {toks(AG)})")
dbx("INSERT INTO app_passwords(user_id,name,pw_hash,created_at,pw_ident) VALUES(?, 'Tablet', 'x', now(), 'p6499')", (ALICE,))
r = A2.post(B + "/api/me/2fa/totp", json={"password": PW})
sec = r.json()["secret"].replace(" ", "")
r = A2.post(B + "/api/me/2fa/totp/confirm", json={"code": totp(sec, int(time.time() // 30))})
check(r.ok, f"2FA on {r.status_code} {r.text[:120]}")
check(toks(ALICE) == 0 and not dbx("SELECT 1 FROM app_passwords WHERE user_id=?", (ALICE,)),
      f"2FA on: alice's API tokens and app passwords ended ({toks(ALICE)})")
check(toks(AG) == 1, "2FA on: her agent's token belongs to the agent and stays")
check(A2.get(B + "/api/state").ok, "2FA on: this session stays")
sys.exit(done("p6499_creator_reauth"))
