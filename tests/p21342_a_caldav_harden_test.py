#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1342.0 (#6553): calendars and contacts, the hardening of audit #4804 C5-C9. Own container (start.sh), invented data;
everything as a person without an organisation (tests/freelancer_fixture.py).
freelancer-matrix: pim, personal
 - 1 a password (CalDAV, CardDAV) or a secret in the address of an ICS link never goes over http:// to a host no admin allowed:
   discover / add / change answer needs_https, a stored subscription fails with needs_https in its sync, cal_http itself
   refuses Basic auth over http; an allowed host and an ICS link without a secret over http stay as before
 - 2 an address book that keeps failing: one News item (integfail "carddav") at the third failure in a row, the admins'
   alert from the fifth; a write-back the server refuses for good names the contact in a News item (once per sync), a
   network error (tried again later) does not
 - 3 the absences link: only the SHA-256 of its secret is stored, the address is in the answer of create / rotate once
   (later url null, active since); a link stored in plain by an older version keeps working and is hashed at its first use
   or at the start (tkh_migrate); wrong tries count per rate_ip() (an IPv6 /64 is one counter)
 - 4 the server log of a failed contacts sync and of a task skipped in the task feed names the type of the error only,
   never its text (which can quote a card or a task)
usage: p21342_a_caldav_harden_test.py <datadir>"""
import hashlib
import json
import os
import subprocess
import sys
import urllib.parse

import requests

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
import kt  # noqa: E402
from kt import B, check, dbx, done  # noqa: E402
from freelancer_fixture import freelancer  # noqa: E402

kt.docker_logs_on_first_fail()
CT = os.environ.get("KALMIDO_TEST_CONTAINER", "kalmido-test")
kt.fresh(env={"KALMIDO_CALENDAR_ALLOW_HOSTS": "dav.allowed.test"}, prefix="P21342A")
A = kt.setup()
A.patch(B + "/api/settings", json={"lang": "en", "tour": "done", "features": "cal,events,family,contacts"})
FID, Fr = freelancer(B, A)


def py(code):
    """Python inside the app container -> the last JSON line it printed."""
    r = subprocess.run(["docker", "exec", "-i", "-w", "/app", CT, "python", "-"], input=code, capture_output=True, text=True, timeout=300)
    if r.returncode:
        print("PY FAILED:", r.stdout[-2000:], r.stderr[-3000:], flush=True)
    for ln in reversed((r.stdout or "").splitlines()):
        if ln.startswith("{"):
            return json.loads(ln)
    return {}


# ================================================================== 1: no password / secret link over plain http
LOGIN = {"username": "frida", "password": "dav-secret-6553"}
r = Fr.post(B + "/api/calendars/discover", json={"url": "http://dav.example.com/", **LOGIN})
check(r.status_code == 400 and r.json().get("code") == "needs_https" and "https://" in r.json().get("error", ""),
      f"1: CalDAV discovery over http:// to a public host: needs_https ({r.status_code} {r.text[:200]})")
r = Fr.post(B + "/api/calendars", json={"kind": "caldav", "url": "http://dav.example.com/", **LOGIN,
                                         "calendars": [{"url": "http://dav.example.com/cal/frida/work/", "name": "Home"}]})
check(r.status_code == 400 and r.json().get("code") == "needs_https", f"1: CalDAV subscription over http://: needs_https ({r.text[:200]})")
r = Fr.post(B + "/api/calendars", json={"kind": "ics", "url": "http://ics.example.com/feed/private-3f9a1c7e5b2d4f60a8c1/basic.ics"})
check(r.status_code == 400 and r.json().get("code") == "needs_https", f"1: an ICS link with a token in its path over http://: needs_https ({r.text[:200]})")
r = Fr.post(B + "/api/calendars", json={"kind": "ics", "url": "http://ics.example.com/cal.ics?token=abc"})
check(r.status_code == 400 and r.json().get("code") == "needs_https", f"1: an ICS link with a query over http://: needs_https ({r.text[:200]})")
r = Fr.post(B + "/api/calendars", json={"kind": "ics", "url": "http://ics.example.com/holidays/feiertage-2026.ics"})
check(r.status_code == 400 and r.json().get("code") != "needs_https", f"1: a plain ICS link without a secret keeps the old way ({r.text[:200]})")
r = Fr.post(B + "/api/family/contacts", json={"url": "http://dav.example.com/", **LOGIN})
check(r.status_code == 400 and r.json().get("code") == "needs_https", f"1: CardDAV over http://: needs_https ({r.status_code} {r.text[:200]})")
r = Fr.post(B + "/api/calendars/discover", json={"url": "http://dav.allowed.test/", **LOGIN})
check(r.status_code == 400 and r.json().get("code") != "needs_https", f"1: an allowed host over http:// is not refused for http ({r.text[:200]})")

j = py(r'''
import json, app
from kalmido.core.db import connect
from kalmido.calendars.subscriptions import CalError, cal_http, cal_seal, cal_sync, cal_url_secret
from kalmido.family.carddav import contacts_sync
c = connect()
out = {}
try:
    cal_http("http://dav.example.com/x", auth=("u", "p"))
except CalError as e:
    out["auth_http"] = e.code
try:
    cal_http("http://dav.allowed.test:1/x", auth=("u", "p"), allow=frozenset({("dav.allowed.test", None)}), timeout=2)
except CalError as e:
    out["auth_allowed"] = e.code
out["secret"] = [cal_url_secret(u) for u in ("https://x.org/a/private-3f9a1c7e5b2d4f60a8c1/basic.ics", "https://x.org/c.ics?export",
                                              "https://x.org/holidays/feiertage-2026.ics", "https://x.org/calendar/Germany_Holidays.ics",
                                              # 2.1342.0 (#6553, Gegenlesen #5177 F1): a token as the file name, a short one, letters only
                                              "http://x.org/3f9a1c7e5b2d4f60a8c1.ics", "http://x.org/feed/a1b2c3d4e5f6/cal.ics",
                                              "http://x.org/u/qwrtzpkdhgfmnbvcxyls/cal.ics", "http://x.org/calendar/basic.ics")]
uid = %d
def sub(kind, url, user="", pw=""):
    c.execute("INSERT INTO cal_subs(user_id,kind,name,color,visible,interval,url,url_hint,username,password,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
              (uid, kind, "Old " + kind, "#f5b041", 1, 60, cal_seal(c, uid, url), "http://x/…", user, cal_seal(c, uid, pw), "ok", "2026-01-01T00:00:00Z"))
    sid = c.execute("SELECT MAX(id) FROM cal_subs").fetchone()[0]
    c.commit()
    cal_sync(c, sid, force=True)
    return c.execute("SELECT error FROM cal_subs WHERE id=?", (sid,)).fetchone()[0]
out["sync_dav"] = sub("caldav", "http://dav.example.com/cal/frida/work/", "frida", "pw")
out["sync_ics"] = sub("ics", "http://ics.example.com/feed/private-3f9a1c7e5b2d4f60a8c1/basic.ics")
c.execute("INSERT INTO contact_srcs(user_id,name,url,url_hint,username,password,lead,created_at) VALUES(?,?,?,?,?,?,?,?)",
          (uid, "Old book", cal_seal(c, uid, "http://dav.example.com/card/"), "http://x/…", "frida", cal_seal(c, uid, "pw"), 7, "2026-01-01T00:00:00Z"))
src = c.execute("SELECT MAX(id) FROM contact_srcs").fetchone()[0]
c.commit()
contacts_sync(c, src)
out["sync_card"] = c.execute("SELECT error FROM contact_srcs WHERE id=?", (src,)).fetchone()[0]
c.execute("DELETE FROM contact_srcs WHERE id=?", (src,))
c.execute("DELETE FROM cal_subs WHERE user_id=?", (uid,))
c.commit()
print(json.dumps(out))
''' % FID)
check(j.get("auth_http") == "needs_https", f"1: cal_http sends no Basic auth over http:// to a host not allowed {j}")
check(j.get("auth_allowed") not in (None, "needs_https"), f"1: … to an allowed host it tries (and fails to connect here) {j}")
check(j.get("secret") == [True, True, False, False, True, True, True, False], f"1: a token in the path or a query counts as a secret, a file name not {j}")
check(j.get("sync_dav") == "needs_https" and j.get("sync_ics") == "needs_https" and j.get("sync_card") == "needs_https",
      f"1: a subscription / address book stored before fails clearly in its sync {j}")

# ================================================================== 2: a failing address book / a refused write-back
j = py(r"""
import json, app
from kalmido.core.db import connect
from kalmido.calendars.subscriptions import CalError, cal_seal
from kalmido.family import carddav as CD
c = connect()
alerts = []
CD.aa_now = lambda kind, key, *a, **k: alerts.append((kind, key))  # the admins' alert as queued (the watchdog sends it)
uid = %d
c.execute("INSERT INTO contact_srcs(user_id,name,url,url_hint,username,password,lead,created_at) VALUES(?,?,?,?,?,?,?,?)",
          (uid, "Club book", cal_seal(c, uid, "https://10.255.255.1/card/"), "https://10.255.255.1/…", "frida", cal_seal(c, uid, "pw"), 7, "2026-01-01T00:00:00Z"))
