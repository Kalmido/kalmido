#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1302.0 (#6429): the limits of the recurrence expansion of calendar subscriptions (kalmido/calendars/subscriptions.py
cal_expand / _cal_sanitize), the one place every foreign calendar goes through (ICS link, CalDAV sync, adding one in the
web request). Own container (start.sh), the app's own functions in a probe; invented events only. The hostile inputs are
small, so a red run (the fix taken back) costs some ten seconds, not the machine. Each case measures its time.

 - the audit's input: DTSTART in the year 1000 with two RRULE:FREQ=DAILY;UNTIL=20200101 -- the rule ending before the
   window goes, nothing is walked (before: 370 000 dates per rule, kept in memory)
 - a rule from the year 1000 ending inside the window still shows its days there (the shift works with UNTIL)
 - two rules on one event: the first one counts
 - a rule that passes more than CAL_WALK_MAX dates before the window and cannot be shifted (MONTHLY;INTERVAL=7 with
   28 days a month) loses its recurrence; an ordinary monthly rule from 2000 stays
 - many events, each under the limit, together over CAL_WALK_TOTAL: "too complex"
 - RDATE: at most CAL_DATES_MAX values per event; EXDATE: values long before the window go first, so an EXDATE in the
   window behind 2000 old ones still counts
 - the time budget is checked between the series, not only per occurrence
 - an ordinary weekly rule from the year 1 still lands on its weekday
