#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1287.0 (#6470): the office log keeps the name of the person who wrote an entry (office_doc_log.user_name, sealed like
the detail), and a finalised document the name of who finalised it (sender.locked_by_name) - so a deleted account (user_id
ON DELETE SET NULL) still shows who finalised and booked. Invented names only. Starts its OWN container (with a server key,
so the sealing is on) and restarts it once keeping the database.
 - an organisation: Bea (admin) finalises an invoice and books a payment; her log entries carry her name sealed (kenc1:);
   her account is deleted -> the log (GET /api/office/log), the invoice's locked_by_name and the tax auditor's export
   (log.csv, column Person) still name her; the hash chain of the finalised documents stays intact
 - an entry from before 2.1287 (no name, the marker of the one-time fill removed, a quotation finalised without the name
   in its sender): the restart fills the name from users once (sealed); after the account is deleted the quotation's
   locked_by_name comes from its finalise entry
 - a person without an organisation (freelancer fixture): the own log entries carry the name too. Deleting the account
   is n/a there: the personal office goes with the account (nobody is left to read its log).
usage: p21287_b_logname_test.py <datadir>"""
# freelancer-matrix: office
import base64
import csv
import io
import os
import sys
import zipfile
from datetime import date, timedelta

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
import kt  # noqa: E402
from freelancer_fixture import FEATURES, freelancer  # noqa: E402
from kt import B, check, done, sess  # noqa: E402

KEY = base64.b64encode(os.urandom(32)).decode()
OFF = "/api/office"
D = OFF + "/docs"
FEAT = FEATURES if "office" in FEATURES else FEATURES + ",office"
COMPANY = {"name": "Studio Beispiel", "street": "Hafenweg 2", "zip": "12345", "city": "Musterstadt", "country": "DE",
           "iban": "DE02120300000000202051", "tax_number": "12/345/67890"}


def one(sql, args=()):
    r = kt.dbx(sql, args)
    return r[0][0] if r else None


def office(s):
    check(s.put(B + OFF + "/settings", json={"company_fields": COMPANY, "lang": "en", "currency": "EUR"}).ok, "office settings")
    r = s.post(B + "/api/clients", json={"name": "Kundin Muster", "email": "kundin@example.com", "street": "Musterweg 1",
                                         "zip": "12345", "city": "Musterstadt", "country": "DE"})
    check(r.status_code == 201, "client " + r.text[:200])
    return r.json().get("id")


def invoice(s, cl, title, kind="invoice"):
    r = s.post(B + D, json={"kind": kind, "client_id": cl, "project_title": title, "service_from": "2026-05-01",
                            "items": [{"title": "Beratung", "qty": 1, "rate": 300, "unit": "flat"}]})
    check(r.status_code in (200, 201), f"{kind} {title} " + r.text[:200])
    did = r.json().get("id")
    r = s.post(B + f"{D}/{did}/finalize")
    check(r.ok and r.json().get("locked"), f"{kind} {title} finalised {r.status_code} {r.text[:200]}")
    return did


def log_names(s, did):
    r = s.get(B + OFF + "/log", params={"limit": 500})
    check(r.ok, "the office log " + r.text[:200])
    return {(x["action"], x.get("user_id"), x.get("user_name")) for x in r.json().get("log") or [] if x.get("doc_id") == did}


def gobd_person(s, did):
    r = s.get(B + OFF + "/gobd/export", params={"from": (date.today() - timedelta(days=30)).isoformat(), "to": date.today().isoformat()})
    check(r.ok, f"the tax auditor's export {r.status_code}")
    if not r.ok:
        return set()
    z = zipfile.ZipFile(io.BytesIO(r.content))
    rows = list(csv.reader(io.StringIO(z.read("log.csv").decode("utf-8"), newline=""), delimiter=";", quotechar='"'))
    return {(x[3], x[2]) for x in rows if x and x[-1] == str(did)}


kt.fresh(env={"KALMIDO_SECRET_KEY": KEY}, prefix="P21287B")
A = kt.setup()
A.patch(B + "/api/settings", json={"lang": "en", "features": FEAT, "tour": "done"})
ALICE = A.get(B + "/api/state").json()["me"]["id"]
r = A.post(B + "/api/admin/orgs", json={"name": "Alpha", "admin_id": ALICE})
assert r.status_code == 201, r.text
ORG = r.json()["id"]
A.patch(B + "/api/settings", json={"workspace": f"org:{ORG}"})
CL = office(A)
U = {}
for u, name in (("bea", "Bea Beispiel"), ("carl", "Carl Muster")):
    r = A.post(B + "/api/users", json={"orgs": [{"id": ORG, "role": "admin"}], "username": u, "display_name": name,
                                       "password": "password123", "email": f"{u}@example.com"})
    check(r.ok, f"setup: {u} as admin of the organisation " + r.text[:200])
    U[u] = r.json().get("id")
Be, Ca = sess("bea"), sess("carl")
for s in (Be, Ca):
    s.patch(B + "/api/settings", json={"lang": "en", "features": FEAT, "tour": "done", "workspace": f"org:{ORG}"})

# ---------------------------------------------------------------- Bea finalises and books, her account goes
INV = invoice(Be, CL, "Eins")
r = Be.post(B + f"{D}/{INV}/payments", json={"date": date.today().isoformat(), "amount": "357.00", "method": "transfer"})
check(r.status_code in (200, 201), "Bea books the payment " + r.text[:200])
mine = kt.dbx("SELECT action, user_name FROM office_doc_log WHERE doc_id=? AND user_id=?", (INV, U["bea"]))
check(mine and all(str(x["user_name"]).startswith("kenc1:") for x in mine), f"Bea's entries carry her name, sealed: {[tuple(x) for x in mine]}")
check({x["action"] for x in mine} >= {"finalize"}, f"the finalise entry is hers: {[x['action'] for x in mine]}")
NB = len(mine)
check(("finalize", U["bea"], "Bea Beispiel") in log_names(A, INV), "before the deletion: the log names Bea")
check(A.delete(B + f"/api/users/{U['bea']}").ok, "Bea's account is deleted")
check(one("SELECT COUNT(*) FROM users WHERE id=?", (U["bea"],)) == 0, "the account is gone")
gone = kt.dbx("SELECT user_id, user_name FROM office_doc_log WHERE doc_id=? AND user_id IS NULL", (INV,))
check(len(gone) == NB and all(x["user_name"] for x in gone), f"her entries lost the account, not the name: {len(gone)} of {NB}")
ln = log_names(A, INV)
check(("finalize", None, "Bea Beispiel") in ln and all(n == "Bea Beispiel" for _a, u, n in ln if u is None),
      f"the log (GET) still names Bea: {sorted(ln, key=str)}")
d = A.get(B + f"{D}/{INV}").json()
check(d.get("locked_by_name") == "Bea Beispiel", f"the invoice's locked_by_name (frozen with the sender): {d.get('locked_by_name')!r}")
gp = gobd_person(A, INV)
check(("finalize", "Bea Beispiel") in gp, f"the tax auditor's export (log.csv) names Bea: {sorted(gp)}")
ch = A.get(B + OFF + "/log/chain").json()
check(ch.get("ok") and not ch.get("first_bad"), f"the hash chain of the finalised documents stays intact: {ch}")
# review: the name frozen with the sender is read on its own (was: read after the sender had left the row - only the log
# entry answered): without the name in the finalise entry the invoice still names Bea
keep = kt.dbx("SELECT id, user_name FROM office_doc_log WHERE doc_id=? AND action='finalize'", (INV,))
kt.dbx("UPDATE office_doc_log SET user_name='' WHERE doc_id=? AND action='finalize'", (INV,))
check(A.get(B + f"{D}/{INV}").json().get("locked_by_name") == "Bea Beispiel", "locked_by_name comes from the sender frozen at finalising, without the log entry's name")
for x in keep:
    kt.dbx("UPDATE office_doc_log SET user_name=? WHERE id=?", (x["user_name"], x["id"]))
# review: the retention export (the organisation's records before it is deleted) names her too (was: the stored name
# was overwritten by the lookup of the missing account)
rz = kt.su_get(A, B + f"/api/retention/org/{ORG}/export.zip")
zn = zipfile.ZipFile(io.BytesIO(rz.content)) if rz.ok and rz.content[:2] == b"PK" else None
lg = zn.read("logs/office-log.csv").decode("utf-8-sig") if zn is not None and "logs/office-log.csv" in zn.namelist() else ""
check("finalize" in lg and "Bea Beispiel" in lg, f"the retention export's office log names Bea ({rz.status_code}): {lg[:300]}")

# ---------------------------------------------------------------- entries from before 2.1287: filled once at the start
OF = invoice(Ca, CL, "Angebot", kind="offer")
check(one("SELECT COUNT(*) FROM office_doc_log WHERE user_id=? AND user_name=''", (U["carl"],)) == 0, "Carl's entries carry his name")
kt.dbx("UPDATE office_doc_log SET user_name='' WHERE user_id=?", (U["carl"],))
kt.dbx("UPDATE office_docs SET sender='{}' WHERE id=?", (OF,))  # a quotation finalised before 2.1287: no name in its sender
kt.dbx("DELETE FROM settings WHERE key='migr_odl6470'")
NC = one("SELECT COUNT(*) FROM office_doc_log WHERE user_id=?", (U["carl"],))
kt.fresh(env={"KALMIDO_SECRET_KEY": KEY}, prefix="P21287B", keep=True)
filled = kt.dbx("SELECT user_name FROM office_doc_log WHERE user_id=?", (U["carl"],))
check(len(filled) == NC and all(str(x["user_name"]).startswith("kenc1:") for x in filled),
      f"the restart filled Carl's old entries once, sealed: {len(filled)} of {NC} {[str(x['user_name'])[:8] for x in filled]}")
check(one("SELECT value FROM settings WHERE key='migr_odl6470'") == "1", "the one-time fill set its marker")
A = sess("alice")
check(A.delete(B + f"/api/users/{U['carl']}").ok, "Carl's account is deleted")
d = A.get(B + f"{D}/{OF}").json()
check(d.get("locked_by_name") == "Carl Muster", f"an older quotation: locked_by_name from its finalise entry: {d.get('locked_by_name')!r}")
check(("finalize", None, "Carl Muster") in log_names(A, OF), "the log names Carl")
ch = A.get(B + OFF + "/log/chain").json()
check(ch.get("ok") and not ch.get("first_bad"), f"the hash chain stays intact after the fill: {ch}")

# ---------------------------------------------------------------- a person without an organisation (parity)
FID, Fr = freelancer(B, A)
FCL = office(Fr)
FI = invoice(Fr, FCL, "Frei")
fl = kt.dbx("SELECT user_name FROM office_doc_log WHERE doc_id=? AND user_id=?", (FI, FID))
check(fl and all(str(x["user_name"]).startswith("kenc1:") for x in fl), "freelancer: the own entries carry the name, sealed")
check(("finalize", FID, "Frida") in log_names(Fr, FI), "freelancer: the own office log names the person")
check(Fr.get(B + f"{D}/{FI}").json().get("locked_by_name") == "Frida", "freelancer: locked_by_name")
sys.exit(done("p21287_b_logname"))
