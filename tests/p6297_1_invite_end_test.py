#!/usr/bin/env python3
# kalmido-suite:
"""#6297 point 1 (audits #4741, #4818, #6007): an organisation invitation (also into the role admin) ends with the admin right
of whoever made it -- through the one way accounts/invite.py invite_void (kind 'org', accounts/orginvite.py ojn_by_void) and
the test of accepting (OJN_BY: the inviter is still an active admin or an instance admin). One container (start.sh, mode
workspaces); invented names only (example.com).
 - demoted (role change): carl's invitation rows go, the invited person sees none and accepting answers 404
 - a right that ends on a way without the hook (a row changed by hand): accepting checks the inviter itself (OJN_BY)
 - locked: the instance admin disables carl -> his invitations end (USER_LOCKED)
 - a new password: carl changes his own password -> his invitations end (ses_access_end, PW_VOID)
 - left: carl leaves the organisation -> his invitation cannot be accepted any more
 - someone joins as admin: every other admin gets a News item (orgjoinres, admin_join)
 - audit #4818 (b): the instance admin adds the invited person directly and removes her: no invitation row is left to come
   back by; leaving takes an old row of the person along
 - audit #4818 (c): a demotion of an admin waits for the organisation's row (FOR UPDATE) and counts the admins after it
usage: p6297_1_invite_end_test.py <datadir>"""
import os
import subprocess
import sys
import threading

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
import kt  # noqa: E402
import dbx as dbxm  # noqa: E402
from freelancer_fixture import org_join  # noqa: E402
from kt import B, DATA, check, dbx, sess, until  # noqa: E402

A = kt.setup()
ids = {}
for u in ("bob", "carl", "dora", "erna", "gerda", "hanna", "ida", "jana"):
    r = A.post(B + "/api/users", json={"username": u, "display_name": u.title(), "password": kt.PASSWORD, "email": f"{u}@example.com"})
    assert r.ok, r.text
    ids[u] = r.json()["id"]
BOB, CARL, DORA, ERNA, GERDA, HANNA, IDA, JANA = (ids[u] for u in ("bob", "carl", "dora", "erna", "gerda", "hanna", "ida", "jana"))
r = A.post(B + "/api/admin/orgs", json={"name": "Alpha", "admin_id": BOB})
assert r.status_code == 201, r.text
ORG = r.json()["id"]
dbx("DELETE FROM org_members WHERE org_id=? AND user_id<>?", (ORG, BOB))
kt.proved()  # an organisation admin invites by address only an account that proved it
Bo = sess("bob")


def joins(user, pw=kt.PASSWORD):
    return [j["org_id"] for j in sess(user, pw).get(B + "/api/orgs").json().get("joins", [])]


def invite(s, email, role="member"):
    return s.put(B + f"/api/orgs/{ORG}/members", json={"email": email, "role": role}).ok


def closed(user, what):
    check(ORG not in joins(user) and sess(user).post(B + f"/api/orgs/{ORG}/join").status_code == 404,
          f"{what}: the invitation of {user} is not listed and accepting answers 404")


def listed_state(email):
    return {x.get("email"): x.get("state") for x in Bo.get(B + f"/api/orgs/{ORG}/invites").json().get("invites", [])}.get(email)


def by_carl():
    return dbx("SELECT COUNT(*) FROM org_joins WHERE org_id=? AND created_by=?", (ORG, CARL))[0][0]


def carl_admin():
    check(Bo.put(B + f"/api/orgs/{ORG}/members", json={"user_id": CARL, "role": "admin"}).ok, "setup: carl is an admin")


