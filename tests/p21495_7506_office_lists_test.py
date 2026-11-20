#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1495.0 (#7506) the office lists work on what they show, not on the data of all years. Own container, org encryption on;
invented companies, people and figures only. tenant-matrix: office  freelancer-matrix: office
 - cash book: entries and cancellations over four years; the year view = the same entries (balance after, cancelled_by /
   storno_of with their numbers) as the full view; the box overview counts and adds up every year (balance, entries) as the
   full list does; the CSV of a year still carries the change log of its entries
 - credit card sheet: an open position gets its suggestion from the documents of its amount or of its original amount (a
   name alone is no suggestion, also with several name hits of another amount); the statements of the sheet stay the same
   (at most +2) for 6 more documents of other amounts (was: every document decrypted and scored for every position)
 - cash flow: a travel receipt counts in its month, also when the trip began in the year before; a trip of another year is
   not in the period; a receipt without a day counts on the trip's first day
 - the same for a person without an organisation (personal office)
usage: p21495_7506_office_lists_test.py <datadir>"""
import re
import sys

import kt
import testclock
from kt import B, check, dbx, until
from freelancer_fixture import freelancer

kt.fresh(env={"KALMIDO_INSTANCE_MODE": "workspaces", "KALMIDO_ORGCRYPT_DELAY": "0", "KALMIDO_TEST_TIMING_ALL": "1"}, prefix="P21495")
kt.docker_logs_on_first_fail(tail=120, chars=9000)
FEAT = "cal,comments,collab,office,clients,docs"
A = kt.setup()
A.patch(B + "/api/settings", json={"lang": "en", "features": FEAT, "tour": "done"})
ALICE = A.get(B + "/api/state").json()["me"]["id"]
ORG = A.post(B + "/api/admin/orgs", json={"name": "Alpha Example", "admin_id": ALICE}).json()["id"]
A.patch(B + "/api/settings", json={"workspace": f"org:{ORG}"})
FID, Fr = freelancer(B, A, features=FEAT)
OF = "/api/office"
K = OF + "/cards"
TODAY = testclock.today()
Y = TODAY.year - 1  # closed years only: nothing of the test lies in the future
TIMING = re.compile(r'db;dur=[\d.]+;desc="n=(\d+)"')


def nstmt(r):
    m = TIMING.search(r.headers.get("Server-Timing", ""))
    return int(m.group(1)) if m else -1


def pdf(lines):
    """A PDF with a text layer, one line per entry (hand-written, no library)."""
    body_ = "\n".join(f"({x}) Tj T*" for x in lines)
    stream = f"BT /F1 10 Tf 12 TL 40 760 Td\n{body_}\nET".encode("latin-1")
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"]
    out, offs = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    x = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1) + b"".join(b"%010d 00000 n \n" % o for o in offs)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, x)
    return out


def strip(e):
    return {k: v for k, v in e.items() if k not in ("locked",)}


def cashbook(who, s):
    books = s.get(B + OF + "/cashbooks").json()["books"]
    bid = books[0]["id"]
    r = s.patch(B + OF + f"/cashbooks/{bid}", json={"opening": "500.00", "opening_day": f"{Y - 3}-01-01"})
    check(r.ok, f"{who}: the opening of the box four years back {r.text[:200]}")
    ids = {}
    for y in range(Y - 3, Y + 1):
        for i, (d, a) in enumerate((("in", "40.00"), ("out", "12.50"), ("out", "7.30"))):
            r = s.post(B + OF + f"/cashbooks/{bid}/entries", json={"day": f"{y}-0{i + 3}-1{i}", "dir": d, "amount": a, "text": f"Example {y} {i}"})
            assert r.status_code == 201, r.text
            ids[(y, i)] = r.json()["id"]
    # a cancellation in the year of the entry, one of an old entry booked a year later
    r1 = s.post(B + OF + f"/cash-entries/{ids[(Y - 2, 1)]}/cancel", json={"day": f"{Y - 2}-11-02"})
    r2 = s.post(B + OF + f"/cash-entries/{ids[(Y - 1, 2)]}/cancel", json={"day": f"{Y}-01-05"})
    check(r1.status_code == 201 and r2.status_code == 201, f"{who}: two cancellations {r1.text[:150]} {r2.text[:150]}")
    full = {e["id"]: strip(e) for e in s.get(B + OF + f"/cashbooks/{bid}/entries?from={Y - 3}-01-01&to={Y}-12-31").json()["entries"]}
    check(len(full) == 14, f"{who}: every entry of four years in the full list ({len(full)})")
    seen = 0
    for y in range(Y - 3, Y + 1):
        j = s.get(B + OF + f"/cashbooks/{bid}/entries?year={y}").json()
        got = {e["id"]: strip(e) for e in j["entries"]}
        seen += len(got)
        check(got and all(full[i] == e for i, e in got.items()),
              f"{who}: the year {y} shows its entries as the full list does (balance after, links) "
              f"{[(e, full.get(i)) for i, e in got.items() if full.get(i) != e][:2]}")
    check(seen == 14, f"{who}: the years together are the full list ({seen})")
    c1 = full[ids[(Y - 2, 1)]]
    check(c1.get("cancelled_by") and full.get(r1.json()["entry"]["id"], {}).get("storno_of"),
          f"{who}: the cancelled entry and its cancellation point at each other {c1}")
    y1 = {e["id"]: e for e in s.get(B + OF + f"/cashbooks/{bid}/entries?year={Y - 1}").json()["entries"]}
    check(y1[ids[(Y - 1, 2)]].get("cancelled_by"), f"{who}: cancelled by an entry of the next year, the link stays in the year view {y1[ids[(Y - 1, 2)]]}")
    j = s.get(B + OF + f"/cashbooks/{bid}/entries?year={Y}").json()
    bk = next(b for b in s.get(B + OF + "/cashbooks").json()["books"] if b["id"] == bid)
    # 500 + 4 * (40 - 12.50 - 7.30) + the two cancellations back (+12.50 +7.30)
    check(bk["entries"] == 14 and bk["balance"] == j["balance"] == "600.60",
          f"{who}: the box overview counts and adds up every year like the list {bk} {j['balance']}")
    r = s.get(B + OF + f"/cashbook.csv?book_id={bid}&year={Y - 1}")
    check(r.ok and r.text.count("Example") >= 3 and ("cancel" in r.text.lower() or "storn" in r.text.lower()), f"{who}: the year's CSV with the change log {r.status_code} {r.text[-300:]}")


def doc(s, ws, name, amount, day, currency=None):
    r = s.post(B + "/api/docs", data={"ws": ws}, files={"files": (name, pdf(["Rechnung " + name]), "application/pdf")})
    assert r.ok, r.text
    nid = r.json()["ids"][0]
    until(lambda: (dbx("SELECT state FROM doc_meta WHERE node_id=?", (nid,)) or [["wait"]])[0][0] in ("done", "failed"), 30)
    b = {"amount": amount, "date": day}
    if currency:
        b["currency"] = currency
    r = s.patch(B + f"/api/docs/{nid}", json=b)
    assert r.ok, r.text
    return nid


def cards(who, s, ws, holder):
    r = s.post(B + K, json={"holder_id": holder, "last4": "4711"})
    assert r.status_code == 201, r.text
    card = r.json()["id"]
    lines = [f"Kreditkartenabrechnung vom 15.03.{Y}", "Beispielbank Mastercard Business", "Karte 5232 12XX XXXX 4711", "Saldo Vormonat 50,00-", "01.03. 01.03. Ihre Zahlung 50,00+",
             "02.03. 02.03. Werkstatt Beispiel 61,20-", "03.03. 04.03. Hosting Beispiel Inc USD 30,00 27,60-", "05.03. 05.03. Papier Beispiel 9,90-",
             "Neuer Saldo 98,70-"]
    r = s.post(B + f"{K}/{card}/statements", files={"file": ("stmt.pdf", pdf(lines), "application/pdf")})
    check(r.status_code == 201 and r.json()["read"] is True, f"{who}: statement read {r.text[:200]}")
    sid = r.json()["statement"]["id"]
    check(s.post(B + f"{K}/statements/{sid}/confirm", json={}).ok, f"{who}: confirmed")
    shop = doc(s, ws, "werkstatt.pdf", "61.20", f"{Y}-03-02")
    host = doc(s, ws, "hosting.pdf", "30.00", f"{Y}-03-03", "USD")
    for i in range(3):  # the name fits, the amount does not
        doc(s, ws, f"papier-beispiel-{i}.pdf", f"{19 + i}.00", f"{Y}-03-05")
    r = s.get(B + f"{K}/statements/{sid}")
    L = r.json()["lines"]
    n0 = nstmt(r)
    check(L[0].get("suggestion", {}) and L[0]["suggestion"]["id"] == shop, f"{who}: the document of the same amount is the suggestion {L[0].get('suggestion')}")
    check(L[1].get("suggestion", {}) and L[1]["suggestion"]["id"] == host, f"{who}: the original amount finds its document {L[1].get('suggestion')}")
    check(L[2].get("suggestion") is None, f"{who}: name hits of another amount suggest nothing {L[2].get('suggestion')}")
    for i in range(6):
        doc(s, ws, f"anderes-{i}.pdf", f"{70 + i}.00", f"{Y}-02-1{i}")
    r = s.get(B + f"{K}/statements/{sid}")
    n1 = nstmt(r)
    check(n0 > 0 and n1 <= n0 + 2, f"{who}: the sheet's statements stay for 6 more documents ({n0} -> {n1})")
    check([x.get("suggestion", {}) and x["suggestion"]["id"] for x in r.json()["lines"]][:2] == [shop, host], f"{who}: the same suggestions")


def cashflow(who, s):
    m = f"{Y}-06"
    trips = [  # (date_from, items) -> what of it counts in June .. August of Y
        (f"{Y}-05-29", [{"date": f"{Y}-06-02", "category": "hotel", "amount": "110"}]),  # began before, receipt in the period
        (f"{Y - 1}-06-10", [{"date": f"{Y - 1}-06-10", "category": "taxi", "amount": "23"}]),  # a year before: not counted
        (f"{Y}-07-04", [{"category": "train", "amount": "44"}]),  # no day: the trip's first day
    ]
    tids = []
    for frm, items in trips:
        r = s.post(B + OF + "/trips", json={"date_from": frm, "dest": "Example Town", "purpose": "job", "items": items})
        check(r.status_code == 201, f"{who}: a trip {r.text[:200]}")
        tids.append(r.json()["id"] if r.ok else None)
    cf = s.get(B + OF + f"/cashflow?from={m}&months=3").json()
    got = sorted((e["date"], e["amount"], e["trip_id"]) for e in cf.get("entries", []) if e.get("kind") == "trip")
    check(got == [(f"{Y}-06-02", "110.00", tids[0]), (f"{Y}-07-04", "44.00", tids[2])],
          f"{who}: the travel receipts of the period, nothing of another year {got}")
    cf = s.get(B + OF + f"/cashflow?from={Y - 1}-06&months=1").json()
    got = [(e["date"], e["amount"]) for e in cf.get("entries", []) if e.get("kind") == "trip"]
    check(got == [(f"{Y - 1}-06-10", "23.00")], f"{who}: the year before shows its own {got}")


for who, s, ws, uid in (("org", A, f"org:{ORG}", ALICE), ("freelancer", Fr, "private", FID)):
    cashbook(who, s)
    cards(who, s, ws, uid)
    cashflow(who, s)

sys.exit(kt.done("p21495_7506_office_lists"))
