#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.380 H API tests (offline queue rest, guest list of an event, pictures in shared pages, the organisation move of polls
and bookmarks), own container (start.sh) with the mail stub and the fake web server of the bookmarks. Invented names only,
addresses @example.com.
freelancer-matrix: wiki
 - #3387: an idempotency key lives 14 days: a write sent again after 10 days gets its stored answer back (nothing changes
   twice); 2.1315.0 (#6409): a key older than 14 days goes with the watchdog's hourly run (idem_prune), not with a write;
   until then a write with it runs and is not replayed; the run caps a person at 5000 keys, the oldest go
 - #3392: an event's switch guests_visible (default off): on, the invitation to an external guest names all guests; off,
   only the recipient; not a boolean = 400; the calendar export carries X-KALMIDO-GUESTS-VISIBLE:TRUE only for the event
   with the switch on; a calendar file with the line sets it, one without the line leaves it as it is, FALSE turns it off;
   the invitation itself never carries the line; a person without an organisation sets it the same way
 - #2356: a page share shows a file store picture embedded in the page only with its switch "images" (default off): the
   public link and a guest (person share) see the picture through a route under the share; never a file that is no
   picture, never a picture that is not embedded in the page, never after the switch went off or the picture went to the
   trash; images not a boolean = 400 (as a person without an organisation)
 - #6321 (2.1284.0): who embedded a picture is kept per page and file (wiki_embeds): a rename of a linked page, of a folder,
   of the page itself, a move never open the embed of someone who does not see the file through the link of someone who
   does, and never take the pictures of others away; taken out and put in = the new person; the same in the private space
   of a person without an organisation with a folder shared to edit; every write of a page's text keeps the rows (source
   guard); the pages of before get their rows at the first start, an import its editor's
   Fable review 1 (F1-F6): only a person's own save of a text claims a picture (source guard) -- an embed that a relink
   (a backtick in a page's / folder's name), the tree's move, a restore, a lock that goes off make appear is nobody's, a
   page from a template keeps the template's embedders, an embed without a row is never the next writer's; every later
   start looks at the pages changed since the start before
 - #6868 (2.1368.0), #7056 (2.1401.0): a share shows a picture only when its row is confirmed for exactly that share (the
   embedder's save under it, its pictures switched on over the page); no move confirms anything: a rename / move (PATCH path,
   /api/wiki/move, the tree), the trash and back, a folder merged into another, a round trip through another workspace
   bring a page under a link with pictures without its pictures; the same shares: nothing changes
 - #6657 (2.1368.0): a page whose stamp (wem_at) does not match its updated_at at the start (written by a version without the
   stamp / by hand): all its pictures are nobody's; a save without expect_updated_at or "Keep mine" (overwrite) claims no picture
 - #2398: the organisation export carries the organisation's polls (options, votes) and bookmarks (with the picture);
   imported into an empty organisation they come with a new poll link (the old one is dead, the report says so), the votes
   name the new options, the bookmark's picture opens; the person's own poll / bookmark (no organisation) stays out