# ---- an admin joins: the other admins hear of it
check(invite(Bo, "carl@example.com", "admin") and org_join(B, "carl", ORG), "setup: carl joins Alpha as admin")
news = dbx("SELECT data FROM notifications WHERE user_id=? AND kind='orgjoinres' ORDER BY id", (BOB,))
check(news and '"yes": true' in news[-1][0].lower(), f"bob (the inviter) hears that carl accepted {news}")
Ca = sess("carl")
check(invite(Ca, "hanna@example.com", "admin") and org_join(B, "hanna", ORG), "setup: carl invites hanna as admin, she accepts")
told = dbx("SELECT data FROM notifications WHERE user_id=? AND kind='orgjoinres' AND data::text LIKE '%admin_join%'", (BOB,))
check(len(told) == 1 and str(ORG) in told[0][0], f"(news) bob, the other admin, is told that hanna joined as an admin {told}")
check(not dbx("SELECT 1 FROM notifications WHERE user_id=? AND kind='orgjoinres' AND data::text LIKE '%admin_join%'", (CARL,)),
      "(news) carl, who invited her, gets only his answer")
check(Bo.put(B + f"/api/orgs/{ORG}/members", json={"user_id": HANNA, "role": "member"}).ok, "setup: hanna becomes a member")

# ---- demoted: the invitations end
check(invite(Ca, "dora@example.com") and ORG in joins("dora"), "(demote) carl (admin) invites dora: her invitation is open")
check(Bo.put(B + f"/api/orgs/{ORG}/members", json={"user_id": CARL, "role": "member"}).ok, "(demote) bob makes carl a member")
closed("dora", "(demote)")
check(by_carl() == 0, "(demote) carl's invitation rows ended (no inviter any more)")
check(listed_state("dora@example.com") == "expired", f"(F9 demote) dora's row stays in the list as expired, like any {listed_state('dora@example.com')}")

# ---- a right that ends on a way without the hook: accepting checks the inviter itself (OJN_BY)
carl_admin()
check(invite(Ca, "erna@example.com") and ORG in joins("erna"), "(by hand) carl invites erna")
dbx("UPDATE org_members SET role='member' WHERE org_id=? AND user_id=?", (ORG, CARL))
closed("erna", "(by hand) carl no admin (row changed directly)")
dbx("UPDATE org_members SET role='admin' WHERE org_id=? AND user_id=?", (ORG, CARL))
check(org_join(B, "erna", ORG), "(by hand) carl admin again: erna accepts (only the inviter's right closed it)")

# ---- locked: the invitations end (the instance admin manages the accounts of an organisation she is in: alice joins as member)
dbx("INSERT INTO org_members(org_id, user_id, role) VALUES(?, (SELECT id FROM users WHERE username='alice'), 'member')", (ORG,))
check(invite(Ca, "ida@example.com") and ORG in joins("ida"), "(lock) carl invites ida")
r = A.patch(B + f"/api/users/{CARL}", json={"disabled": True})
check(r.ok, f"(lock) the instance admin disables carl {r.status_code} {r.text[:300]}")
check(by_carl() == 0, "(lock) carl's invitation rows went")
closed("ida", "(lock)")
r = A.patch(B + f"/api/users/{CARL}", json={"disabled": False})
check(r.ok, f"(lock) carl unlocked again {r.status_code} {r.text[:300]}")
check(ORG not in joins("ida"), "(lock) unlocking brings no invitation back")

# ---- a new password (after a break-in): the invitations end
Ca = sess("carl")
check(invite(Ca, "jana@example.com", "admin") and ORG in joins("jana"), "(password) carl invites jana as admin")
NEWPW = kt.PASSWORD + "-neu"
r = Ca.patch(B + "/api/me", json={"password": NEWPW, "current_password": kt.PASSWORD})
check(r.ok, f"(password) carl changes his password {r.status_code} {r.text[:200]}")
check(by_carl() == 0, "(password) carl's invitation rows went")
closed("jana", "(password)")
Ca = sess("carl", NEWPW)

# ---- Leser #6120 F1: the invitation of a NEW account (org_invites row) ends for good as well - a new password or a lock and
# unlock of the inviter, then the link: no way in; the row stays listed without inviter, resending makes the resender its inviter
import hashlib  # noqa: E402


def fresh(s, email, role="admin"):
    r = s.post(B + f"/api/orgs/{ORG}/invites", json={"email": email, "role": role})
    check(r.ok, f"(F1) setup: a new account for {email} invited as {role} {r.status_code} {r.text[:200]}")
    return dbx("SELECT id FROM users WHERE lower(email)=?", (email,))[0][0]


