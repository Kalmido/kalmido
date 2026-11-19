#!/usr/bin/env python3
# kalmido-suite: after=p2296_a_pdfa nodata
"""2.1327.0 (#6816): the subtotal of the positions before the first surcharge / discount, and the discount line naming its base
(kalmido/office/calc.py + pdf.py of the source tree), no server, no container. Invented companies and figures only.
freelancer-matrix: office (the calculator and the PDF know no organisation; the API suite p6816_zwischensumme_api_test runs the
quotation, its parts and its invoice as a person without an organisation)
 - office_calc: a line {kind: subtotal, items: 1} = items_net ("Zwischensumme" / "Subtotal") right before the first line after the
   positions (a surcharge, included raw data, the discount; producing counts as a position since #7291); with a surcharge and a discount only once (before the
   surcharge); only a discount: before it; nothing after the positions (or only the raw data option): none; with the sections'
   subtotals on: after the last section's one; the sums (net, tax, gross, discount) the same
 - the discount's explanation always names its base (the discountable positions): "5 % auf die rabattfähigen Positionen
   (1.200,00 €)", "Fester Betrag auf die rabattfähigen Positionen (…)", English likewise
 - a quotation sent before (doc["sub_legacy"], docs._sub_legacy): no subtotal, the explanation without its base; else it_sub = 2
   (2.1435.0, #7291: the producing line counts like a position; p7291_producing_sub_test)
 - inv_calc: before a trailing discount position or a markup position from a quotation (sur_pct) the sum of the positions
   above; a discount between positions or a final invoice's deductions (abs_tax): none
 - the PDF: the row "Zwischensumme" bold between the last position and the surcharge, a short rule above its amount; with
   sections and only a discount (that goes into the totals as "Summe Positionen") no row in the table
usage: p6816_zwischensumme_test.py            (KALMIDO_SRC = the source tree, default ../ next to tests/)"""
import importlib.util
import os
import sys
from decimal import Decimal

N = os.path.dirname(os.path.abspath(__file__))
SRC = os.environ.get("KALMIDO_SRC") or os.path.join(N, "..")


