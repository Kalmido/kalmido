#!/usr/bin/env python3
"""2.281.0 D (#3118): a backup keeps no transaction open while pg_dump and the ZIP run. The test container cuts idle
transactions after 1.5 s (KALMIDO_TEST_BK_IDLE_TX_MS) and delays the ZIP step by 4 s (KALMIDO_TEST_BK_ZIP_DELAY): without
the rollback before the dump the bookkeeping fails ("io"), with it the backup counts as done and bk_last_ok is set.
2.1265.0 (#6383): the same over the schedule's path (backup_tick): the loop's own connection gets the short limit too; the
day marker is set and the next tick makes no second backup; a marker that cannot be written holds the schedule for an hour.
freelancer-matrix: backup (instance-wide admin function, no organisation involved)
usage: p2281_f_backup_test.py <datadir>"""
import os
import subprocess
import sys
import time

import dbx as dbxm
from kt import FAILS, OKS, check, sess

N = os.path.dirname(os.path.abspath(__file__))
DATA = sys.argv[1]
B = "http://127.0.0.1:" + os.environ.get("KALMIDO_TEST_PORT", "3048")

env = dict(os.environ, KALMIDO_ADMIN_ALERTS="1",
           EXTRA=" ".join(["-e KALMIDO_BACKUP_TICK=1", "-e KALMIDO_BACKUPS=1", "-e KALMIDO_TEST_BK_IDLE_TX_MS=1500",
                           "-e KALMIDO_TEST_BK_ZIP_DELAY=4", "-e KALMIDO_TEST_BK_MARK_FAIL=/data/bk-mark-fail"]))
r = subprocess.run(["bash", os.path.join(N, "start.sh"), DATA], env=env, capture_output=True, text=True)
assert r.returncode == 0, r.stdout + r.stderr
assert sess().post(B + "/api/auth/setup", json={"username": "alice", "display_name": "Alice", "password": "password123"}).ok
A = sess("alice")
r = A.post(B + "/api/admin/backups")
check(r.status_code == 202, f"back up now accepted ({r.status_code})")
j = {}
t0 = time.time()
while time.time() - t0 < 60:  # until the run has ended with a result
    j = A.get(B + "/api/admin/backups").json()
    if not j["running"] and (j["items"] or j["last_error"]):
        break
    time.sleep(0.3)
check(not j.get("last_error"), f"no error recorded: {j.get('last_error')}")
check(bool(j.get("last_ok")) and len(j.get("items", [])) == 1, "bk_last_ok set and the backup is listed")


# ---- 2.1265.0 (#6383): the scheduled backup (backup_tick), not "Back up now"
def dbx(sql, args=()):
    c = dbxm.connect(os.path.join(DATA, "tasks.db"), timeout=10)
    try:
        r = c.execute(sql, args).fetchall()
        c.commit()
        return r
    finally:
        c.close()


def mark():
    return dbx("SELECT value FROM settings WHERE key='bk_last_day'")[0][0] or ""


def autos():
    return [x for x in A.get(B + "/api/admin/backups").json()["items"] if x["kind"] == "auto"]


def wait_autos(n, t=60):
    t0 = time.time()
    while time.time() - t0 < t:  # until the n-th scheduled backup is written and nothing runs any more
        j = A.get(B + "/api/admin/backups").json()
        if not j["running"] and len([x for x in j["items"] if x["kind"] == "auto"]) >= n:
            return
        time.sleep(0.3)


# A backup takes over 4 s (ZIP delay), the tick is 1 s: one quiet window of 7 s spans several ticks after a backup.
QUIET = 7
r = A.patch(B + "/api/admin/backups", json={"on": True, "time": "00:00"})
check(r.ok and r.json()["on"], "schedule on (time already passed today)")
dbx("UPDATE settings SET value='' WHERE key='bk_last_day'")  # as if the day had just begun: the next tick backs up
wait_autos(1)
check(len(autos()) == 1, f"the scheduled backup ran ({len(autos())})")
t0 = time.time()
while not mark() and time.time() - t0 < 10:  # the marker follows the backup within its tick
    time.sleep(0.3)
day = mark()
check(bool(day), "day marker set although the backup ran longer than the idle limit of the loop's connection")
time.sleep(QUIET)
check(len(autos()) == 1, f"no second scheduled backup on the next ticks ({len(autos())})")

# the marker cannot be written although the backup is there: the next try waits an hour
open(os.path.join(DATA, "bk-mark-fail"), "w").close()
dbx("UPDATE settings SET value='' WHERE key='bk_last_day'")
wait_autos(2)
check(len(autos()) == 2, f"the next scheduled backup ran ({len(autos())})")
time.sleep(QUIET)
check(mark() == "", "the marker stays unwritten (test hook)")
check(len(autos()) == 2, f"still no further scheduled backup within the hour ({len(autos())})")
os.remove(os.path.join(DATA, "bk-mark-fail"))

print(f"\n{OKS[0]} ok, {len(FAILS)} failed")
sys.exit(1 if FAILS else 0)