def plant(uid, tok):  # the mailed link's token is only stored hashed: the test sets its own
    dbx("UPDATE user_invites SET token_hash=? WHERE user_id=?", (hashlib.sha256(tok.encode()).hexdigest(), uid))


def accept(tok, s=None):
    return (s or sess(None)).post(B + "/api/auth/invite/accept", json={"token": tok, "password": kt.PASSWORD + "-x"})


KIM = fresh(Ca, "kim@example.com", "member")  # a member: the admin count of (1c) below stays
plant(KIM, "f1kim" + "k" * 30)
# reader job/6130 F9: carl's silent invitation of an existing account and a neutral row (its account deleted) - set as
# org_member_put / ojn_neutral leave them (a silent one needs an organisation of its own and an account carl may not see)
r = A.post(B + "/api/users", json={"username": "lotte", "display_name": "Lotte", "password": kt.PASSWORD, "email": "lotte@example.com"})
assert r.ok, r.text
dbx("INSERT INTO org_joins(org_id,user_id,role,created_by,created_at,silent,email) VALUES(?,?,?,?,now(),true,?)",
    (ORG, r.json()["id"], "member", CARL, "lotte@example.com"))
dbx("INSERT INTO org_joins(org_id,user_id,role,created_by,created_at,silent,email) VALUES(?,NULL,?,?,now(),true,?)",
    (ORG, "member", CARL, "gone@example.com"))


NEWPW2 = NEWPW + "2"
check(Ca.patch(B + "/api/me", json={"password": NEWPW2, "current_password": NEWPW}).ok, "(F1 password) carl changes his password again")
check(dbx("SELECT created_by FROM org_joins WHERE org_id=? AND user_id=?", (ORG, KIM))[0][0] is None,
      "(F1 password) the new account's row lost its inviter (created_by NULL)")
check(accept("f1kim" + "k" * 30).status_code == 404, "(F1 password) the new account's link is ended: setting up answers 404")
check(any(x.get("email") == "kim@example.com" for x in Bo.get(B + f"/api/orgs/{ORG}/invites").json().get("invites", [])),
      "(F1 password) the other admins still see the row in the list")
ST = {e: listed_state(e) for e in ("kim@example.com", "lotte@example.com", "gone@example.com", "jana@example.com")}
check(set(ST.values()) == {"expired"}, f"(F9) a new account's, a silent, a neutral and an ordinary row stand alike in the list - "
      f"nothing tells which address has an account {ST}")
check(dbx("SELECT COUNT(*) FROM org_joins WHERE org_id=? AND silent AND created_by IS NULL", (ORG,))[0][0] == 2,
      "(F9) the silent and the neutral row lost their inviter, they stay")
ref = [x["ref"] for x in Bo.get(B + f"/api/orgs/{ORG}/invites").json()["invites"] if x.get("email") == "kim@example.com"][0]
check(Bo.post(B + f"/api/orgs/{ORG}/invites/{ref}/resend").ok, "(F1 resend) bob sends it again")
check(dbx("SELECT created_by FROM org_joins WHERE org_id=? AND user_id=?", (ORG, KIM))[0][0] == BOB, "(F1 resend) bob is its inviter now")
plant(KIM, "f1kim2" + "k" * 30)
K = sess(None)
r = accept("f1kim2" + "k" * 30, K)
check(r.ok and K.post(B + f"/api/orgs/{ORG}/join").ok, f"(F1 resend) the new link sets the account up and kim joins {r.status_code} {r.text[:200]}")
Ca = sess("carl", NEWPW2)
LENA = fresh(Ca, "lena@example.com")
plant(LENA, "f1lena" + "l" * 30)
check(A.patch(B + f"/api/users/{CARL}", json={"disabled": True}).ok and A.patch(B + f"/api/users/{CARL}", json={"disabled": False}).ok,
      "(F1 lock) the instance admin locks and unlocks carl")