usage: p2380r_h_api_test.py <datadir>"""
import ast
import base64
import email as _em
import email.policy  # noqa: F401  (_em.policy)
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import time
import zlib
from datetime import date, timedelta, timezone

import requests

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
import dbx as dbxm  # noqa: E402
from freelancer_fixture import FEATURES, freelancer  # noqa: E402
from kt import FAILS, OKS, check, sess, su_get, until  # noqa: E402
from testclock import now as tnow  # noqa: E402

DATA = sys.argv[1] if len(sys.argv) > 1 else os.path.join(N, ".data")
B = "http://127.0.0.1:" + os.environ.get("KALMIDO_TEST_PORT", "3048")
H = {"X-Requested-With": "kalmido"}
CT = os.environ.get("KALMIDO_TEST_CONTAINER", "kalmido-test")
KEY = base64.b64encode(os.urandom(32)).decode()
FEED = "http://127.0.0.1:8098/"


def dbx(sql, args=()):
    c = dbxm.connect(os.path.join(DATA, "tasks.db"), timeout=10)
    try:
        r = c.execute(sql, args).fetchall()
        c.commit()
        return r
    finally:
        c.close()


def one(sql, args=()):
    r = dbx(sql, args)
    return r[0][0] if r else None


def usess(user):
    s = sess(user)
    r = s.patch(B + "/api/settings", json={"lang": "en", "features": FEATURES, "tour": "done"})
    assert r.ok, (user, r.text)
    return s


def mails(to=None):
    try:
        out = [json.loads(x) for x in open(os.path.join(DATA, "mail", "out.jsonl"), encoding="utf-8") if x.strip()]
    except FileNotFoundError:
        return []
    return [m for m in out if not to or to in json.dumps(m["to"])]


def ics_of(m):
    msg = _em.message_from_string(m["raw"], policy=_em.policy.default)
    out = ""
    for x in msg.walk():
        if x.get_content_type() == "text/calendar":
            c = x.get_content()
            out += c.decode("utf-8") if isinstance(c, bytes) else c
    return re.sub(r"\r\n[ \t]", "", out)


def png(w=2, h=2):
    raw = b"".join(b"\x00" + b"\x80\x40\xc0" * w for _ in range(h))
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)  # noqa: E731
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def put_feed(name, data):
    os.makedirs(os.path.join(DATA, "feeds"), exist_ok=True)
    with open(os.path.join(DATA, "feeds", name), "wb") as f:
        f.write(data if isinstance(data, bytes) else data.encode())


def upload(s, name, data, mime, **form):
    r = s.post(B + "/api/files/upload", data=form, files={"file": (name, data, mime)})
    assert r.status_code == 201, r.text
    return r.json()["items"][0]["id"]


def iso_s(dt):
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")



def imp_upload(s, data, name="alpha.kalmido-export"):
    r = s.post(B + "/api/account/import", json={"size": len(data), "name": name})
    assert r.ok, r.text
    iid, off = r.json()["id"], 0
    while off < len(data):
        part = data[off:off + (1 << 20)]
        r = s.put(B + f"/api/account/import/{iid}?offset={off}", data=part, headers={"Content-Type": "application/octet-stream"})
        assert r.ok, r.text
        off += len(part)
    return iid


def imp_wait(s, iid, secs=240):
    j = {}
    for _ in range(secs * 4):
        j = s.get(B + f"/api/account/import/{iid}").json()
        if j.get("state") not in ("checking", "running", "upload"):
            return j
        time.sleep(0.25)
    return j


# ---------------------------------------------------------------- server, people
env = dict(os.environ, EXTRA=os.environ.get("EXTRA", "") + " -e KALMIDO_INSTANCE_MODE=workspaces -e KALMIDO_SMTP_HOST=127.0.0.1"
           " -e KALMIDO_SMTP_PORT=1025 -e KALMIDO_SMTP_TLS=none -e KALMIDO_MAIL_FROM=kalmido@example.test"
           f" -e KALMIDO_SECRET_KEY={KEY} -e KALMIDO_BOOKMARK_ALLOW_HOSTS=127.0.0.1:8098"
           " -e KALMIDO_TEST_RATE_WINDOW_S=4")  # 2.1284.0 (#6321): the picture route's limit per minute is waited out (img)
r = subprocess.run(["bash", os.path.join(N, "start.sh"), DATA], env=env, capture_output=True, text=True)
assert r.returncode == 0, r.stdout + r.stderr
for f in ("stub_mail.py", "fake_feeds.py"):
    shutil.copy(os.path.join(N, f), DATA)
    subprocess.run(["docker", "exec", "-d", CT, "python", "/data/" + f])
s0 = requests.Session()
s0.headers.update(H)
assert s0.post(B + "/api/auth/setup", json={"username": "alice", "display_name": "Alice Admin", "password": "password123"}).ok
A = sess("alice")
A.post(B + "/api/admin/setup", json={"lang": "en", "collab_all": True})
A = usess("alice")
ALICE = A.get(B + "/api/state").json()["me"]["id"]
A.patch(B + f"/api/users/{ALICE}", json={"email": "alice@example.com"})
if not one("SELECT email FROM users WHERE id=?", (ALICE,)):
    dbx("UPDATE users SET email='alice@example.com' WHERE id=?", (ALICE,))
orgs = {}
for name in ("Alpha Team", "Gamma Leer"):
    r = A.post(B + "/api/admin/orgs", json={"name": name, "admin_id": ALICE})
    assert r.status_code == 201, r.text
    orgs[name] = r.json()["id"]
ORG, ORG2 = orgs["Alpha Team"], orgs["Gamma Leer"]
uid = {}
for u in ("bob", "carol"):
    r = A.post(B + "/api/users", json={"username": u, "display_name": u.title(), "password": "password123", "email": f"{u}@example.com"})
    assert r.ok, r.text
    uid[u] = r.json()["id"]
Bo, Ca = usess("bob"), usess("carol")
dbx("UPDATE users SET email_proved=lower(email) WHERE id=?", (uid["bob"],))  # 2.983.0 (#5643): a share by address binds only a proved address (a mailed link / OIDC); here set directly
FID, Fr = freelancer(B, A)
Fr.patch(B + "/api/settings", json={"lang": "en", "features": FEATURES, "tour": "done"})
D = (date.today() + timedelta(days=5)).isoformat()
PNG = png()

# ================================================================== #3387: idempotency keys live 14 days
L = A.post(B + "/api/lists", json={"name": "Idem"}).json()["id"]
T = A.post(B + "/api/tasks", json={"title": "Null", "list_id": L}).json()["id"]
K1 = {"Idempotency-Key": "p2380h-k1"}
r = A.patch(B + f"/api/tasks/{T}", json={"title": "Eins"}, headers=K1)
check(r.ok and r.json().get("title") == "Eins", "#3387: a change with its key " + r.text[:120])
check(one("SELECT COUNT(*) FROM idem_keys WHERE user_id=? AND k='p2380h-k1'", (ALICE,)) == 1, "#3387: the key is kept")
dbx("UPDATE idem_keys SET created_at=? WHERE user_id=? AND k='p2380h-k1'", (iso_s(tnow() - timedelta(days=10)), ALICE))
dbx("INSERT INTO idem_keys(user_id,k,method,path,status,body,created_at) VALUES(?,?,?,?,?,?,?)",
    (ALICE, "p2380h-old", "PATCH", f"/api/tasks/{T}", 200, "{}", iso_s(tnow() - timedelta(days=15))))
r = A.patch(B + f"/api/tasks/{T}", json={"title": "Zwei"}, headers={"Idempotency-Key": "p2380h-k2"})
check(r.ok and r.json().get("title") == "Zwei", "#3387: another change with a new key")
# 2.1315.0 (#6409): the request no longer tidies (was: the old keys went here); the watchdog's idem_prune does it
check(one("SELECT COUNT(*) FROM idem_keys WHERE user_id=? AND k='p2380h-old'", (ALICE,)) == 1, "#6409: a write with a key deletes no keys")
# 2.1315.0 (#6409): until the next run a key older than 14 days counts as gone: the change with it runs, nothing is replayed
r = A.patch(B + f"/api/tasks/{T}", json={"title": "Drei"}, headers={"Idempotency-Key": "p2380h-old"})
check(r.ok and r.headers.get("Idempotent-Replayed") is None and r.json().get("title") == "Drei",
      f"#6409: an expired key is not replayed ({r.status_code} {r.headers.get('Idempotent-Replayed')} {r.text[:80]})")
check(one("SELECT COUNT(*) FROM idem_keys WHERE user_id=? AND k='p2380h-old' AND created_at>?", (ALICE, iso_s(tnow() - timedelta(days=1)))) == 1,
      "#6409: the expired key is claimed anew")
r = A.patch(B + f"/api/tasks/{T}", json={"title": "Eins"}, headers=K1)
check(r.ok and r.headers.get("Idempotent-Replayed") == "true", f"#3387: the change sent again after 10 days gets its answer back "
      f"({r.status_code} {r.headers.get('Idempotent-Replayed')})")
check(A.get(B + f"/api/tasks/{T}").json().get("title") == "Drei", "#3387: and changes nothing a second time")
# 2.380 review: the keys of one person are capped (IDEM_MAX_KEYS 5000), the oldest go first
# 2.1315.0 (#6409): by the watchdog's run (idem_prune), no longer by the request
dbx("INSERT INTO idem_keys(user_id,k,method,path,status,body,created_at) SELECT ?, 'p2380h-f' || g, 'PATCH', '/x', 200, '{}', ? "
    "FROM generate_series(1, 5000) g", (ALICE, iso_s(tnow() - timedelta(days=1))))
dbx("INSERT INTO idem_keys(user_id,k,method,path,status,body,created_at) VALUES(?,?,?,?,?,?,?)",
    (ALICE, "p2380h-old2", "PATCH", "/x", 200, "{}", iso_s(tnow() - timedelta(days=15))))
dbx("INSERT INTO idem_keys(user_id,k,method,path,status,body,created_at) VALUES(?,?,?,?,?,?,?)",
    (uid["bob"], "p2380h-bob", "PATCH", "/x", 200, "{}", iso_s(tnow() - timedelta(days=13))))
r = A.patch(B + f"/api/tasks/{T}", json={"title": "Zwei"}, headers={"Idempotency-Key": "p2380h-k3"})
n_before = one("SELECT COUNT(*) FROM idem_keys WHERE user_id=?", (ALICE,))
check(r.ok and n_before == 5005, f"#6409: the request caps nothing ({n_before} keys)")
out = subprocess.run(["docker", "exec", CT, "python3", "-c", "import app\nfrom kalmido.core.db import connect\nfrom kalmido.core.idem import idem_prune\n"
                      "c = connect()\nprint('N=%d' % idem_prune(c, force=True))\nc.close()"], capture_output=True, text=True, timeout=180)
check(out.returncode == 0 and "N=5" in out.stdout.split(), f"#6409: one run of the watchdog section removes 5 keys ({out.stdout[-200:]} {out.stderr[-300:]})")
check(one("SELECT COUNT(*) FROM idem_keys WHERE user_id=?", (ALICE,)) == 5000
      and one("SELECT COUNT(*) FROM idem_keys WHERE user_id=? AND k='p2380h-old2'", (ALICE,)) == 0
      and one("SELECT COUNT(*) FROM idem_keys WHERE user_id=? AND k='p2380h-k1'", (ALICE,)) == 0
      and one("SELECT COUNT(*) FROM idem_keys WHERE user_id=? AND k='p2380h-k3'", (ALICE,)) == 1
      and one("SELECT COUNT(*) FROM idem_keys WHERE user_id=? AND k='p2380h-bob'", (uid["bob"],)) == 1,
      "#3387 review / #6409: the run takes the keys older than 14 days and the oldest over 5000, the new one and another person's stay")

# ================================================================== #3392: the guest list of an event
CAL = A.post(B + "/api/evcals", json={"name": "Alice Termine", "org_id": None}).json()["id"]


def ev(title, guests, **kw):
    return A.post(B + "/api/events", json={"cal_id": CAL, "title": title, "start": f"{D}T10:00", "end": f"{D}T11:00", "tz": "Europe/Berlin",
                                           "send_invites": True, "attendees": [{"email": g, "name": g.split("@")[0]} for g in guests], **kw})


r = ev("Workshop offen", ["gv.eins@example.com", "gv.zwei@example.com"], guests_visible=True)
check(r.status_code == 201 and r.json().get("guests_visible") is True, "#3392: an event with the guest list visible " + r.text[:200])
E1 = r.json().get("id")
m = until(lambda: mails("gv.eins@example.com"), 15)
ics = ics_of(m[0]) if m else ""
check("mailto:gv.eins@example.com" in ics and "mailto:gv.zwei@example.com" in ics, "#3392: the invitation names every guest " + ics[-500:])
check("X-KALMIDO-GUESTS-VISIBLE" not in ics, "#3392: the invitation does not carry the switch")
r = ev("Workshop still", ["off.eins@example.com", "off.zwei@example.com"])
check(r.status_code == 201 and r.json().get("guests_visible") is False, "#3392: default off " + r.text[:200])
E2 = r.json().get("id")
m = until(lambda: mails("off.eins@example.com"), 15)
ics = ics_of(m[0]) if m else ""
check("mailto:off.eins@example.com" in ics and "off.zwei" not in ics, "#3392: off = the invitation names only its recipient (as since 2.360)")
check(A.patch(B + f"/api/events/{E2}", json={"guests_visible": "yes"}).status_code == 400, "#3392: not a boolean = 400")
check(A.get(B + f"/api/events/{E1}").json().get("guests_visible") is True and A.get(B + f"/api/events/{E2}").json().get("guests_visible") is False,
      "#3392: the API shows the switch")
ex = A.get(B + f"/api/evcals/{CAL}/export.ics").text
check(ex.count("X-KALMIDO-GUESTS-VISIBLE:TRUE") == 1, "#3392: the calendar file carries the line only for the event with the switch on")


def ics_file(title, line=None):
    return ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Example//EN\r\nBEGIN:VEVENT\r\nUID:p2380h-gv@example.com\r\nDTSTAMP:20261001T000000Z\r\n"
            f"DTSTART:{D.replace('-', '')}T090000Z\r\nDTEND:{D.replace('-', '')}T100000Z\r\nSUMMARY:{title}\r\n"
            + (f"X-KALMIDO-GUESTS-VISIBLE:{line}\r\n" if line else "") + "END:VEVENT\r\nEND:VCALENDAR\r\n").encode()


def imp(title, line=None):
    r = A.post(B + f"/api/evcals/{CAL}/import", files={"file": ("x.ics", ics_file(title, line), "text/calendar")})
    got = dbx("SELECT title, guests_visible, extra FROM events WHERE cal_id=? AND uid='p2380h-gv@example.com' AND deleted_at IS NULL", (CAL,))
    return r, (got[0] if got else None)


r, g = imp("Aus Datei", "TRUE")
check(r.ok and g and g[1] == 1 and "GUESTS-VISIBLE" not in (g[2] or ""), f"#3392: a calendar file with the line turns it on {g} {r.text[:120]}")
r, g = imp("Aus Datei, geaendert")
check(r.ok and g and g[0] == "Aus Datei, geaendert" and g[1] == 1, f"#3392: a file without the line leaves the switch as it is {g}")
r, g = imp("Aus Datei, aus", "FALSE")
check(r.ok and g and g[1] == 0, f"#3392: FALSE turns it off {g}")
FCAL = Fr.post(B + "/api/evcals", json={"name": "Freie Termine", "org_id": None}).json()["id"]
r = Fr.post(B + "/api/events", json={"cal_id": FCAL, "title": "Kundentermin", "start": f"{D}T15:00", "end": f"{D}T16:00", "tz": "Europe/Berlin",
                                     "guests_visible": True, "attendees": [{"email": "kunde.eins@example.com"}]})
check(r.status_code == 201 and r.json().get("guests_visible") is True, "#3392: without an organisation the same " + r.text[:200])

# ================================================================== #2356: pictures of the file store in shared pages (freelancer)
IMG = upload(Fr, "plan.png", PNG, "image/png", space="private")
TXT = upload(Fr, "notiz.txt", b"geheime Notiz", "text/plain", space="private")
IMG2 = upload(Fr, "anderes.png", png(3, 3), "image/png", space="private")
r = Fr.post(B + "/api/wiki/pages", json={"space": "private", "path": "Kunde Y/Plan",
                                         "body": f"# Plan\n\n![Der Plan](/api/files/nodes/{IMG}/content)\n\n![Notiz](/api/files/nodes/{TXT}/content)\n\n```\n![Code](/api/files/nodes/{IMG2}/content)\n```\n\n`![Inline](/api/files/nodes/{IMG2}/content)`\n"})
assert r.status_code == 201, r.text
PID = r.json()["id"]
check(Fr.post(B + "/api/wiki/shares", json={"page_id": PID, "kind": "link", "images": "ja"}).status_code == 400, "#2356: images not a boolean = 400")
r = Fr.post(B + "/api/wiki/shares", json={"page_id": PID, "kind": "link"})
check(r.status_code == 201 and r.json().get("images") is False, "#2356: a link without the switch (default off) " + r.text[:200])
T0 = r.json().get("url", "").rsplit("/", 1)[-1]
p = requests.get(B + "/s/w/" + T0)
check(p.ok and "/img/" not in p.text and "<img" not in p.text, "#2356: off = no picture on the public page")
check(requests.get(B + f"/s/w/{T0}/img/{PID}/{IMG}").status_code == 404, "#2356: off = the picture route answers 404")
r = Fr.post(B + "/api/wiki/shares", json={"page_id": PID, "kind": "link", "images": True})
check(r.status_code == 201 and r.json().get("images") is True, "#2356: a link with the switch " + r.text[:200])
S1, T1 = r.json().get("id"), r.json().get("url", "").rsplit("/", 1)[-1]
p = requests.get(B + "/s/w/" + T1)
check(p.ok and f'src="/s/w/{T1}/img/{PID}/{IMG}"' in p.text, "#2356: the public page shows the picture " + p.text[-400:])
# 2.549.0 (#4636): exact paths, a bare "/<id>" matched other ids that merely contain the number
check(f"/img/{PID}/{TXT}\"" not in p.text and f"/api/files/nodes/{TXT}/" not in p.text and "geheime" not in p.text, "#2356: a file that is no picture stays hidden")
q = requests.get(B + f"/s/w/{T1}/img/{PID}/{IMG}")
check(q.ok and q.content == PNG and q.headers.get("Content-Type", "").startswith("image/png") and "nosniff" in q.headers.get("X-Content-Type-Options", "")
      and "no-store" in q.headers.get("Cache-Control", ""), f"#2356: the picture comes through the link ({q.status_code} {q.headers.get('Content-Type')})")
check(requests.get(B + f"/s/w/{T1}/img/{PID}/{TXT}").status_code == 404, "#2356: the text file never comes through the route")
check(requests.get(B + f"/s/w/{T1}/img/{PID}/{IMG2}").status_code == 404, "#2356: a picture only named in code (not embedded) never comes")
check(requests.get(B + f"/s/w/{T0}x/img/{PID}/{IMG}").status_code in (404, 410), "#2356: an unknown link: nothing")
# a guest (person share by e-mail address) with the switch
r = Fr.post(B + "/api/wiki/shares", json={"page_id": PID, "kind": "person", "email": "bob@example.com", "images": True})
check(r.ok, "#2356: shared with bob, pictures on " + r.text[:160])
g = Bo.get(B + f"/api/wiki/shared/pages/{PID}")
check(g.ok and f"/api/wiki/shared/pages/{PID}/img/{IMG}" in g.json().get("html", ""), "#2356: the guest sees the picture " + g.text[:300])
q = Bo.get(B + f"/api/wiki/shared/pages/{PID}/img/{IMG}")
check(q.ok and q.content == PNG, f"#2356: the guest's picture route ({q.status_code})")
check(Bo.get(B + f"/api/wiki/shared/pages/{PID}/img/{TXT}").status_code == 404, "#2356: the guest never gets the text file")
check(Ca.get(B + f"/api/wiki/shared/pages/{PID}/img/{IMG}").status_code == 404, "#2356: somebody the page is not shared with: 404")
# the switch goes off
check(Fr.patch(B + f"/api/wiki/shares/{S1}", json={"images": False}).ok, "#2356: the switch goes off")
check(requests.get(B + f"/s/w/{T1}/img/{PID}/{IMG}").status_code == 404 and "<img" not in requests.get(B + "/s/w/" + T1).text,
      "#2356: off again = the picture is gone from the link")
check(Fr.patch(B + f"/api/wiki/shares/{S1}", json={"images": True}).ok and requests.get(B + f"/s/w/{T1}/img/{PID}/{IMG}").ok, "#2356: on again")
# the picture goes to the trash: the sharer cannot see it any more
check(Fr.delete(B + f"/api/files/nodes/{IMG}").ok, "the picture goes to the trash")
check(requests.get(B + f"/s/w/{T1}/img/{PID}/{IMG}").status_code == 404 and Bo.get(B + f"/api/wiki/shared/pages/{PID}/img/{IMG}").status_code == 404,
      "#2356: a picture in the trash is never shown")

# ================================================================== 2.1257.0 (#6295): a fellow editor and the pictures of a colleague's link
# (audit #4741 Z6-F1) carol makes a link with pictures of an organisation page; bob (member, writes the wiki) may neither switch
# the pictures of her link nor read a picture only carol sees by embedding it into the page; alice (admin) may switch them
A.patch(B + "/api/admin/settings", json={"public_links": True})
for u in ("bob", "carol"):
    assert A.put(B + f"/api/orgs/{ORG}/members", json={"email": f"{u}@example.com", "role": "member"}).ok, u
CIMG = upload(Ca, "nur-carol.png", png(4, 4), "image/png", space=f"org:{ORG}")
OIMG = upload(Ca, "fuer-alle.png", png(5, 5), "image/png", space=f"org:{ORG}")
dbx("UPDATE fs_nodes SET org_access='' WHERE id=?", (CIMG,))
dbx("UPDATE fs_nodes SET org_access='view' WHERE id=?", (OIMG,))
check(Bo.get(B + f"/api/files/nodes/{CIMG}").status_code in (403, 404), "#6295 setup: bob does not see carol's picture")
check(Bo.get(B + f"/api/files/nodes/{OIMG}").ok, "#6295 setup: bob sees the picture open to the organisation")
r = Ca.post(B + "/api/wiki/pages", json={"space": f"org:{ORG}", "path": "Team/Galerie", "body": f"# Galerie\n\n![Offen](/api/files/nodes/{OIMG}/content)\n"})
assert r.status_code == 201, r.text
GP = r.json()["id"]
r = Ca.post(B + "/api/wiki/shares", json={"page_id": GP, "kind": "link"})
check(r.status_code == 201 and r.json().get("images") is False, "#6295: carol's link without pictures " + r.text[:200])
GS, GT = r.json().get("id"), r.json().get("url", "").rsplit("/", 1)[-1]
r = Bo.patch(B + f"/api/wiki/shares/{GS}", json={"images": True})
check(r.status_code == 403, f"#6295: bob may not switch on the pictures of carol's link ({r.status_code} {r.text[:120]})")
check(requests.get(B + f"/s/w/{GT}/img/{GP}/{OIMG}").status_code == 404, "#6295: the pictures stay off")
check(Bo.patch(B + f"/api/wiki/shares/{GS}", json={"expires": D}).ok, "#6295: bob still may change the link's date")
check(A.patch(B + f"/api/wiki/shares/{GS}", json={"images": True}).ok, "#6295: alice (admin) may switch on the pictures")
check(requests.get(B + f"/s/w/{GT}/img/{GP}/{OIMG}").ok, "#6295: carol's own embed of an open picture comes")
# bob embeds carol's picture into the page the link covers: bob (the last editor) does not see it -> nothing
pg = Bo.get(B + f"/api/wiki/pages/{GP}").json()
r = Bo.patch(B + f"/api/wiki/pages/{GP}", json={"body": pg["body"] + f"\n![Fremd](/api/files/nodes/{CIMG}/content)\n", "expect_updated_at": pg.get("updated_at")})
check(r.ok, "#6295: bob writes the page " + r.text[:160])
check(requests.get(B + f"/s/w/{GT}/img/{GP}/{CIMG}").status_code == 404, "#6295: the picture only carol sees never comes through her link")
check(f"/img/{GP}/{CIMG}" not in requests.get(B + f"/s/w/{GT}/p/{GP}").text, "#6295: and the public page does not show it")
# 2.1284.0 (#6321): was "carol saves the page herself: now it comes" -- the picture is bob's embed and stays his while it
# stands in the text, whoever saves; carol takes it out and puts it in herself: now it is hers and comes
pg = Ca.get(B + f"/api/wiki/pages/{GP}").json()
check(Ca.patch(B + f"/api/wiki/pages/{GP}", json={"body": pg["body"] + "\nOK\n", "expect_updated_at": pg.get("updated_at")}).ok, "#6295: carol saves the page")


def img(tok, pid, nid):
    """The status of the public picture route; the route's limit per address and minute (429) is waited out (a refused
    request does not count, the window here is KALMIDO_TEST_RATE_WINDOW_S)."""
    def get():
        g = requests.get(B + f"/s/w/{tok}/img/{pid}/{nid}").status_code
        return g if g != 429 else None
    return until(get, 30, step=0.5)


def upd(pid):
    return one("SELECT updated_by FROM wiki_pages WHERE id=?", (pid,))


def emb(pid, nid):
    """Who embedded picture nid into page pid: an account id, None = nobody, "-" = no row."""
    r = dbx("SELECT user_id FROM wiki_embeds WHERE page_id=? AND node_id=?", (pid, nid))
    return r[0][0] if r else "-"


def wnode(pid):
    """(node id, folder node id) of a page in the tree."""
    return dbx("SELECT id, parent_id FROM fs_nodes WHERE kind='ref' AND ref_kind='wiki' AND ref_id=?", (pid,))[0]


def wbody(s, pid):
    return s.get(B + f"/api/wiki/pages/{pid}").json()["body"]


def wsave(s, pid, text):
    """A person's save from the editor: on the state it was written on (expect_updated_at). 2.1368.0 (#6657): was a save
    without it -- such a save claims no picture any more (re-check N4), the editor always sends it."""
    exp = s.get(B + f"/api/wiki/pages/{pid}").json().get("updated_at")
    return s.patch(B + f"/api/wiki/pages/{pid}", json={"body": text, "expect_updated_at": exp})


FREMD = f"\n![Fremd](/api/files/nodes/{CIMG}/content)\n"
g = img(GT, GP, CIMG)
check(g == 404 and emb(GP, CIMG) == uid["bob"] and upd(GP) == uid["carol"], f"#6321: carol saving the text next to bob's embed does not make it hers ({g} {emb(GP, CIMG)})")
full = wbody(Ca, GP)
assert FREMD in full, full
check(wsave(Ca, GP, full.replace(FREMD, "\n")).ok and emb(GP, CIMG) == "-", f"#6321: the embed taken out of the text: its row goes ({emb(GP, CIMG)})")
check(wsave(Ca, GP, full).ok and emb(GP, CIMG) == uid["carol"] and emb(GP, OIMG) == uid["carol"], f"#6321: put in by carol, it is hers ({emb(GP, CIMG)})")
q = requests.get(B + f"/s/w/{GT}/img/{GP}/{CIMG}")
check(q.ok and q.content == png(4, 4), f"#6295: carol's own embed comes through her link ({q.status_code})")

# ---- 2.1284.0 (#6321, Fable review of #6295): the other side -- someone who does not see the file changes the page, and the
# pictures of others stay (before: the last editor counted, so bob's save / rename took carol's picture away)
check(wsave(Bo, GP, full + "\nBob war hier\n").ok and upd(GP) == uid["bob"], "#6321: bob changes the text next to carol's embed")
g = img(GT, GP, CIMG)
check(g == 200 and emb(GP, CIMG) == uid["carol"], f"#6321: carol's picture stays after bob's save ({g})")
r = Bo.patch(B + f"/api/wiki/pages/{GP}", json={"path": "Team/Galerie zwei"})
check(r.ok and upd(GP) == uid["bob"], f"#6321: bob renames the page ({r.status_code} {r.text[:120]})")
g = (img(GT, GP, CIMG), img(GT, GP, OIMG))
check(g == (200, 200), f"#6321: carol's pictures stay after bob's rename {g}")

# ---- the attack: bob embeds the picture only carol sees into his page and links two pages; carol (who sees the picture) has
# a link with pictures on bob's page and then renames / moves things WITHOUT touching the text -- each step made her the last
# editor (wiki_pages.updated_by) and so opened the picture; now bob stays the one who embedded it
X1 = Ca.post(B + "/api/wiki/pages", json={"space": f"org:{ORG}", "path": "Ziele/Eins", "body": "eins"}).json()["id"]
X2 = Ca.post(B + "/api/wiki/pages", json={"space": f"org:{ORG}", "path": "Ziele/Zwei", "body": "zwei"}).json()["id"]
r = Bo.post(B + "/api/wiki/pages", json={"space": f"org:{ORG}", "path": "Team/Bobs Seite", "body": f"[[Ziele/Eins]] und [[Ziele/Zwei]]\n{FREMD}"})
assert r.status_code == 201, r.text
BQ = r.json()["id"]
r = Ca.post(B + "/api/wiki/shares", json={"page_id": BQ, "kind": "link"})
assert r.status_code == 201, r.text
BS, BT = r.json().get("id"), r.json().get("url", "").rsplit("/", 1)[-1]
assert A.patch(B + f"/api/wiki/shares/{BS}", json={"images": True}).ok
g = img(BT, BQ, CIMG)
check(requests.get(B + f"/s/w/{BT}/p/{BQ}").ok and g == 404 and emb(BQ, CIMG) == uid["bob"], f"#6321: bob's embed in his own page never comes through carol's link ({g} {emb(BQ, CIMG)})")


def closed(what, r, editor=True):
    """After carol's step r: (where the step sets it) she is the page's last editor, and still nothing comes."""
    check(r.ok and (not editor or upd(BQ) == uid["carol"]), f"#6321 {what}: done{', carol is the last editor now' if editor else ''} ({r.status_code} {r.text[:120]} {upd(BQ)})")
    g, page = img(BT, BQ, CIMG), requests.get(B + f"/s/w/{BT}/p/{BQ}")
    check(g == 404 and emb(BQ, CIMG) == uid["bob"] and page.ok and f"/img/{BQ}/{CIMG}" not in page.text,
          f"#6321 {what}: the picture is still bob's embed and does not come ({g} {emb(BQ, CIMG)} {page.status_code})")
    dbx("UPDATE wiki_pages SET updated_by=? WHERE id=?", (uid["bob"], BQ))


r = Ca.patch(B + f"/api/wiki/pages/{X1}", json={"path": "Ziele/Eins neu"})
check(r.ok and r.json().get("relinked") == 1 and "[[Ziele/Eins neu]]" in wbody(Bo, BQ), f"#6321 setup: the rename relinked bob's page {r.text[:120]}")
closed("carol renames a linked page (relink)", r)
r = Ca.post(B + "/api/wiki/move", json={"space": f"org:{ORG}", "from": "Ziele", "to": "Ziele neu"})
check("[[Ziele neu/Zwei]]" in wbody(Bo, BQ), "#6321 setup: the folder's rename relinked bob's page")
closed("carol renames the folder of the linked pages (relink of many)", r)
closed("carol renames bob's page (PATCH with path only)", Ca.patch(B + f"/api/wiki/pages/{BQ}", json={"path": "Team/Bobs Seite zwei"}))
closed("carol renames the folder of bob's page in the tree", Ca.patch(B + f"/api/files/nodes/{wnode(BQ)[1]}", json={"name": "Team neu"}), editor=False)
closed("carol moves bob's page into another folder", Ca.post(B + f"/api/files/nodes/{wnode(BQ)[0]}/order", json={"parent_id": wnode(X2)[1]}), editor=False)
check(one("SELECT path FROM wiki_pages WHERE id=?", (BQ,)) == "Ziele neu/Bobs Seite zwei", "#6321 setup: the page did move " + str(one("SELECT path FROM wiki_pages WHERE id=?", (BQ,))))

# ---- an embed taken out and put in by someone else is the new person's; 2.1284.0 (#6321, review 1 F4): a restored version's
# embed is nobody's (was: the restoring person's -- carol restored bob's version and so opened his embed)
full = wbody(Bo, GP)
ok = wsave(Bo, GP, full.replace(FREMD, "\n")).ok and wsave(Bo, GP, full).ok
g = (img(GT, GP, CIMG), img(GT, GP, OIMG))
check(ok and emb(GP, CIMG) == uid["bob"] and g[0] == 404, f"#6321: carol's embed taken out and put in again by bob is bob's: nothing ({emb(GP, CIMG)} {g})")
check(g[1] == 200 and emb(GP, OIMG) == uid["carol"], f"#6321: the other picture of the page stays carol's {g}")
check(wsave(Ca, GP, full.replace(FREMD, "\n")).ok and emb(GP, CIMG) == "-", "#6321: carol takes it out")
vs = [v["id"] for v in Ca.get(B + f"/api/wiki/pages/{GP}/versions").json().get("versions", [])]
old = next((v for v in vs if FREMD.strip() in Ca.get(B + f"/api/wiki/pages/{GP}/versions/{v}").json().get("body", "")), None)
r = Ca.post(B + f"/api/wiki/pages/{GP}/versions/{old}/restore", json={})
g = img(GT, GP, CIMG)
check(old is not None and r.ok and FREMD.strip() in wbody(Ca, GP) and emb(GP, CIMG) is None and g == 404,
      f"#6321 F4: carol restores a version with bob's embed: it is nobody's and does not come ({old} {r.status_code} {emb(GP, CIMG)} {g})")
check(emb(GP, OIMG) == uid["carol"] and img(GT, GP, OIMG) == 200, f"#6321 F4: the picture that stayed in the text keeps its person ({emb(GP, OIMG)})")
full = wbody(Ca, GP)
check(wsave(Ca, GP, full + "\nnoch da\n").ok and emb(GP, CIMG) is None, f"#6321 F4: her next save does not take it over ({emb(GP, CIMG)})")
ok = wsave(Ca, GP, full.replace(FREMD, "\n")).ok and wsave(Ca, GP, full).ok
g = img(GT, GP, CIMG)
check(ok and emb(GP, CIMG) == uid["carol"] and g == 200, f"#6321 F4: taken out and put in by carol, it is hers and comes ({emb(GP, CIMG)} {g})")

# ---- the private space of a person without an organisation, a folder shared with bob to edit: bob's new page embeds a
# private picture of hers (he does not see it); her link with pictures shows nothing, also after she renames the linked page;
# her own embed stays after bob renames her page through the share
FIMG = upload(Fr, "privat.png", png(6, 6), "image/png", space="private")
check(Bo.get(B + f"/api/files/nodes/{FIMG}").status_code in (403, 404), "#6321 setup: bob does not see her private picture")
FEMB = f"\n![Privat](/api/files/nodes/{FIMG}/content)\n"
r = Fr.post(B + "/api/wiki/pages", json={"space": "private", "path": "Kunde Z/Ziel", "body": "ziel"})
assert r.status_code == 201, r.text
FZ = r.json()["id"]
r = Fr.post(B + "/api/wiki/pages", json={"space": "private", "path": "Kunde Z/Eigene", "body": "# Eigene\n" + FEMB})
assert r.status_code == 201, r.text
FO = r.json()["id"]
FN = wnode(FZ)[1]
# shared by address in the knowledge dialog (read), then made an edit share in the database: the dialogs offer "edit" only
# inside a workspace, the rule must hold for such a row all the same
r = Fr.post(B + "/api/wiki/shares", json={"space": "private", "folder": "Kunde Z", "kind": "person", "email": "bob@example.com"})
dbx("UPDATE fs_shares SET role='edit' WHERE node_id=? AND user_id=?", (FN, uid["bob"]))
check(r.ok and one("SELECT role FROM fs_shares WHERE node_id=? AND user_id=?", (FN, uid["bob"])) == "edit",
      f"#6321 setup: her folder shared with bob to edit ({r.status_code} {r.text[:160]})")
r = Bo.post(B + "/api/wiki/shared/pages", json={"folder_id": FN, "name": "Von Bob", "body": f"[[Kunde Z/Ziel]]\n{FEMB}"})
check(r.status_code == 201, f"#6321 setup: bob's page in her folder ({r.status_code} {r.text[:160]})")
FB = r.json().get("id")
check(one("SELECT owner_id FROM wiki_pages WHERE id=?", (FB,)) == FID and emb(FB, FIMG) == uid["bob"],
      f"#6321: the page is hers, the embed is bob's (the guest wrote the text, not the owner) ({emb(FB, FIMG)})")
r = Fr.post(B + "/api/wiki/shares", json={"page_id": FB, "kind": "link", "images": True})
assert r.status_code == 201, r.text
FT = r.json().get("url", "").rsplit("/", 1)[-1]
g = img(FT, FB, FIMG)
check(requests.get(B + f"/s/w/{FT}").ok and g == 404, f"#6321 private: bob's embed of her picture does not come through her link ({g})")
r = Fr.patch(B + f"/api/wiki/pages/{FZ}", json={"path": "Kunde Z/Ziel neu"})
check(r.ok and r.json().get("relinked") == 1 and upd(FB) == FID, f"#6321 private: she renames the linked page, she is the last editor of bob's page now ({r.text[:120]} {upd(FB)})")
g = img(FT, FB, FIMG)
check(g == 404 and emb(FB, FIMG) == uid["bob"], f"#6321 private: still nothing after her rename ({g} {emb(FB, FIMG)})")
r = Fr.post(B + "/api/wiki/shares", json={"page_id": FO, "kind": "link", "images": True})
assert r.status_code == 201, r.text
FOT = r.json().get("url", "").rsplit("/", 1)[-1]
g = img(FOT, FO, FIMG)
check(g == 200, f"#6321 private: her own embed comes through her link ({g})")
r = Bo.patch(B + f"/api/wiki/pages/{FO}", json={"path": "Kunde Z/Eigene zwei"})
check(r.ok and upd(FO) == uid["bob"], f"#6321 private: bob renames her page through the share ({r.status_code} {r.text[:120]} {upd(FO)})")
g = img(FOT, FO, FIMG)
check(g == 200 and emb(FO, FIMG) == FID, f"#6321 private: her picture stays after bob's rename ({g} {emb(FO, FIMG)})")

# ================================================================== 2.1284.0 (#6321, Fable review 1 of the first build, F1-F5)
# one rule: only who SAVES a text they wrote claims a picture. A relink, a move, a restore, a template, a text out of a
# space's lock only follow -- an embed that appears there is nobody's (a row with user_id NULL: no picture until someone
# takes it out and puts it in again); a picture without a row is never "the next writer's"
SPO = f"org:{ORG}"


def wnew(s, path, text, space=SPO, **kw):
    r = s.post(B + "/api/wiki/pages", json={"space": space, "path": path, "body": text, **kw})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def piclink(pid):
    """carol's link with pictures on an organisation page -> its token."""
    r = Ca.post(B + "/api/wiki/shares", json={"page_id": pid, "kind": "link"})
    assert r.status_code == 201, r.text
    assert A.patch(B + f"/api/wiki/shares/{r.json()['id']}", json={"images": True}).ok
    return r.json().get("url", "").rsplit("/", 1)[-1]