src = c.execute("SELECT MAX(id) FROM contact_srcs").fetchone()[0]
c.commit()
news = lambda what: [json.loads(d) for (d,) in c.execute("SELECT data FROM notifications WHERE user_id=? AND kind='integfail'", (uid,)).fetchall()
                     if json.loads(d).get("what") == what]
out = {"after": []}
for i in range(5):
    c.execute("UPDATE contact_srcs SET tried_at=NULL WHERE id=?", (src,))
    c.commit()
    CD.contacts_sync(c, src)
    out["after"].append([len(news("carddav")), len([q for q in alerts if q[0] == "integration" and q[1].startswith(f"carddav:{src}:")])])
out["fails"] = c.execute("SELECT fails, error FROM contact_srcs WHERE id=?", (src,)).fetchone()[:]
out["text"] = (news("carddav") or [{}])[0].get("text", "")
out["focus"] = (news("carddav") or [{}])[0].get("focus")
lid = 4242  # only stored in the News data (the project a click opens)
s = c.execute("SELECT * FROM contact_srcs WHERE id=?", (src,)).fetchone()
def wb(exc):
    def boom(*a, **k):
        raise exc
    CD._wb_write = boom
    ln = {"want": json.dumps({"mo": 5, "dy": 1}), "uid": "card-1", "kind": "birthday"}
    CD.contacts_writeback(c, s, ("frida", "pw"), frozenset(), [(ln, {"id": 0, "list_id": lid}, "https://10.255.255.1/card/b/1.vcf",
                          "https://10.255.255.1/card/b/", ("Erika Probe", 3, 15, None))], set(), "en")
    return news("carddav_wb")