check(accept("f1lena" + "l" * 30).status_code == 404, "(F1 lock) after the lock the new account's link answers 404, unlocking brings it not back")
check(dbx("SELECT created_by FROM org_joins WHERE org_id=? AND user_id=?", (ORG, LENA))[0][0] is None, "(F1 lock) the row has no inviter")
Ca = sess("carl", NEWPW2)

# ---- left: the invitation cannot be accepted
check(invite(Ca, "jana@example.com") and ORG in joins("jana"), "(leave) carl invites jana again")
check(Ca.delete(B + f"/api/orgs/{ORG}/members/{CARL}").ok, "(leave) carl leaves Alpha")
closed("jana", "(leave)")

# ---- (b) audit #4818: added directly and removed: no invitation left to come back by
check(invite(Bo, "gerda@example.com", "admin") and ORG in joins("gerda"), "(1b) bob invites gerda as admin")
check(A.patch(B + f"/api/admin/orgs/{ORG}", json={"members_add": [GERDA]}).ok, "(1b) the instance admin adds gerda directly")
check(dbx("SELECT COUNT(*) FROM org_joins WHERE org_id=? AND user_id=?", (ORG, GERDA))[0][0] == 0, "(1b) her invitation row went with the adding")
check(A.patch(B + f"/api/admin/orgs/{ORG}", json={"members_remove": [GERDA]}).ok, "(1b) the instance admin removes gerda")
check(sess("gerda").post(B + f"/api/orgs/{ORG}/join").status_code == 404 and not dbx(
      "SELECT 1 FROM org_members WHERE org_id=? AND user_id=?", (ORG, GERDA)), "(1b) gerda cannot come back as admin by the old invitation")
dbx("INSERT INTO org_joins(org_id,user_id,role,created_by,created_at) VALUES(?,?,'admin',?,now())", (ORG, ERNA, BOB))
check(sess("erna").delete(B + f"/api/orgs/{ORG}/members/{ERNA}").ok, "(1b) erna leaves Alpha")
check(dbx("SELECT COUNT(*) FROM org_joins WHERE org_id=? AND user_id=?", (ORG, ERNA))[0][0] == 0
      and sess("erna").post(B + f"/api/orgs/{ORG}/join").status_code == 404, "(1b) leaving took her invitation row along (no way back)")

# ---- (c) audit #4818: a demotion of an admin locks the organisation's row before counting the admins
check(Bo.put(B + f"/api/orgs/{ORG}/members", json={"user_id": HANNA, "role": "admin"}).ok, "(1c) setup: hanna is an admin again")
dbc, dbn = dbxm._target(DATA)
hold = subprocess.Popen(["docker", "exec", "-i", dbc, "psql", "-U", "kalmido", "-d", dbn, "-X", "-q", "-A", "-t"], stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
hold.stdin.write(f"BEGIN;\nSELECT id FROM orgs WHERE id={int(ORG)} FOR UPDATE;\n\\echo held\n")
hold.stdin.flush()
check(until(lambda: hold.stdout.readline().strip() == "held", 30), "(1c) a second session holds Alpha's row")
res = {}
t = threading.Thread(target=lambda: res.update(r=sess("hanna").put(B + f"/api/orgs/{ORG}/members", json={"user_id": HANNA, "role": "member"})))
t.start()


def waiting():
    return dbx("SELECT 1 FROM pg_stat_activity WHERE wait_event_type='Lock' AND query LIKE '%FROM orgs WHERE id=% FOR UPDATE%' "
               "AND query NOT LIKE '%pg_stat_activity%'") or ("r" in res)


check(until(waiting, 30) and "r" not in res, "(1c) hanna stepping down waits for the organisation's row (no count without it)")
hold.stdin.write("COMMIT;\n")
hold.stdin.close()
hold.wait(30)
t.join(60)
check("r" in res and res["r"].ok, f"(1c) after the other session ends, the demotion goes through ({res.get('r') and res['r'].status_code})")
check(Bo.put(B + f"/api/orgs/{ORG}/members", json={"user_id": BOB, "role": "member"}).status_code == 409,
      "(1c) bob, now the only admin, cannot step down (counted after the lock)")

sys.exit(kt.done("p6297_1_invite_end"))