def wpath(pid):
    return one("SELECT path FROM wiki_pages WHERE id=?", (pid,))


# ---- F1: a backtick in a page's name hides bob's embed as code (no embed, no row); carol's rename of that page relinks
# bob's text, the code ends and the embed appears -- it was written to carol, who sees the file: the picture came
HID = f"![x](/api/files/nodes/{CIMG}/content) `"
R1Z = wnew(Bo, "Kniff/a`b", "ziel")
R1 = wnew(Bo, "Kniff/Bobs Kniff", f"[[Kniff/a`b]] {HID}")
R1T = piclink(R1)
check(wpath(R1Z) == "Kniff/a`b" and emb(R1, CIMG) == "-" and img(R1T, R1, CIMG) == 404, f"#6321 F1 setup: a name with a backtick, the picture stands in code: no embed ({wpath(R1Z)} {emb(R1, CIMG)})")
r = Ca.patch(B + f"/api/wiki/pages/{R1Z}", json={"path": "Kniff/ab"})
check(r.ok and r.json().get("relinked") == 1 and wbody(Bo, R1).startswith("[[Kniff/ab]] ![x]("), f"#6321 F1 setup: carol's rename relinked bob's page, the code ended ({r.status_code} {r.text[:120]})")
g = img(R1T, R1, CIMG)
check(emb(R1, CIMG) is None and g == 404, f"#6321 F1: the embed a relink makes appear is nobody's and does not come ({emb(R1, CIMG)} {g})")
check(wsave(Ca, R1, wbody(Ca, R1) + "\nCarol war hier\n").ok and emb(R1, CIMG) is None and img(R1T, R1, CIMG) == 404,
      f"#6321 F1: carol's own save next to it does not take it over ({emb(R1, CIMG)})")
