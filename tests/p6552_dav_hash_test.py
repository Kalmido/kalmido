#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1271.0 (#6552): the CalDAV/CardDAV sign-in computes at most one password hash per request and refuses an address with
30 failures before any hash. Invented accounts only. Counted in a second process of the container (Flask test client,
check_password_hash of calendars/caldav.py wrapped by a counter), not by the clock:
 - a new app password has an id of 8 characters in front (app_passwords.pw_ident); it signs in with one hash, a second
   time without one (the cache of verified passwords)
 - one hash each for: an unknown name, a known name with 3 app passwords and a wrong password (an unknown id or the id of
   one of its rows), a known name with a password without an id but no old rows; an old app password without an id
   (made before 2.1271, pw_ident NULL) still signs in
 - 30 failures from one address with changing invented names: from then on 429 there without a hash; a name that synced
   from that address before still signs in there (#3111, office address with an old phone); another address is free
 - right after the update: a name known at that address under the old key of the shared table (name in clear, before
   2.1271) still signs in there (the known addresses are read under the old key until 20.12.2026)
 - a person without an organisation (freelancer fixture) signs in with an app password with an id
freelancer-matrix: n/a (area auth; the freelancer's app password is checked here too)
usage: p6552_dav_hash_test.py <datadir>"""
import json
import os
import re
import subprocess
import sys
import time

import kt
from kt import B, CT, check, done, sess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from freelancer_fixture import freelancer  # noqa: E402


def py(code):
    """Runs code in a second process of the container (no loops, role web); the last line of its output = JSON."""
    extra = []
    for k, v in {"TASKS_WATCHDOG": "0", "KALMIDO_ROLE": "web"}.items():
        extra += ["-e", f"{k}={v}"]
    for _try in range(3):  # the import may meet the running server's start-up DDL (deadlock): try again
        r = subprocess.run(["docker", "exec", "-w", "/app", *extra, CT, "python", "-c", "import app\n" + code],
                           capture_output=True, text=True)
        if "DeadlockDetected" not in r.stdout + r.stderr:
            break
        time.sleep(2)
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        print((r.stdout + r.stderr)[-2000:], flush=True)
        return {}


kt.fresh()
A = kt.sess(None)
assert A.post(B + "/api/auth/setup", json={"username": "alice", "display_name": "Alice", "password": "password123"}).ok
A = sess("alice")
A.post(B + "/api/admin/setup", json={"org_name": "Alpha", "lang": "en", "modules": ["comments"]})
PW = {}
for u in ("hana", "ivo", "kai", "lena"):
    r = A.post(B + "/api/users", json={"username": u, "display_name": u.title(), "password": "password123"})
    assert r.ok, r.text
FID, Fr = freelancer(B, A)
for u, n in (("hana", 3), ("kai", 1), ("lena", 1), ("frida", 1)):
    s_ = Fr if u == "frida" else sess(u)
    for i in range(n):
        r = s_.post(B + "/api/me/app-passwords", json={"name": f"Phone {i}"})
        assert r.status_code == 201, r.text
        PW.setdefault(u, []).append(r.json()["password"])
check(all(re.fullmatch(r"[a-z2-9]{8}(-[a-z2-9]{5}){4}", p) for ps in PW.values() for p in ps),
      f"#6552: a new app password: an id of 8 characters + 4 groups of 5 {PW['hana'][0]}")
ids = kt.dbx("SELECT pw_ident FROM app_passwords ORDER BY id")
check(len(ids) == 6 and all(x[0] and len(x[0]) == 8 for x in ids) and [x[0] for x in ids] == [p[:8] for u in ("hana", "kai", "lena", "frida") for p in PW[u]],
      f"#6552: the id is stored in clear (pw_ident), the rest only as a hash {ids}")

RUN = """
import base64, json
from werkzeug.security import generate_password_hash
from kalmido.core.config import app as fl
from kalmido.core.db import connect
from kalmido.core.pg import system_ctx
from kalmido.calendars import caldav as CD
CNT = [0]
orig = CD.check_password_hash
def counted(h, p):
    CNT[0] += 1
    return orig(h, p)
CD.check_password_hash = counted
# an app password made before 2.1271 (20 symbols, no id): written as the old code wrote it
c = connect()
with system_ctx(c):
    uid = c.execute("SELECT id FROM users WHERE username='ivo'").fetchone()[0]
    c.execute("INSERT INTO app_passwords(user_id,name,pw_hash,created_at) VALUES(?,?,?,?)",
              (uid, "Old phone", generate_password_hash("abcde" * 4), "2026-01-01T00:00:00+00:00"))
c.commit()
c.close()
cl = fl.test_client()
def go(user, pw, ip):
    h = {{"Authorization": "Basic " + base64.b64encode((user + ":" + pw).encode()).decode(), "Depth": "0"}}
    n0 = CNT[0]
    r = cl.open("/dav/", method="PROPFIND", headers=h, environ_base={{"REMOTE_ADDR": ip}}, base_url="https://localhost")
    return [r.status_code, CNT[0] - n0]
P = {pw}
other = "zzzzzzzz-" + P["hana"][0][9:]  # an id nobody has
wrong_same_id = P["hana"][0][:9] + "aaaaa-aaaaa-aaaaa-aaaaa"
out = {{}}
H1 = "203.0.113.61"
out["right"] = go("hana", P["hana"][0], H1)
out["right_again"] = go("hana", P["hana"][0], H1)
out["unknown_name"] = go("nobody-here", other, H1)
out["known_unknown_id"] = go("hana", other, H1)
out["known_same_id"] = go("hana", wrong_same_id, H1)
out["known_old_form"] = go("hana", "wrong-app-password", H1)
out["old_pw"] = go("ivo", "ABCDE-abcde-abcde-abcde", H1)
out["freelancer"] = go("frida", P["frida"][0], H1)
FLOOD = "203.0.113.62"
out["kai_before"] = go("kai", P["kai"][0], FLOOD)
# lena synced from FLOOD before the update: the shared table holds that under the key of 2.1270 (the name in clear)
from kalmido.core.ratedb import rate_known_add
from kalmido.accounts.session import rate_key_ip
rate_known_add("dav:uall:lena", rate_key_ip(FLOOD), 30)
out["flood"] = [go("inv%d" % i, "wrong-app-password", FLOOD) for i in range(30)]
out["after_unknown"] = go("inv-new", "wrong-app-password", FLOOD)
out["after_hana_right"] = go("hana", P["hana"][1], FLOOD)
out["after_kai"] = go("kai", P["kai"][0], FLOOD)
out["after_lena_old_key"] = go("lena", P["lena"][0], FLOOD)
out["other_address"] = go("hana", P["hana"][1], "198.51.100.62")
print(json.dumps(out))
"""
q = py(RUN.format(pw=json.dumps(PW)))
print(json.dumps({k: v for k, v in q.items() if k != "flood"}), flush=True)
check(q.get("right") == [207, 1] and q.get("right_again") == [207, 0],
      f"#6552: the right app password: one hash, then none (cache) {q.get('right')} {q.get('right_again')}")
for k, what in (("unknown_name", "an unknown name"), ("known_unknown_id", "a known name with 3 app passwords, an unknown id"),
                ("known_same_id", "a known name, the id of one of its rows, a wrong secret"),
                ("known_old_form", "a known name, a password without an id (no old rows)")):
    check(q.get(k) == [401, 1], f"#6552: {what}: 401 after exactly one hash {q.get(k)}")
check(q.get("old_pw") == [207, 1], f"#6552: an old app password without an id still signs in {q.get('old_pw')}")
check(q.get("freelancer") == [207, 1], f"#6552: a person without an organisation signs in with an app password {q.get('freelancer')}")
fl = q.get("flood") or []
check(q.get("kai_before") == [207, 1] and len(fl) == 30 and all(x == [401, 1] for x in fl),
      f"#6552: 30 wrong sign-ins with changing names from one address: 401 each {fl[:3]}...")
check(q.get("after_unknown") == [429, 0], f"#6552: then a new name from there: 429 without a hash {q.get('after_unknown')}")
check(q.get("after_hana_right") == [429, 0],
      f"#6552: ... also a real name with its right password that never synced from there {q.get('after_hana_right')}")
check(q.get("after_kai") == [207, 0], f"#3111: a name that synced from there before goes on (cached: no hash) {q.get('after_kai')}")
check(q.get("after_lena_old_key") == [207, 1],
      f"#6552 review: a name known there under the key from before 2.1271 (name in clear) still signs in {q.get('after_lena_old_key')}")
check(q.get("other_address") == [207, 1], f"#6552: another address is not affected {q.get('other_address')}")

subprocess.run(["docker", "rm", "-f", CT], capture_output=True)
sys.exit(done("p6552_dav_hash"))
