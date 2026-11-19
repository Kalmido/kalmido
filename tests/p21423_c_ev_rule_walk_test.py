#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1423.0 (#6727): the recurrence expansion of own events (kalmido/events/model.py ev_expand / is_occ / ev_rule) no
longer walks from a start in 1900 to the window. Own events (CalDAV PUT, ICS import, app) keep their rule and start;
dateutil walked every date from DTSTART (FREQ=DAILY from 1900: about 46 000 dates per series and per calendar query).
Own container (start.sh), the app's own functions in a probe; invented rows only. Each case measures its time, and its
dates are compared with the unmoved rule (the reference, outside the timing).

 - 100 timed daily series from 1900 (Europe/Berlin, the window crosses the end of summer time): same dates, fast
 - weekly every 2nd week on Monday + Thursday from 1900 (all day), daily from 1900 with UNTIL inside the window,
   an EXDATE in the window, yearly from 1900, monthly from 1900 (first Monday, every workday 100 times, the 31st by
   default, every 5th month, the last workday by BYSETPOS), every 3rd year on the first Monday of November, COUNT=9999
   from 2000 (never moved): all the same dates as the unmoved rule
 - is_occ of a daily series from 1900: a real date yes, another time no -- fast
 - a rule that cannot move and passes more than EV_WALK_MAX dates before the window (COUNT, the stop lowered to 100)
   shows only its extra date (RDATE) there
