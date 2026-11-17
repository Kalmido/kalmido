#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1327.0 API tests (#6816): the subtotal of the positions before the first surcharge / discount on a quotation with parts
(title page and a part's own page), in its print model, its PDF and the invoice made from it; the discount line names its base.
Once in the personal office of a person without an organisation (freelancer fixture; freelancer-matrix: office) and once in an
organisation's office (its admin). Invented companies, people and figures only.
 - title page "Regie" 1000.00 + part A "Schnitt" 2 x 500.00 + part B "Buchlizenz" 400.00 (7 %), surcharge 15 %, discount 5 %:
   one line {kind: subtotal, items: 1} = items_net 2400.00 right before the surcharge, none between surcharge and discount; the
   discount's explanation "5 % auf die rabattfähigen Positionen (2.400,00 €)"; net / gross as without it
 - part A with its own discount 10 %: its page has the subtotal 1000.00 before its discount
 - the print model (render) and the PDF have the row "Zwischensumme" before "Zuschlag"; a flat price quotation has none
 - the invoice from the quotation (parts_mode full): the subtotal before its markup position, the same net as the quotation
 - a quotation sent before (cached totals without "it_sub", status sent): its print model keeps the lines it was sent with (no
   subtotal, the discount's explanation without its base); a draft from before set to sent is computed once more and takes them
usage: p6816_zwischensumme_api_test.py <datadir>"""
import io
import os
import sys

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
from freelancer_fixture import FEATURES, freelancer  # noqa: E402
from kt import FAILS, OKS, check, sess  # noqa: E402
import requests  # noqa: E402
import dbx as dbxm  # noqa: E402

try:
    from pypdf import PdfReader
except ImportError:  # the PDF text is checked where pypdf is there
    PdfReader = None

B = "http://127.0.0.1:" + os.environ.get("KALMIDO_TEST_PORT", "3048")
H = {"X-Requested-With": "kalmido"}
OFC = "/api/office"
D = OFC + "/docs"
COMPANY = {"name": "Studio Nordlicht", "street": "Hafenstraße 12", "zip": "20457", "city": "Hamburg", "country": "DE",
           "email": "hallo@nordlicht.example", "phone": "+49 40 000000", "tax_number": "12/345/67890", "vat_id": "DE999999999",
           "iban": "DE02120300000000202051", "bic": "BYLADEM1001", "bank_name": "Beispielbank"}


def subs(lines):
    return [x for x in lines or [] if x.get("kind") == "subtotal" and x.get("items")]


def kinds(lines):
    return [x.get("kind") for x in lines or []]


def pdf_text(S, did):
    if PdfReader is None:
        return None
    r = S.get(B + f"{D}/{did}/pdf")
    return " ".join(x.extract_text() or "" for x in PdfReader(io.BytesIO(r.content)).pages) if r.ok else ""


def dbx(sql, args=()):
    return dbxm.connect(sys.argv[1]).execute(sql, args).fetchall()


def legacy(S, who):
    """A quotation sent before 2.1327.0 (its totals without "it_sub") keeps its lines (the hash of an open approval link); a
    draft from before set to sent is computed once more and takes them."""
    def ok(cond, what):
        check(cond, f"legacy {who}: {what}")

    def offer(title):
        r = S.post(B + D, json={"project_title": title, "raw_mode": "none", "producing_on": 0, "discount_pct": 5})
        assert r.status_code == 201, r.text
        did = r.json()["id"]
        ok(S.put(B + f"{D}/{did}/items", json={"items": [{"title": "Kamera", "qty": 2, "rate": 1000, "unit": "day"}]}).ok, "the position")
        return did

    OS = offer("Rabatt alt versendet")
    dbx("UPDATE office_docs SET totals=(totals::jsonb - 'it_sub')::text, status='sent' WHERE id=?", (OS,))
    rd = S.get(B + f"{D}/{OS}/render").json()
    dl = [x for x in rd.get("lines") or [] if x.get("kind") == "discount"]
    ok(not subs(rd.get("lines")) and dl and dl[0].get("detail") == "5 % auf die rabattfähigen Positionen",
       f"sent before: no subtotal, the discount's explanation as sent {kinds(rd.get('lines'))} {dl}")
    ODR = offer("Rabatt Entwurf alt")
    dbx("UPDATE office_docs SET totals=(totals::jsonb - 'it_sub')::text WHERE id=?", (ODR,))
    ok(S.post(B + f"{D}/{ODR}/status", json={"status": "sent"}).ok, "the draft from before set to sent")
    ok(dbx("SELECT (totals::jsonb ->> 'it_sub') FROM office_docs WHERE id=?", (ODR,))[0][0] == "1", "sent: its totals now say it_sub")
    rd = S.get(B + f"{D}/{ODR}/render").json()
    ok(len(subs(rd.get("lines"))) == 1, f"sent: it keeps the subtotal {kinds(rd.get('lines'))}")


def run(S, who):
    def ok(cond, what):
        check(cond, f"{who}: {what}")

    r = S.put(B + OFC + "/settings", json={"company": {"name": COMPANY["name"]}, "lang": "de", "currency": "EUR", "payment_days": 14,
                                         "company_fields": COMPANY, "industry_packs": []})
    ok(r.ok, "office settings " + r.text[:200])
    r = S.post(B + "/api/clients", json={"name": "Beispielkunde AG", "street": "Marktstraße 5", "zip": "50667", "city": "Köln", "country": "DE"})
    assert r.status_code == 201, r.text
    r = S.post(B + D, json={"client_id": r.json()["id"], "project_title": "Imagefilm", "raw_mode": "none", "producing_on": 0,
                            "service_from": "2026-10-01", "service_to": "2026-10-20"})
    assert r.status_code == 201, r.text
    OF = r.json()["id"]
    pids = []
    for title in ("Modul A", "Modul B"):
        r = S.post(B + f"{D}/{OF}/parts", json={"kind": "items", "title": title})
        ok(r.status_code in (200, 201), f"part {title} created {r.status_code} {r.text[:160]}")
        pids.append((r.json().get("part") or {}).get("id"))
    PA, PB = pids
    ok(S.put(B + f"{D}/{OF}/parts/{PA}/items", json={"items": [{"title": "Schnitt", "qty": 2, "rate": 500, "unit": "day"}]}).ok, "part A: its position")
    ok(S.put(B + f"{D}/{OF}/parts/{PB}/items", json={"items": [{"title": "Buchlizenz", "qty": 1, "rate": 400, "unit": "flat", "tax": "reduced"}]}).ok,
       "part B: its position")
    d = S.get(B + f"{D}/{OF}").json()
    title = [{k: x.get(k) for k in ("id", "kind", "title", "qty", "unit", "ref_part_id")} for x in d.get("items") or []]
    r = S.put(B + f"{D}/{OF}/items", json={"items": [{"title": "Regie", "qty": 1, "rate": 1000, "unit": "flat", "in_markup": 1}] + title,
                                            "parts_known": [PA, PB]})
    ok(r.ok, "title page: Regie + the two part lines " + r.text[:200])
    t = (S.get(B + f"{D}/{OF}").json().get("totals") or {})
    ok(not subs(t.get("lines")), f"no surcharge, no discount: no subtotal {kinds(t.get('lines'))}")
    r = S.patch(B + f"{D}/{OF}", json={"markup_pct": 15, "discount_pct": 5})
    ok(r.ok, "surcharge 15 % and discount 5 % " + r.text[:200])
    d = S.get(B + f"{D}/{OF}").json()
    t = d.get("totals") or {}
    ln = t.get("lines") or []
    s = subs(ln)
    k = kinds(ln)
    ok(len(s) == 1 and s[0]["total"] == t.get("items_net") == 2400 and s[0].get("label") == "Zwischensumme" and s[0].get("total_text") == "2.400,00 €",
       f"title page: one subtotal = items_net 2400.00 {s} {t.get('items_net')}")
    ok("subtotal" in k and k[k.index("subtotal") + 1] == "surcharge" and k[-1] == "discount" and k.count("subtotal") == 1,
       f"title page: right before the surcharge, none before the discount {k}")
    dl = [x for x in ln if x.get("kind") == "discount"]
    ok(dl and dl[0].get("detail") == "5 % auf die rabattfähigen Positionen (2.400,00 €)", f"the discount names its base {dl}")
    mk = [x for x in ln if x.get("kind") == "surcharge"]
    ok(mk and t.get("net") == 2400 + mk[0]["total"] - 120, f"the net: positions + surcharge - discount {t.get('net')} {mk}")
    # part A with its own discount
    r = S.patch(B + f"{D}/{OF}/parts/{PA}", json={"settings": {"discount_pct": 10}})
    ok(r.ok, "part A: its own discount 10 % " + r.text[:200])
    d = S.get(B + f"{D}/{OF}").json()
    pa = [p for p in d.get("parts") or [] if p.get("id") == PA]
    pl = ((pa[0].get("totals") or {}).get("lines") or []) if pa else []
    ok(kinds(pl) == ["item", "subtotal", "discount"] and subs(pl)[0]["total"] == 1000, f"part A: the subtotal before its discount {kinds(pl)} {subs(pl)}")
    # the print model and the PDF
    rd = S.get(B + f"{D}/{OF}/render").json()
    rk = kinds(rd.get("lines"))
    ok(len(subs(rd.get("lines"))) == 1 and rk[rk.index("subtotal") + 1] == "surcharge", f"print model: the title page's subtotal {rk}")
    rpa = [p for p in rd.get("parts") or [] if p.get("id") == PA]
    ok(rpa and len(subs(rpa[0].get("lines"))) == 1, "print model: part A's page has it too")
    txt = pdf_text(S, OF)
    if txt is not None:
        # part A is 900.00 now (its own discount): the title page's positions 2300.00
        ok("Zwischensumme 2.300,00 €" in txt and txt.index("Zwischensumme") < txt.index("Zuschlag") and "rabattfähigen Positionen (2.300,00 €)" in txt,
           "PDF: Zwischensumme before Zuschlag, the discount with its base " + txt[:900].replace("\n", " | "))
    # the invoice from the quotation
    r = S.post(B + f"{D}/{OF}/invoice", json={"force": True, "parts_mode": "full"})
    ok(r.status_code == 201, "invoice from the quotation " + r.text[:200])
    if r.status_code == 201:
        iv = r.json()
        il = (iv.get("totals") or {}).get("lines") or []
        si = subs(il)
        at = [i for i, x in enumerate(il) if x.get("kind") == "subtotal" and x.get("items")]
        nxt = il[at[0] + 1] if at and at[0] + 1 < len(il) else {}
        ok(len(si) == 1 and (nxt.get("sur_pct") is not None or nxt.get("kind") == "discount"),
           f"invoice: one subtotal before its markup / discount position {kinds(il)} {nxt}")
        ok((iv.get("totals") or {}).get("net") == f"{d['totals']['net']:.2f}", f"invoice: the quotation's net {(iv.get('totals') or {}).get('net')} {d['totals']['net']}")
        txt = pdf_text(S, iv["id"])
        if txt is not None:
            ok("Zwischensumme" in txt, "invoice PDF: the row " + txt[:600].replace("\n", " | "))
        S.delete(B + f"{D}/{iv['id']}")
    # a flat price quotation: no subtotal of the positions in its print model
    r = S.patch(B + f"{D}/{OF}", json={"flat_print": 1})
    ok(r.ok, "flat price on " + r.text[:160])
    rd = S.get(B + f"{D}/{OF}/render").json()
    ok(rd.get("flat") is True and not subs(rd.get("lines")) and not any(subs(p.get("lines")) for p in rd.get("parts") or []),
       f"flat price: no subtotal of the positions {kinds(rd.get('lines'))}")


s0 = requests.Session()
s0.headers.update(H)
assert s0.post(B + "/api/auth/setup", json={"username": "alice", "display_name": "Alice Admin", "password": "password123"}).ok
A = sess("alice")
A.post(B + "/api/admin/setup", json={"lang": "en"})
FEAT = FEATURES if "office" in FEATURES else FEATURES + ",office"
A.patch(B + "/api/settings", json={"lang": "en", "features": FEAT, "tour": "done"})
ALICE = A.get(B + "/api/state").json()["me"]["id"]
r = A.post(B + "/api/admin/orgs", json={"name": "Alpha", "admin_id": ALICE})
assert r.status_code == 201, r.text
A.patch(B + "/api/settings", json={"workspace": f"org:{r.json()['id']}"})
FID, Fr = freelancer(B, A)

run(Fr, "freelancer")
run(A, "organisation")
legacy(Fr, "freelancer")
legacy(A, "organisation")
print(f"p6816_zwischensumme_api: {OKS[0]} ok, {len(FAILS)} failed")
sys.exit(1 if FAILS else 0)
