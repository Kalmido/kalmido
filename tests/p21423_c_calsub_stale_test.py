#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1423.0 (#6551): a calendar subscription that could not be fetched for more than a day (CAL_STALE_S since its last
success) is "out of date". The owner decision (16.11.2026): a warning mark at the calendar and its events with "as of", one
push; the old events stay and still count as busy (rather busy than booked twice). Own container (start.sh), checked as a
person without an organisation (tests/freelancer_fixture.py); invented rows only.

 - a subscription that fails but succeeded 23 h ago: not out of date, nothing told
 - its last success 25 h back, the sync before still within the day: the next failed sync makes it out of date ->
   GET /api/calendars says stale, the events answer marks the calendar (stale + synced_at), one News item + one push
   (event "integration") naming the calendar and "as of"
 - the next failed sync tells nothing again (once per outage)
 - its events stay: the events answer still has them, free / busy still counts them, the booking page settings name it
 - a success ends it (stale false, no mark)
freelancer-matrix: pim
usage: p21423_c_calsub_stale_test.py <datadir>      (P21423CS_NOSTART=1 = the server already runs)"""
import json
import os
import subprocess
import sys

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
import kt  # noqa: E402
from kt import B, CT, DATA, check, dbx  # noqa: E402
from freelancer_fixture import freelancer  # noqa: E402

kt.fresh(prefix="P21423CS", env={"KALMIDO_CALENDAR_REFRESH_GAP": "0"})
A = kt.setup()
FID, Fr = freelancer(B, A)
A.patch(B + f"/api/users/{FID}", json={"ntfy_topic": "t-frida"})


def py(code):
    r = subprocess.run(["docker", "exec", "-i", CT, "python", "-"], input=code, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-1500:]
    return r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""


def add_sub(hours_ok, hours_tried):
    """A failing ICS subscription of frida (its link is refused at once: a loopback address) whose last success lies
    hours_ok back and whose last failed try hours_tried back, with one event today 07:00-07:15 UTC."""
    return int(py(f"""
from datetime import timedelta
from kalmido.core.db import connect, iso, now_utc, local_now
from kalmido.calendars.subscriptions import cal_seal
c = connect()
now = now_utc()
c.execute("INSERT INTO cal_subs(user_id,kind,name,color,visible,interval,url,url_hint,username,password,status,error,fails,synced_at,tried_at,created_at) "
          "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
          ({FID}, 'ics', 'Club fixtures', '#f5b041', 1, 60, cal_seal(c, {FID}, 'https://127.0.0.1:9/club.ics'), 'https://127.0.0.1/...', '', '',
           'error', 'network', 1, iso(now - timedelta(hours={hours_ok})), iso(now - timedelta(hours={hours_tried})), iso(now - timedelta(days=30))))
sid = c.execute('SELECT MAX(id) FROM cal_subs').fetchone()[0]
d = local_now().date().isoformat()
c.execute("INSERT INTO cal_events(sub_id,uid,title,all_day,start,\\"end\\",d0,d1) VALUES(?,?,?,?,?,?,?,?)",
          (sid, 'club-1', 'Club match', 0, d + 'T07:00:00Z', d + 'T07:15:00Z', d, d))
c.execute("UPDATE cal_subs SET events=1 WHERE id=?", (sid,))
c.commit(); c.close()
print(sid)"""))


def told(sid):
    return [r[0] for r in dbx("SELECT data FROM notifications WHERE user_id=? AND kind='integfail'", (FID,))
            if json.loads(r[0] or "{}").get("sub_id") == sid]


def pushes():
    try:
        return [json.loads(x) for x in open(os.path.join(DATA, "ntfy.log"), encoding="utf-8")
                if x.strip() and json.loads(x).get("topic") == "t-frida" and "more than a day" in x]
    except FileNotFoundError:
        return []


def sub_of(sid):
    return next((s for s in Fr.get(B + "/api/calendars").json()["subs"] if s["id"] == sid), {})


TODAY = py("from kalmido.core.db import local_now\nprint(local_now().date().isoformat())")

# ---- failing, but the last success only 23 h back: not out of date
young = add_sub(23, 1)
r = Fr.post(B + f"/api/calendars/{young}/refresh")
check(r.ok and r.json()["status"] == "error" and r.json().get("stale") is False, f"23 h since the last success: not out of date ({r.text[:200]})")
check(told(young) == [], "nothing told for it")

# ---- 25 h back, the try before was still within the day: this failure makes it out of date, told once
sid = add_sub(25, 1.5)
r = Fr.post(B + f"/api/calendars/{sid}/refresh")
check(r.ok and r.json()["status"] == "error" and r.json().get("stale") is True, f"25 h since the last success: out of date ({r.text[:200]})")
t = told(sid)
check(len(t) == 1 and "Club fixtures" in t[0] and "as of" in t[0] and "still count as busy" in t[0], f"one News item naming it, as of when ({t})")
p = kt.until(pushes, 15) or []
check(len(p) == 1 and "Club fixtures" in p[0]["msg"], f"one push ({p})")
r = Fr.post(B + f"/api/calendars/{sid}/refresh")
check(r.ok and r.json().get("stale") is True and len(told(sid)) == 1, f"the next failure tells nothing again ({len(told(sid))})")
check(len(pushes()) == 1, f"still one push ({len(pushes())})")

# ---- the view marks it; its events stay and still block
j = Fr.get(B + "/api/calendars/events", params={"from": TODAY, "to": TODAY}).json()
mark = j.get("subs", {}).get(str(sid), {})
check(mark.get("stale") is True and mark.get("synced_at"), f"the events answer marks the calendar, with its last success ({mark})")
check(not j.get("subs", {}).get(str(young), {}).get("stale"), "the young one carries no mark")
check(any(e.get("sub") == sid and e["title"] == "Club match" for e in j.get("events", [])), "its event is still there")
fb = Fr.get(B + "/api/events/freebusy", params={"day": TODAY, "users": str(FID), "tz": "UTC"})
slots = (fb.json().get("people") or [{}])[0].get("slots", []) if fb.ok else []
check(any(s["start"] <= "07:00" and s["end"] >= "07:15" for s in slots), f"free / busy still counts it as busy ({fb.status_code} {slots})")
ap = Fr.get(B + "/api/appt/page")
check(ap.ok and [x["name"] for x in ap.json().get("stale_subs", [])] == ["Club fixtures"], f"the booking page settings name it ({ap.text[:300]})")

# ---- a success ends it
py(f"""from kalmido.core.db import connect
c = connect()
c.execute("UPDATE cal_subs SET status='ok', error='', fails=0, synced_at=tried_at WHERE id=?", ({sid},))
c.commit(); c.close()""")
check(sub_of(sid).get("stale") is False, "fetched again: no longer out of date")
j = Fr.get(B + "/api/calendars/events", params={"from": TODAY, "to": TODAY}).json()
check("stale" not in j.get("subs", {}).get(str(sid), {}), "and no mark in the view")

sys.exit(kt.done("p21423_c_calsub_stale"))