usage: p21423_c_ev_rule_walk_test.py <datadir>      (P21423C_NOSTART=1 = the server already runs)"""
import json
import os
import subprocess
import sys

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
import kt  # noqa: E402
from kt import CT, check  # noqa: E402

PROBE = r'''
import json, time, traceback
from datetime import date, datetime, timedelta
from kalmido.core.config import app
from kalmido.events import model as m

out = {}
LO, HI = date(2026, 10, 20), date(2026, 11, 10)  # the end of summer time (25.10.) inside


def row(start, end, rule, all_day=0, tz="Europe/Berlin", exdates="", extra=""):
    return {"id": 1, "start": start, "end": end, "rrule": rule, "all_day": all_day, "tz": tz, "exdates": exdates,
            "overrides": "[]", "extra": extra}


def ref(r):
    """occurrence keys of the unmoved rule inside [LO, HI] (local days) -- the walk the code made before 2.1423.0"""
    rule = m.ev_rule(r)
    if rule is None:
        raise ValueError(f"no rule: {r['rrule']} problem={m.rr_problem(r['rrule'])!r}")
    a = datetime(LO.year, LO.month, LO.day) - timedelta(days=3)
    if not r["all_day"]:
        a = a.replace(tzinfo=m.ev_zone(r["tz"]))
    ex = set(x for x in r["exdates"].split(",") if x)
    keys = []
    for dt in rule.xafter(a, inc=True):
        d = dt.date()
        if d > HI:
            break
        k = m.occ_key(r, dt)
        if d >= LO and k not in ex:
            keys.append(k)
    return keys


def run(key, r, n=1, compare=True):
    """[same dates as the reference (or the keys), seconds for n expansions]"""
    try:
        t0 = time.monotonic()
        for _ in range(n):
            got = [o["occ"] for o in m.ev_expand(r, LO, HI)]
        secs = round(time.monotonic() - t0, 3)
        out[key] = [(got == ref(r)) if compare else got, secs, len(got)]
    except Exception:  # noqa: BLE001  (shown as a red case, the other cases still run)
        out[key] = [traceback.format_exc()[-800:], 0, 0]

with app.test_request_context("/", headers={"Accept-Language": "en"}):
    run("daily_1900", row("1900-01-01T09:00", "1900-01-01T10:00", "FREQ=DAILY"), n=100)
    run("weekly2_1900", row("1900-01-01", "1900-01-02", "FREQ=WEEKLY;INTERVAL=2;BYDAY=MO,TH", all_day=1))
    run("until_1900", row("1900-01-01T18:30", "1900-01-01T19:00", "FREQ=DAILY;UNTIL=20261028"))
    run("exdate_1900", row("1900-01-01", "1900-01-02", "FREQ=DAILY", all_day=1, exdates="2026-10-30,2026-11-02"))
    run("yearly_1900", row("1900-10-25", "1900-10-26", "FREQ=YEARLY", all_day=1))
    run("monthly_1mo", row("1900-01-01T08:00", "1900-01-01T09:00", "FREQ=MONTHLY;BYDAY=1MO"))
    run("monthly_workdays", row("1900-01-01T08:00", "1900-01-01T17:00", "FREQ=MONTHLY;BYDAY=MO,TU,WE,TH,FR"), n=100)
    run("monthly_31", row("1900-01-31", "1900-02-01", "FREQ=MONTHLY", all_day=1))
    run("monthly_i5", row("1900-03-03T12:00", "1900-03-03T13:00", "FREQ=MONTHLY;INTERVAL=5"))
    run("monthly_last_wd", row("1900-01-31T16:00", "1900-01-31T17:00", "FREQ=MONTHLY;BYDAY=MO,TU,WE,TH,FR;BYSETPOS=-1"))
    run("yearly_i3", row("1903-11-02", "1903-11-03", "FREQ=YEARLY;INTERVAL=3;BYMONTH=11;BYDAY=1MO", all_day=1))
    run("count_2000", row("2000-01-01T07:00", "2000-01-01T07:30", "FREQ=DAILY;COUNT=9999"))
    # the walk stop (a COUNT rule cannot move; 9999 dates stay under the real stop, so the stop is lowered here)
    keep = getattr(m, "EV_WALK_MAX", None)
    m.EV_WALK_MAX = 100
    try:
        run("walk_cap", row("2000-01-01", "2000-01-02", "FREQ=DAILY;COUNT=9999", all_day=1, extra="RDATE;VALUE=DATE:20261104"),
            compare=False)
    finally:
        m.EV_WALK_MAX = keep
    r = row("1900-01-01T09:00", "1900-01-01T10:00", "FREQ=DAILY")
    t0 = time.monotonic()
    hits = [m.is_occ(r, "2026-11-02T09:00") for _ in range(50)] + [m.is_occ(r, "2026-11-02T10:00")]
    out["is_occ"] = [hits, round(time.monotonic() - t0, 3)]
    out["walk_max"] = getattr(m, "EV_WALK_MAX", None)
print(json.dumps(out))
'''

kt.fresh(prefix="P21423C")
kt.setup()

r = subprocess.run(["docker", "exec", "-i", CT, "python", "-"], input=PROBE, capture_output=True, text=True, encoding="utf-8", timeout=900)
check(r.returncode == 0, "#6727 the probe runs in the app container " + r.stderr[-1500:])
P = json.loads(r.stdout.strip().splitlines()[-1]) if r.returncode == 0 else {}
print("measured:", json.dumps(P)[:3000])
# 100 expansions of a daily series from 1900 took 4,4 s before on a fast test machine (0,044 s each, ten times that on a small server); moved, a few ms
FAST = 0.5


def got(key, fast=FAST):
    res, secs, n = P.get(key) or ["missing", 99, 0]
    check(secs < fast, f"#6727 {key}: within {fast} s ({secs} s)")
    return res, n


res, n = got("daily_1900")
check(res is True and n == 22, f"#6727 daily from 1900: the window's 22 days at 09:00 local time, as the unmoved rule ({res}, {n})")
for key, want in (("weekly2_1900", None), ("until_1900", 9), ("exdate_1900", 20), ("yearly_1900", 1), ("monthly_1mo", 1),
                  ("monthly_workdays", 16), ("monthly_31", 1), ("monthly_i5", 1), ("monthly_last_wd", 1), ("yearly_i3", 1),
                  ("count_2000", 22)):
    res, n = got(key)
    check(res is True and (want is None or n == want), f"#6727 {key}: the same dates as the unmoved rule ({res}, {n} dates)")
res, n = got("walk_cap")
check(res == ["2026-11-04"], f"#6727 a rule passing more than EV_WALK_MAX dates before the window: only its extra date ({res})")
hits, secs = P.get("is_occ") or [[], 99]
check(hits == [True] * 50 + [False] and secs < FAST, f"#6727 is_occ of a daily series from 1900: right and fast ({hits}, {secs} s)")
check(P.get("walk_max") == 10000, f"#6727 the walk stop is the documented one ({P.get('walk_max')})")

sys.exit(kt.done("p21423_c_ev_rule_walk"))
