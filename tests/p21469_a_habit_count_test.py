#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1469.0 A (#6343): a habit's day count from two devices (kalmido/personal/habits.py habit_log). Invented names only.
 - the app sends the count it saw (prev) with the new count: when the day moved meanwhile (another device ticked), the server
   puts the step on top of the count now instead of overwriting it -- two +1 on prev=2 = 4, not 3
 - the answer carries the count now (the device shows it)
 - a step down on a stale prev takes one off the count now; never below 0
 - without prev (old clients, the API): as before, the count sent is the count
 - a person without an organisation (freelancer) uses it the same way (P4)
usage: p21469_a_habit_count_test.py <datadir>      (KMT_NOSTART=1 / P21469A_NOSTART=1: a running server)"""
import sys
from datetime import timedelta

import testclock

from freelancer_fixture import freelancer
from kt import B, check, done, fresh, setup

fresh(prefix="P21469A")
A = setup()
A.patch(B + "/api/settings", json={"lang": "en", "tour": "done", "features": "habits"})
FID, F = freelancer(B, A)
DAY = (testclock.today() - timedelta(days=1)).isoformat()  # yesterday: inside the state's 400 days


def habit(s, name, goal=8):
    r = s.post(B + "/api/habits", json={"name": name, "goal": goal})
    assert r.ok, r.text
    return r.json()["id"]


def count(s, hid):
    h = next(x for x in s.get(B + "/api/state").json()["habits"] if x["id"] == hid)
    return (h.get("logs") or {}).get(DAY, 0)


def log(s, hid, **b):
    return s.post(B + f"/api/habits/{hid}/log", json={"day": DAY, **b})


for who, s in (("admin", A), ("freelancer", F)):
    hid = habit(s, f"Water {who}")
    check(log(s, hid, count=2).ok and count(s, hid) == 2, f"{who}: an old client sets the count (no prev)")
    r1 = log(s, hid, count=3, prev=2)  # phone: saw 2, taps +1
    check(r1.ok and r1.json().get("count") == 3, f"{who}: the first +1 on 2 = 3 " + r1.text[:200])
    r2 = log(s, hid, count=3, prev=2)  # laptop: also saw 2, taps +1
    check(r2.ok and r2.json().get("count") == 4 and count(s, hid) == 4, f"{who}: the second +1 on the stale 2 = 4, not 3 " + r2.text[:200])
    r3 = log(s, hid, count=1, prev=2)  # a stale -1
    check(r3.ok and r3.json().get("count") == 3 and count(s, hid) == 3, f"{who}: a stale -1 takes one off the count now " + r3.text[:200])
    r4 = log(s, hid, count=0, prev=9)  # a stale "off" from far above: never below 0
    check(r4.ok and r4.json().get("count") == 0 and count(s, hid) == 0, f"{who}: never below 0 " + r4.text[:200])
    check(log(s, hid, count=5).ok and count(s, hid) == 5, f"{who}: without prev the count sent is the count")
    check(log(s, hid, note="tired").ok and count(s, hid) == 5, f"{who}: a note alone keeps the count")

sys.exit(done("p21469_a_habit_count"))
