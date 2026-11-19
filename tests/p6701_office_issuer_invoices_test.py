#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1427.0 API tests (#6701): the invoice drafts of an invoice issuer (office/issdocs.py), their read routes, the preview and
the withdrawal. Own container (start.sh, mode workspaces, KALMIDO_ISSUER_KEYS on, a watchdog that does not tick by itself).
Invented companies, people and figures only. tenant-matrix: office  freelancer-matrix: office
In an organisation's office (Alice its admin) and in the personal office of a person without an organisation (Frida):
 - POST /api/v1/issuer/invoices: 201 a draft (no number, no date, the issuer's range, made by the person's own functions),
   Kalmido's sums; expect differs = 409 totals_mismatch and nothing made; a unit price with 4 places: expect after the line's
   rounding 201, after the sum's rounding 409; the same request again 200 (also after a person changed the draft, also at the
   day's limit); the same client_ref with another content 409 ref_conflict; a key's vat_check differs = still 200 (not hashed)
 - 400: unknown fields (date, number, finalize, series, currency, iban), more than 50 positions, a negative quantity, an
   IBAN / web / e-mail address in a position or in order_ref, due_days with due_date, a key twice; 404 client_unknown
 - wish: stored for the persons, never in the key's answer; payee of another issuer 404 payee_unknown, a wrong payee_check
   409 payee_mismatch (nothing made, an alarm); a due date less than 7 days after the date stops finalising (missing)
 - flags: client_new, over_limit (max_gross: made anyway, alarm), vat_territory (DE 78266 Büsingen, DE 27498 Heligoland)
 - limits: day_docs and open_drafts 429 limit_reached (no pause)
 - the read routes: the fixed list of fields (no intro, project, created_by, payment notes); another issuer's draft, a
   person's copy of the draft and a person's document of the same range: 404 by id; changed_since with the cursor; a
   person's correction of the finalised invoice: kind credit, corrects_doc_id, origin manual, no client_ref
 - the preview: 200 a PDF while the draft is as delivered, 409 edited_by_human after a person's change
 - withdraw: into the office's trash, the ref answers 410 withdrawn (also after the trash is purged), day_withdraw 429
 - the office: the draft names its issuer and the unconfirmed wish; it cannot become a series template (409), its client
   cannot become a person's client (409); a copy is no issuer draft; the list filter issuer=any
 - parallel: five equal requests at once = one draft
 - review of job/5472 (Fable reader): F1 the key cannot withdraw a person's correction draft (409 not_own_draft); F2 a person's
   change of the date or a switch alone ends the preview; F3 an IBAN split by dashes, dots, no-break or zero-width spaces and
   a direction mark: 400; round 2: F3 more ways to write an IBAN (a valid one is found by its check digits), F4 the key's own
   change of a client a person changed does not clear the preview's 409
 - the personal office: Frida's key makes Frida's draft (created_by Frida), she sees it
 - ISS_REUSED: every function of the drafts named there and run here with the issuer's context