out["net"] = len(wb(CalError("network")))
got = wb(CalError("weak_etag"))
out["wb"] = [len(got), got[-1].get("text", "") if got else "", got[-1].get("list") if got else None, lid]
c.execute("DELETE FROM contact_srcs WHERE id=?", (src,))
c.execute("DELETE FROM notifications WHERE user_id=? AND kind='integfail'", (uid,))
c.commit()
print(json.dumps(out))
""" % FID)
check(j.get("after") == [[0, 0], [0, 0], [1, 0], [1, 0], [1, 1]], f"2: News once at the third failure, the alert from the fifth {j}")
check(j.get("fails", [0])[0] == 5 and "Club book" in j.get("text", "") and "10.255" not in j.get("text", "") and j.get("focus") == "carddav",
      f"2: the News names the address book (never its address) and opens its settings {j}")
check(j.get("net") == 0, f"2: a network error of a write-back (tried again later) tells nobody {j}")
check((j.get("wb") or [0])[0] == 1 and "Erika Probe" in j["wb"][1] and "Club book" in j["wb"][1] and "version tags" in j["wb"][1]
      and j["wb"][2] == j["wb"][3], f"2: a refused write-back names the contact and the reason, a click opens its project {j}")

# ================================================================== 3: the absences link, hashed
r = Fr.post(B + "/api/team/absences/feed", json={"action": "create"})
url = r.json().get("url") or ""
check(r.ok and "/ical/abs/" in url and r.json().get("active") is True, f"3: create shows the link once ({r.status_code} {r.text[:200]})")
fid, sec = urllib.parse.urlparse(url).path.rsplit("/", 1)[1][:-4].split(".", 1) if url else ("0", "")
row = dbx("SELECT secret, secret_hash FROM abs_cal_feeds WHERE id=?", (int(fid),))
check(row and row[0][0] == "" and row[0][1] == hashlib.sha256(sec.encode()).hexdigest(), f"3: only the hash is stored ({row})")
check(not dbx("SELECT 1 FROM abs_cal_feeds WHERE secret LIKE ? OR secret_hash LIKE ?", (f"%{sec}%", f"%{sec}%")), "3: the secret is nowhere in the table")
j = Fr.get(B + "/api/team/absences/feed").json()
check(j.get("url") is None and j.get("active") is True and j.get("created_at"), f"3: later only 'active since' ({j.get('url')}, {j.get('active')})")
r = requests.get(B + urllib.parse.urlparse(url).path)
check(r.status_code == 200 and "BEGIN:VCALENDAR" in r.text, f"3: the link opens with the hashed secret ({r.status_code})")
j = Fr.post(B + "/api/team/absences/feed", json={"action": "rotate"}).json()
check(j.get("url") and j["url"] != url and requests.get(B + urllib.parse.urlparse(url).path).status_code == 404, "3: rotate: a new link once, the old one stops")
# a link of an older version (plain secret, no hash): opens, then it is hashed; another one is hashed at the start
AID = dbx("SELECT id FROM users WHERE username='alice'")[0][0]
OLD = "plain-secret-of-an-older-version-6553-a"
dbx("INSERT INTO abs_cal_feeds(user_id, secret, created_at) VALUES(?,?,now())", (AID, OLD))
oid = dbx("SELECT id FROM abs_cal_feeds WHERE user_id=?", (AID,))[0][0]
r = requests.get(B + f"/ical/abs/{oid}.{OLD}.ics")
check(r.status_code == 200, f"3: an old plain link keeps working ({r.status_code})")
check(tuple(dbx("SELECT secret, secret_hash FROM abs_cal_feeds WHERE id=?", (oid,))[0]) == ("", hashlib.sha256(OLD.encode()).hexdigest()),
      "3: … and is stored as a hash at its first use")
dbx("UPDATE abs_cal_feeds SET secret=?, secret_hash=NULL WHERE id=?", (OLD + "b", oid))
# the start-up step (tkh_migrate; an app process may already run it at import)
j = py("""import json, app
from kalmido.core.db import connect
from kalmido.core.pg import system_ctx
from kalmido.core.tokenhash import tkh_migrate
c = connect()
with system_ctx(c):  # as at the start (row-level security: every person's links)
    n = tkh_migrate(c)
