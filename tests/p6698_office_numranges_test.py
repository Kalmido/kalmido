#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1365.0 API tests (#6698): additional number ranges of an office area (office_num_ranges; office/numranges.py,
office/model.py num_view). Own container (start.sh, mode workspaces). Invented companies, people and figures only.
tenant-matrix: office  freelancer-matrix: office
Once in an organisation's office (its admin; a plain member and a person of another office for the rights) and once in the
personal office of a person without an organisation (freelancer fixture), with a main range like a long-running one
({seq}_{kuerzel}_{isodate}_R, corrections on the invoices' counter with _RK):
 - rights: only the admin adds / changes / removes a range (member 403), members read it with the series (GET
   .../number-ranges: extra), another office's range is 404 for PATCH / DELETE / the next number; bad schemes 400 (a client
   block, no fixed text in front, the scheme of a main series), a code twice 400
 - two ranges count apart: an invoice in GT gets GT-<year>-001 and the date of the day it is finalised (its draft said another
   day), the main counter is not moved (before / after); a main invoice dated yesterday is finalised after it (the date order
   is per range, both ways); the main range's own date order still refuses an older date
 - no number by hand in a range: 400, neither the range's nor the main counter moves
 - the correction of a range invoice keeps its range (a change: 409) and counts on the same counter with the ending -K
 - hash chain per range ('r<id>', places 1..n), the office's chain check intact; the main numbers keep their scheme
 - the year: a counter row of the year before does not touch this year's (the period is the scheme's year); the finalise
   dialog's preview shows the range's next number
 - list filter range=<id> / main; a copy of a range invoice starts in the main range; a quotation number by hand that follows
   the range's scheme 400
 - payment reminders: an overdue invoice of the range gets no overdue mark and no suggestion while the range has them off
   (the main range's overdue invoice does), switched on it gets them
 - one way: a range with a finalised document is not removed (409, close it); its scheme changes for the future with an
   office log line; an unused range is removed, its draft goes back to the main range; a closed range takes no new invoice
   (choice 409, finalising an older draft 409), a correction stays possible
 - the auditor's export names the range in number_ranges.csv
 - moving the personal office into an organisation: the range moves with its counter (the next number continues, nothing
   left behind in the personal office); a code the organisation has already refuses the move
2.1390.0 (#7037): a new range checks its correction scheme too (F3), the settings never take a range's scheme (F4), a closed
range opens only with a valid scheme (F1), the move of the personal office refuses a range scheme the organisation uses (F2)
usage: p6698_office_numranges_test.py <datadir>"""
import csv
import io
import os
import re
import sys
import zipfile
from datetime import timedelta

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
import kt  # noqa: E402
from kt import B, check, until  # noqa: E402
import dbx as dbxm  # noqa: E402
from freelancer_fixture import FEATURES, freelancer, org_join, login  # noqa: E402
from testclock import today  # noqa: E402

kt.docker_logs_on_first_fail()
DATA = sys.argv[1] if len(sys.argv) > 1 else kt.DATA
OF = "/api/office"
D = OF + "/docs"
NR = OF + "/num-ranges"
COMPANY = {"name": "Studio Nordlicht", "street": "Hafenstraße 12", "zip": "20457", "city": "Hamburg", "country": "DE",
           "email": "hallo@nordlicht.example", "tax_number": "12/345/67890", "vat_id": "DE999999999",
           "iban": "DE02120300000000202051", "bic": "BYLADEM1001", "bank_name": "Beispielbank"}
MAIN = "{seq}_{kuerzel}_{isodate}_R"


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


def ws(s, v):
    r = s.patch(B + "/api/settings", json={"workspace": v})
    assert r.ok, r.text


kt.fresh({"KALMIDO_INSTANCE_MODE": "workspaces"}, data=DATA)
A = kt.setup()
A.patch(B + "/api/settings", json={"lang": "en", "features": FEATURES, "tour": "done"})
ALICE = A.get(B + "/api/state").json()["me"]["id"]
r = A.post(B + "/api/users", json={"username": "bob", "display_name": "Bob Member", "password": "password123", "email": "bob@example.com"})
assert r.ok, r.text
ORG = A.post(B + "/api/admin/orgs", json={"name": "Alpha", "admin_id": ALICE}).json()["id"]
assert A.put(B + f"/api/orgs/{ORG}/members", json={"email": "bob@example.com", "role": "member"}).ok
org_join(B, "bob", ORG)
ws(A, f"org:{ORG}")
Bo = login(B, "bob")
Bo.patch(B + "/api/settings", json={"lang": "en", "features": FEATURES, "tour": "done", "workspace": f"org:{ORG}"})
FID, Fr = freelancer(B, A)
ws(Fr, "private")
TODAY = today()
Y = TODAY.year


def run(S, who, member=None, stranger=None):
    def ok(cond, what):
        return check(cond, f"{who}: {what}")

    r = S.put(B + OF + "/settings", json={"company": {"name": COMPANY["name"]}, "lang": "de", "currency": "EUR", "payment_days": 14,
                                       "company_fields": COMPANY, "invoice_scheme": MAIN, "credit_shared": 1,
                                       "overdue_notice": 1, "dunning_suggest": 1, "dunning_grace_days": 0})
    ok(r.ok, "office settings " + r.text[:200])
    s = S.get(B + OF + "/settings").json().get("settings") or {}
    ok(s.get("invoice_scheme") == MAIN and s.get("credit_shared") and s.get("credit_scheme", "").endswith("_RK"), f"setup: the main range as before {s.get('credit_scheme')}")
    cl = S.post(B + "/api/clients", json={"name": "Testkunde Nord", "street": "Marktstraße 5", "zip": "50667", "city": "Köln", "country": "DE"})
    assert cl.status_code == 201, cl.text
    CL = cl.json()["id"]

    def invoice(**kw):
        r = S.post(B + D, json={"kind": "invoice", "client_id": CL, "service_from": f"{Y}-01-01", "service_to": f"{Y}-01-02",
                                "items": [{"title": "Tarif Studio", "qty": 1, "rate": 150, "unit": "piece"}], **kw})
        assert r.status_code == 201, r.text
        return r.json()

    def fin(did, body=None):
        return S.post(B + f"{D}/{did}/finalize", json=body or {})

    def doc(did):
        return S.get(B + f"{D}/{did}").json()

    def ranges():
        return S.get(B + OF + "/number-ranges").json()

    def main_next():
        return {x["kind"]: x for x in ranges()["ranges"]}["invoice"]["next"]

    def extra(rid):
        return next((x for x in ranges().get("extra") or [] if x["id"] == rid), {})

    # ---------------------------------------------------------------- rights and rules of a range
    if member:
        r = member.post(B + "/api/office/num-ranges", json={"code": "MB", "scheme": "MB-{yyyy}-{seq:03}"})
        ok(r.status_code == 403, f"a member adds no range {r.status_code}")
    for bad in ("{client}-{seq}", "{seq}-GT", "GT-{date}-{seq}", MAIN, "GT-{yyyy}"):
        r = S.post(B + "/api/office/num-ranges", json={"code": "XX", "scheme": bad})
        ok(r.status_code == 400, f"scheme {bad}: 400 {r.status_code} {r.text[:120]}")
    r = S.post(B + "/api/office/num-ranges", json={"code": "gt", "name": "Plattform", "scheme": "GT-{yyyy}-{seq:03}"})
    ok(r.status_code == 201, "the admin adds the range GT " + r.text[:200])
    g = r.json()
    G = g["id"]
    ok(g["code"] == "GT" and g["credit_suffix"] == "-K" and g["dunning"] is False and g["next"] == 1 and g["preview"] == f"GT-{Y}-001"
       and g["credit_preview"] == f"GT-{Y}-001-K", f"the range: code upper case, -K, reminders off, next GT-{Y}-001 {g}")
    r = S.post(B + "/api/office/num-ranges", json={"code": "GT", "scheme": "GX-{yyyy}-{seq:03}"})
    ok(r.status_code == 400, f"a code twice: 400 {r.status_code}")
    # 2.1390.0 (#7037, Fable F3): a new range's correction scheme never one used already (here GT's corrections GT-...-K)
    r = S.post(B + "/api/office/num-ranges", json={"code": "GK", "scheme": "GT-{yyyy}-{seq:03}-", "credit_suffix": "K"})
    ok(r.status_code == 400, f"#7037 F3: a correction scheme taken by GT: 400 {r.status_code} {r.text[:160]}")
    # 2.1390.0 (#7037, Fable F4): the settings never give a main series the scheme of a range (nor its correction scheme)
    for sch in ("GT-{yyyy}-{seq:03}", "GT-{yyyy}-{seq:03}-K"):
        r = S.put(B + OF + "/settings", json={"invoice_scheme": sch})
        ok(r.status_code == 400, f"#7037 F4: the invoice scheme {sch} of the range GT refused {r.status_code} {r.text[:160]}")
    ok((S.get(B + OF + "/settings").json().get("settings") or {}).get("invoice_scheme") == MAIN, "#7037 F4: the main scheme stays")
    if member:
        x = member.get(B + OF + "/number-ranges").json()
        ok(any(e["id"] == G for e in x.get("extra") or []), "a member reads the range with the series")
        r = member.patch(B + f"/api/office/num-ranges/{G}", json={"name": "x"})
        ok(r.status_code == 403, f"a member changes no range {r.status_code}")
        r = member.delete(B + f"/api/office/num-ranges/{G}")
        ok(r.status_code == 403, f"a member removes no range {r.status_code}")
    if stranger:
        r = stranger.patch(B + f"/api/office/num-ranges/{G}", json={"name": "fremd"})
        ok(r.status_code in (403, 404), f"another office: PATCH {r.status_code}")
        r = stranger.delete(B + f"/api/office/num-ranges/{G}")
        ok(r.status_code in (403, 404), f"another office: DELETE {r.status_code}")
        r = stranger.post(B + f"/api/office/number-ranges/r{G}", json={"next": 50, "reason": "fremd"})
        ok(r.status_code in (403, 404), f"another office: the next number {r.status_code}")
        ok(extra(G).get("name") == "Plattform" and extra(G).get("next") == 1, "... nothing changed")

    # ---------------------------------------------------------------- two ranges count apart, the date of the range
    m0 = main_next()
    g1 = invoice(range_id=G, date=f"{Y}-01-02")
    ok(g1.get("range_id") == G, "a draft in the range")
    pv = S.get(B + f"{D}/{g1['id']}/number-preview").json()
    ok(pv.get("number") == f"GT-{Y}-001", f"the finalise dialog shows the range's number {pv}")
    r = fin(g1["id"])
    j = r.json() if r.ok else {}
    ok(r.ok and j.get("number") == f"GT-{Y}-001", f"first invoice of GT {r.status_code} {r.text[:200]}")
    ok(doc(g1["id"])["date"] == TODAY.isoformat(), f"Kalmido set the date of the day it was finalised {doc(g1['id'])['date']}")
    ok(main_next() == m0, f"the main counter did not move {m0} -> {main_next()}")
    m1 = invoice(date=(TODAY - timedelta(days=1)).isoformat())
    r = fin(m1["id"])
    m1n = r.json().get("number") if r.ok else ""
    ok(r.ok and re.fullmatch(rf"{m0}_[A-Z]{{3}}_{(TODAY - timedelta(days=1)).isoformat()}_R", m1n or ""),
       f"a main invoice dated yesterday after the range's one of today, the main scheme and counter {r.text[:200]}")
    ok(main_next() == m0 + 1, "the main counter continues by one")
    m2 = invoice(date=(TODAY - timedelta(days=3)).isoformat())
    r = fin(m2["id"])
    ok(r.status_code == 400, f"the main range keeps its own date order (older date refused) {r.status_code}")
    S.patch(B + f"{D}/{m2['id']}", json={"date": TODAY.isoformat()})

    # ---------------------------------------------------------------- no number by hand in a range
    g2 = invoice(range_id=G)
    r = fin(g2["id"], {"number": f"GT-{Y}-050", "reason": "Sprung im Test"})
    ok(r.status_code == 400 and "by hand" in r.text, f"a number by hand in the range: 400 {r.status_code} {r.text[:200]}")
    ok(main_next() == m0 + 1 and extra(G).get("next") == 2, f"neither counter moved {main_next()} {extra(G).get('next')}")
    ok(not doc(g2["id"]).get("number"), "the draft has no number")
    r = fin(g2["id"])
    ok(r.ok and r.json().get("number") == f"GT-{Y}-002", "the next of the range " + r.text[:200])

    # ---------------------------------------------------------------- the correction keeps the range, -K on the same counter
    r = S.post(B + f"{D}/{g1['id']}/credit", json={})
    ok(r.status_code == 201 and r.json().get("range_id") == G, f"the correction draft keeps the range {r.status_code} {r.text[:200]}")
    cr = r.json()
    r = S.patch(B + f"{D}/{cr['id']}", json={"range_id": None})
    ok(r.status_code == 409, f"a correction's range does not change {r.status_code}")
    r = fin(cr["id"])
    ok(r.ok and r.json().get("number") == f"GT-{Y}-003-K", f"the correction on the range's counter with -K {r.text[:200]}")

    # ---------------------------------------------------------------- the chain per range
    ch = S.get(B + OF + "/log/chain").json()
    ok(ch.get("ok") is True and ch.get("pending") == 0, f"the office's chain check intact {ch}")
    rows = sql("SELECT id, chain_key, chain_seq FROM office_docs WHERE id IN (?, ?, ?, ?) ORDER BY chain_seq", (g1["id"], g2["id"], cr["id"], m1["id"]))
    keys = {i: (k, q) for i, k, q in rows}
    ok([keys.get(x) for x in (g1["id"], g2["id"], cr["id"])] == [(f"r{G}", 1), (f"r{G}", 2), (f"r{G}", 3)], f"the range's own chain {keys}")
    ok(keys.get(m1["id"], ("",))[0] == "invoice", f"the main invoice in the main chain {keys.get(m1['id'])}")

    # ---------------------------------------------------------------- the year: the counter per period of the scheme
    sql("INSERT INTO office_numbers(org_id, kind, period, last) SELECT org_id, ?, ?, 41 FROM office_docs WHERE id=?", (f"r{G}", str(Y - 1), g1["id"]), write=True)
    ok(extra(G).get("next") == 4 and extra(G).get("period") == str(Y), f"the year before's counter leaves this year's alone {extra(G)}")

    # ---------------------------------------------------------------- list filter, copy, quotation numbers
    ids = {x["id"] for x in S.get(B + D + f"?kind=invoice&range={G}").json().get("docs", [])}
    ok({g1["id"], g2["id"]} <= ids and m1["id"] not in ids, f"list filter by range {ids}")
    ids = {x["id"] for x in S.get(B + D + "?kind=invoice&range=main").json().get("docs", [])}
    ok(m1["id"] in ids and g1["id"] not in ids, "list filter main range")
    r = S.post(B + f"{D}/{g1['id']}/duplicate", json={})
    ok(r.status_code == 201 and r.json().get("range_id") is None, f"a copy starts in the main range {r.text[:160]}")
    off = S.post(B + D, json={"kind": "offer", "client_id": CL, "items": [{"title": "Kamera", "qty": 1, "rate": 500}]}).json()
    r = S.post(B + f"{D}/{off['id']}/number", json={"number": f"GT-{Y}-099"})
    ok(r.status_code == 400, f"a quotation number of the range's scheme: 400 {r.status_code}")

    # ---------------------------------------------------------------- payment reminders per range (default off)
    past = (TODAY - timedelta(days=30)).isoformat()
    sql("UPDATE office_docs SET due_date=? WHERE id IN (?, ?)", (past, g2["id"], m1["id"]), write=True)

    def marked(did):
        return bool(sql("SELECT 1 FROM office_dunning_marks WHERE doc_id=?", (did,)))
    ok(until(lambda: marked(m1["id"]), 90), "the main range's overdue invoice is told about")
    ok(not marked(g2["id"]), "the range's overdue invoice is not (reminders off)")
    r = S.patch(B + f"/api/office/num-ranges/{G}", json={"dunning": True})
    ok(r.ok and r.json().get("dunning") is True, "reminders switched on for the range " + r.text[:160])
    ok(until(lambda: marked(g2["id"]), 90), "... now the range's overdue invoice is told about too")

    # ---------------------------------------------------------------- one way, close, remove
    r = S.delete(B + f"/api/office/num-ranges/{G}")
    ok(r.status_code == 409, f"a used range is never removed {r.status_code}")
    r = S.patch(B + f"/api/office/num-ranges/{G}", json={"scheme": "GT{yyyy}-{seq:04}"})
    ok(r.ok and extra(G).get("preview") == f"GT{Y}-0004", f"a new scheme applies from the next number on {r.text[:160]}")
    logs = [x for x in S.get(B + OF + "/log?limit=500").json().get("log", []) if x["action"] == "num_range"]
    ok(any((x.get("detail") or {}).get("after", {}).get("scheme") == "GT{yyyy}-{seq:04}" for x in logs), "the change is in the office log")
    S.patch(B + f"/api/office/num-ranges/{G}", json={"scheme": "GT-{yyyy}-{seq:03}"})
    t = S.post(B + "/api/office/num-ranges", json={"code": "TS", "scheme": "TS-{yyyy}-{seq:03}"}).json()
    td = invoice(range_id=t["id"])
    r = S.delete(B + f"/api/office/num-ranges/{t['id']}")
    ok(r.ok and doc(td["id"]).get("range_id") is None, f"an unused range goes, its draft back to the main range {r.status_code}")
    g3 = invoice(range_id=G)
    r = S.patch(B + f"/api/office/num-ranges/{G}", json={"closed": True})
    ok(r.ok and r.json().get("closed") is True, "the range closed")
    r = S.post(B + D, json={"kind": "invoice", "client_id": CL, "range_id": G})
    ok(r.status_code == 409, f"a closed range takes no new invoice {r.status_code}")
    r = fin(g3["id"])
    ok(r.status_code == 409, f"... nor finalises an older draft {r.status_code}")
    r = S.post(B + f"{D}/{g2['id']}/credit", json={})
    r = fin(r.json()["id"]) if r.status_code == 201 else r
    ok(r.ok and r.json().get("number", "").endswith("-K"), f"a correction stays possible in a closed range {r.text[:160]}")
    # 2.1390.0 (#7037, Fable F1): a closed range opens only with a scheme the office accepts (an import closes one it refused)
    sql("UPDATE office_num_ranges SET scheme=? WHERE id=?", (MAIN, G), write=True)
    r = S.patch(B + f"/api/office/num-ranges/{G}", json={"closed": False})
    ok(r.status_code == 400 and extra(G).get("closed") is True, f"#7037 F1: the main scheme in a closed range: opening refused {r.status_code} {r.text[:160]}")
    sql("UPDATE office_num_ranges SET scheme=? WHERE id=?", ("GT-{yyyy}-{seq:03}", G), write=True)
    S.patch(B + f"/api/office/num-ranges/{G}", json={"closed": False})
    ok(extra(G).get("closed") is False, "#7037 F1: with its valid scheme it opens again")

    # ---------------------------------------------------------------- the auditor's export
    r = S.get(B + OF + f"/gobd/export?from={Y}-01-01&to={Y}-12-31")
    ok(r.ok, f"auditor's export {r.status_code}")
    if r.ok:
        z = zipfile.ZipFile(io.BytesIO(r.content))
        name = next((n for n in z.namelist() if n.endswith("number_ranges.csv")), None)
        rows = list(csv.reader(io.StringIO(z.read(name).decode("utf-8-sig")), delimiter=";")) if name else []
        ok(any(row and row[0].startswith("GT: ") for row in rows), f"number_ranges.csv names the range {rows[:4]}")
    return G


# ---------------------------------------------------------------- the organisation's office  # tenant-matrix: office
run(A, "org", member=Bo, stranger=Fr)
# ---------------------------------------------------------------- the personal office of a person without an organisation  # freelancer-matrix: office
FG = run(Fr, "private", stranger=A)
PB = sql("SELECT id FROM orgs WHERE personal_of=?", (FID,))[0][0]

# ---------------------------------------------------------------- the move of the personal office into an organisation
BETA = A.post(B + "/api/admin/orgs", json={"name": "Beta", "admin_id": FID}).json()["id"]
ws(Fr, f"org:{BETA}")
r = Fr.post(B + "/api/office/num-ranges", json={"code": "GT", "scheme": "GTB-{yyyy}-{seq:03}"})
check(r.status_code == 201, "move: the organisation has a range GT of its own " + r.text[:160])
BG = r.json().get("id") if r.status_code == 201 else None
ws(Fr, "private")
r = Fr.get(B + OF + f"/move/check?org={BETA}")
check(r.ok and r.json().get("ok") is False and any("GT" in x for x in r.json().get("conflicts") or []), f"move: the same code refuses the move {r.text[:300]}")
ws(Fr, f"org:{BETA}")
if BG:
    check(Fr.delete(B + f"/api/office/num-ranges/{BG}").ok, "move: the organisation's unused range removed")
# 2.1390.0 (#7037, Fable F2): a range of the organisation with another code but the scheme of the moving range refuses the move too
r = Fr.post(B + "/api/office/num-ranges", json={"code": "PT", "scheme": "GT-{yyyy}-{seq:03}"})
check(r.status_code == 201, "move: the organisation's range PT numbers like the personal GT " + r.text[:160])
BP = r.json().get("id") if r.status_code == 201 else None
ws(Fr, "private")
r = Fr.get(B + OF + f"/move/check?org={BETA}")
check(r.ok and r.json().get("ok") is False and any(x.startswith("GT:") for x in r.json().get("conflicts") or []), f"#7037 F2: the same scheme refuses the move {r.text[:300]}")
ws(Fr, f"org:{BETA}")
if BP:
    check(Fr.delete(B + f"/api/office/num-ranges/{BP}").ok, "move: the range PT removed")
ws(Fr, "private")
nxt = next(x for x in Fr.get(B + OF + "/number-ranges").json()["extra"] if x["id"] == FG)["next"]
r = Fr.post(B + OF + "/move/org", json={"org": BETA, "confirm": True})
check(r.ok, f"move: the personal office moves {r.status_code} {r.text[:300]}")
check(not sql("SELECT 1 FROM office_numbers WHERE org_id=? AND kind=?", (PB, f"r{FG}")), "move: no counter of the range left in the personal office")
ws(Fr, f"org:{BETA}")
x = next((e for e in Fr.get(B + OF + "/number-ranges").json().get("extra") or [] if e["id"] == FG), {})
check(x.get("code") == "GT" and x.get("next") == nxt, f"move: the range moved with its counter (next {nxt}) {x}")
assert Fr.put(B + OF + "/settings", json={"company_fields": COMPANY}).ok
c2 = Fr.post(B + "/api/clients", json={"name": "Testkunde Süd", "street": "Domplatz 1", "zip": "50667", "city": "Köln", "country": "DE"}).json()["id"]
r = Fr.post(B + D, json={"kind": "invoice", "client_id": c2, "range_id": FG, "service_from": f"{Y}-01-01", "service_to": f"{Y}-01-02", "items": [{"title": "Tarif", "qty": 1, "rate": 100, "unit": "piece"}]})
r = Fr.post(B + f"{D}/{r.json()['id']}/finalize", json={}) if r.status_code == 201 else r
check(r.ok and r.json().get("number") == f"GT-{Y}-{nxt:03d}", f"move: the next number continues {r.text[:200]}")
ch = Fr.get(B + OF + "/log/chain").json()
check(ch.get("ok") is True and ch.get("pending") == 0, f"move: the organisation's chain intact {ch}")

sys.exit(kt.done("p6698_office_numranges"))
