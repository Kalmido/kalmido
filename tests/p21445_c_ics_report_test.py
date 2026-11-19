#!/usr/bin/env python3
# kalmido-suite: fresh
"""#6588 (audit #4808 T16): a calendar import loses nothing silently. Invented events only. freelancer-matrix: events
 - more than 5000 events in one file (IMPORT_MAX_EVENTS): the answer says it -- total 5003, skipped 3, limit 5000 (the app
   shows "5000 of 5003 events imported" in its report, static/js/calevents.js evImpReport); a file within the cap has no limit
 - a series Kalmido cannot keep (FREQ=HOURLY, a second RRULE, extra dates RDATE) stands with its title and the reason in
   warnings; it still comes in (a single event / the first rule / the regular dates) as before
 - an unreadable event (no DTSTART) is named with its title, not only counted in errors
 - importing the same file twice: the same warnings, no doubles; a plain file: warnings [] (nothing to show, the app toasts)
 - the agent route POST /api/v1/event-calendars/<id>/import answers the same fields
 - P4: a person without an organisation, the own calendar, the same
usage: p21445_c_ics_report_test.py <datadir>      (P21445CI_NOSTART=1: a running server)"""
import os
import sys

import requests

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
from freelancer_fixture import freelancer  # noqa: E402
from kt import B, check, docker_logs_on_first_fail, done, fresh, setup  # noqa: E402

docker_logs_on_first_fail()
fresh(prefix="P21445CI")
A = setup()
A.patch(B + "/api/settings", json={"lang": "en", "tour": "done", "features": "cal,events,contacts,comments"})


def ev(uid, title, start="20261201T090000Z", *extra):
    return ["BEGIN:VEVENT", f"UID:{uid}", "DTSTAMP:20261101T080000Z", f"SUMMARY:{title}"] + ([f"DTSTART:{start}"] if start else []) \
        + ["DURATION:PT1H", *extra, "END:VEVENT"]


def cal(*events):
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Example//Guard//EN"] + [x for e in events for x in e] + ["END:VCALENDAR"]
    return ("\r\n".join(lines) + "\r\n").encode()


def imp(s, cid, data, dry=False):
    r = s.post(B + f"/api/evcals/{cid}/import" + ("?dry=1" if dry else ""), files={"file": ("cal.ics", data, "text/calendar")})
    assert r.ok, r.text[:300]
    return r.json()


C = A.post(B + "/api/evcals", json={"name": "Imported"}).json()["id"]

# ---------------------------------------------------------------- the cap of 5000 events per import
BIG = cal(*[ev(f"big-{i}@example.com", f"Event {i}", f"2027{1 + i % 12:02d}{1 + i % 28:02d}T09{i % 60:02d}00Z") for i in range(5003)])
j = imp(A, C, BIG, dry=True)
check(j.get("total") == 5003 and j.get("skipped") == 3 and j.get("limit") == 5000 and j.get("created") == 5000,
      f"over the cap: total 5003, skipped 3, limit 5000 named in the answer {({k: v for k, v in j.items() if k != 'warnings'})}")
j = imp(A, C, cal(*[ev(f"small-{i}@example.com", f"Small {i}") for i in range(3)]), dry=True)
check(j.get("total") == 3 and "limit" not in j and j.get("skipped") == 0, f"within the cap: no limit in the answer {j}")

# ---------------------------------------------------------------- series Kalmido cannot keep, an unreadable event
FILE = cal(ev("hourly@example.com", "Hourly standup", "20261201T090000Z", "RRULE:FREQ=HOURLY;COUNT=3"),
           ev("two@example.com", "Two rules", "20261202T090000Z", "RRULE:FREQ=WEEKLY;COUNT=4", "RRULE:FREQ=DAILY;COUNT=2"),
           ev("rdate@example.com", "Board meeting", "20261203T090000Z", "RRULE:FREQ=MONTHLY;COUNT=3", "RDATE:20261224T090000Z"),
           ev("broken@example.com", "Broken thing", None),
           ev("plain@example.com", "Plain event", "20261204T090000Z"))
j = imp(A, C, FILE)
W = {(x["title"], x["reason"]) for x in j.get("warnings", [])}
check(j.get("created") == 4 and j.get("errors") == 1 and j.get("total") == 5, f"four came in, one unreadable {({k: v for k, v in j.items() if k != 'warnings'})}")
check(("Hourly standup", "Its repeat rule is not supported: imported as a single event") in W, f"an hourly series is named with its title {W}")
check(("Two rules", "It has a second repeat rule: only the first one is imported") in W, f"a second repeat rule is named {W}")
check(("Board meeting", "Its extra dates (RDATE) are not supported: only the regular dates are imported") in W, f"extra dates are named {W}")
check(("Broken thing", "The event could not be read and was not imported") in W, f"the unreadable event is named, not only counted {W}")
check(not any(t == "Plain event" for t, _ in W) and len(W) == 4, f"a plain event has no warning {W}")
occ = A.get(B + f"/api/events?from=2026-12-01&to=2026-12-31&calendar_id={C}").json().get("items", [])
eid = {x["title"]: x.get("eid") or x.get("id") for x in occ}
rr = {t: (A.get(B + f"/api/events/{e}").json().get("rrule") or "") for t, e in eid.items() if t in ("Hourly standup", "Board meeting")}
check(rr.get("Hourly standup") == "" and rr.get("Board meeting", "").startswith("FREQ=MONTHLY"),
      f"as before: the hourly one a single event, the monthly one a series {rr}")
j2 = imp(A, C, FILE)
check(j2.get("created") == 0 and j2.get("updated") == 4 and {(x["title"], x["reason"]) for x in j2.get("warnings", [])} == W,
      f"twice: no doubles, the same warnings {({k: v for k, v in j2.items() if k != 'warnings'})}")
j = imp(A, C, cal(ev("plain2@example.com", "Another plain event")))
check(j.get("warnings") == [] and j.get("created") == 1, f"a plain file: no warnings {j}")

# ---------------------------------------------------------------- the agent route
A.put(B + "/api/admin/agent-policy", json={"user_agents": True})
r = A.post(B + "/api/my/agents", json={"username": "calbot", "display_name": "Cal Bot", "scopes": ["read", "calendar"]})
check(r.ok, "setup: an agent " + r.text[:200])
AH = {"Authorization": "Bearer " + r.json().get("token", "")}
r = requests.post(B + "/api/v1/event-calendars", headers=AH, json={"name": "Bot calendar"})
check(r.status_code in (200, 201), f"setup: the agent's own calendar ({r.status_code} {r.text[:200]})")
AC = (r.json().get("data") or r.json()).get("id") if r.ok else 0
r = requests.post(B + f"/api/v1/event-calendars/{AC}/import", headers=AH, json={"ics": FILE.decode(), "dry_run": True})
check(r.ok and r.json().get("total") == 5 and len(r.json().get("warnings", [])) == 4, f"agent: the same answer ({r.status_code} {r.text[:200]})")

# ---------------------------------------------------------------- P4: a person without an organisation
FID, Fr = freelancer(B, A, features="cal,events")
FC = Fr.post(B + "/api/evcals", json={"name": "Own"}).json()["id"]
j = imp(Fr, FC, FILE)
check(j.get("created") == 4 and len(j.get("warnings", [])) == 4, f"freelancer: the same warnings in the own calendar {j}")

sys.exit(done("p21445_c_ics_report"))