# the same through a folder's name and the many-relink (POST /api/wiki/move)
R1b = wnew(Bo, "Kn`iff zwei/Ziel", "ziel")
R1c = wnew(Bo, "Kniff/Bobs Kniff zwei", f"[[Kn`iff zwei/Ziel]] {HID}")
R1cT = piclink(R1c)
r = Ca.post(B + "/api/wiki/move", json={"space": SPO, "from": "Kn`iff zwei", "to": "Kniff zwei"})
g = img(R1cT, R1c, CIMG)
check(r.ok and wbody(Bo, R1c).startswith("[[Kniff zwei/Ziel]] ![x](") and emb(R1c, CIMG) is None and g == 404,
      f"#6321 F1: the same after a folder's rename (relink of many) ({r.status_code} {emb(R1c, CIMG)} {g})")

# ---- F2: the relink through the file tree (PATCH parent_id of the page's node): carol moves the linked page out of a
# folder with a backtick in its name
R2Z = wnew(Bo, "Or`dner/Ziel zwei", "ziel")
R2 = wnew(Bo, "Kniff/Bobs Kniff drei", f"[[Or`dner/Ziel zwei]] {HID}")
R2T = piclink(R2)
check(emb(R2, CIMG) == "-", f"#6321 F2 setup: in code, no embed ({emb(R2, CIMG)})")
r = Ca.patch(B + f"/api/files/nodes/{wnode(R2Z)[0]}", json={"parent_id": wnode(R1)[1]})
check(r.ok and wpath(R2Z) == "Kniff/Ziel zwei" and wbody(Bo, R2).startswith("[[Kniff/Ziel zwei]] ![x]("), f"#6321 F2 setup: moved in the tree, bob's page relinked ({r.status_code} {r.text[:120]} {wpath(R2Z)})")
g = img(R2T, R2, CIMG)
check(emb(R2, CIMG) is None and g == 404, f"#6321 F2: the embed the tree's move makes appear is nobody's ({emb(R2, CIMG)} {g})")
# the guest of an edit folder share in a private space: the tree's relink ran in the owner's name -- the owner must never
# become the one who embedded a file of her own store into bob's text
G2P = wnew(Fr, "Kunde Z/U`nter/Platz", "platz", space="private")
r = Bo.post(B + "/api/wiki/shared/pages", json={"folder_id": wnode(G2P)[1], "name": "Ziel drei", "body": "ziel"})
G2Z = r.json().get("id") if r.status_code == 201 else None
r2 = Bo.post(B + "/api/wiki/shared/pages", json={"folder_id": FN, "name": "Von Bob zwei", "body": f"[[Kunde Z/U`nter/Ziel drei]] ![x](/api/files/nodes/{FIMG}/content) `"})
G2 = r2.json().get("id") if r2.status_code == 201 else None
check(G2Z and G2 and emb(G2, FIMG) == "-", f"#6321 F2 guest setup: bob's two pages in her folders ({r.status_code} {r2.status_code} {r.text[:100]} {r2.text[:100]})")
if G2Z and G2:
    r = Fr.post(B + "/api/wiki/shares", json={"page_id": G2, "kind": "link", "images": True})
    assert r.status_code == 201, r.text
    G2T = r.json().get("url", "").rsplit("/", 1)[-1]
    r = Bo.patch(B + f"/api/files/nodes/{wnode(G2Z)[0]}", json={"parent_id": FN})
    print(f"#6321 F2 guest: the guest's move in the owner's tree answers {r.status_code}, page now {wpath(G2Z)}, embed {emb(G2, FIMG)}", flush=True)
    g = img(G2T, G2, FIMG)
    check(emb(G2, FIMG) in (None, "-") and g == 404, f"#6321 F2 guest: the owner never becomes the one who embedded it ({r.status_code} {emb(G2, FIMG)} {g})")

