#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1271.0 (#6420): a user name of megabytes never sits in the failure counters of the sign-in. Invented accounts only.
 - the sign-in (POST /api/auth/login) and the cancelling of an account deletion (POST /api/auth/delete-cancel) with a name of
   the length the JSON limit lets through (10 MB live), several times: 401, and every counter key of the process stays short (the name is cut to 64 characters and
   kept as a hash only, accounts/session.py rate_name); a name that differs only after character 64 counts as the same
   name, so the pair lock (5 failures of one name at one address) still trips at the 6th try
 - over HTTP: a 1 MB name gets 401 like any wrong name, the server answers the next request
 - the pair lock of a real name still holds (5 failures -> 429 at that address, another address signs in), also for a
   person without an organisation (freelancer fixture)
 - the clean-up of idle counters runs by time (at least every 60 s), not only above 20,000 keys
freelancer-matrix: n/a (area auth; the freelancer's sign-in is checked here too)
usage: p6420_rate_name_test.py <datadir>"""
import json
import os
import subprocess
import sys
import time

import requests

import kt
from kt import B, CT, check, done, sess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from freelancer_fixture import freelancer  # noqa: E402

H = {"X-Requested-With": "kalmido"}


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


def login(user, pw, ip):
    return requests.post(B + "/api/auth/login", json={"username": user, "password": pw}, headers={**H, "X-Forwarded-For": ip})


kt.fresh()
A = kt.sess(None)
assert A.post(B + "/api/auth/setup", json={"username": "alice", "display_name": "Alice", "password": "password123"}).ok
A = sess("alice")
A.post(B + "/api/admin/setup", json={"org_name": "Alpha", "lang": "en", "modules": ["comments"]})
r = A.post(B + "/api/users", json={"username": "bob", "display_name": "Bob", "password": "password123"})
assert r.ok, r.text
FID, Fr = freelancer(B, A)

# ---- in one process: the routes with a name as long as the JSON limit allows, then a look into the process's counters
KEYS = """
import json
from kalmido.core.config import app as fl
from kalmido.accounts import session as S
from kalmido.core.jsonlimit import jl_cap
big = "x" * (jl_cap("POST", "{route}") - 4096)  # as long as the JSON limit lets through (core/jsonlimit.py; 10 MiB live)
out = {{"codes": [], "size": len(big)}}
cl = fl.test_client()
for i in range({n}):
    r = cl.post("{route}", json={{"username": big + str(i), "password": "wrong-pass"}},
                headers={{"X-Requested-With": "kalmido"}}, environ_base={{"REMOTE_ADDR": "{ip}"}})
    out["codes"].append(r.status_code)
out["longest"] = max([len(k) for k in S._fails] + [len(k) for k in S._known] + [0])
out["keys"] = len(S._fails)
with fl.test_request_context("/", environ_base={{"REMOTE_ADDR": "{ip}"}}):
    out["key_len"] = max(len(k) for k, _ in S._rate_keys(big))
print(json.dumps(out))
"""
for route, ip in (("/api/auth/login", "203.0.113.41"), ("/api/auth/delete-cancel", "203.0.113.42")):
    q = py(KEYS.format(route=route, n=6, ip=ip))
    codes = q.get("codes") or []
    check(codes[:5] == [401] * 5, f"#6420: {route}: 5 tries with a name of {q.get('size', 0) // 1024} KB: 401 each {codes}")
    # the names differ only after character 64: one name for the counters, so the pair lock trips at the 6th
    check(codes[5:] == [429], f"#6420: {route}: the names are cut to 64 characters: the 6th try is refused (pair lock) {codes}")
    check(0 < q.get("longest", 10 ** 9) < 120 and q.get("key_len", 10 ** 9) < 120,
          f"#6420: {route}: every counter key stays short (longest {q.get('longest')}, _rate_keys {q.get('key_len')})")
    check(q.get("keys", 99) <= 3, f"#6420: {route}: 6 tries of one cut name = the three keys of one name ({q.get('keys')})")

# ---- over HTTP: a 1 MB name is just a wrong name; the server goes on
r = login("y" * (1024 * 1024), "wrong-pass", "203.0.113.43")
check(r.status_code == 401, f"#6420: a name of 1 MB over HTTP: 401 ({r.status_code} {r.text[:80]})")
check(login("alice", "password123", "203.0.113.43").status_code == 200, "#6420: the next sign-in from there works")

# ---- the pair lock of a real name still holds (also for a person without an organisation)
for who in ("bob", "frida"):
    codes = [login(who, "wrong-pass", "203.0.113.44").status_code for _ in range(5)]
    r = login(who, "password123", "203.0.113.44")
    check(codes == [401] * 5 and r.status_code == 429, f"#6420: {who}: 5 failures at one address -> refused there {codes} {r.status_code}")
    check(login(who, "password123", "198.51.100.44").status_code == 200, f"#6420: {who}: another address signs in")

# ---- the clean-up by time: few keys, one of them idle for longer than the window, the last sweep over 60 s ago
SWEEP = """
import json, time
from kalmido.accounts import session as S
now = time.time()
S._fails.clear()
S._fails["p6420:idle"] = [now - S.FAIL_WINDOW - 5]
S._fails["p6420:fresh"] = [now - 10]
S._fails_swept[0] = now - 30
S._rate_fail([("p6420:new1", 5)])
early = sorted(S._fails)
S._fails_swept[0] = now - getattr(S, "_FAILS_SWEEP_S", 60) - 1
S._rate_fail([("p6420:new2", 5)])
print(json.dumps([early, sorted(S._fails), len(S._fails) < S._FAILS_MAX]))
"""
q = py(SWEEP)
check(isinstance(q, list) and len(q) == 3 and "p6420:idle" in q[0] and q[2],
      f"#6420: within the minute after a sweep nothing is swept (few keys) {q}")
check(isinstance(q, list) and len(q) == 3 and "p6420:idle" not in q[1] and "p6420:fresh" in q[1] and "p6420:new2" in q[1],
      f"#6420: a minute later the idle key is forgotten although there are far fewer than 20,000 keys {q}")

subprocess.run(["docker", "rm", "-f", CT], capture_output=True)
sys.exit(done("p6420_rate_name"))