c.commit()
print(json.dumps({"n": n}))""")
check(tuple(dbx("SELECT secret, secret_hash FROM abs_cal_feeds WHERE id=?", (oid,))[0]) == ("", hashlib.sha256((OLD + "b").encode()).hexdigest())
      and j.get("n") in (0, 1), f"3: the start hashes a plain link left {j}")
check(requests.get(B + f"/ical/abs/{oid}.{OLD}b.ics").status_code == 200, "3: … which keeps working")
# wrong tries: one counter per rate_ip() (an IPv6 /64), not per single address
codes = [requests.get(B + f"/ical/abs/{oid}.wrong{i}.ics", headers={"X-Forwarded-For": f"2001:db8:6553:1::{i + 1:x}"}).status_code for i in range(30)]
r = requests.get(B + f"/ical/abs/{oid}.{OLD}b.ics", headers={"X-Forwarded-For": "2001:db8:6553:1::ffff"})
check(set(codes) == {404} and r.status_code == 429, f"3: 30 wrong tries from one /64 block that /64 ({set(codes)} then {r.status_code})")
r = requests.get(B + f"/ical/abs/{oid}.{OLD}b.ics", headers={"X-Forwarded-For": "2001:db8:6553:2::1"})
check(r.status_code == 200, f"3: … another /64 is not blocked ({r.status_code})")

# ================================================================== 4: log lines with the type of the error only
r = Fr.post(B + "/api/tasks", json={"title": "Feed task 6553", "due": "2026-12-01"})
check(r.status_code in (200, 201), f"4: a task with a date ({r.status_code} {r.text[:200]})")
FEED = urllib.parse.urlparse(Fr.post(B + "/api/ical", json={"action": "rotate"}).json().get("url") or "").path
j = py(r"""
import contextlib, io, json, app
from kalmido.core.db import connect
from kalmido.core.config import app as kapp
from kalmido.calendars import icalfeed as IF
from kalmido.calendars.subscriptions import cal_seal
from kalmido.family import carddav as CD
def boom(*a, **k):
    raise ValueError("leaked text 6553 of a task")
def boom2(*a, **k):
    raise RuntimeError("leaked text 6553 of a card")
IF.ics_event, CD.carddav_books = boom, boom2
buf = io.StringIO()
c = connect()
uid = %d
c.execute("INSERT INTO contact_srcs(user_id,name,url,url_hint,username,password,lead,created_at) VALUES(?,?,?,?,?,?,?,?)",
          (uid, "Log book", cal_seal(c, uid, "https://10.255.255.1/card/"), "https://10.255.255.1/…", "frida", cal_seal(c, uid, "pw"), 7, "2026-01-01T00:00:00Z"))
src = c.execute("SELECT MAX(id) FROM contact_srcs").fetchone()[0]
c.commit()
with contextlib.redirect_stdout(buf):
    st = kapp.test_client().get(%r).status_code
    CD.contacts_sync(c, src)
c.execute("DELETE FROM contact_srcs WHERE id=?", (src,))
c.commit()
print(json.dumps({"status": st, "log": buf.getvalue()[-2000:]}))
""" % (FID, FEED))
lg = j.get("log", "")
check(j.get("status") == 200 and "ical: skipping task" in lg and "ValueError" in lg, f"4: the feed skips the broken task and says so {j}")
check("contacts sync: source" in lg and "RuntimeError" in lg and "leaked" not in lg, f"4: only the type of the error is logged {j}")

sys.exit(done("p21342_a_caldav_harden"))