# ---- F3: an embed without a row (the pages of an account that went before wiki_embeds) is not the next writer's: not
# after a relink, not after a person's save
R3Z = wnew(Ca, "Kniff/Ziel vier", "ziel")
R3 = wnew(Bo, "Kniff/Seite ohne Zeile", f"[[Kniff/Ziel vier]]\n{FREMD}")
R3T = piclink(R3)
dbx("DELETE FROM wiki_embeds WHERE page_id=?", (R3,))
dbx("UPDATE wiki_pages SET updated_by=NULL WHERE id=?", (R3,))
r = Ca.patch(B + f"/api/wiki/pages/{R3Z}", json={"path": "Kniff/Ziel vier neu"})
g = img(R3T, R3, CIMG)
check(r.ok and r.json().get("relinked") == 1 and emb(R3, CIMG) is None and g == 404, f"#6321 F3: an embed without a row is nobody's after carol's relink ({r.status_code} {emb(R3, CIMG)} {g})")
dbx("DELETE FROM wiki_embeds WHERE page_id=?", (R3,))
ok = wsave(Ca, R3, wbody(Ca, R3) + "\nCarol war hier\n").ok
g = img(R3T, R3, CIMG)
check(ok and emb(R3, CIMG) is None and g == 404, f"#6321 F3: and nobody's after carol's own save of the text ({emb(R3, CIMG)} {g})")
full3 = wbody(Ca, R3)
ok = wsave(Ca, R3, full3.replace(FREMD, "\n")).ok and wsave(Ca, R3, full3).ok
g = img(R3T, R3, CIMG)
check(ok and emb(R3, CIMG) == uid["carol"] and g == 200, f"#6321 F3: carol takes it out and puts it in: hers, it comes ({emb(R3, CIMG)} {g})")
# what a person's save turns into an embed is theirs (the picture stood in code before: no embed of the old text)
R3b = wnew(Bo, "Kniff/Erst Code", f"`![x](/api/files/nodes/{OIMG}/content)`\n")
check(emb(R3b, OIMG) == "-" and wsave(Ca, R3b, f"![x](/api/files/nodes/{OIMG}/content)\n").ok and emb(R3b, OIMG) == uid["carol"],
      f"#6321: the save that makes it an embed claims it ({emb(R3b, OIMG)})")

# ---- F4: a page made from a template: never the maker's by making it (was: who made the page); N1 below: only one's own travel
R4V = wnew(Bo, "Vorlagen/Bobs Vorlage", "# Vorlage\n" + FREMD)
r = Ca.post(B + "/api/wiki/pages", json={"space": SPO, "path": "Kniff/Aus Bobs Vorlage", "template_id": R4V})
assert r.status_code == 201, r.text
R4 = r.json()["id"]
R4T = piclink(R4)
g = img(R4T, R4, CIMG)
check(FREMD.strip() in wbody(Ca, R4) and emb(R4, CIMG) is None and g == 404, f"#6321 F4: carol's page from bob's template: the embed is not hers (nobody's, N1), nothing comes ({emb(R4, CIMG)} {g})")
R4W = wnew(Ca, "Vorlagen/Carols Vorlage", "# Vorlage\n" + FREMD)
r = Bo.post(B + "/api/wiki/pages", json={"space": SPO, "path": "Kniff/Aus Carols Vorlage", "template_id": R4W})
assert r.status_code == 201, r.text
R4b = r.json()["id"]
R4bT = piclink(R4b)
g = img(R4bT, R4b, CIMG)
# 2.1284.0 (#6321, re-check N1): was "her embed stays hers and comes" -- bob only reads the template and would carry carol's
# embed, with her name on it, to a page he chooses; only one's own embeds travel with a template
check(emb(R4b, CIMG) is None and g == 404, f"#6321 N1: bob's page from carol's template: her embed does not travel, nobody's, nothing comes ({emb(R4b, CIMG)} {g})")
r = Ca.post(B + "/api/wiki/pages", json={"space": SPO, "path": "Kniff/Aus Carols eigener Vorlage", "template_id": R4W})
assert r.status_code == 201, r.text
R4c = r.json()["id"]
g = img(piclink(R4c), R4c, CIMG)
check(emb(R4c, CIMG) == uid["carol"] and g == 200, f"#6321 N1: carol's page from her own template: her embed stays hers and comes ({emb(R4c, CIMG)} {g})")

# ---- F5: a space's lock goes off -- the browser of whoever switches sends every plain text back: nobody's pictures (was:
# all of them the switching person's). carol's private space: lock on (the rows go), lock off
def _b64(n):
    return base64.b64encode(os.urandom(n)).decode()


def _b64u(n):
    return base64.urlsafe_b64encode(os.urandom(n)).decode().rstrip("=")


def _ct():
    return "e2e1:" + json.dumps({"v": 1, "g": 1, "iv": _b64(12), "ct": _b64(48)}, separators=(",", ":"))


PIMG = upload(Ca, "tresor.png", png(7, 7), "image/png", space="private")
R5 = wnew(Ca, "Tresor/Bild", f"# Tresor\n\n![T](/api/files/nodes/{PIMG}/content)\n", space="private")
check(emb(R5, PIMG) == uid["carol"], f"#6321 F5 setup: carol's own embed in her private page ({emb(R5, PIMG)})")
r = Ca.put(B + "/api/e2e/keys", json={
    "pub": {"kty": "EC", "crv": "P-256", "x": _b64u(32), "y": _b64u(32), "ext": True, "key_ops": []},
    "bundle_pass": {"v": 1, "kdf": "pbkdf2-sha256", "iter": 600000, "salt": _b64(16), "iv": _b64(12), "ct": _b64(200)},
    "bundle_rec": {"v": 1, "kdf": "hkdf-sha256", "salt": _b64(16), "iv": _b64(12), "ct": _b64(200)}})