def load(name):
    spec = importlib.util.spec_from_file_location("office_" + name, os.path.join(SRC, "kalmido", "office", name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pdf, calc = load("pdf"), load("calc")
sys.path.insert(0, N)
import pdfcheck  # noqa: E402
from kt import check, done  # noqa: E402

PACK = {"tax": {"standard": 19, "reduced": 7, "exempt": 0}}
DOC = {"lang": "de", "currency": "EUR", "raw_mode": "none", "producing_on": 0}


def it(title, qty, rate, **kw):
    return {"kind": "service", "title": title, "qty": qty, "rate": rate, "unit": "day", "tax": "standard", **kw}


def kinds(t):
    return [x["kind"] for x in t["lines"]]


def subs(t):
    return [x for x in t["lines"] if x["kind"] == "subtotal" and x.get("items")]


ITS = [it("Dreh", 2, 4200, in_markup=1), it("Schnitt", 1, 4600, in_markup=1), it("Musik", 1, 1200, discountable=0)]
# ---------------------------------------------------------------- the calculator
base = calc.office_calc(DOC, ITS, PACK)
check(not subs(base) and kinds(base) == ["item"] * 3, f"nothing after the positions: no subtotal {kinds(base)}")
t = calc.office_calc({**DOC, "markup_pct": 10}, ITS, PACK)
s = subs(t)
check(kinds(t) == ["item"] * 3 + ["subtotal", "surcharge"], f"surcharge: the subtotal right before it {kinds(t)}")
check(len(s) == 1 and s[0]["total"] == t["items_net"] == 14200 and s[0]["label"] == "Zwischensumme" and s[0]["total_text"] == "14.200,00 €",
      f"its amount = items_net, label and text {s}")
t = calc.office_calc({**DOC, "markup_pct": 10, "discount_pct": 5}, ITS, PACK)
check(kinds(t) == ["item"] * 3 + ["subtotal", "surcharge", "discount"], f"surcharge + discount: one subtotal, before the surcharge {kinds(t)}")
dl = [x for x in t["lines"] if x["kind"] == "discount"][0]
check(dl["detail"] == "5 % auf die rabattfähigen Positionen (13.000,00 €)" and dl["total"] == -650,
      f"the discount names its base (Musik is not discountable): {dl['detail']} {dl['total']}")
check(t["net"] == 14200 + 1300 - 650 and t["discount"] == 650 and t["markup_total"] == 1300, f"the sums as before {t['net']}")
t = calc.office_calc({**DOC, "discount_pct": 5}, ITS, PACK)
check(kinds(t) == ["item"] * 3 + ["subtotal", "discount"] and subs(t)[0]["total"] == 14200, f"only a discount: before it {kinds(t)}")
t = calc.office_calc({**DOC, "discount_amount": 500}, ITS, PACK)
dl = [x for x in t["lines"] if x["kind"] == "discount"][0]
check(dl["detail"] == "Fester Betrag auf die rabattfähigen Positionen (13.000,00 €)", f"a fixed amount names its base too: {dl['detail']}")
t = calc.office_calc({**DOC, "lang": "en", "discount_pct": 5, "markup_pct": 10}, ITS, PACK)
dl = [x for x in t["lines"] if x["kind"] == "discount"][0]
check(subs(t)[0]["label"] == "Subtotal" and dl["detail"] == "5 % on the discountable positions (€13,000.00)", f"English: {subs(t)} {dl['detail']}")
t = calc.office_calc({**DOC, "producing_on": 1, "prod_quotient": 1, "producing_rate": 100}, [it("Dreh", 2, 1000, producing=1)], PACK)
check(kinds(t) == ["item", "producing"] and not subs(t), f"(#7291): producing alone counts like a position, no subtotal {kinds(t)}")
PRD = {**DOC, "producing_on": 1, "prod_quotient": 1, "producing_rate": 100}
t = calc.office_calc({**PRD, "discount_pct": 5}, [it("Dreh", 2, 1000, producing=1)], PACK)
check(kinds(t) == ["item", "producing", "subtotal", "discount"] and subs(t)[0]["total"] == 2200 and t["discount"] == 100 and t["net"] == 2100,
      f"#7291: with a discount the subtotal after producing = positions + producing, the discount on the positions only {kinds(t)} {subs(t)}")
t = calc.office_calc({**PRD, "markup_pct": 10, "discount_pct": 5}, [it("Dreh", 2, 1000, producing=1, in_markup=1)], PACK)
check(kinds(t) == ["item", "producing", "subtotal", "surcharge", "discount"] and subs(t)[0]["total"] == 2200 and t.get("it_sub") == 2,
      f"#7291: surcharge + discount: once, after producing {kinds(t)}")
t = calc.office_calc({**PRD, "raw_mode": "included", "raw_factor": 0.25}, [it("Dreh", 2, 1000, producing=1, raw_fee=1)], PACK)
check(not subs(t), f"#7291: producing + included raw data, no surcharge / discount: none {kinds(t)}")
lg = calc.office_calc({**PRD, "discount_pct": 5, "prod_sub_legacy": 1}, [it("Dreh", 2, 1000, producing=1)], PACK)
check(kinds(lg) == ["item", "subtotal", "producing", "discount"] and subs(lg)[0]["total"] == 2000 and lg.get("it_sub") == 1,
      f"#7291: a quotation sent with the rule of #6816 (prod_sub_legacy): before producing, = items_net, it_sub 1 {kinds(lg)} {subs(lg)}")
lg = calc.office_calc({**PRD, "prod_sub_legacy": 1}, [it("Dreh", 2, 1000, producing=1)], PACK)
check(kinds(lg) == ["item", "subtotal", "producing"], f"#7291: ... also with producing alone {kinds(lg)}")
t = calc.office_calc({**DOC, "raw_mode": "optional", "raw_factor": 0.25}, [it("Dreh", 2, 1000, raw_fee=1)], PACK)
check(not subs(t), f"only the raw data option: none {kinds(t)}")
t = calc.office_calc({**DOC, "raw_mode": "included", "raw_factor": 0.25}, [it("Dreh", 2, 1000, raw_fee=1)], PACK)
check(not subs(t), f"only included raw data: none (no surcharge, no discount) {kinds(t)}")
t = calc.office_calc({**DOC, "raw_mode": "included", "raw_factor": 0.25, "discount_pct": 10}, [it("Dreh", 2, 1000, raw_fee=1)], PACK)
check(kinds(t) == ["item", "subtotal", "raw", "discount"], f"included raw data + discount: before the first of them {kinds(t)}")
t = calc.office_calc({**DOC, "markup_pct": 10}, [it("Dreh", 1, 1000, in_markup=1), it("Option", 1, 9000, opt="optional")], PACK)
check(subs(t)[0]["total"] == 1000 == t["items_net"], f"an optional position is not in it {subs(t)}")
# with the sections' subtotals: the last section closes first, then the positions' one
SEC = [{"kind": "heading", "title": "Dreh"}, it("Kamera", 2, 1000, in_markup=1), {"kind": "heading", "title": "Post"}, it("Schnitt", 1, 600)]
t = calc.office_calc({**DOC, "subtotals": 1, "markup_pct": 10, "discount_pct": 5}, SEC, PACK)
check(kinds(t) == ["heading", "item", "subtotal", "heading", "item", "subtotal", "subtotal", "surcharge", "discount"],
      f"sections on: their subtotals and once the positions' one {kinds(t)}")
check([(x.get("sec"), x["total"]) for x in t["lines"] if x["kind"] == "subtotal"] == [(0, 2000), (1, 600), (None, 2600)],
      f"the amounts: the sections' and items_net {[x for x in t['lines'] if x['kind'] == 'subtotal']}")
lg = calc.office_calc({**DOC, "markup_pct": 10, "discount_pct": 5, "sub_legacy": 1}, ITS, PACK)
dl = [x for x in lg["lines"] if x["kind"] == "discount"][0]
check(not subs(lg) and "it_sub" not in lg and dl["detail"] == "5 % auf die rabattfähigen Positionen",
      f"a quotation sent before (sub_legacy): its lines as sent {kinds(lg)} {dl['detail']}")
lg = calc.office_calc({**DOC, "lang": "en", "discount_amount": 500, "sub_legacy": 1}, ITS, PACK)
check([x["detail"] for x in lg["lines"] if x["kind"] == "discount"] == ["Fixed amount on the discountable positions"], "... the fixed amount too")
check(calc.office_calc({**DOC, "discount_pct": 5}, ITS, PACK).get("it_sub") == 2, "a new computation says it_sub 2 (#7291)")
off = calc.office_calc({**DOC, "markup_pct": 10, "discount_pct": 5}, SEC, PACK)
check(all(t[k] == off[k] for k in ("net", "gross", "tax_lines", "discount", "items_net")), "the sums do not depend on it")

# ---------------------------------------------------------------- the invoice calculator
D = {"kind": "discount", "title": "Rabatt", "detail": "5 % auf die rabattfähigen Positionen (13.000,00 €)", "qty": 1, "rate": 650, "unit": "flat", "tax": "standard"}
iv = calc.inv_calc({"lang": "de"}, ITS + [D], PACK)
check(kinds(iv) == ["item"] * 3 + ["subtotal", "discount"] and subs(iv)[0]["total"] == 14200 and iv["net"] == "13550.00",
      f"invoice: before the trailing discount position, the sum above, the net unchanged {kinds(iv)} {iv['net']}")
MK = {"kind": "service", "title": "Zuschlag", "qty": 1, "unit": "flat", "rate": 1300, "tax": "standard", "sur_pct": 10, "sur_base": 13000}
iv = calc.inv_calc({"lang": "de"}, ITS + [MK, D], PACK)
check(kinds(iv) == ["item"] * 3 + ["subtotal", "item", "discount"] and subs(iv)[0]["total"] == 14200,
      f"invoice from a quotation: before its markup position, once {kinds(iv)}")
iv = calc.inv_calc({"lang": "de"}, [ITS[0], D, ITS[1]], PACK)
check(not subs(iv), f"a discount between positions: none {kinds(iv)}")
iv = calc.inv_calc({"lang": "de"}, ITS, PACK)
check(not subs(iv), "an invoice of positions only: none")
iv = calc.inv_calc({"lang": "de"}, ITS + [dict(D, abs_tax="123.50")], PACK)
check(not subs(iv), "a final invoice's deductions: none")
iv = calc.inv_calc({"lang": "en"}, ITS + [D], PACK)
check(subs(iv)[0]["label"] == "Subtotal" and subs(iv)[0]["total_text"] == "€14,200.00", f"invoice in English {subs(iv)}")

# ---------------------------------------------------------------- the PDF
CO = {"name": "Beispielstudio GmbH", "lines": ["Musterweg 1", "12345 Musterstadt"], "color": "#2f5d8a"}


def model(t, net):
    for ln in t["lines"]:
        if ln.get("total") is not None and not ln.get("total_text"):
            ln["total_text"] = calc.fmt_money(ln["total"], "de", "EUR")
    return {"kind": "offer", "lang": "de", "currency": "EUR", "number": "KVA-2026-816", "date": "2026-11-17", "date_text": "17.11.2026",
            "title": "Angebot", "project_title": "Imagefilm Frühjahr", "company": CO,
            "recipient": {"name": "Beispielkunde GmbH", "lines": ["Beispielkunde GmbH", "Kundenweg 5", "10115 Beispielstadt"]},
            "meta": [["Angebot Nr.", "KVA-2026-816"], ["Datum", "17.11.2026"]], "lines": t["lines"], "intro": "Sehr geehrte Damen und Herren,",
            "totals": {"net": net, "rows": [["Summe netto", calc.fmt_money(net, "de", "EUR")]], "show_tax_lines": False}, "rights": {},
            "labels": {"pos": "Pos.", "title": "Leistung", "qty": "Menge", "unit_price": "Preis", "total": "Gesamt", "vat": "MwSt."}}


def find(pg, s):
    return [(n, x) for n, p in enumerate(pg) for x in p["texts"] if x["s"] == s]


t = calc.office_calc({**DOC, "markup_pct": 10, "discount_pct": 5}, ITS, PACK)
data = pdf.office_pdf(model(t, t["net"]))
pg = pdfcheck.layout(data)
sub, last, sur, rab = find(pg, "Zwischensumme"), find(pg, "Musik"), find(pg, "Zuschlag"), find(pg, "5 % auf die rabattfähigen Positionen (13.000,00 €)")
check(len(sub) == 1 and last and sur and rab, f"PDF: the subtotal row once, the discount's explanation with its base {len(sub)} {bool(last)} {bool(sur)} {bool(rab)}")
if sub and last and sur:
    (n, s_), (_, l_), (_, z_) = sub[0], last[-1], sur[-1]
    check(l_["y"] < s_["y"] < z_["y"] and s_["bold"], f"PDF: bold, between the last position and the surcharge ({l_['y']:.1f} {s_['y']:.1f} {z_['y']:.1f})")
    amt = [x for _, x in find(pg, "14.200,00 €") if abs(x["y"] - s_["y"]) < 1]
    check(amt and amt[0]["bold"], "PDF: its amount 14.200,00 € bold in the same row")
    short = [r for r in pg[n]["rules"] if abs(r[1] - r[3]) < 0.01 and 0 < s_["y"] - r[1] < 12 and r[0] > pdf.PDF_L + 100
             and r[2] - r[0] < pdf.PDF_CW / 2 and abs(r[2] - (pdf.PDF_L + pdf.PDF_CW)) < 1]
    check(short, f"PDF: a short rule above the amount columns {[r for r in pg[n]['rules'] if abs(r[1] - r[3]) < 0.01 and abs(r[1] - s_['y']) < 15]}")
check(not pdfcheck.problems(data), f"PDF: clean {pdfcheck.problems(data)[:3]}")
t = calc.office_calc(DOC, ITS, PACK)
check(not find(pdfcheck.layout(pdf.office_pdf(model(t, t["net"]))), "Zwischensumme"), "PDF: without surcharge and discount no row")
# sections, only the discount on the whole quotation: it goes into the totals ("Summe Positionen", #6174), no row in the table
t = calc.office_calc({**DOC, "discount_pct": 5}, SEC, PACK)
check(any(x["kind"] == "subtotal" and x.get("items") for x in t["lines"]), "sections + discount: the calculation has the line")
pg = pdfcheck.layout(pdf.office_pdf(model(t, t["net"])))
check(not find(pg, "Zwischensumme") and find(pg, "Summe Positionen"), "PDF: ... but the table not (the totals say 'Summe Positionen')")
check(Decimal(str(t["items_net"])) == Decimal("2600"), "items_net of the sections")
sys.exit(done("p6816_zwischensumme"))
