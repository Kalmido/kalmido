#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1271.0 (#6497): a support session ends with exactly the grant it was made through. Own container (start.sh, hosted with
KALMIDO_HOSTED=1, a server key). Invented accounts only (example.com); the client is a person without an organisation (P4).
 - the sign-in link carries the grant (user_invites.grant_id), the session inherits it (sessions.grant_id, via 'support')
 - a long grant ended early, then a short one: the session from the short one ends with the short one (not with the planned end
   of the long one); its end time passing without a click = 401
 - the operator loses the admin right between link and sign-in: the session is still a support session (positive list) and
   ending the grant ends it
 - a link whose grant is no longer open (ended, run out) signs nobody in (404); a new grant ends the sessions of the one before
 - from before grant_id: a support session / an operator's link without it no longer holds
freelancer-matrix: own
tenant-matrix: support
usage: p21271_b_support_test.py <datadir>"""
import os
import sys

import kt
from kt import B, check, sess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from freelancer_fixture import freelancer, login  # noqa: E402

KEY = "AQIDBAUGBwgJCgsMDQ4PEBESExQVFhcYGRobHB0eHyA="  # a test server key (32 bytes, base64)


def dbw(q, a=()):
    c = kt._dbx.connect(os.path.join(kt.DATA, "tasks.db"))
    try:
        c.execute(q, a)
        c.commit()
    finally:
        c.close()


kt.fresh(env={"KALMIDO_SECRET_KEY": KEY, "KALMIDO_HOSTED": "1"})
A = kt.sess(None)
assert A.post(B + "/api/auth/setup", json={"username": "alice", "display_name": "Alice", "password": "password123"}).ok
A = sess("alice")
A.post(B + "/api/admin/setup", json={"org_name": "Alpha", "lang": "en", "collab_all": True, "modules": ["comments"]})
A = sess("alice")
ALICE = kt.dbx("SELECT id FROM users WHERE username='alice'")[0][0]
FID, _Fr = freelancer(B, A)
F = login(B, "frida")
assert F.patch(B + "/api/settings", json={"lang": "en", "tour": "done"}).ok


def grant(hours):
    r = F.post(B + "/api/support-access", json={"hours": hours})
    assert r.ok, r.text
    return r.json()["grant"]["id"]


def link():
    r = A.post(B + f"/api/users/{FID}/signin-link")
    assert r.ok, r.text
    return r.json()["link"].split("#signin/")[1]


def sign_in(tok):
    x = kt.sess(None)
    return x, x.post(B + "/api/auth/link", json={"token": tok})


def end_in_db(gid, col="ends_at"):
    """The grant's end as a real state: set into the past in the database (no fixed waiting, no click)."""
    dbw(f"UPDATE support_grants SET {col}='2020-01-01T00:00:00Z' WHERE id=?", (gid,))


# ---- (a) a long grant ended early, then a short one: the session holds only the short one
G1 = grant(168)
check(F.delete(B + f"/api/support-access/{G1}").ok, "frida grants 7 days and ends it after a while")
G2 = grant(1)
T = link()
check(kt.dbx("SELECT grant_id FROM user_invites WHERE user_id=?", (FID,)) == [(G2,)], "the sign-in link carries the grant it was made through")
X, r = sign_in(T)
check(r.ok and X.get(B + "/api/state").ok, "the operator signs in with it " + r.text[:120])
check(kt.dbx("SELECT COUNT(*) FROM sessions t, support_grants s WHERE s.id=? AND t.user_id=? AND t.via='support' AND t.grant_id=s.id "
             "AND t.expires_at<=s.ends_at", (G2, FID)) == [(1,)], "the session is a support session of the short grant, ending with it at the latest")
end_in_db(G2)
check(X.get(B + "/api/state").status_code == 401, "the short grant's end passes without a click: the session answers 401 (not the long one's end)")
check(F.get(B + "/api/state").ok, "frida's own session stays")

# ---- (c) the operator loses the admin right between link and sign-in
G3 = grant(24)
T = link()
dbw("UPDATE users SET is_admin=FALSE WHERE id=?", (ALICE,))
X, r = sign_in(T)
dbw("UPDATE users SET is_admin=TRUE WHERE id=?", (ALICE,))
check(r.ok and X.get(B + "/api/state").ok, "the link still signs in " + r.text[:120])
check(kt.dbx("SELECT via, grant_id FROM sessions WHERE user_id=? AND grant_id IS NOT NULL", (FID,)) == [("support", G3)],
      "... as a support session of the grant (the mark follows the link's grant, not the maker's admin right today)")
r = X.post(B + "/api/me/tokens", json={"name": "ops"})
check(r.status_code == 403 and r.json().get("code") == "support_session", "... with the positive list: no token " + r.text[:120])
check(F.delete(B + f"/api/support-access/{G3}").ok and X.get(B + "/api/state").status_code == 401, "ending the grant ends that session")
check(not kt.dbx("SELECT 1 FROM sessions WHERE user_id=? AND via='support'", (FID,)), "... and its row is gone (no longer in the session list)")

# ---- a link whose grant is no longer open signs nobody in
G4 = grant(24)
T = link()
end_in_db(G4, "ended_at")  # ended in the database only: the link row stays, the check at the sign-in refuses it
X, r = sign_in(T)
check(r.status_code == 404 and X.get(B + "/api/state").status_code == 401, f"a link of an ended grant: invalid, no session {r.status_code}")
G5 = grant(24)
T = link()
end_in_db(G5)
X, r = sign_in(T)
check(r.status_code == 404, f"a link of a grant whose end time passed: invalid {r.status_code}")

# ---- a new grant ends the sessions of the one before (each session holds exactly its own grant)
G6 = grant(1)
X, r = sign_in(link())
check(r.ok and X.get(B + "/api/state").ok, "a support session of a 1-hour grant")
G7 = grant(168)
check(X.get(B + "/api/state").status_code == 401, "frida replaces the grant by a longer one: the session of the old one ends")
check(kt.dbx("SELECT COUNT(*) FROM support_grants WHERE id=? AND ended_at IS NOT NULL", (G6,)) == [(1,)], "... the old grant is ended")

# ---- from before grant_id: neither a support session nor an operator's link without it holds
X, r = sign_in(link())
check(r.ok and X.get(B + "/api/state").ok, "a support session of the open grant")
dbw("UPDATE sessions SET grant_id=NULL WHERE user_id=? AND via='support'", (FID,))
check(X.get(B + "/api/state").status_code == 401, "a support session without grant_id (made before 2.1271.0) no longer holds")
T = link()
dbw("UPDATE user_invites SET grant_id=NULL WHERE user_id=?", (FID,))
X, r = sign_in(T)
check(r.status_code == 404 and X.get(B + "/api/state").status_code == 401,
      f"an operator's link from before grant_id (made while a grant was open): invalid, never a full session {r.status_code}")
check(F.get(B + "/api/state").ok and F.delete(B + f"/api/support-access/{G7}").ok, "frida ends the last grant")
sys.exit(kt.done("p21271_b_support"))