assert r.ok, r.text
r = Ca.post(B + "/api/wiki/e2e/start", json={"space": "private", "keys": [{"user_id": uid["carol"], "wrapped": {"v": 1, "iv": _b64(12), "ct": _b64(48)}}]})
check(r.ok and r.json().get("mode") == "encrypting", f"#6321 F5 setup: the lock of her private space starts ({r.status_code} {r.text[:200]})")
todo = Ca.get(B + "/api/wiki/e2e/todo", params={"space": "private"}).json().get("pages", [])
r = Ca.post(B + "/api/wiki/e2e/bulk", json={"space": "private", "pages": [{"id": x["id"], "path": _ct(), **({"body": _ct()} if x.get("body") else {})} for x in todo]})
r2 = Ca.post(B + "/api/wiki/e2e/finish", json={"space": "private"})
check(r.ok and r2.ok and r2.json().get("mode") == "on" and emb(R5, PIMG) == "-", f"#6321 F5 setup: behind the lock, no rows ({r.status_code} {r2.status_code} {r2.text[:160]} {emb(R5, PIMG)})")
r = Ca.post(B + "/api/wiki/e2e/stop", json={"space": "private", "password": "password123"})
check(r.ok and r.json().get("mode") == "decrypting", f"#6321 F5 setup: the lock goes off ({r.status_code} {r.text[:200]})")
r = Ca.post(B + "/api/wiki/e2e/bulk", json={"space": "private", "pages": [{"id": x["id"], "path": x["path"], **({"body": x["body"]} if x.get("body") else {})} for x in todo]})
r2 = Ca.post(B + "/api/wiki/e2e/finish", json={"space": "private"})
check(r.ok and r2.ok and r2.json().get("mode") is None and f"/api/files/nodes/{PIMG}/content" in wbody(Ca, R5), f"#6321 F5 setup: open again, the text is back ({r.status_code} {r.text[:160]} {r2.text[:160]})")
check(emb(R5, PIMG) is None, f"#6321 F5: the pictures of a text that came out of the lock are nobody's ({emb(R5, PIMG)})")
full5 = wbody(Ca, R5)
check(wsave(Ca, R5, "# Tresor\n").ok and wsave(Ca, R5, full5).ok and emb(R5, PIMG) == uid["carol"], f"#6321 F5: taken out and put in again, it is hers ({emb(R5, PIMG)})")

# ---- 2.1368.0 (#6657, re-check N4): bob embeds carol's picture and takes it out again; carol saves from her editor's state of
# before ("Keep mine" over bob's save, or through the API without expect_updated_at) -- the picture comes back with her text
# and was hers (carol sees the file: it came through her link) without her ever putting it in. Now nobody's
N4P = wnew(Ca, "Kniff/Alter Stand", "start\n")
N4T = piclink(N4P)
check(wsave(Bo, N4P, "start\n" + FREMD).ok and emb(N4P, CIMG) == uid["bob"], f"#6657 N4 setup: bob embeds carol's picture ({emb(N4P, CIMG)})")
stale4 = Ca.get(B + f"/api/wiki/pages/{N4P}").json()
check(wsave(Bo, N4P, "start\n").ok and emb(N4P, CIMG) == "-", f"#6657 N4 setup: bob takes it out again ({emb(N4P, CIMG)})")
r = Ca.patch(B + f"/api/wiki/pages/{N4P}", json={"body": stale4["body"] + "\nCarol\n", "expect_updated_at": stale4["updated_at"]})
check(r.status_code == 409 and r.json().get("page", {}).get("updated_at"), f"#6657 N4 setup: carol's save from the old state meets bob's save (409) ({r.status_code})")
r = Ca.patch(B + f"/api/wiki/pages/{N4P}", json={"body": stale4["body"] + "\nCarol\n", "expect_updated_at": r.json()["page"]["updated_at"], "overwrite": True})
g = img(N4T, N4P, CIMG)
check(r.ok and FREMD.strip() in wbody(Ca, N4P) and emb(N4P, CIMG) is None and g == 404,
      f"#6657 N4: \"Keep mine\" (overwrite) brings the picture back as nobody's, nothing comes ({r.status_code} {emb(N4P, CIMG)} {g})")
check(wsave(Bo, N4P, "start\n").ok and emb(N4P, CIMG) == "-", "#6657 N4 setup: out again")
r = Ca.patch(B + f"/api/wiki/pages/{N4P}", json={"body": stale4["body"]})
g = img(N4T, N4P, CIMG)
check(r.ok and emb(N4P, CIMG) is None and g == 404, f"#6657 N4: a save without expect_updated_at: nobody's ({r.status_code} {emb(N4P, CIMG)} {g})")
check(wsave(Ca, N4P, "start\n").ok and wsave(Ca, N4P, stale4["body"]).ok and emb(N4P, CIMG) == uid["carol"] and img(N4T, N4P, CIMG) == 200,
      f"#6657 N4: carol's own save on the current state puts it in: hers, it comes ({emb(N4P, CIMG)})")

# ---- the guard: every place of the app that writes a page's text keeps wiki_embeds (pages.wiki_set_links, or the plain
# DELETE of a text that goes behind a space's lock) -- a new write of wiki_pages.body without it is red here
WRITES = re.compile(r"UPDATE wiki_pages SET (?:[^\"\n]*\bbody\s*=|\{)|INSERT INTO wiki_pages\b|DELETE FROM wiki_links\b")
KEEPS = re.compile(r"\bwiki_set_links\(|\bwem_embeds_(?:set|drop)\(|DELETE FROM wiki_embeds\b")
# 2.1284.0 (#6321, review 1): and only the places where a person or an agent saves a text they wrote may CLAIM (pass by / old
# to wiki_set_links, or call wem_embeds_set with them): a new page, the save, the page files' import and list, the
# organisation import (the matched last editor). A relink, a move, a restore, a lock that goes off never do -- a new
# claiming place is red here until it is named
CLAIMS = {"pages.py:wiki_set_links", "pages.py:wiki_insert", "pages.py:wiki_update", "wikiatt.py:_wka_save", "oi_store.py:_finish_wiki"}
bare, seen, claims = [], 0, set()
for root, _dirs, files in os.walk(os.path.join(os.path.dirname(N), "kalmido")):
    for fn in files:
        if not fn.endswith(".py") or os.sep + "migrations.d" in root:
            continue
        src = open(os.path.join(root, fn), encoding="utf-8").read()
        if not WRITES.search(src) and "wiki_set_links" not in src and "wem_embeds_set" not in src:
            continue
        tree = ast.parse(src)
        for f in tree.body:
            seg = ast.get_source_segment(src, f) or ""
            for x in ast.walk(f):
                if (isinstance(x, ast.Call) and getattr(x.func, "id", getattr(x.func, "attr", "")) in ("wiki_set_links", "wem_embeds_set")
                        and len(x.args) + len(x.keywords) > 3):
                    claims.add(f"{fn}:{getattr(f, 'name', f.lineno)}")
            if WRITES.search(seg):
                seen += 1
                if not KEEPS.search(seg):
                    bare.append(f"{fn}:{getattr(f, 'name', f.lineno)}")
check(seen >= 10 and not bare, f"#6321: every write of a page's text keeps wiki_embeds ({seen} places; without: {bare})")
check(claims == CLAIMS, f"#6321: only a person's own save of a text claims a picture (unexpected: {sorted(claims - CLAIMS)}, missing: {sorted(CLAIMS - claims)})")
check(KEEPS.search("c.execute('UPDATE wiki_pages SET body=? WHERE id=?')") is None and WRITES.search('"UPDATE wiki_pages SET body=?, attrs=?"')
      and WRITES.search('f"UPDATE wiki_pages SET {cols}"') and not WRITES.search('"UPDATE wiki_pages SET path=? WHERE id=?"'),
      "#6321: the guard's patterns tell a text write from a rename")

# ================================================================== 2.1368.0 (#6868), 2.1401.0 (#7056): a move under a share with pictures
# carol embeds a picture only she sees (CIMG) and one bob sees too (OIMG) into her page; carol has a folder link with pictures
# on another folder. bob (writes the wiki, does not see CIMG) moves her page under that link -- the row said carol, so the
# picture came through the link. 2.1401.0 (#7056): the check sits at the output: a share shows a picture only when the row
# is confirmed for exactly that share (its embedder's save under it, or its pictures switched on over the page) -- no way of
# moving a page confirms anything (Fable re-check of 2.1368: F1 the trash, F6 a folder merged into another, F7 a round trip
# through another workspace; was: wem_after_move on three of the ways, the others open). The rows stay whose they are.
def mvpage(path, s=None):
    return wnew(s or Ca, path, f"# Seite\n\n![Nur Carol](/api/files/nodes/{CIMG}/content)\n\n![Offen](/api/files/nodes/{OIMG}/content)\n")


M0 = mvpage("Galerie6868/Drin")
r = Ca.post(B + "/api/wiki/shares", json={"space": SPO, "folder": "Galerie6868", "kind": "link"})
assert r.status_code == 201, r.text
check(img(r.json().get("url", "").rsplit("/", 1)[-1], M0, CIMG) == 404, "#7056: a link without pictures confirms nothing")
assert A.patch(B + f"/api/wiki/shares/{r.json()['id']}", json={"images": True}).ok
MS, MT = r.json()["id"], r.json().get("url", "").rsplit("/", 1)[-1]


def oks(pid, nid):
    """The shares picture nid of page pid is confirmed for (wiki_embeds.shares), "-" = no row."""
    r = dbx("SELECT shares FROM wiki_embeds WHERE page_id=? AND node_id=?", (pid, nid))
    v = r[0][0] if r else "-"
    return "-" if v == "-" else sorted((json.loads(v) if isinstance(v, str) else v) or [])


check(img(MT, M0, CIMG) == 200 and emb(M0, CIMG) == uid["carol"] and oks(M0, CIMG) == [f"w{MS}"],
      f"#7056 setup: the pictures switched on (by alice, the admin): carol's picture is confirmed for her link and comes ({oks(M0, CIMG)})")