usage: p6701_office_issuer_invoices_test.py <datadir>"""
import json
import os
import re
import sys
import threading

import requests

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
import kt  # noqa: E402
from kt import B, check  # noqa: E402
import dbx as dbxm  # noqa: E402
from freelancer_fixture import FEATURES, PASSWORD, freelancer  # noqa: E402

kt.docker_logs_on_first_fail()
DATA = sys.argv[1] if len(sys.argv) > 1 else kt.DATA
OF = "/api/office"
D = OF + "/docs"
V = B + "/api/v1"
CR = "/issuer/clients/by-ref/"
TODAY = __import__("datetime").date.today()
COMPANY = {"name": "Studio Nordlicht", "street": "Hafenstraße 12", "zip": "20457", "city": "Hamburg", "country": "DE",
           "email": "hallo@nordlicht.example", "phone": "+49 40 1234567", "tax_number": "12/345/67890", "iban": "DE02120300000000202051", "bic": "BYLADEM1001"}
ADDR = {"street": "Marktweg 5", "zip": "50667", "city": "Köln", "country": "DE"}
REUSED_HERE = ("office.docs.doc_create", "office.docs._put_items", "office.docs.recalc", "office.invoices.inv_missing",
               "office.docs.odoc_trash", "office.pdfweb._render")


def sql(q, args=(), write=False):
    c = dbxm.connect(os.path.join(DATA, "tasks.db"), timeout=10)
    try:
        r = c.execute(q, args)
        if write:
            c.commit()
            return None
        return r.fetchall()
    finally:
        c.close()


def hk(key):
    return {"Authorization": "Bearer " + key}


def kput(key, ref, b):
    return requests.put(V + CR + ref, headers=hk(key), json=b, timeout=30)


def kpost(key, b, raw=None):
    if raw is not None:
        return requests.post(V + "/issuer/invoices", headers={**hk(key), "Content-Type": "application/json"}, data=raw, timeout=30)
    return requests.post(V + "/issuer/invoices", headers=hk(key), json=b, timeout=30)


def kget(key, path):
    return requests.get(V + "/issuer" + path, headers=hk(key), timeout=30)


def code(r):
    try:
        e = r.json().get("error")
        return e.get("code") if isinstance(e, dict) else None
    except ValueError:
        return None


def field(r):
    try:
        return (r.json().get("error") or {}).get("field")
    except (ValueError, AttributeError):
        return None


def news(uid, what):
    return sql("SELECT data FROM notifications WHERE user_id=? AND kind='integfail' AND data->>'what'=?", (uid, what))


def n_docs(iid):
    return sql("SELECT COUNT(*) FROM office_docs WHERE issuer_id=?", (iid,))[0][0]


def setup_area(S, code_):
    assert S.put(B + OF + "/settings", json={"lang": "de", "company_fields": COMPANY}).ok
    r = S.post(B + OF + "/num-ranges", json={"code": code_, "scheme": code_ + "-{yyyy}-{seq:03}"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def issuer(S, rg, name, limits=None):
    r = S.post(B + OF + "/issuers", json={"name": name, "range_id": rg, "password": PASSWORD, **({"limits": limits} if limits else {})})
    assert r.status_code == 201, r.text
    return r.json()["issuer"]["id"], r.json()["key"]


def body(ref, ext="acc:1", items=None, expect=None, **more):
    items = items or [{"text": "Tarif Studio, Dezember", "qty": 1, "unit": "flat", "rate": "150.00", "tax": "standard"}]
    return {"client_ref": ref, "client": {"external_ref": ext}, "service_from": TODAY.isoformat(), "service_to": TODAY.isoformat(),
            "items": items, "expect": expect or {"net": "150.00", "tax": "28.50", "gross": "178.50"}, **more}


# ---------------------------------------------------------------- the container
kt.fresh({"KALMIDO_INSTANCE_MODE": "workspaces", "KALMIDO_ISSUER_KEYS": "1", "TASKS_WATCHDOG_INTERVAL": "3600"}, data=DATA)
A = kt.setup()
A.patch(B + "/api/settings", json={"lang": "en", "features": FEATURES, "tour": "done"})
ALICE = A.get(B + "/api/state").json()["me"]["id"]
ORG = A.post(B + "/api/admin/orgs", json={"name": "Alpha", "admin_id": ALICE}).json()["id"]
assert A.patch(B + "/api/settings", json={"workspace": f"org:{ORG}"}).ok
FID, Fr = freelancer(B, A)
Fr.patch(B + "/api/settings", json={"workspace": "private"})

RG = setup_area(A, "GT")
IID, KEY = issuer(A, RG, "Shop")
IID2, KEY2 = issuer(A, RG, "Booking", {"day_docs": 3, "open_drafts": 50})
IID3, KEY3 = issuer(A, RG, "Checks")  # its own key for the 400s (60 calls a minute each)
FRG = setup_area(Fr, "WEB")
FI, FK = issuer(Fr, FRG, "Own script")
for k, ref in ((KEY, "acc:1"), (KEY, "acc:2"), (KEY2, "acc:1"), (KEY3, "acc:1"), (FK, "acc:1")):
    assert kput(k, ref, {"name": f"Kundin {ref}", **ADDR, "email_invoice": "rechnung@kunde.example"}).status_code == 201
assert kput(KEY, "acc:bues", {"name": "Hof am Rhein", "street": "Junkerstraße 3", "zip": "78266", "city": "Büsingen", "country": "DE"}).status_code == 201
assert kput(KEY, "acc:helgo", {"name": "Inselladen", "street": "Am Falm 1", "zip": "27498", "city": "Helgoland", "country": "DE"}).status_code == 201

# ---------------------------------------------------------------- a draft
r = kpost(KEY, body("kauf:1", wish={"send": True, "paid": {"amount": "178.50", "date": TODAY.isoformat(), "method": "card", "provider": "mollie",
                                                         "online_ref": "tr_123"}, "reference": "GT-4711-ABCD", "due_days": 14},
                    vat_check={"source": "VIES", "valid": True, "checked_at": "2026-11-01T10:00:00Z"},
                    business_check={"kind": "vat_id", "checked_at": "2026-11-01T10:00:00Z"}, order_ref="Kauf 4711"))
j = r.json() if r.status_code == 201 else {}
check(r.status_code == 201 and j.get("status") == "draft" and j.get("number") is None and j.get("date") is None and j.get("range") == "GT"
      and j.get("totals", {}).get("gross") == "178.50" and j.get("client_ref") == "kauf:1" and j.get("origin") == "issuer",
      f"a draft: 201, no number, no date, the issuer's range, Kalmido's sums {r.status_code} {r.text[:300]}")
DOC1 = j.get("doc_id")
check("client_new" in (j.get("flags") or []), f"the first draft of a client the key set up: client_new {j.get('flags')}")
check(not {"wish", "vat_check", "business_check", "intro", "project_title", "created_by", "closing", "issuer_wish"} & set(j),
      f"the key's answer: the fixed list of fields {sorted(j)}")
row = sql("SELECT issuer_id, range_id, number, created_by, issuer_wish, status FROM office_docs WHERE id=?", (DOC1,))
check(row and row[0][0] == IID and row[0][1] == RG and row[0][2] == "" and row[0][3] is None and row[0][4] and row[0][5] == "draft",
      f"the row: the issuer's, its range, no number, no person {row}")
r = A.get(B + D + f"/{DOC1}")
d = r.json() if r.ok else {}
w = d.get("issuer_wish") or {}
check(r.ok and (d.get("issuer") or {}).get("name") == "Shop" and (w.get("wish") or {}).get("paid", {}).get("method") == "card"
      and (w.get("vat_check") or {}).get("source") == "VIES" and (w.get("business_check") or {}).get("kind") == "vat_id",
      f"the office: made by issuer Shop, the unconfirmed wish and the checks {d.get('issuer')} {w}")
check(d.get("order_ref") == "Kauf 4711", f"order_ref on the draft {d.get('order_ref')}")
check(any(x["action"] == "issuer_write" and x.get("doc_id") == DOC1 for x in (A.get(B + OF + f"/issuers/{IID}/log").json().get("log") or []))
      or sql("SELECT 1 FROM office_doc_log WHERE issuer_id=? AND action='issuer_write' AND doc_id=?", (IID, DOC1)),
      "the office log: issuer_write with the document")

# ---------------------------------------------------------------- idempotency
r = kpost(KEY, body("kauf:1", wish={"send": True, "paid": {"amount": "178.50", "date": TODAY.isoformat(), "method": "card", "provider": "mollie",
                                                         "online_ref": "tr_123"}, "reference": "GT-4711-ABCD", "due_days": 14},
                    vat_check={"source": "VIES", "valid": True, "checked_at": "2026-11-02T10:00:00Z"}, order_ref="Kauf 4711"))
check(r.status_code == 200 and r.json().get("doc_id") == DOC1 and n_docs(IID) == 1, f"the same again (vat_check / business_check not hashed): 200 the first draft {r.status_code} {r.text[:200]}")
r = kpost(KEY, body("kauf:1", order_ref="Kauf 4712"))
check(r.status_code == 409 and code(r) == "ref_conflict" and n_docs(IID) == 1, f"the same client_ref with another content: 409 ref_conflict {r.status_code} {r.text[:200]}")
cur = A.get(B + D + f"/{DOC1}").json()
r = A.patch(B + D + f"/{DOC1}", json={"project_title": "Studio Dezember", "expect_updated_at": cur.get("updated_at")})
check(r.ok, f"a person corrects the draft {r.status_code} {r.text[:200]}")
r = kpost(KEY, body("kauf:1", wish={"send": True, "paid": {"amount": "178.50", "date": TODAY.isoformat(), "method": "card", "provider": "mollie",
                                                         "online_ref": "tr_123"}, "reference": "GT-4711-ABCD", "due_days": 14}, order_ref="Kauf 4711"))
check(r.status_code == 200 and r.json().get("doc_id") == DOC1 and "project_title" not in r.json(), f"the retry after a person's correction: 200, no conflict {r.status_code}")

# ---------------------------------------------------------------- sums and rounding
r = kpost(KEY, body("kauf:2", expect={"net": "150.00", "tax": "28.50", "gross": "178.51"}))
check(r.status_code == 409 and code(r) == "totals_mismatch" and (r.json()["error"].get("totals") or {}).get("gross") == "178.50"
      and n_docs(IID) == 1 and not sql("SELECT 1 FROM office_issuer_refs WHERE client_ref='kauf:2'"),
      f"a sum differs: 409 totals_mismatch with Kalmido's sums, nothing made, no ref {r.status_code} {r.text[:200]}")
four = [{"text": "Stunde A", "qty": "1", "unit": "hour", "rate": "10.0050"}, {"text": "Stunde B", "qty": "1", "unit": "hour", "rate": "10.0050"}]
# each line 10.005 -> 10.01 (half up to the cent), summed 20.02, the tax 19 % on the sum 3.80; rounding only the sum would be 20.01
r = kpost(KEY, body("kauf:4a", items=four, expect={"net": "20.02", "tax": "3.80", "gross": "23.82"}))
check(r.status_code == 201, f"4 places: expect after the lines' rounding: 201 {r.status_code} {r.text[:200]}")
r = kpost(KEY, body("kauf:4b", items=four, expect={"net": "20.01", "tax": "3.80", "gross": "23.81"}))
check(r.status_code == 409 and code(r) == "totals_mismatch" and (r.json()["error"].get("totals") or {}).get("net") == "20.02",
      f"expect from the rounded sum instead of the rounded lines: 409 with net 20.02 {r.status_code} {r.text[:200]}")

# ---------------------------------------------------------------- 400s
for extra, name in (({"date": TODAY.isoformat()}, "date"), ({"number": "GT-1"}, "number"), ({"finalize": True}, "finalize"),
                    ({"series": "GT"}, "series"), ({"currency": "USD"}, "currency"), ({"iban": "DE02120300000000202051"}, "iban")):
    r = kpost(KEY3, body("bad:1", **extra))
    check(r.status_code == 400 and code(r) == "unknown_field", f"{name}: no such field, 400 unknown_field {r.status_code} {r.text[:160]}")
r = kpost(KEY3, body("bad:1", items=[{"text": f"Pos {i}", "qty": 1, "rate": "1.00"} for i in range(51)], expect={"net": "51.00", "tax": "9.69", "gross": "60.69"}))
check(r.status_code == 400, f"more than 50 positions: 400 {r.status_code}")
r = kpost(KEY3, body("bad:1", items=[{"text": "Erstattung", "qty": -1, "rate": "150.00"}], expect={"net": "-150.00", "tax": "-28.50", "gross": "-178.50"}))
check(r.status_code == 400 and "qty" in (field(r) or ""), f"a negative quantity: 400 {r.status_code} {r.text[:160]}")
r = kpost(KEY3, body("bad:1", items=[{"text": "Zahlung an DE89 3704 0044 0532 0130 00", "qty": 1, "rate": "150.00"}]))
check(r.status_code == 400 and "text" in (field(r) or ""), f"an IBAN in a position: 400 {r.status_code} {r.text[:160]}")
# review F3 (2.1427.0): an IBAN split by dashes, dots, a no-break space, or a zero-width space / a direction mark in the text: 400
for txt in ("Zahlung an DE89-3704-0044-0532-0130-00", "Zahlung an DE89.3704.0044.0532.0130.00", "Zahlung an DE89\u00a03704\u00a00044\u00a00532\u00a00130\u00a000",
            "Zahlung an DE89\u200b3704004405320130 00", "Tarif \u202eoidutS",
            # review F3 round 2: a space after the country code, several separators, colons, commas, a line break, a thin space,
            # full-width digits, a combining grapheme joiner
            "Zahlung an DE 89 3704 0044 0532 0130 00", "Zahlung an DE89 -- 3704 -- 0044 -- 0532 -- 0130 -- 00", "Zahlung an DE89:3704:0044:0532:0130:00",
            "Zahlung an DE89,3704,0044,0532,0130,00", "Zahlung an DE89\n3704 0044 0532 0130 00", "Zahlung an DE89\u20093704\u20090044\u20090532\u20090130\u200900",
            "Zahlung an \uff24\uff25\uff18\uff19\uff13\uff17\uff10\uff14\uff10\uff10\uff14\uff14\uff10\uff15\uff13\uff12\uff10\uff11\uff13\uff10\uff10\uff10",
            "Zahlung an DE8\u034f9370400440532013000"):
    r = kpost(KEY3, body("bad:1", items=[{"text": txt, "qty": 1, "rate": "150.00"}]))
    check(r.status_code == 400 and "text" in (field(r) or ""), f"review F3: {txt!r} in a position: 400 {r.status_code} {r.text[:120]}")
r = kpost(KEY3, body("bad:1", order_ref="Infos auf www.example.com"))
check(r.status_code == 400 and field(r) == "order_ref", f"a web address in order_ref: 400 {r.status_code}")
r = kpost(KEY3, body("bad:1", wish={"due_days": 14, "due_date": TODAY.isoformat()}))
check(r.status_code == 400 and "due" in (field(r) or ""), f"due_days and due_date together: 400 {r.status_code} {r.text[:160]}")
r = kpost(KEY3, body("bad:1", items=[{"text": "Abo", "qty": 1, "unit": "month", "rate": "150.00"}]))
check(r.status_code == 400 and "unit" in (field(r) or ""), f"a unit Kalmido does not know: 400 {r.status_code}")
r = kpost(KEY3, None, raw=json.dumps(body("bad:1"))[:-1] + ', "client_ref": "bad:2"}')
check(r.status_code == 400, f"a key twice: 400 {r.status_code}")
r = kpost(KEY3, body("bad:1", ext="acc:none"))
check(r.status_code == 404 and code(r) == "client_unknown", f"an unknown client: 404 client_unknown {r.status_code}")
r = kpost(KEY3, body("ok:1", items=[{"text": "Tarif Studio 2026, Dezember, Raum 12 B, Nr. 4711-0815-2026", "qty": 1, "rate": "150.00"}], order_ref="Kauf 12345678 / 2026-12-01"))
check(r.status_code == 201, f"ordinary numbers in texts are no IBAN {r.status_code} {r.text[:160]}")
check(not sql("SELECT 1 FROM office_issuer_refs WHERE issuer_id=? AND route='invoices' AND client_ref<>'ok:1'", (IID3,)) and n_docs(IID3) == 1, "no 400 / 404 stored a ref or a draft")
check(not sql("SELECT paused FROM office_issuers WHERE id=?", (IID3,))[0][0], "400s pause nothing")

# ---------------------------------------------------------------- payee, due date
r = A.post(B + OF + f"/issuers/{IID2}/payees", json={"label": "Konto Booking", "holder": "Studio Nordlicht", "iban": "DE89370400440532013000", "password": PASSWORD})
check(r.status_code in (200, 201), f"an admin allows an account to Booking {r.status_code} {r.text[:160]}")
PB = (r.json().get("payee") or r.json()).get("id") if r.ok else 0
r = kpost(KEY, body("pay:1", wish={"payee": PB, "payee_check": "3000"}))
check(r.status_code == 404 and code(r) == "payee_unknown", f"the account of another issuer: 404 payee_unknown {r.status_code} {r.text[:160]}")
r = kpost(KEY2, body("pay:1", wish={"payee": PB, "payee_check": "9999"}))
check(r.status_code == 409 and code(r) == "payee_mismatch" and n_docs(IID2) == 0 and kt.until(lambda: news(ALICE, "issuer_payee_mismatch"), timeout=10),
      f"a wrong payee_check: 409 payee_mismatch, nothing made, an alarm {r.status_code} {r.text[:160]}")
r = kpost(KEY2, body("pay:1", wish={"payee": PB, "payee_check": "3000", "due_date": (TODAY + __import__("datetime").timedelta(days=3)).isoformat()}))
check(r.status_code == 201 and any("7" in m for m in r.json().get("missing") or []), f"the right account: 201; a due date in 3 days stops finalising (missing) {r.status_code} {r.text[:300]}")
DOCP = r.json().get("doc_id") if r.status_code == 201 else 0

# ---------------------------------------------------------------- flags: over_limit, vat_territory
assert A.patch(B + OF + f"/issuers/{IID}", json={"limits": {"max_gross": "100.00"}}).ok
r = kpost(KEY, body("big:1", ext="acc:2"))
check(r.status_code == 201 and "over_limit" in (r.json().get("flags") or []) and kt.until(lambda: news(ALICE, "issuer_over_limit"), timeout=10),
      f"over max_gross: made anyway, over_limit, an alarm {r.status_code} {r.text[:200]}")
assert A.patch(B + OF + f"/issuers/{IID}", json={"limits": {"max_gross": "2000.00"}, "password": PASSWORD}).ok
for ext in ("acc:bues", "acc:helgo"):
    r = kpost(KEY, body(f"terr:{ext}", ext=ext))
    check(r.status_code == 201 and "vat_territory" in (r.json().get("flags") or []), f"{ext}: the flag vat_territory {r.status_code} {r.text[:200]}")

# ---------------------------------------------------------------- limits
for i in range(3):
    r = kpost(KEY2, body(f"day:{i}"))
r = kpost(KEY2, body("day:9"))
check(r.status_code == 429 and code(r) == "limit_reached" and r.headers.get("Retry-After"), f"over day_docs: 429 limit_reached {r.status_code} {r.text[:160]}")
r = kpost(KEY2, body("day:0"))
check(r.status_code == 200, f"the retry of a made draft at the day's limit: 200 {r.status_code}")
check(not sql("SELECT paused FROM office_issuers WHERE id=?", (IID2,))[0][0], "a limit pauses nothing")

# ---------------------------------------------------------------- read routes
r = kget(KEY, f"/docs/{DOC1}")
j = r.json() if r.ok else {}
check(r.ok and set(j) <= {"doc_id", "client_ref", "origin", "kind", "status", "range", "number", "date", "service_from", "service_to", "due_date",
                          "totals", "corrects_doc_id", "payments", "missing", "flags", "mail", "updated_at"} and "Studio Dezember" not in r.text,
      f"GET: the fixed list of fields, not the person's project title {sorted(j)}")
check(j.get("mail") == {"state": "none", "at": None}, f"(#6820): mail {{state, at}} of a draft never mailed {j.get('mail')}")
check(kget(KEY, "/docs/by-ref/kauf:1").json().get("doc_id") == DOC1, "by-ref")
check(kget(KEY2, f"/docs/{DOC1}").status_code == 404, "another issuer's draft: 404")
check(kget(KEY, "/docs/by-ref/none:1").status_code == 404, "an unknown ref: 404")
r = A.post(B + D + f"/{DOC1}/duplicate", json={})
CP = r.json().get("id") if r.ok else 0
check(r.ok and sql("SELECT issuer_id, issuer_wish FROM office_docs WHERE id=?", (CP,))[0] == (None, None) and kget(KEY, f"/docs/{CP}").status_code == 404,
      f"a person's copy: not the issuer's, 404 for the key {r.status_code}")
r = A.post(B + D, json={"kind": "invoice", "lang": "de", "client_id": sql("SELECT id FROM clients WHERE external_ref='acc:1' AND issuer_id=?", (IID,))[0][0],
                        "range_id": RG, "service_from": TODAY.isoformat(), "service_to": TODAY.isoformat(), "items": [{"title": "Hand", "qty": 1, "rate": 10}]})
HAND = r.json().get("id") if r.status_code == 201 else 0
check(HAND and kget(KEY, f"/docs/{HAND}").status_code == 404, f"a person's document in the same range: 404 {r.status_code}")

# ---------------------------------------------------------------- the office: series, client, list
check(A.post(B + OF + "/series", json={"template_id": DOC1, "every": "monthly", "start": TODAY.isoformat()}).status_code == 409, "an issuer's draft is no series template")
pc = A.post(B + "/api/clients", json={"name": "Handkunde AG", **ADDR})
PC = pc.json().get("id") if pc.ok else 0
cur = A.get(B + D + f"/{DOC1}").json()
r = A.patch(B + D + f"/{DOC1}", json={"client_id": PC, "expect_updated_at": cur.get("updated_at")})
check(r.status_code == 409, f"the issuer's draft to a person's client: 409 {r.status_code} {r.text[:160]}")
lst = A.get(B + D + "?kind=invoice&issuer=any").json()
ids = {x["id"] for x in (lst.get("docs") if isinstance(lst, dict) else lst) or []}
check(DOC1 in ids and HAND not in ids and CP not in ids, f"the list filter issuer=any {sorted(ids)[:10]}")

# ---------------------------------------------------------------- the preview
r = kget(KEY, f"/docs/{DOCP}/pdf") if False else kget(KEY2, f"/docs/{DOCP}/pdf")
check(r.status_code == 200 and r.content[:4] == b"%PDF", f"the preview of a draft as delivered: a PDF {r.status_code} {r.text[:160] if r.status_code != 200 else ''}")
r = kget(KEY, f"/docs/{DOC1}/pdf")
check(r.status_code == 409 and code(r) == "edited_by_human", f"after a person's change: 409 edited_by_human {r.status_code} {r.text[:160]}")
# review F2 (2.1427.0): a person's change of a field outside the head's usual ones (the date, a position's switch) ends it too
for i, chg in enumerate(({"date": (TODAY - __import__("datetime").timedelta(days=1)).isoformat()}, {"subtotals": True})):
    di = kpost(KEY, body(f"fp:{i}", ext="acc:2")).json().get("doc_id")
    check(kget(KEY, f"/docs/{di}/pdf").status_code == 200, f"review F2: the fresh draft's preview {chg}")
    cur = A.get(B + D + f"/{di}").json()
    rr = A.patch(B + D + f"/{di}", json={**chg, "expect_updated_at": cur.get("updated_at")})
    r = kget(KEY, f"/docs/{di}/pdf")
    check(rr.ok and r.status_code == 409 and code(r) == "edited_by_human", f"review F2: a person changed {list(chg)}: 409 edited_by_human {rr.status_code} {r.status_code}")

# review F4 (2.1427.0): a person changed the client (customer number): the key's own later change of the client does not clear the 409
assert kput(KEY, "acc:f4", {"name": "Kundin F4", **ADDR}).status_code == 201
DF4 = kpost(KEY, body("f4:1", ext="acc:f4")).json().get("doc_id")
CF4 = sql("SELECT id FROM clients WHERE external_ref='acc:f4' AND issuer_id=?", (IID,))[0][0]
check(kget(KEY, f"/docs/{DF4}/pdf").status_code == 200, "review F4: the preview as delivered")
cu = kput(KEY, "acc:f4", {"name": "Kundin F4"}).json()
r = kput(KEY, "acc:f4", {"city": "Bonn", "expect_updated_at": cu.get("updated_at")})
check(r.ok and kget(KEY, f"/docs/{DF4}/pdf").status_code == 200, f"review F4: the key's own change of the client keeps its preview {r.status_code}")
check(A.patch(B + f"/api/clients/{CF4}", json={"customer_no": "K-4711"}).ok, "a person sets the customer number")
check(kget(KEY, f"/docs/{DF4}/pdf").status_code == 409, "review F4: after the person's change 409")
cu = requests.get(V + CR + "acc:f4", headers=hk(KEY), timeout=30).json()
r = kput(KEY, "acc:f4", {"city": "Köln", "expect_updated_at": cu.get("updated_at")})
r2 = kget(KEY, f"/docs/{DF4}/pdf")
check(r.ok and r2.status_code == 409 and code(r2) == "edited_by_human", f"review F4: the key's change afterwards does not clear it {r.status_code} {r2.status_code}")


# ---------------------------------------------------------------- finalise, correct, changed_since
D2 = kpost(KEY, body("fin:1", ext="acc:2")).json()["doc_id"]
hold = A.get(B + D + f"/{D2}/number-preview").json().get("client_hold") or {}
r = A.post(B + D + f"/{D2}/finalize", json={"client_hold_ok": hold.get("at")} if hold else {})
check(r.ok, f"a person finalises the issuer's draft {r.status_code} {r.text[:200]}")
r = A.post(B + D + f"/{D2}/credit", json={})
CRD = r.json().get("id") if r.ok else 0
check(r.ok and sql("SELECT issuer_id, kind FROM office_docs WHERE id=?", (CRD,))[0] == (IID, "credit"), f"a person's correction inherits issuer_id {r.status_code} {r.text[:200]}")
r = requests.post(V + f"/issuer/docs/{CRD}/withdraw", headers=hk(KEY), timeout=30)
check(r.status_code == 409 and code(r) == "not_own_draft" and not sql("SELECT deleted_at FROM office_docs WHERE id=?", (CRD,))[0][0],
      f"review F1: the key cannot withdraw the person's correction draft: 409 not_own_draft {r.status_code} {r.text[:160]}")
seen, cursor, pages = {}, None, 0
while pages < 20:
    r = kget(KEY, "/docs?limit=2" + (f"&cursor={requests.utils.quote(cursor)}" if cursor else ""))
    assert r.ok, r.text
    for x in r.json()["docs"]:
        seen[x["doc_id"]] = x
    cursor = r.json().get("next_cursor")
    pages += 1
    if not cursor:
        break
check(D2 in seen and seen[D2]["number"] and seen[D2]["status"] != "draft", f"changed_since: the finalised invoice with its number {seen.get(D2)}")
check(CRD in seen and seen[CRD]["kind"] == "credit" and seen[CRD]["corrects_doc_id"] == D2 and seen[CRD]["client_ref"] is None and seen[CRD]["origin"] == "manual",
      f"changed_since: the person's correction, kind credit, corrects_doc_id, origin manual {seen.get(CRD)}")
check(CRD in seen and "missing" not in seen[CRD] and "flags" not in seen[CRD],
      f"(#7203, reader F2): the person's correction draft gives the key no missing / flags {sorted(seen.get(CRD) or {})}")
check(CP not in seen and pages >= 2, f"no person's copy; the cursor pages {pages}")
# (#6820): the delivery state of the mail - a person's "Delivery failed" on the mailed invoice shows as bounced with its
# time, never the address or an error text (the mail itself went out in a test of its own: p6820_office_mail_state_test.py)
sql("UPDATE office_docs SET mail_state='sent', mail_at=CURRENT_TIMESTAMP WHERE id=?", (D2,), write=True)
r = A.post(B + D + f"/{D2}/mail-bounced", json={})
j = kget(KEY, f"/docs/{D2}").json()
check(r.ok and (j.get("mail") or {}).get("state") == "bounced" and j["mail"].get("at") and set(j["mail"]) == {"state", "at"},
      f"#6820: the key sees mail bounced with its time, nothing else {r.status_code} {j.get('mail')}")

# ---------------------------------------------------------------- withdraw
W1 = kpost(KEY, body("wd:1", ext="acc:2")).json()["doc_id"]
r = requests.post(V + f"/issuer/docs/{W1}/withdraw", headers=hk(KEY), timeout=30)
check(r.ok and r.json().get("status") == "withdrawn" and sql("SELECT deleted_at IS NOT NULL FROM office_docs WHERE id=?", (W1,))[0][0],
      f"withdraw: into the office's trash {r.status_code} {r.text[:160]}")
r = kpost(KEY, body("wd:1", ext="acc:2"))
check(r.status_code == 410 and code(r) == "withdrawn", f"the ref of a withdrawn draft: 410 withdrawn {r.status_code}")
check(requests.post(V + f"/issuer/docs/{D2}/withdraw", headers=hk(KEY), timeout=30).status_code == 409, "a finalised invoice cannot be withdrawn: 409")
sql("DELETE FROM office_doc_items WHERE doc_id=?", (W1,), write=True)
sql("DELETE FROM office_docs WHERE id=?", (W1,), write=True)  # as the purge of the trash does
r = kpost(KEY, body("wd:1", ext="acc:2"))
check(r.status_code == 410 and code(r) == "withdrawn" and kget(KEY, "/docs/by-ref/wd:1").status_code == 410, f"after the trash was purged: still 410 {r.status_code}")
assert A.patch(B + OF + f"/issuers/{IID}", json={"limits": {"day_withdraw": 1}}).ok
W2 = kpost(KEY, body("wd:2", ext="acc:2")).json()["doc_id"]
r = requests.post(V + f"/issuer/docs/{W2}/withdraw", headers=hk(KEY), timeout=30)
check(r.status_code == 429 and code(r) == "limit_reached", f"over day_withdraw: 429 {r.status_code} {r.text[:160]}")

# ---------------------------------------------------------------- parallel
res = []


def go():
    res.append(kpost(KEY, body("par:1", ext="acc:2")).status_code)


ts = [threading.Thread(target=go) for _ in range(5)]
for t in ts:
    t.start()
for t in ts:
    t.join()
n = sql("SELECT COUNT(*) FROM office_issuer_refs WHERE issuer_id=? AND client_ref='par:1'", (IID,))[0][0]
check(n == 1 and sorted(res).count(201) == 1 and set(res) <= {200, 201}, f"five equal requests at once: one draft {res}")

# ---------------------------------------------------------------- the personal office
r = kpost(FK, body("f:1"))
FD = r.json().get("doc_id") if r.status_code == 201 else 0
row = sql("SELECT created_by, issuer_id FROM office_docs WHERE id=?", (FD,))
check(r.status_code == 201 and row and row[0] == (FID, FI), f"Frida's key: Frida's draft {r.status_code} {row}")
r = Fr.get(B + D + f"/{FD}")
check(r.ok and (r.json().get("issuer") or {}).get("name") == "Own script", f"Frida sees it with its issuer {r.status_code}")
# the other area's key (Frida's personal office <-> the organisation): 404 on every route, nothing changed
# tenant: GET /api/v1/issuer/docs/{}
check(kget(FK, f"/docs/{DOC1}").status_code == 404 and kget(KEY, f"/docs/{FD}").status_code == 404, "never across areas")
# tenant: GET /api/v1/issuer/docs/by-ref/{}
check(kget(FK, "/docs/by-ref/kauf:1").status_code == 404, "another area's client_ref: 404")
# tenant: GET /api/v1/issuer/docs/{}/pdf
check(kget(FK, f"/docs/{DOC1}/pdf").status_code == 404, "another area's preview: 404")
# tenant: POST /api/v1/issuer/docs/{}/withdraw
r = requests.post(V + f"/issuer/docs/{DOC1}/withdraw", headers=hk(FK), timeout=30)
check(r.status_code == 404 and not sql("SELECT deleted_at FROM office_docs WHERE id=?", (DOC1,))[0][0], f"another area's withdrawal: 404, nothing changed {r.status_code}")
# tenant: POST /api/v1/issuer/invoices
r = kpost(FK, body("x:1", ext="acc:2"))
check(r.status_code == 404 and code(r) == "client_unknown" and n_docs(FI) == 1, f"a client of another area: 404, nothing made {r.status_code}")
# tenant: GET /api/v1/issuer/docs
check(kget(FK, "/docs").ok and {x["doc_id"] for x in kget(FK, "/docs").json()["docs"]} == {FD}, "Frida's key reads only its own")

# ---------------------------------------------------------------- ISS_REUSED
src = open(os.path.join(N, "..", "kalmido", "office", "issuers.py"), encoding="utf-8").read()
m = re.search(r"ISS_REUSED = \(([^)]*)\)", src)
check(m and set(REUSED_HERE) <= set(re.findall(r'"([^"]+)"', m.group(1))), "ISS_REUSED names the drafts' functions this suite runs with the issuer")


# (#7203, reader F1): a customer number a person set before the draft is not in the key's preview (the office's PDF has it)
def pdf_hex(data):
    import zlib
    out = b""
    for m in re.finditer(rb"stream\r?\n(.*?)\nendstream", data, re.S):
        try:
            out += zlib.decompress(m.group(1))
        except zlib.error:
            out += m.group(1)
    return out.decode("latin-1")


IIDF1, KEYF1 = issuer(A, RG, "F1 preview")  # a fresh key: the one above used its limits and its minute of previews
assert kput(KEYF1, "acc:f1", {"name": "Kundin F1", **ADDR}).status_code == 201
CF1 = sql("SELECT id FROM clients WHERE external_ref='acc:f1' AND issuer_id=?", (IIDF1,))[0][0]
check(A.patch(B + f"/api/clients/{CF1}", json={"customer_no": "KN-90017"}).ok, "F1: a person sets the customer number first")
DF1 = kpost(KEYF1, body("f1:1", ext="acc:f1")).json().get("doc_id")
own = A.get(B + D + f"/{DF1}/pdf")
r = kget(KEYF1, f"/docs/{DF1}/pdf")
hx = "KN-90017".encode("cp1252").hex()
check(own.ok and hx in pdf_hex(own.content), f"F1: the office's own preview prints the customer number {own.status_code}")
check(r is not None and r.status_code == 200 and hx not in pdf_hex(r.content), f"#7203 F1: the key's preview leaves the person's customer number out {getattr(r, 'status_code', None)}")

sys.exit(kt.done("p6701_office_issuer_invoices"))
