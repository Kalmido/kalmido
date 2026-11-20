#!/usr/bin/env python3
# kalmido-suite: fresh
"""#6498 (audit #4800 F3, decision 16.11.2026): the second factor has its own count of wrong tries per account over 24 hours.
Invented names and documentation addresses only (RFC 5737), no SMTP server: the security mails are counted in bg_jobs.
freelancer-matrix: auth (bob is a person without an organisation)
 - an attacker with the password on many addresses (each below the pair limit): from the 3rd wrong code from an unknown address
   one security mail "2fa_fail" (once), at 20 a second one; afterwards an unknown address gets 429 twofa_locked right after
   the password, a known address (bob signed in from it before) still reaches the second step and signs in
 - an open second-step ticket ends with a new password set by an admin (the old ticket: 401 expired)
 - the second step after a reset link that came by mail passes the ceiling of the password's way (its own count; the address
   does not become known: afterwards the password alone from there is still refused, reader F1)
usage: p6498_twofa_day_test.py <datadir>      (KMT_NOSTART=1 / P6498_NOSTART=1: a running server)"""
import sys
import base64
import hashlib
import hmac
import struct
import time

import requests

import kt
from kt import B, H, check, dbx, done
from freelancer_fixture import freelancer

kt.fresh(env={"KALMIDO_SMTP_HOST": "127.0.0.1", "KALMIDO_SMTP_PORT": "1025", "KALMIDO_SMTP_TLS": "none",
              "KALMIDO_MAIL_FROM": "kalmido@example.test", "KALMIDO_LOGIN_SLOW_S": "0"}, prefix="P6498")
A = kt.setup()
BOB, _ = freelancer(B, A, name="bob")
HOME = "198.51.100.10"  # bob's own address


def at(ip):
    s = requests.Session()
    s.headers.update({**H, "X-Forwarded-For": ip})
    return s


def totp(secret, step):
    key = base64.b32decode(secret + "=" * (-len(secret) % 8))
    mac = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    o = mac[-1] & 15
    return str((struct.unpack(">I", mac[o:o + 4])[0] & 0x7FFFFFFF) % 10 ** 6).zfill(6)


def mails():
    return dbx("SELECT count(*) FROM bg_jobs WHERE kind='mail:security' AND user_id=?", (BOB,))[0][0]


def password_step(s, pw="password123"):
    return s.post(B + "/api/auth/login", json={"username": "bob", "password": pw})


# bob signs in from home and switches the authenticator app on
Bh = at(HOME)
check(password_step(Bh).ok, "setup: bob signs in from home")
r = Bh.post(B + "/api/me/2fa/totp", json={"password": "password123"})
SEC = r.json()["secret"].replace(" ", "")
r = Bh.post(B + "/api/me/2fa/totp/confirm", json={"code": totp(SEC, int(time.time() // 30))})
check(r.ok and r.json().get("recovery_codes"), f"setup: the app is on {r.status_code} {r.text[:120]}")
CODES = list(r.json()["recovery_codes"])
m0 = mails()

# ---------------------------------------------------------------- the attacker: the password, wrong codes from many addresses
n, ip_i, sent3 = 0, 1, None
while n < 20:
    s = at(f"203.0.113.{ip_i}")
    ip_i += 1
    for _ in range(4):  # below the pair limit (5) of each address
        r = password_step(s)
        if not (r.ok and r.json().get("twofa")):
            break
        r = s.post(B + "/api/auth/2fa", json={"code": "000000"})
        check(r.status_code == 401, f"wrong code {n + 1}: 401 {r.status_code}")
        n += 1
        if n == 3:
            sent3 = kt.until(lambda: mails() > m0, 10)
        if n >= 20:
            break
check(sent3, "from the 3rd wrong code from an unknown address: a security mail")
check(kt.until(lambda: mails() == m0 + 2, 10), f"at the ceiling (20): a second mail, not one per try ({mails() - m0})")

r = password_step(at("203.0.113.200"))
check(r.status_code == 429 and r.json().get("twofa_locked") is True, f"ceiling: an unknown address gets 429 twofa_locked {r.status_code} {r.text[:160]}")
Bk = at(HOME)
r = password_step(Bk)
check(r.ok and r.json().get("twofa") is True, f"ceiling: bob's own address still reaches the second step {r.status_code} {r.text[:120]}")
r = Bk.post(B + "/api/auth/2fa", json={"recovery": CODES.pop()})
check(r.ok and Bk.get(B + "/api/state").ok, f"ceiling: bob signs in at home {r.status_code} {r.text[:120]}")

# ---------------------------------------------------------------- a new password ends the open ticket
Bt = at(HOME)
check(password_step(Bt).json().get("twofa") is True, "an open second step at home")
r = A.patch(B + f"/api/users/{BOB}", json={"password": "another-password-456"})
check(r.ok, f"the admin sets a new password {r.status_code} {r.text[:120]}")
r = Bt.post(B + "/api/auth/2fa", json={"recovery": CODES[-1]})
check(r.status_code == 401 and r.json().get("expired") is True, f"the ticket of the old password ended {r.status_code} {r.text[:120]}")

# ---------------------------------------------------------------- a reset link that came by mail makes its address known
r = A.post(B + f"/api/users/{BOB}/invite", json={"send": False})
link = r.json().get("link") or ""
check(r.ok and "#invite/" in link, f"a reset link {r.status_code} {r.text[:160]}")
tok = link.rsplit("/", 1)[-1]
dbx("UPDATE user_invites SET sent_at=now() WHERE user_id=?", (BOB,))  # as if it went out by mail
Bn = at("192.0.2.77")  # a new device
r = Bn.post(B + "/api/auth/invite/accept", json={"token": tok, "password": "third-password-789"})
check(r.ok and r.json().get("twofa") is True, f"reset from a new address: the second step follows {r.status_code} {r.text[:160]}")
r = password_step(at("192.0.2.77"), "third-password-789")
check(r.status_code == 429 and r.json().get("twofa_locked") is True, f"reset link: the address did not become known - the password alone from there is still refused {r.status_code} {r.text[:120]}")
r = Bn.post(B + "/api/auth/2fa", json={"recovery": CODES.pop()})
check(r.ok, f"reset link: its second step works despite the ceiling (a full sign-in: from now on the address is known) {r.status_code} {r.text[:160]}")
sys.exit(done("p6498_twofa_day"))