r = Bo.patch(B + f"/api/wiki/pages/{M0}", json={"path": "Galerie6868/Drin neu"})
g = img(MT, M0, CIMG)
check(r.ok and g == 200 and emb(M0, CIMG) == uid["carol"], f"#6868: bob renames the page under the same link: the picture stays ({r.status_code} {g} {emb(M0, CIMG)})")
M1 = mvpage("Quelle6868/Eins")
r = Bo.patch(B + f"/api/wiki/pages/{M1}", json={"path": "Galerie6868/Eins"})
g = (img(MT, M1, CIMG), img(MT, M1, OIMG))
check(r.ok and wpath(M1) == "Galerie6868/Eins" and emb(M1, CIMG) == uid["carol"] and oks(M1, CIMG) == [] and g == (404, 404),
      f"#7056: bob moves carol's page under her link (PATCH path): the rows stay hers, nothing is confirmed, nothing comes ({r.status_code} {emb(M1, CIMG)} {oks(M1, CIMG)} {g})")
M2 = mvpage("Quelle6868b/Zwei")
r = Bo.post(B + "/api/wiki/move", json={"space": SPO, "from": "Quelle6868b", "to": "Galerie6868/Quelle"})
g = img(MT, M2, CIMG)
check(r.ok and wpath(M2) == "Galerie6868/Quelle/Zwei" and g == 404,
      f"#6868: the same when bob moves the folder of the page (/api/wiki/move) ({r.status_code} {r.text[:100]} {emb(M2, CIMG)} {g})")
M3 = mvpage("Quelle6868c/Drei")
r = Bo.patch(B + f"/api/files/nodes/{wnode(M3)[0]}", json={"parent_id": wnode(M0)[1]})
g = img(MT, M3, CIMG)
check(r.ok and wpath(M3) == "Galerie6868/Drei" and g == 404,
      f"#6868: the same when bob moves the page in the tree ({r.status_code} {r.text[:100]} {wpath(M3)} {emb(M3, CIMG)} {g})")
# 2.1401.0 (#7056, re-check F2 / Meadows F1): the trash -- bob puts carol's page into the trash, moves its folder under the
# link (the page in the trash follows), takes it back out
M5 = mvpage("Quelle7056e/Fuenf")
wnew(Bo, "Quelle7056e/Bleibt", "bleibt")  # a live page, so the folder moves
check(Bo.delete(B + f"/api/wiki/pages/{M5}").ok, "#7056 F2 setup: bob puts carol's page into the trash")
r = Bo.post(B + "/api/wiki/move", json={"space": SPO, "from": "Quelle7056e", "to": "Galerie6868/Quelle7056e"})
check(r.ok, f"#7056 F2 setup: bob moves the folder under the link ({r.status_code} {r.text[:120]})")
r = Bo.post(B + "/api/wiki/restore", json={"ids": [M5]})
g = (img(MT, M5, CIMG), img(MT, M5, OIMG))
check(r.ok and wpath(M5).startswith("Galerie6868/") and emb(M5, CIMG) == uid["carol"] and g == (404, 404),
      f"#7056 F2: back from the trash under carol's link: nothing comes ({r.status_code} {r.text[:120]} {wpath(M5)} {emb(M5, CIMG)} {g})")
# F6: the share wanders to the pages -- carol's link with pictures on the folder Pub7056; bob merges Pub7056 into the
# existing folder Intern7056: the link follows its folder and now covers carol's internal page there
PUB = mvpage("Pub7056/Offen")
r = Ca.post(B + "/api/wiki/shares", json={"space": SPO, "folder": "Pub7056", "kind": "link", "images": True})
assert r.status_code == 201, r.text
PS, PT = r.json()["id"], r.json().get("url", "").rsplit("/", 1)[-1]
check(img(PT, PUB, CIMG) == 200 and oks(PUB, CIMG) == [f"w{PS}"], f"#7056 F6 setup: a link made with pictures confirms the pictures of its pages now ({oks(PUB, CIMG)})")
INT = mvpage("Intern7056/Geheim")
r = Bo.post(B + "/api/wiki/move", json={"space": SPO, "from": "Pub7056", "to": "Intern7056"})
g = (img(PT, INT, CIMG), img(PT, INT, OIMG), img(PT, PUB, CIMG))
check(r.ok and wpath(PUB) == "Intern7056/Offen" and requests.get(B + f"/s/w/{PT}/p/{INT}").ok and g == (404, 404, 200),
      f"#7056 F6: bob merges the shared folder into another: the link covers carol's internal page, its pictures never come; the page shared before keeps its picture ({r.status_code} {r.text[:120]} {g})")
# F7: a round trip through another workspace -- alice (the admin) takes carol's page out of the organisation into her
# private space and brings it back with dest under carol's link
M6 = mvpage("Quelle7056f/Sechs")
r = A.post(B + "/api/wiki/move-space", json={"space": SPO, "to": "private", "pages": [M6]})
check(r.ok, f"#7056 F7 setup: alice moves carol's page into her private space ({r.status_code} {r.text[:160]})")
r = A.post(B + "/api/wiki/move-space", json={"space": "private", "to": SPO, "pages": [M6], "dest": "Galerie6868"})
g = img(MT, M6, CIMG)
check(r.ok and (wpath(M6) or "").startswith("Galerie6868/") and g == 404,
      f"#7056 F7: back under carol's link: nothing comes ({r.status_code} {r.text[:160]} {wpath(M6)} {emb(M6, CIMG)} {g})")
assert wsave(Ca, M6, wbody(Ca, M6) + "\ncarol\n").ok  # its last editor carol again (the import below matches no person but alice)
# who sees the file and moves the page changes nothing either (was: carol's own move kept it, #6868); a later save of the
# text confirms nothing that stood there already (reader F1 of job/5494: bob pushes carol's page under a link, her next typo
# fix would have sent her picture out) -- only a picture put in there by its embedder is confirmed for the link
M4 = mvpage("Quelle6868d/Vier")
r = Ca.patch(B + f"/api/wiki/pages/{M4}", json={"path": "Galerie6868/Vier"})
g = img(MT, M4, CIMG)
check(r.ok and emb(M4, CIMG) == uid["carol"] and g == 404, f"#7056: carol (who sees it) moves her page under the link: not confirmed ({emb(M4, CIMG)} {g})")
check(wsave(Bo, M4, wbody(Bo, M4) + "\nbob\n").ok and img(MT, M4, CIMG) == 404 and img(MT, M4, OIMG) == 404,
      f"#7056: bob's save confirms nothing (the pictures are carol's) {oks(M4, OIMG)}")
check(wsave(Ca, M4, wbody(Ca, M4) + "\ncarol\n").ok and img(MT, M4, CIMG) == 404 and oks(M4, CIMG) == [],
      f"#7056 reader F1: carol's typo fix confirms none of the pictures standing there ({oks(M4, CIMG)})")
check(img(MT, M1, CIMG) == 404 and wsave(Ca, M1, wbody(Ca, M1) + "\ncarol\n").ok and img(MT, M1, CIMG) == 404,
      f"#7056 reader F1: bob pushed her page under the link, her next save does not send her picture out ({oks(M1, CIMG)})")
full4 = wbody(Ca, M4)
check(wsave(Ca, M4, full4.replace(f"![Nur Carol](/api/files/nodes/{CIMG}/content)", "")).ok and wsave(Ca, M4, full4).ok
      and img(MT, M4, CIMG) == 200 and oks(M4, CIMG) == [f"w{MS}"],
      f"#7056: carol takes her picture out and puts it in under the link: confirmed for it, it comes ({oks(M4, CIMG)})")
# reader F2: alice (admin) switches on the pictures of carol's link: only what alice sees, too, is confirmed (CIMG only carol)
M7 = mvpage("Galerie7056g/Sieben")
r = Ca.post(B + "/api/wiki/shares", json={"space": SPO, "folder": "Galerie7056g", "kind": "link"})
assert r.status_code == 201, r.text
S7, T7 = r.json()["id"], r.json().get("url", "").rsplit("/", 1)[-1]
see_a = A.get(B + f"/api/files/nodes/{CIMG}").ok
assert A.patch(B + f"/api/wiki/shares/{S7}", json={"images": True}).ok
g = (img(T7, M7, CIMG), img(T7, M7, OIMG))
check(g == ((200 if see_a else 404), 200), f"#7056 reader F2: the admin's switch confirms only what the admin sees too (alice sees CIMG: {see_a}) {g}")

# ================================================================== #2398: polls and bookmarks move with the organisation
A.patch(B + "/api/settings", json={"workspace": f"org:{ORG}"})
put_feed("pic.png", PNG)
put_feed("page.html", '<!doctype html><html><head><meta charset="utf-8"><title>Beispielseite</title><meta property="og:image" content="/pic.png">'
                      '</head><body><p>Ein paar Worte Text auf der Seite, damit es etwas zu lesen gibt.</p></body></html>')
r = A.post(B + "/api/polls", json={"title": "Teamtreffen", "duration": 60, "space": f"org:{ORG}",
                                   "options": [{"start": f"{D}T10:00"}, {"start": f"{D}T14:00"}]})
check(r.status_code == 201, "an organisation poll " + r.text[:200])
POLL = r.json().get("poll", {})
OPTS = [o["id"] for o in POLL.get("options", [])]
OLD_TOK = (POLL.get("url") or "").rsplit("/", 1)[-1]
NOW = iso_s(tnow())
if len(OPTS) == 2:
    dbx("INSERT INTO sched_poll_votes(poll_id,name,email,answers,edit_hash,ip_hash,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
        (POLL["id"], "Gast Beispiel", "", json.dumps({str(OPTS[0]): "y", str(OPTS[1]): "n"}), "x" * 64, "iphash", NOW, NOW))
r = A.post(B + "/api/polls", json={"title": "Privates Treffen", "duration": 30, "space": "private",
                                   "options": [{"start": f"{D}T09:00"}, {"start": f"{D}T11:00"}]})
check(r.status_code == 201, "a private poll " + r.text[:200])
r = A.post(B + "/api/bookmarks", json={"url": FEED + "page.html", "space": f"org:{ORG}"})
check(r.status_code == 201, "an organisation bookmark " + r.text[:200])
BM = r.json().get("bookmark", {}).get("id")
bm = until(lambda: (lambda j: j if j.get("preview") not in ("pending", "image") else None)(A.get(B + f"/api/bookmarks/{BM}").json()), 30) or {}
check(bm.get("image", "").startswith(f"/api/bookmarks/{BM}/image"), "the bookmark has its picture " + json.dumps(bm)[:200])
check(A.post(B + "/api/bookmarks", json={"url": FEED + "page.html?privat=1", "space": "private"}).status_code == 201, "a private bookmark")
r = A.post(B + f"/api/orgs/{ORG}/export")
check(r.status_code == 202, "organisation export started " + r.text[:120])
until(lambda: A.get(B + f"/api/orgs/{ORG}/export").json().get("state") != "running", 240)
OX = su_get(A, B + f"/api/orgs/{ORG}/export/file").content
RK = A.post(B + f"/api/orgs/{ORG}/encryption/recovery", json={"password": "password123"}).json().get("recovery_key", "")
check(OX[:13] == b"KALMIDO-ORGX\n" and RK, "the organisation export + recovery key")
iid = imp_upload(A, OX)
j = imp_wait(A, iid)
if j.get("state") == "key":
    check(A.post(B + f"/api/account/import/{iid}/key", json={"recovery_key": RK}).status_code == 202, "the recovery key is taken")
    j = imp_wait(A, iid)