usage: p21302_c_calsub_limits_test.py <datadir>      (P21302C_NOSTART=1 = the server already runs)"""
import json
import os
import subprocess
import sys

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
import kt  # noqa: E402
from kt import CT, check  # noqa: E402

PROBE = r'''
import json, time, resource, types
from datetime import date, datetime, timedelta
from kalmido.core.config import app
from kalmido.calendars import subscriptions as subs

out = {}
today = subs.local_now().date()
w0 = today - timedelta(days=subs.CAL_BACK_DAYS)


def ymd(d):
    return d.strftime("%Y%m%d")


def cal(*events):
    return ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//test//limits//EN\r\n" + "".join(events) + "END:VCALENDAR\r\n").encode()


def ev(uid, start, *lines):
    return ("BEGIN:VEVENT\r\nUID:" + uid + "\r\nDTSTAMP:20260101T000000Z\r\n" + start + "\r\n" + "".join(x + "\r\n" for x in lines)
            + "SUMMARY:" + uid + "\r\nEND:VEVENT\r\n")


def run(key, data):
    """[result, seconds, MB of new peak memory]: result = {uid: occurrences, "_trunc": bool} or "CalError:<code>"."""
    rss0 = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    t0 = time.monotonic()
    try:
        evs, trunc, _name = subs.cal_expand([data])
        r = {"_trunc": trunc}
        for e in evs:
            r[e["uid"]] = r.get(e["uid"], 0) + 1
    except subs.CalError as e:
        r = "CalError:" + e.code
    except Exception as e:  # noqa: BLE001  (shown as a red case, the other cases still run)
        r = type(e).__name__ + ":" + str(e)[:200]
    out[key] = [r, round(time.monotonic() - t0, 3), round((resource.getrusage(resource.RUSAGE_SELF).ru_maxrss - rss0) / 1024, 1)]

with app.test_request_context("/", headers={"Accept-Language": "en"}):
    # the audit's input (two events of it; the audit's file carries 20 000)
    run("attack", cal(*[ev(f"old-{i}", "DTSTART;VALUE=DATE:10000101", "RRULE:FREQ=DAILY;UNTIL=20200101", "RRULE:FREQ=DAILY;UNTIL=20200101")
                        for i in range(2)]))
    # from the year 1000, ending 5 days into the window: those days (6) are shown; the second rule is left
    run("until_in_window", cal(ev("upto", "DTSTART;VALUE=DATE:10000101", f"RRULE:FREQ=DAILY;UNTIL={ymd(w0 + timedelta(days=5))}",
                                  "RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR,SA,SU")))
    # two rules on one event, both inside the window: the first one counts (3 dates, before: 3 + 5 - 1)
    run("two_rules", cal(ev("two", "DTSTART;VALUE=DATE:" + ymd(today - timedelta(days=10)), "RRULE:FREQ=WEEKLY;COUNT=3", "RRULE:FREQ=DAILY;COUNT=5")))
    # 28 dates a month every 7th month from the year 1000: about 49 000 dates before the window, no 400-year shift (4800 % 7)
    days = ",".join(str(i) for i in range(1, 29))
    run("walk_cap", cal(ev("walk", "DTSTART;VALUE=DATE:10000101", f"RRULE:FREQ=MONTHLY;INTERVAL=7;BYMONTHDAY={days}"),
                        ev("monthly", "DTSTART;VALUE=DATE:20000115", "RRULE:FREQ=MONTHLY")))
    # many small walks together: 20 yearly series from 1900 (about 125 dates before the window each) over a total of 1000
    yearly = cal(*[ev(f"y-{i}", "DTSTART;VALUE=DATE:1900" + f"{1 + i % 12:02d}10", "RRULE:FREQ=YEARLY") for i in range(20)])
    keep = getattr(subs, "CAL_WALK_TOTAL", None)  # None: the code before 2.1302.0 (the red run)
    subs.CAL_WALK_TOTAL = 1000
    try:
        run("walk_total", yearly)
    finally:
        subs.CAL_WALK_TOTAL = keep
    run("walk_total_default", yearly)
    # RDATE: 3000 dates in the window (30 lines of 100), the event's own start besides
    st = datetime(today.year, today.month, today.day, 10)
    lines = ["RDATE:" + ",".join((st + timedelta(hours=1 + 100 * k + i)).strftime("%Y%m%dT%H%M%SZ") for i in range(100)) for k in range(30)]
    run("rdates", cal(ev("rd", "DTSTART:" + st.strftime("%Y%m%dT%H%M%SZ"), *lines)))
    # EXDATE: 2000 dates of the year 2000 first, then one in the window
    d0 = today - timedelta(days=30)
    old = ["EXDATE;VALUE=DATE:" + ",".join(ymd(date(2000, 1, 1) + timedelta(days=100 * k + i)) for i in range(100)) for k in range(20)]
    run("exdates", cal(ev("ex", "DTSTART;VALUE=DATE:" + ymd(d0), "RRULE:FREQ=DAILY;COUNT=20", *old, "EXDATE;VALUE=DATE:" + ymd(d0 + timedelta(days=2)))))
    # the time budget between the series: the clock runs out once the library has the calendar
    clk = [0.0]
    real_time, real_rie = subs.time, subs.recurring_ical_events

    def of(*a, **kw):
        q = real_rie.of(*a, **kw)
        clk[0] = subs.CAL_CPU_S + 1
        return q
    subs.time = types.SimpleNamespace(monotonic=lambda: clk[0], time=real_time.time)
    subs.recurring_ical_events = types.SimpleNamespace(of=of)
    try:
        run("series_time", cal(*[ev(f"s-{i}", "DTSTART;VALUE=DATE:" + ymd(today + timedelta(days=i))) for i in range(3)]))
    finally:
        subs.time, subs.recurring_ical_events = real_time, real_rie
    # an ordinary weekly rule from the year 1 (shifted, still on Mondays: 0001-01-01 is a Monday)
    run("ancient_weekly", cal(ev("anc", "DTSTART;VALUE=DATE:00010101", "RRULE:FREQ=DAILY;INTERVAL=7")))
    out["window"] = [w0.isoformat(), today.isoformat()]
print(json.dumps(out))
'''

kt.fresh(prefix="P21302C")
kt.setup()

r = subprocess.run(["docker", "exec", "-i", CT, "python", "-"], input=PROBE, capture_output=True, text=True, encoding="utf-8", timeout=900)
check(r.returncode == 0, "#6429 the probe runs in the app container " + r.stderr[-1500:])
P = json.loads(r.stdout.strip().splitlines()[-1]) if r.returncode == 0 else {}
print("measured:", json.dumps(P)[:3000])
FAST = 2.0   # seconds per case (the audit's input took several seconds per rule before)
MEM = 60     # MB of new peak memory per case


def got(key, fast=FAST, mem=MEM):
    res, secs, mb = P.get(key) or ["missing", 99, 0]
    check(secs < fast and mb < mem, f"#6429 {key}: within {fast} s and {mem} MB ({secs} s, {mb} MB)")
    return res


# the audit's input, two events: before the fix 0.8 s and 22 MB (on the Mac), i.e. about 0.2 s and 5 MB per rule -- a file of
# 20 000 such events meant hours and some 100 GB; with the fix nothing is walked (0.002 s)
res = got("attack", 0.3, 8)
check(res == {"_trunc": False}, f"#6429 DTSTART 1000 with two DAILY rules ending 2020: no date walked, nothing in the window ({res})")
res = got("until_in_window")
check(isinstance(res, dict) and res.get("upto") == 6, f"#6429 a rule from the year 1000 ending 5 days into the window: those 6 days, the second rule left ({res})")
res = got("two_rules")
check(isinstance(res, dict) and res.get("two") == 3, f"#6429 two rules on one event: the first one counts, 3 dates ({res})")
res = got("walk_cap")
check(isinstance(res, dict) and "walk" not in res, f"#6429 49 000 dates before the window: the recurrence goes, the first date (year 1000) is outside ({res})")
check(isinstance(res, dict) and 13 <= res.get("monthly", 0) <= 15, f"#6429 an ordinary monthly rule from 2000 stays ({res})")
res = got("walk_total")
check(res == "CalError:too_complex", f"#6429 20 yearly series from 1900 over a total of 1000 dates: too complex ({res})")
res = got("walk_total_default")
check(isinstance(res, dict) and len([k for k in res if k.startswith("y-")]) == 20, f"#6429 ... under the real total all 20 series show ({res})")
res = got("rdates")
check(isinstance(res, dict) and res.get("rd") in (1000, 1001), f"#6429 3000 RDATE values: at most 1000 kept, plus the start ({res})")
res = got("exdates")
check(isinstance(res, dict) and res.get("ex") == 19, f"#6429 an EXDATE in the window behind 2000 old ones still counts: 19 of 20 ({res})")
res = got("series_time")
check(res == {"_trunc": True}, f"#6429 the time budget is checked before each series: cut off before the first one ({res})")
res = got("ancient_weekly")
check(isinstance(res, dict) and 50 <= res.get("anc", 0) <= 62, f"#6429 DAILY;INTERVAL=7 from the year 1 still expands cheaply ({res})")

sys.exit(kt.done("p21302_c_calsub_limits"))