check(j.get("state") == "preview", f"the export opens {j.get('state')} {j.get('error')}")
r = A.post(B + f"/api/account/import/{iid}/run", json={"again": True, "target": ORG2, "people": {}})
check(r.status_code == 202, "the import runs " + r.text[:160])
j = imp_wait(A, iid)
check(j.get("state") == "done", f"imported into the empty organisation {j.get('state')} {j.get('error')}")
polls = dbx("SELECT id, title, token_hash, chosen_id FROM sched_polls WHERE org_id=? AND deleted_at IS NULL", (ORG2,))
check([p[1] for p in polls] == ["Teamtreffen"], f"#2398: the organisation's poll came along, the private one not {polls}")
NP = polls[0][0] if polls else 0
check(polls and not polls[0][2].startswith("import:") and polls[0][2] != one("SELECT token_hash FROM sched_polls WHERE id=?", (POLL.get("id"),)),
      "#2398: the poll has a new link")
nopts = [x[0] for x in dbx("SELECT id FROM sched_poll_options WHERE poll_id=? ORDER BY start", (NP,))]
check(len(nopts) == 2 and not set(nopts) & set(OPTS), f"#2398: its options came along {nopts}")
votes = dbx("SELECT name, answers, ip_hash, edit_hash FROM sched_poll_votes WHERE poll_id=?", (NP,))
check(votes and votes[0][3] and votes[0][3] != "x" * 64, "#2398 review: the vote gets a new edit hash, never the exported one")
ans = json.loads(votes[0][1]) if votes else {}
check(len(votes) == 1 and votes[0][0] == "Gast Beispiel" and len(nopts) == 2 and ans == {str(nopts[0]): "y", str(nopts[1]): "n"} and votes[0][2] == "",
      f"#2398: the vote came along and names the new options {votes}")
NT = A.get(B + f"/api/polls/{NP}").json().get("poll", {}).get("url", "") if NP else ""
check(NT and requests.get(NT.replace(NT.split("/s/v/")[0], B.rstrip("/"))).ok, "#2398: the new link opens " + NT)
check(OLD_TOK and requests.get(B + "/s/v/" + OLD_TOK).ok, "the old organisation's link still works (it was not removed)")
check("new links" in json.dumps(j), "#2398: the import report says the poll links are new")
bms = dbx("SELECT id, url, image FROM bookmarks WHERE org_id=? AND deleted_at IS NULL", (ORG2,))
check(len(bms) == 1 and bms[0][1] == FEED + "page.html" and bms[0][2].startswith("bookmarks/"), f"#2398: the organisation's bookmark came along {bms}")
A.patch(B + "/api/settings", json={"workspace": f"org:{ORG2}"})
q = A.get(B + f"/api/bookmarks/{bms[0][0]}/image") if bms else None
check(q is not None and q.ok and q.content == PNG, f"#2398: its picture opens ({q.status_code if q is not None else '-'})")

# ================================================================== 2.1284.0 (#6321): the embedders after an import and of the pages of before
# the organisation import above wrote the pages of ORG into ORG2: the export carries no embedders, the page's last editor as
# matched here stands in; here nobody matched (updated_by empty), so the embeds are nobody's (review 1 F3: rows with
# user_id NULL, was: no row and "the first person who writes the text") until a person takes one out and puts it in again
imp = dbx("SELECT p.id, p.updated_by, (SELECT COUNT(*) FROM wiki_embeds e WHERE e.page_id=p.id AND e.user_id IS NOT NULL) FROM wiki_pages p WHERE p.org_id=? ORDER BY 1", (ORG2,))
texts = {x[0]: A.get(B + f"/api/wiki/pages/{x[0]}").json().get("body", "") for x in imp}
IP, IN = next(((k, int(m.group(1))) for k, t in texts.items() for m in [re.search(r"!\[[^\]]*\]\(/api/files/nodes/(\d+)/content\)", t)] if m), (None, None))
check(IP is not None and all(x[1] is None and x[2] == 0 for x in imp) and emb(IP, IN) is None, f"#6321: the embeds of an imported page whose editor matched nobody are nobody's {imp} {IP} {emb(IP, IN) if IP else None}")
check(IP is not None and wsave(A, IP, texts[IP] + "\nübernommen\n").ok and emb(IP, IN) is None, f"#6321 F3: the first person who writes its text does not take them over ({emb(IP, IN) if IP else None})")
check(IP is not None and wsave(A, IP, "leer\n").ok and wsave(A, IP, texts[IP]).ok and emb(IP, IN) == ALICE, f"#6321: taken out and put in by alice, it is hers ({emb(IP, IN) if IP else None})")
# the pages written before wiki_embeds: at the first start (no "wem_since6321") every embed gets the page's last editor (the
# rule of #6295), nobody when the page has no editor (review 1 F3); a page that has rows already keeps them. Simulated: the
# rows of all pages but one go, the start step's mark goes, the server restarts
dbx("UPDATE wiki_pages SET updated_by=NULL WHERE id=?", (R3,))
before = dbx("SELECT e.page_id, e.node_id, p.updated_by FROM wiki_embeds e JOIN wiki_pages p ON p.id=e.page_id "
             "WHERE e.page_id<>? ORDER BY 1, 2", (BQ,))
dbx("UPDATE wiki_pages SET updated_by=? WHERE id=?", (uid["carol"], BQ))
dbx("DELETE FROM wiki_embeds WHERE page_id<>?", (BQ,))
dbx("DELETE FROM settings WHERE key='wem_since6321'")
g = img(GT, GP, OIMG)
check(g == 404, f"#6321: no row = no picture ({g})")


def up():
    try:
        return requests.get(B + "/api/health", timeout=2).ok
    except requests.RequestException:
        return False


def restart():
    subprocess.run(["docker", "restart", CT], capture_output=True)
    return until(up, 60)


check(restart(), "#6321: the server is up again")
after = dbx("SELECT page_id, node_id, user_id FROM wiki_embeds WHERE page_id<>? ORDER BY 1, 2", (BQ,))
check(len(before) >= 6 and after == before, f"#6321: the start step gives every embed of before the page's last editor {before} -> {after}")
check(any(tuple(x) == (R3, CIMG, None) for x in after), f"#6321 F3: a page without an editor: its embeds are nobody's (a row, not none) {[x for x in after if x[0] == R3]}")
g = (img(BT, BQ, CIMG), img(GT, GP, OIMG))
since = one("SELECT value FROM settings WHERE key='wem_since6321'")
check(since and emb(BQ, CIMG) == uid["bob"] and g[0] == 404,
      f"#6321: the first pass is marked, and a page with rows keeps them (bob's embed stays bob's though carol is its last editor) ({since} {emb(BQ, CIMG)} {g})")
check(g[1] == 200, f"#6321: the pictures come again {g}")
# review 1 F6: every later start looks at the pages changed since the start before (a version without wiki_embeds ran in
# between, a rollback): a row whose picture left the text goes, an embed without a row is nobody's -- never the last
# editor's any more; a page not changed since is not touched
dbx("UPDATE wiki_embeds SET node_id=999999 WHERE page_id=? AND node_id=?", (GP, CIMG))
dbx("UPDATE wiki_pages SET updated_at=CAST(? AS timestamptz) + interval '1 second' WHERE id=?", (since, GP))
dbx("INSERT INTO wiki_embeds(page_id,node_id,user_id,created_at) VALUES(?,999998,?,now())", (R4, uid["carol"]))
check(restart(), "#6321 F6: the server is up again")
# 2.1368.0 (#6657): was "the rest stays" -- the page's updated_at was set by hand, not by this version (its stamp wem_at stayed
# behind): then nobody stands for any of its pictures (re-check N2), also the one that stayed in the text
check(emb(GP, 999999) == "-" and emb(GP, CIMG) is None and emb(GP, OIMG) is None and upd(GP) == uid["carol"],
      f"#6321 F6 / #6657: a page changed since the last start: the stale row went, the embed without a row is nobody's, written without the stamp: all nobody's ({emb(GP, 999999)} {emb(GP, CIMG)} {emb(GP, OIMG)})")
check(emb(R4, 999998) == uid["carol"] and one("SELECT value FROM settings WHERE key='wem_since6321'") > since,
      f"#6321 F6: a page not changed since is not opened again ({emb(R4, 999998)})")
dbx("DELETE FROM wiki_embeds WHERE node_id=999998")

# ---- 2.1368.0 (#6657, re-check N2): under a version without the stamp (a rollback; here a write by hand) carol takes her
# picture out and bob puts it in again -- the text is the same, the row still says carol. The stamp (wem_at) stayed behind:
# the next start sets all rows of the page to nobody; a page this version wrote keeps its rows
N2P = wnew(Ca, "Kniff/Rueckfall", "# R\n" + FREMD)
N2T = piclink(N2P)
check(emb(N2P, CIMG) == uid["carol"] and img(N2T, N2P, CIMG) == 200 and one("SELECT wem_at=updated_at FROM wiki_pages WHERE id=?", (N2P,)),
      f"#6657 N2 setup: carol's picture comes, the page is stamped ({emb(N2P, CIMG)})")
check(wsave(Ca, R4c, wbody(Ca, R4c) + "\nneu\n").ok and one("SELECT wem_at=updated_at FROM wiki_pages WHERE id=?", (R4c,)),
      "#6657: a save of this version stamps the page")
dbx("UPDATE wiki_pages SET updated_at=now(), updated_by=? WHERE id=?", (uid["bob"], N2P))
check(one("SELECT wem_at<>updated_at FROM wiki_pages WHERE id=?", (N2P,)), "#6657 N2 setup: a write without this version leaves the stamp behind")
check(restart(), "#6657 N2: the server is up again")
g = img(N2T, N2P, CIMG)
check(emb(N2P, CIMG) is None and g == 404, f"#6657 N2: the page written without the stamp: its picture is nobody's, nothing comes ({emb(N2P, CIMG)} {g})")
check(emb(R4c, CIMG) == uid["carol"] and img(piclink(R4c), R4c, CIMG) == 200, f"#6657 N2: a page this version wrote keeps its rows ({emb(R4c, CIMG)})")
check(one("SELECT COUNT(*) FROM wiki_pages WHERE wem_at IS DISTINCT FROM updated_at") == 0, "#6657 N2: the start stamped every page")

print(f"p2380r_h_api: {OKS[0]} ok, {len(FAILS)} failed", flush=True)
sys.exit(1 if FAILS else 0)
